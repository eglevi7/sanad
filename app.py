import os
import json
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS

from book_search import (
    load_books,
    load_or_build_index,
    search as book_search_func,
    SUBJECT_MAP,
)

# =========================
# إعداد Flask
# =========================

app = Flask(__name__, static_folder="ui", static_url_path="")
CORS(app)

# =========================
# المتغيرات العامة
# =========================

BOOKS = []
INDEX = {}
IDF = {}
TOTAL_PAGES = 0

CONVERSATION_HISTORY = []
MAX_HISTORY = 10


def add_to_history(role, content):
    CONVERSATION_HISTORY.append({"role": role, "content": content})
    while len(CONVERSATION_HISTORY) > MAX_HISTORY:
        CONVERSATION_HISTORY.pop(0)


def clear_history():
    CONVERSATION_HISTORY.clear()


def normalize_text(text):
    import re
    text = text.lower()
    text = re.sub(r'[\u064B-\u065F\u0670]', '', text)
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = text.replace("ة", "ه").replace("ى", "ي")
    text = re.sub(r'[؟?!.,،:؛()"\'\-]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# =========================
# عقل Sanad
# =========================

def get_chat_response(message, is_stream=False):
    message = message.strip()
    if not message:
        return "اكتبلي حاجة الأول 😅" if not is_stream else iter(["اكتبلي حاجة الأول 😅"])

    try:
        from ai_brain import ask_groq, ask_groq_stream
    except Exception as e:
        print(f"⚠️ مش قادر أحمّل ai_brain: {e}")
        return "حدث خطأ في النظام." if not is_stream else iter(["حدث خطأ في النظام."])

    norm_msg = normalize_text(message)

    # =====================================================
    # 1. هل الطالب بيطلب بحث حقيقي في الكتب؟ (نية البحث)
    # =====================================================
    SEARCH_INTENT_KEYWORDS = [
        "اشرح", "اشرحلي", "لخص", "لخصلي", "قارن", "احسب", "حل", "حللي",
        "عرف", "تعريف", "مثال", "امثلة", "اذكر", "عدد",
        "درس", "الدرس", "وحدة", "الوحدة", "محتوى", "منهج",
        "عايز اعرف", "ايه هي", "ايه هو", "ما هي", "ما هو"
    ]
    
    is_search_intent = any(kw in norm_msg for kw in SEARCH_INTENT_KEYWORDS)
    
    # لو الطالب ذكر اسم مادة صراحة مع نية بحث
    has_subject = False
    for subj in SUBJECT_MAP.keys():
        if normalize_text(subj) in norm_msg:
            has_subject = True
            break

    # لو الكلام مجرد سؤال عادي (ازيك، الحمد لله، عندي قناة...)، منبحثش في الكتب
    context = None
    if is_search_intent:
        results = book_search_func(message, BOOKS, INDEX, IDF, top_k=3)
        if results and results[0]["score"] >= 1.0:
            context_parts = []
            for r in results:
                context_parts.append(f"[{r['book']} — صفحة {r['page']}]\n{r['text'][:2000]}")
            context = "\n\n---\n\n".join(context_parts)

    # =====================================================
    # 2. نبعت للـ AI (مع أو بدون سياق من الكتب)
    # =====================================================
    if is_stream:
        return ask_groq_stream(message, context=context, history=CONVERSATION_HISTORY, is_lesson=False)
    else:
        ans = ask_groq(message, context=context, history=CONVERSATION_HISTORY, is_lesson=False)
        if ans:
            add_to_history("user", message)
            add_to_history("assistant", ans)
            return ans
        return "معلش، مش قادر أجاوب دلوقتي. جرب تاني."


# =========================
# Routes
# =========================

@app.route("/")
def index():
    return send_from_directory("ui", "index.html")


@app.route("/ui/<path:filename>")
def serve_ui(filename):
    return send_from_directory("ui", filename)

@app.route("/manifest.json")
def serve_manifest():
    return send_from_directory(".", "manifest.json")

@app.route("/service-worker.js")
def serve_sw():
    return send_from_directory(".", "service-worker.js")

@app.route("/icon-192.png")
def serve_icon_192():
    return send_from_directory(".", "icon-192.png")

@app.route("/icon-512.png")
def serve_icon_512():
    return send_from_directory(".", "icon-512.png")

@app.route("/logo.png")
def serve_logo():
    return send_from_directory(".", "logo.png")


@app.route("/api/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json()
        message = data.get("message", "").strip()
        if not message:
            return jsonify({"ok": False, "error": "الرسالة فاضية"}), 400

        response = get_chat_response(message, is_stream=False)
        return jsonify({"ok": True, "text": response, "suggestions": []})
    except Exception as e:
        print(f"❌ خطأ: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    try:
        data = request.get_json()
        message = data.get("message", "").strip()
        if not message:
            return jsonify({"ok": False, "error": "الرسالة فاضية"}), 400

        generator_or_text = get_chat_response(message, is_stream=True)

        if isinstance(generator_or_text, str):
            def text_generate():
                yield f"data: {json.dumps({'chunk': generator_or_text}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
            return Response(text_generate(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

        def generate():
            full_response = []
            try:
                for chunk in generator_or_text:
                    full_response.append(chunk)
                    yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"
                
                final_answer = "".join(full_response)
                add_to_history("user", message)
                add_to_history("assistant", final_answer)
                yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

        return Response(generate(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    except Exception as e:
        print(f"❌ خطأ في streaming: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/clear", methods=["POST"])
def clear():
    clear_history()
    return jsonify({"ok": True})


# =========================
# تحميل الكتب
# =========================

def load_data():
    global BOOKS, INDEX, IDF, TOTAL_PAGES
    print("⏳ بنجهز الكتب...")
    try:
        BOOKS = load_books()
        INDEX, IDF, TOTAL_PAGES = load_or_build_index(BOOKS)
        print(f"✅ جاهز — {len(BOOKS)} كتاب، {TOTAL_PAGES} صفحة")
    except Exception as e:
        print(f"⚠️ فشل تحميل الكتب: {e}")

load_data()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

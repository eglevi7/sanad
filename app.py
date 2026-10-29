import os
import json
import re
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS

from book_search import (
    load_books,
    load_or_build_index,
    find_answer,
    is_location_question,
    search as book_search_func,
    detect_lesson_request,
    get_lesson_text,
    get_lesson_by_order,
    get_total_lessons,
    detect_lesson_number,
    detect_question_type,
    extract_comparison_terms,
    load_lessons,
    is_grammar_question,
    get_grammar_text,
    find_grammar_by_name,
    SUBJECT_MAP,
    UNIT_MAP,
)

# =========================
# إعداد Flask
# =========================

app = Flask(__name__, static_folder="ui", static_url_path="")
CORS(app)

# =========================
# تحميل قاعدة المعرفة
# =========================

def load_knowledge(path="knowledge.json"):
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as e:
        print(f"❌ خطأ في knowledge.json: {e}")
        return {}


knowledge = load_knowledge()

# =========================
# المتغيرات العامة
# =========================

BOOKS = []
INDEX = {}
IDF = {}
TOTAL_PAGES = 0

CONVERSATION_HISTORY = []
MAX_HISTORY = 10

PENDING_LESSON = None
LAST_LESSON = None

SUGGESTIONS = []

AVAILABLE_SUBJECTS = ["تاريخ", "عربي", "إنجليزي"]


def add_to_history(role, content):
    CONVERSATION_HISTORY.append({"role": role, "content": content})
    while len(CONVERSATION_HISTORY) > MAX_HISTORY:
        CONVERSATION_HISTORY.pop(0)


def clear_history():
    CONVERSATION_HISTORY.clear()


# =========================
# دوال مساعدة
# =========================

def normalize_text(text):
    text = text.lower()
    text = re.sub(r'[\u064B-\u065F\u0670]', '', text)
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = text.replace("ة", "ه").replace("ى", "ي")
    text = re.sub(r'[؟?!.,،:؛()"\'\-]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def make_subject_suggestions():
    return AVAILABLE_SUBJECTS.copy()


def make_unit_suggestions(subject):
    lessons_data = load_lessons()
    if subject not in lessons_data:
        return []
    units = lessons_data[subject]["units"]
    return list(units.keys())


# =========================
# الدالة الرئيسية للرد
# =========================

def get_chat_response(message, is_stream=False):
    global PENDING_LESSON, SUGGESTIONS, LAST_LESSON

    if not message.strip():
        return "اكتبلي حاجة الأول 😅" if not is_stream else iter(["اكتبلي حاجة الأول 😅"])

    norm_msg = normalize_text(message)
    SUGGESTIONS = []

    try:
        from ai_brain import ask_groq, ask_groq_stream
    except Exception as e:
        print(f"⚠️ مش قادر أحمّل ai_brain: {e}")
        return "حدث خطأ في النظام." if not is_stream else iter(["حدث خطأ في النظام."])

    # 1. تصحيح الكلام (قصدي...)
    CORRECTION_KEYWORDS = ["قصدي", "لا اقصد", "مش كده", "انا اقصد"]
    if any(kw in norm_msg for kw in CORRECTION_KEYWORDS):
        temp_msg = message
        for kw in CORRECTION_KEYWORDS:
            temp_msg = temp_msg.replace(kw, "")
        temp_msg = temp_msg.strip()
        if temp_msg:
            message = temp_msg 
            norm_msg = normalize_text(message)

    # 2. طلب الدرس اللي بعده (والتاني / واللي بعده)
    NEXT_LESSON_KEYWORDS = ["والتاني", "والتالت", "واللي بعده", "اللي بعده", "والرابع"]
    if any(normalize_text(kw) in norm_msg for kw in NEXT_LESSON_KEYWORDS) and LAST_LESSON is not None:
        lessons_data = load_lessons()
        subject = LAST_LESSON["subject"]
        current_unit = LAST_LESSON["unit"]
        current_lesson = LAST_LESSON["lesson"]
        
        current_order = None
        if subject in lessons_data and current_unit in lessons_data[subject]["units"]:
            lessons_in_unit = lessons_data[subject]["units"][current_unit]["lessons"]
            if current_lesson in lessons_in_unit:
                current_order = lessons_in_unit[current_lesson].get("order")
        
        if current_order is not None:
            next_lesson = get_lesson_by_order(subject, current_order + 1)
            if next_lesson:
                next_unit = next_lesson["unit"]
                next_lesson_name = next_lesson["lesson"]
                lesson_data = get_lesson_text(subject, next_unit, next_lesson_name, BOOKS)
                
                if lesson_data:
                    LAST_LESSON = {
                        "subject": subject, "unit": next_unit, "lesson": next_lesson_name,
                        "text": lesson_data["text"], "title": lesson_data["title"],
                        "unit_title": lesson_data["unit_title"], "is_grammar": False
                    }
                    context = f"الدرس: {lesson_data['title']}\nمن {next_unit}: {lesson_data['unit_title']}\n\n{lesson_data['text'][:8000]}"
                    if is_stream:
                        return ask_groq_stream(message, context=context, history=CONVERSATION_HISTORY, is_lesson=True, question_type="explain")
                    else:
                        ans = ask_groq(message, context=context, history=CONVERSATION_HISTORY, is_lesson=True, question_type="explain")
                        add_to_history("user", message); add_to_history("assistant", ans)
                        return ans

    # 3. لو في سؤال درس معلّق
    if PENDING_LESSON is not None:
        step = PENDING_LESSON.get("step")
        if step == "subject":
            found_subject = None
            for subj in SUBJECT_MAP.keys():
                if normalize_text(subj) in norm_msg:
                    found_subject = subj
                    break
            if found_subject:
                lessons_data = load_lessons()
                if found_subject not in lessons_data:
                    PENDING_LESSON = None
                    return f"المادة دي ({found_subject}) لسه مش متاحة 🚧"
                PENDING_LESSON = {
                    "subject": found_subject, "lesson": PENDING_LESSON["lesson"],
                    "question_type": PENDING_LESSON.get("question_type"),
                    "is_grammar": PENDING_LESSON.get("is_grammar", False), "step": "unit"
                }
                SUGGESTIONS = make_unit_suggestions(found_subject)
                return f"تمام! عايز أشرحلك {PENDING_LESSON['lesson']} في {found_subject} 📚\n\nأي وحدة؟"
            else:
                PENDING_LESSON = None
        elif step == "unit":
            found_unit = None
            for key, val in UNIT_MAP.items():
                if normalize_text(key) in norm_msg:
                    found_unit = val
                    break
            if found_unit:
                subject = PENDING_LESSON["subject"]
                lesson = PENDING_LESSON["lesson"]
                saved_type = PENDING_LESSON.get("question_type")
                is_grammar = PENDING_LESSON.get("is_grammar", False)
                PENDING_LESSON = None
                if is_grammar:
                    lesson_data = get_grammar_text(subject, found_unit, lesson, BOOKS)
                else:
                    lesson_data = get_lesson_text(subject, found_unit, lesson, BOOKS)
                
                if lesson_data:
                    LAST_LESSON = {
                        "subject": subject, "unit": found_unit, "lesson": lesson,
                        "text": lesson_data["text"], "title": lesson_data["title"],
                        "unit_title": lesson_data["unit_title"], "is_grammar": is_grammar
                    }
                    prefix = "درس النحو: " if is_grammar else "الدرس: "
                    context = f"{prefix}{lesson_data['title']}\nمن {found_unit}: {lesson_data['unit_title']}\n\n{lesson_data['text'][:8000]}"
                    if is_stream:
                        return ask_groq_stream(message, context=context, history=CONVERSATION_HISTORY, is_lesson=True, question_type=saved_type)
                    else:
                        ans = ask_groq(message, context=context, history=CONVERSATION_HISTORY, is_lesson=True, question_type=saved_type)
                        add_to_history("user", message); add_to_history("assistant", ans)
                        return ans
                return "معلش، مش لاقي الدرس ده في الكتاب."
            else:
                PENDING_LESSON = None

    # 4. درس بدون مادة (مع أو بدون وحدة)
    lesson_num = detect_lesson_number(message)
    has_lesson_word = ("درس" in norm_msg) or ("الدرس" in norm_msg)
    if lesson_num and has_lesson_word:
        lesson_info = detect_lesson_request(message)
        if not lesson_info:
            lesson_arabic = None
            lesson_names = {"الاول": "الدرس الأول", "الأول": "الدرس الأول", "التاني": "الدرس الثاني", "الثاني": "الدرس الثاني", "التالت": "الدرس الثالث", "الثالث": "الدرس الثالث", "الرابع": "الدرس الرابع", "الخامس": "الدرس الخامس", "السادس": "الدرس السادس"}
            for key, val in lesson_names.items():
                if normalize_text(key) in norm_msg:
                    lesson_arabic = val
                    break
            if not lesson_arabic:
                lesson_arabic = f"الدرس {lesson_num}"
            
            PENDING_LESSON = {
                "subject": None, "lesson": lesson_arabic,
                "question_type": detect_question_type(message),
                "is_grammar": is_grammar_question(message), "step": "subject"
            }
            SUGGESTIONS = make_subject_suggestions()
            return f"عايز أشرحلك {lesson_arabic} 📚\n\nأي مادة؟"

    # 5. درس + مادة
    lesson_info = detect_lesson_request(message)
    if lesson_info:
        subject = lesson_info["subject"]
        unit = lesson_info["unit"]
        lesson = lesson_info["lesson"]
        qtype = detect_question_type(message)
        is_grm = is_grammar_question(message)

        if unit:
            lesson_data = get_grammar_text(subject, unit, lesson, BOOKS) if is_grm else get_lesson_text(subject, unit, lesson, BOOKS)
            if lesson_data:
                LAST_LESSON = {
                    "subject": subject, "unit": unit, "lesson": lesson,
                    "text": lesson_data["text"], "title": lesson_data["title"],
                    "unit_title": lesson_data["unit_title"], "is_grammar": is_grm
                }
                context = f"{'درس النحو: ' if is_grm else 'الدرس: '}{lesson_data['title']}\nمن {unit}: {lesson_data['unit_title']}\n\n{lesson_data['text'][:8000]}"
                if is_stream:
                    return ask_groq_stream(message, context=context, history=CONVERSATION_HISTORY, is_lesson=True, question_type=qtype)
                else:
                    ans = ask_groq(message, context=context, history=CONVERSATION_HISTORY, is_lesson=True, question_type=qtype)
                    add_to_history("user", message); add_to_history("assistant", ans)
                    return ans
            return "معلش، مش لاقي الدرس ده في الكتاب."
        else:
            lesson_num = detect_lesson_number(message)
            if lesson_num:
                by_order = get_lesson_by_order(subject, lesson_num)
                if lesson_num > 4 and by_order:
                    unit_found = by_order["unit"]
                    lesson_found = by_order["lesson"]
                    lesson_data = get_lesson_text(subject, unit_found, lesson_found, BOOKS)
                    if lesson_data:
                        LAST_LESSON = {
                            "subject": subject, "unit": unit_found, "lesson": lesson_found,
                            "text": lesson_data["text"], "title": lesson_data["title"],
                            "unit_title": lesson_data["unit_title"], "is_grammar": False
                        }
                        context = f"الدرس: {lesson_data['title']}\nمن {unit_found}: {lesson_data['unit_title']}\n\n{lesson_data['text'][:8000]}"
                        if is_stream:
                            return ask_groq_stream(message, context=context, history=CONVERSATION_HISTORY, is_lesson=True, question_type=qtype)
                        else:
                            ans = ask_groq(message, context=context, history=CONVERSATION_HISTORY, is_lesson=True, question_type=qtype)
                            add_to_history("user", message); add_to_history("assistant", ans)
                            return ans
                PENDING_LESSON = {
                    "subject": subject, "lesson": lesson, "question_type": qtype,
                    "is_grammar": False, "step": "unit"
                }
                SUGGESTIONS = make_unit_suggestions(subject)
                return f"تمام! عايز أشرحلك {lesson} في {subject} 📚\n\nأي وحدة؟"

    # 6. المقارنة
    question_type = detect_question_type(message)
    if question_type == "compare":
        terms = extract_comparison_terms(message)
        if terms:
            term1, term2 = terms
            results1 = book_search_func(term1, BOOKS, INDEX, IDF, top_k=2)
            results2 = book_search_func(term2, BOOKS, INDEX, IDF, top_k=2)
            context_parts = []
            if results1:
                context_parts.append(f"--- {term1} ---\n" + "\n\n".join(f"[{r['book']} — صفحة {r['page']}]\n{r['text'][:1500]}" for r in results1))
            if results2:
                context_parts.append(f"--- {term2} ---\n" + "\n\n".join(f"[{r['book']} — صفحة {r['page']}]\n{r['text'][:1500]}" for r in results2))
            context = "\n\n===\n\n".join(context_parts) if context_parts else None
            if is_stream:
                return ask_groq_stream(message, context=context, history=CONVERSATION_HISTORY, question_type="compare")
            else:
                ans = ask_groq(message, context=context, history=CONVERSATION_HISTORY, question_type="compare")
                add_to_history("user", message); add_to_history("assistant", ans)
                return ans

    # 7. مكان
    if is_location_question(message):
        result = find_answer(message, BOOKS, INDEX, IDF)
        if result:
            return result["text"]

    # 8. بحث عادي
    results = book_search_func(message, BOOKS, INDEX, IDF, top_k=5)
    context_parts = []
    if results and results[0]["score"] >= 0.5:
        for r in results:
            context_parts.append(f"[{r['book']} — صفحة {r['page']}]\n{r['text'][:2000]}")
    context = "\n\n---\n\n".join(context_parts) if context_parts else None

    if is_stream:
        return ask_groq_stream(message, context=context, history=CONVERSATION_HISTORY, is_lesson=False, question_type=question_type)
    else:
        ans = ask_groq(message, context=context, history=CONVERSATION_HISTORY, is_lesson=False, question_type=question_type)
        if ans:
            add_to_history("user", message); add_to_history("assistant", ans)
            return ans
    
    return "مش قادر أحدد قصدك لسه 😅، ممكن تكتب السؤال بطريقة تانية؟"


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
        return jsonify({"ok": True, "text": response, "suggestions": SUGGESTIONS})
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

        # نجيب الـ generator من الدالة الرئيسية
        generator_or_text = get_chat_response(message, is_stream=True)

        # لو رجع نص عادي (زي سؤال عن وحدة أو تصحيح)، نبعته كـ chunk واحد
        if isinstance(generator_or_text, str):
            def text_generate():
                yield f"data: {json.dumps({'chunk': generator_or_text}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'done': True, 'suggestions': SUGGESTIONS}, ensure_ascii=False)}\n\n"
            return Response(text_generate(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

        # لو رجع generator (streaming من Groq)
        def generate():
            full_response = []
            try:
                for chunk in generator_or_text:
                    full_response.append(chunk)
                    yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"
                
                final_answer = "".join(full_response)
                add_to_history("user", message)
                add_to_history("assistant", final_answer)
                yield f"data: {json.dumps({'done': True, 'suggestions': SUGGESTIONS}, ensure_ascii=False)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

        return Response(generate(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    except Exception as e:
        print(f"❌ خطأ في streaming: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/clear", methods=["POST"])
def clear():
    global PENDING_LESSON, SUGGESTIONS, LAST_LESSON
    clear_history()
    PENDING_LESSON = None
    LAST_LESSON = None
    SUGGESTIONS = []
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

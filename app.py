import os
import json
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS

app = Flask(__name__, static_folder="ui", static_url_path="")
CORS(app)

CONVERSATION_HISTORY = []

def add_to_history(role, content):
    CONVERSATION_HISTORY.append({"role": role, "content": content})
    if len(CONVERSATION_HISTORY) > 10:
        CONVERSATION_HISTORY.pop(0)

def get_chat_response(message, is_stream=False):
    message = message.strip()
    if not message:
        return "اكتبلي حاجة الأول 😅" if not is_stream else iter(["اكتبلي حاجة الأول 😅"])

    # 1. الفلتر الممنوع (الرفض المباشر)
    import re
    norm_msg = message.lower()
    norm_msg = re.sub(r'[\u064B-\u065F\u0670]', '', norm_msg)
    norm_msg = norm_msg.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه").replace("ى", "ي")
    
    BANNED_PHRASES = ["كورة", "مباراة", "لاعب", "ريال مدريد", "برشلونة", "الأهلي", "الزمالك", "فن", "مسلسل", "فيلم", "أغنية", "سياسة", "انتخابات", "يوتيوب", "قناتي", "فلوس", "شغلانة"]
    
    if any(word in norm_msg for word in BANNED_PHRASES):
        refusal_msg = "أنا مساعد تعليمي 📚، ومش هقدر أساعدك في الموضوع ده. ممكن أسألك في حاجة تانية في دراستك؟"
        return iter([refusal_msg]) if is_stream else refusal_msg

    try:
        from ai_brain import ask_groq, ask_groq_stream
    except:
        return "حدث خطأ في النظام." if not is_stream else iter(["حدث خطأ في النظام."])

    # 2. بنبعت كل حاجة لـ AI على طول (من غير بحث في الكتب)
    if is_stream:
        return ask_groq_stream(message, context=None, history=CONVERSATION_HISTORY, is_lesson=False)
    else:
        ans = ask_groq(message, context=None, history=CONVERSATION_HISTORY, is_lesson=False)
        if ans:
            add_to_history("user", message)
            add_to_history("assistant", ans)
            return ans
        return "معلش، مش قادر أجاوب دلوقتي."

@app.route("/")
def index(): return send_from_directory("ui", "index.html")
@app.route("/ui/<path:filename>")
def serve_ui(filename): return send_from_directory("ui", filename)
@app.route("/manifest.json")
def serve_manifest(): return send_from_directory(".", "manifest.json")
@app.route("/service-worker.js")
def serve_sw(): return send_from_directory(".", "service-worker.js")
@app.route("/icon-192.png")
def serve_icon_192(): return send_from_directory(".", "icon-192.png")
@app.route("/icon-512.png")
def serve_icon_512(): return send_from_directory(".", "icon-512.png")
@app.route("/logo.png")
def serve_logo(): return send_from_directory(".", "logo.png")

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json()
    return jsonify({"ok": True, "text": get_chat_response(data.get("message", ""), False)})

@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    data = request.get_json()
    gen = get_chat_response(data.get("message", ""), True)
    if isinstance(gen, str):
        return Response(iter([f"data: {json.dumps({'chunk': gen}, ensure_ascii=False)}\n\n", f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"]), mimetype="text/event-stream")
    def generate():
        full = []
        for chunk in gen:
            full.append(chunk)
            yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"
        add_to_history("user", data.get("message", ""))
        add_to_history("assistant", "".join(full))
        yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
    return Response(generate(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache"})

@app.route("/api/clear", methods=["POST"])
def clear():
    CONVERSATION_HISTORY.clear()
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

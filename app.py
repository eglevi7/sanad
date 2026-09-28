import os
import json
from flask import Flask, request, jsonify, send_from_directory
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
    import re
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
# Handlers (نفس main.py بس بدون tkinter/webview)
# =========================

def handle_empty(message):
    if not message.strip():
        return "اكتبلي حاجة الأول 😅"
    return None


def handle_intent(message):
    # مبسط — نرجع None عشان نعدي للبحث
    return None


def handle_books(message):
    global PENDING_LESSON, SUGGESTIONS, LAST_LESSON

    if not BOOKS or not INDEX:
        return None

    try:
        from ai_brain import ask_groq
    except Exception as e:
        print(f"⚠️ مش قادر أحمّل ai_brain: {e}")
        ask_groq = None

    # Follow-up
    FOLLOWUP_KEYWORDS = [
        "مثال", "أمثلة", "امثلة", "بسطها", "بسط", "بسّط",
        "والتاني", "والتالت", "كمّل", "كمل", "وضح أكتر", "وضح اكتر"
    ]

    norm_msg = normalize_text(message)
    is_followup = any(normalize_text(kw) in norm_msg for kw in FOLLOWUP_KEYWORDS)

    if is_followup and LAST_LESSON is not None:
        lesson_data = LAST_LESSON
        prefix = "درس النحو: " if lesson_data.get("is_grammar") else "الدرس: "
        context = (
            f"{prefix}{lesson_data['title']}\n"
            f"من {lesson_data['unit']}: {lesson_data['unit_title']}\n\n"
            f"{lesson_data['text'][:8000]}"
        )
        if ask_groq is not None:
            try:
                answer = ask_groq(
                    message,
                    context=context,
                    history=CONVERSATION_HISTORY,
                    is_lesson=True,
                    question_type=detect_question_type(message)
                )
                if answer:
                    add_to_history("user", message)
                    add_to_history("assistant", answer)
                    return answer
            except Exception as e:
                print(f"⚠️ AI error: {e}")

    # PENDING
    if PENDING_LESSON is not None:
        q_norm = normalize_text(message)
        step = PENDING_LESSON.get("step")

        if step == "subject":
            found_subject = None
            for subj in SUBJECT_MAP.keys():
                if normalize_text(subj) in q_norm:
                    found_subject = subj
                    break

            if found_subject:
                lessons_data = load_lessons()
                if found_subject not in lessons_data:
                    PENDING_LESSON = None
                    SUGGESTIONS = []
                    return f"المادة دي ({found_subject}) لسه مش متاحة 🚧"

                PENDING_LESSON = {
                    "subject": found_subject,
                    "lesson": PENDING_LESSON["lesson"],
                    "question_type": PENDING_LESSON.get("question_type"),
                    "is_grammar": PENDING_LESSON.get("is_grammar", False),
                    "step": "unit"
                }
                SUGGESTIONS = make_unit_suggestions(found_subject)
                return f"تمام! عايز أشرحلك {PENDING_LESSON['lesson']} في {found_subject} 📚\n\nأي وحدة؟"
            else:
                PENDING_LESSON = None
                SUGGESTIONS = []

        elif step == "unit":
            found_unit = None
            for key, val in UNIT_MAP.items():
                if normalize_text(key) in q_norm:
                    found_unit = val
                    break

            if found_unit:
                subject = PENDING_LESSON["subject"]
                lesson = PENDING_LESSON["lesson"]
                saved_type = PENDING_LESSON.get("question_type")
                is_grammar = PENDING_LESSON.get("is_grammar", False)
                PENDING_LESSON = None
                SUGGESTIONS = []

                if is_grammar:
                    lesson_data = get_grammar_text(subject, found_unit, lesson, BOOKS)
                else:
                    lesson_data = get_lesson_text(subject, found_unit, lesson, BOOKS)

                if lesson_data:
                    LAST_LESSON = {
                        "subject": subject,
                        "unit": found_unit,
                        "lesson": lesson,
                        "text": lesson_data["text"],
                        "title": lesson_data["title"],
                        "unit_title": lesson_data["unit_title"],
                        "is_grammar": is_grammar
                    }

                    prefix = "درس النحو: " if is_grammar else "الدرس: "
                    context = (
                        f"{prefix}{lesson_data['title']}\n"
                        f"من {found_unit}: {lesson_data['unit_title']}\n\n"
                        f"{lesson_data['text'][:8000]}"
                    )
                    if ask_groq is not None:
                        try:
                            answer = ask_groq(
                                message + f" ({lesson} {found_unit} {subject})",
                                context=context,
                                history=CONVERSATION_HISTORY,
                                is_lesson=True,
                                question_type=saved_type
                            )
                            if answer:
                                add_to_history("user", message)
                                add_to_history("assistant", answer)
                                return answer
                        except Exception as e:
                            print(f"⚠️ AI error: {e}")
                return "معلش، مش لاقي الدرس ده في الكتاب."
            else:
                PENDING_LESSON = None
                SUGGESTIONS = []

    # نحو بالرقم
    if is_grammar_question(message) and detect_lesson_request(message):
        lesson_info = detect_lesson_request(message)
        subject = lesson_info["subject"]
        unit = lesson_info["unit"]
        lesson = lesson_info["lesson"]
        qtype = detect_question_type(message)

        if unit:
            SUGGESTIONS = []
            grammar_data = get_grammar_text(subject, unit, lesson, BOOKS)
            if grammar_data:
                LAST_LESSON = {
                    "subject": subject,
                    "unit": unit,
                    "lesson": lesson,
                    "text": grammar_data["text"],
                    "title": grammar_data["title"],
                    "unit_title": grammar_data["unit_title"],
                    "is_grammar": True
                }
                context = (
                    f"درس النحو: {grammar_data['title']}\n"
                    f"من {unit}: {grammar_data['unit_title']}\n\n"
                    f"{grammar_data['text'][:8000]}"
                )
                if ask_groq is not None:
                    try:
                        answer = ask_groq(
                            message,
                            context=context,
                            history=CONVERSATION_HISTORY,
                            is_lesson=True,
                            question_type=qtype
                        )
                        if answer:
                            add_to_history("user", message)
                            add_to_history("assistant", answer)
                            return answer
                    except Exception as e:
                        print(f"⚠️ AI error: {e}")
            return "معلش، مش لاقي درس النحو ده في الكتاب."
        else:
            lesson_num = detect_lesson_number(message)
            if lesson_num:
                PENDING_LESSON = {
                    "subject": subject,
                    "lesson": lesson,
                    "question_type": qtype,
                    "is_grammar": True,
                    "step": "unit"
                }
                SUGGESTIONS = make_unit_suggestions(subject)
                return f"عايز أشرحلك {lesson} نحو في {subject} 📚\n\nأي وحدة؟"

    # نحو بالاسم
    if is_grammar_question(message) and "عربي" in normalize_text(message):
        temp_msg = message
        for kw in ["اشرحلي", "اشرح", "قواعد نحوية", "قواعد", "نحوية", "نحو", "عربي", "اللغة العربية"]:
            temp_msg = temp_msg.replace(kw, "")
        temp_msg = temp_msg.strip()

        if temp_msg:
            grammar_found = find_grammar_by_name("عربي", temp_msg, BOOKS)
            if grammar_found:
                SUGGESTIONS = []
                grammar_data = get_grammar_text(
                    "عربي",
                    grammar_found["unit"],
                    grammar_found["lesson"],
                    BOOKS
                )
                if grammar_data:
                    LAST_LESSON = {
                        "subject": "عربي",
                        "unit": grammar_found["unit"],
                        "lesson": grammar_found["lesson"],
                        "text": grammar_data["text"],
                        "title": grammar_data["title"],
                        "unit_title": grammar_data["unit_title"],
                        "is_grammar": True
                    }
                    context = (
                        f"درس النحو: {grammar_data['title']}\n"
                        f"من {grammar_found['unit']}: {grammar_data['unit_title']}\n\n"
                        f"{grammar_data['text'][:8000]}"
                    )
                    if ask_groq is not None:
                        try:
                            answer = ask_groq(
                                message,
                                context=context,
                                history=CONVERSATION_HISTORY,
                                is_lesson=True,
                                question_type="explain"
                            )
                            if answer:
                                add_to_history("user", message)
                                add_to_history("assistant", answer)
                                return answer
                        except Exception as e:
                            print(f"⚠️ AI error: {e}")

    # درس بدون مادة
    lesson_num = detect_lesson_number(message)
    has_lesson_word = ("درس" in norm_msg) or ("الدرس" in norm_msg)

    if lesson_num and has_lesson_word and not detect_lesson_request(message):
        lesson_arabic = None
        lesson_names = {
            "الاول": "الدرس الأول", "الأول": "الدرس الأول",
            "التاني": "الدرس الثاني", "الثاني": "الدرس الثاني",
            "التالت": "الدرس الثالث", "الثالث": "الدرس الثالث",
            "الرابع": "الدرس الرابع",
            "الخامس": "الدرس الخامس",
            "السادس": "الدرس السادس",
        }
        for key, val in lesson_names.items():
            if normalize_text(key) in norm_msg:
                lesson_arabic = val
                break
        if not lesson_arabic:
            lesson_arabic = f"الدرس {lesson_num}"

        PENDING_LESSON = {
            "subject": None,
            "lesson": lesson_arabic,
            "question_type": detect_question_type(message),
            "is_grammar": is_grammar_question(message),
            "step": "subject"
        }
        SUGGESTIONS = make_subject_suggestions()
        return f"عايز أشرحلك {lesson_arabic} 📚\n\nأي مادة؟"

    # درس + مادة
    lesson_info = detect_lesson_request(message)

    if lesson_info:
        subject = lesson_info["subject"]
        unit = lesson_info["unit"]
        lesson = lesson_info["lesson"]
        qtype = detect_question_type(message)

        if unit:
            SUGGESTIONS = []
            lesson_data = get_lesson_text(subject, unit, lesson, BOOKS)
            if lesson_data:
                LAST_LESSON = {
                    "subject": subject,
                    "unit": unit,
                    "lesson": lesson,
                    "text": lesson_data["text"],
                    "title": lesson_data["title"],
                    "unit_title": lesson_data["unit_title"],
                    "is_grammar": False
                }
                context = (
                    f"الدرس: {lesson_data['title']}\n"
                    f"من {unit}: {lesson_data['unit_title']}\n\n"
                    f"{lesson_data['text'][:8000]}"
                )
                if ask_groq is not None:
                    try:
                        answer = ask_groq(
                            message,
                            context=context,
                            history=CONVERSATION_HISTORY,
                            is_lesson=True,
                            question_type=qtype
                        )
                        if answer:
                            add_to_history("user", message)
                            add_to_history("assistant", answer)
                            return answer
                    except Exception as e:
                        print(f"⚠️ AI error: {e}")
            return "معلش، مش لاقي الدرس ده في الكتاب."
        else:
            lesson_num = detect_lesson_number(message)
            if lesson_num:
                by_order = get_lesson_by_order(subject, lesson_num)
                if lesson_num > 4 and by_order:
                    unit_found = by_order["unit"]
                    lesson_found = by_order["lesson"]
                    SUGGESTIONS = []
                    lesson_data = get_lesson_text(subject, unit_found, lesson_found, BOOKS)
                    if lesson_data:
                        LAST_LESSON = {
                            "subject": subject,
                            "unit": unit_found,
                            "lesson": lesson_found,
                            "text": lesson_data["text"],
                            "title": lesson_data["title"],
                            "unit_title": lesson_data["unit_title"],
                            "is_grammar": False
                        }
                        context = (
                            f"الدرس: {lesson_data['title']}\n"
                            f"من {unit_found}: {lesson_data['unit_title']}\n\n"
                            f"{lesson_data['text'][:8000]}"
                        )
                        if ask_groq is not None:
                            try:
                                answer = ask_groq(
                                    message,
                                    context=context,
                                    history=CONVERSATION_HISTORY,
                                    is_lesson=True,
                                    question_type=qtype
                                )
                                if answer:
                                    add_to_history("user", message)
                                    add_to_history("assistant", answer)
                                    return answer
                            except Exception as e:
                                print(f"⚠️ AI error: {e}")
                PENDING_LESSON = {
                    "subject": subject,
                    "lesson": lesson,
                    "question_type": qtype,
                    "is_grammar": False,
                    "step": "unit"
                }
                SUGGESTIONS = make_unit_suggestions(subject)
                return f"تمام! عايز أشرحلك {lesson} في {subject} 📚\n\nأي وحدة؟"

    # المقارنة
    SUGGESTIONS = []
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
            if ask_groq is not None:
                try:
                    answer = ask_groq(message, context=context, history=CONVERSATION_HISTORY, question_type="compare")
                    if answer:
                        add_to_history("user", message)
                        add_to_history("assistant", answer)
                        return answer
                except Exception as e:
                    print(f"⚠️ AI error: {e}")

    # مكان
    if is_location_question(message):
        result = find_answer(message, BOOKS, INDEX, IDF)
        if result:
            return result["text"]
        return None

    # بحث عادي
    results = book_search_func(message, BOOKS, INDEX, IDF, top_k=5)
    context_parts = []
    if results and results[0]["score"] >= 0.5:
        for r in results:
            context_parts.append(f"[{r['book']} — صفحة {r['page']}]\n{r['text'][:2000]}")
    context = "\n\n---\n\n".join(context_parts) if context_parts else None

    if ask_groq is not None:
        try:
            answer = ask_groq(message, context=context, history=CONVERSATION_HISTORY, is_lesson=False, question_type=question_type)
            if answer:
                add_to_history("user", message)
                add_to_history("assistant", answer)
                return answer
        except Exception as e:
            print(f"⚠️ AI error: {e}")

    return None


def handle_fallback(message):
    return "مش قادر أحدد قصدك لسه 😅، ممكن تكتب السؤال بطريقة تانية؟"


def think(message):
    global SUGGESTIONS
    SUGGESTIONS = []

    message = message.strip()

    for handler in [handle_empty, handle_books]:
        response = handler(message)
        if response is not None:
            return response

    return handle_fallback(message)


# =========================
# Routes
# =========================

@app.route("/")
def index():
    return send_from_directory("ui", "index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json()
        message = data.get("message", "").strip()

        if not message:
            return jsonify({"ok": False, "error": "الرسالة فاضية"}), 400

        response = think(message)

        return jsonify({
            "ok": True,
            "text": response,
            "suggestions": SUGGESTIONS
        })
    except Exception as e:
        print(f"❌ خطأ: {e}")
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
# تحميل الكتب عند البدء
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
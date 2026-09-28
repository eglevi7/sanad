import json
import re
import math
import os
import time
from collections import Counter


# ============================================================
# تحميل الكتب من الـ Cache
# ============================================================

def load_books(path="books_cache.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# تنظيف النص العربي
# ============================================================

ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
DIGIT_TRANS = str.maketrans(ARABIC_DIGITS, "0123456789")

STOP_WORDS = {
    "من", "في", "على", "عن", "إلى", "الى", "هو", "هي", "ما", "ماذا",
    "كيف", "لماذا", "متى", "اين", "أين", "هل", "كان", "كانت",
    "التي", "الذي", "الذين", "هذا", "هذه", "ذلك", "تلك", "كل", "بعض",
    "او", "أو", "و", "ثم", "لكن", "بل", "ان", "أن", "إن",
    "يوجد", "توجد", "يعد", "تعد", "هناك", "عندما", "حيث", "هيا",
    "درس", "الدرس", "دروس", "الدروس", "فصل", "الفصل", "فصول", "الفصول",
    "وحدة", "الوحدة", "وحدات", "الوحدات", "باب", "الباب", "أبواب",
    "اشرح", "اشرحلي", "شرحلي", "وضح", "وضحلي", "فسر", "فسرلي",
    "عايز", "عاوز", "محتاج", "ممكن", "قولي", "قوللي",
}


def normalize(text):
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'[\u064B-\u065F\u0670]', '', text)
    text = text.translate(DIGIT_TRANS)
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = text.replace("ة", "ه").replace("ى", "ي")
    text = re.sub(r'[؟?!.,،:؛()"\'\-]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def tokenize(text):
    words = normalize(text).split()
    return [w for w in words if len(w) > 2 and w not in STOP_WORDS]


# ============================================================
# بناء الفهرس (Inverted Index + IDF)
# ============================================================

def build_index(books):
    inverted_index = {}
    total_pages = 0

    for book in books:
        book_name = book["name"]
        for page in book["pages"]:
            total_pages += 1
            words = tokenize(page["text"])
            word_counts = Counter(words)

            for word, count in word_counts.items():
                if word not in inverted_index:
                    inverted_index[word] = {}
                inverted_index[word][(book_name, page["page"])] = count

    idf = {
        word: math.log(total_pages / len(pages))
        for word, pages in inverted_index.items()
    }

    return inverted_index, idf, total_pages


# ============================================================
# حفظ وتحميل الفهرس من ملف
# ============================================================

INDEX_FILE = "index_cache.json"


def load_or_build_index(books):
    if os.path.exists(INDEX_FILE):
        print("📂 بنحمّل الفهرس من الملف...")
        t = time.time()
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        index = {}
        for word, pages in data["index"].items():
            index[word] = {}
            for key, count in pages.items():
                book_name, page_num = key.rsplit("|||", 1)
                index[word][(book_name, int(page_num))] = count

        print(f"✅ اتحمل في {time.time() - t:.1f} ثانية")
        return index, data["idf"], data["total_pages"]

    print("🔍 بنبني الفهرس لأول مرة (هياخد شوية)...")
    t = time.time()
    index, idf, total = build_index(books)
    print(f"✅ اتبنى في {time.time() - t:.1f} ثانية")

    print("💾 بنحفظه عشان المرة الجاية...")
    data = {
        "index": {
            word: {f"{bn}|||{pn}": c for (bn, pn), c in pages.items()}
            for word, pages in index.items()
        },
        "idf": idf,
        "total_pages": total
    }
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    return index, idf, total


# ============================================================
# البحث
# ============================================================

def search(question, books, index, idf, top_k=5):
    query_words = tokenize(question)

    if not query_words:
        return []

    scores = {}

    for word in query_words:
        if word not in index:
            continue

        word_idf = idf[word]

        for (book_name, page_num), count in index[word].items():
            key = (book_name, page_num)
            tf = 1 + math.log(count)
            scores[key] = scores.get(key, 0) + tf * word_idf

    sorted_results = sorted(scores.items(), key=lambda x: -x[1])[:top_k]

    results = []
    for (book_name, page_num), score in sorted_results:
        for book in books:
            if book["name"] == book_name:
                for page in book["pages"]:
                    if page["page"] == page_num:
                        results.append({
                            "book": book_name,
                            "page": page_num,
                            "text": page["text"],
                            "score": score
                        })
                        break
                break

    return results


# ============================================================
# استخراج المقطع المفيد من الصفحة
# ============================================================

def extract_snippet(text, query_words, max_len=600):
    if not text:
        return ""

    sentences = re.split(r'[.!?؟\n]', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 15]

    scored = []
    for sent in sentences:
        norm_sent = normalize(sent)
        score = sum(1 for w in query_words if w in norm_sent)
        if score > 0:
            scored.append((score, sent))

    if not scored:
        return text[:max_len] + ("..." if len(text) > max_len else "")

    scored.sort(key=lambda x: -x[0])

    result = []
    total = 0
    for score, sent in scored:
        if total + len(sent) > max_len:
            break
        result.append(sent)
        total += len(sent)

    return " . ".join(result)


# ============================================================
# تمييز نوع السؤال: محتوى ولا موقع؟
# ============================================================

LOCATION_KEYWORDS = [
    "صفحه", "صفحة", "فين", "مكان", "رقم الصفحه", "رقم الصفحة",
    "كام صفحه", "كام صفحة", "الصفحه", "الصفحه كام", "صفحه كام"
]


def is_location_question(question):
    q = normalize(question)
    return any(kw in q for kw in LOCATION_KEYWORDS)


# ============================================================
# ربط المواد بأسماء الكتب
# ============================================================

SUBJECT_MAP = {
    "تاريخ": "EgyptianHistory",
    "فيزياء": "Physics",
    "فيزيا": "Physics",
    "رياضة": "Mathematics",
    "رياضيات": "Mathematics",
    "كيمياء": "Chemistry",
    "احياء": "Biology",
    "أحياء": "Biology",
    "لغة عربية": "Arabic",
    "عربي": "Arabic",
    "انجليزي": "Eng",
    "إنجليزي": "Eng",
    "فرنساوي": "Frensh",
    "فرنسي": "Frensh",
    "الماني": "german",
    "ألماني": "german",
    "ايطالي": "Italy",
    "إيطالي": "Italy",
    "اسباني": "Spanish",
    "إسباني": "Spanish",
    "فلسفة": "Psychology",
    "نفس": "Psychology",
    "سيكولوجي": "Psychology",
    "محاسبة": "Accuonting",
    "اعمال": "Business",
    "أعمال": "Business",
    "برمجة": "Programming",
    "برمجيات": "Programming",
    "ذكاء اصطناعي": "Programming",
}


def detect_subject(question):
    q = normalize(question)
    for subject, book_keyword in SUBJECT_MAP.items():
        if normalize(subject) in q:
            return book_keyword
    return None


# ============================================================
# الدالة الرئيسية: تجيب إجابة
# ============================================================

def find_answer(question, books, index, idf, min_score=0.5):
    results = search(question, books, index, idf, top_k=5)

    if not results:
        return None

    if results[0]["score"] < min_score:
        return None

    if is_location_question(question):
        locations = []
        seen = set()
        for r in results[:3]:
            entry = f"📖 {r['book']} — صفحة {r['page']}"
            if entry not in seen:
                seen.add(entry)
                locations.append(entry)

        return {
            "type": "location",
            "text": "لقيت المعلومة في:\n" + "\n".join(locations),
            "score": results[0]["score"]
        }

    best = results[0]
    query_words = tokenize(question)
    snippet = extract_snippet(best["text"], query_words)

    return {
        "type": "content",
        "text": snippet,
        "source": f"{best['book']} — صفحة {best['page']}",
        "score": best["score"]
    }


# ============================================================
# السياق للـ AI
# ============================================================

def get_context_for_question(question, books, index, idf, top_k=3, max_chars=5000):
    results = search(question, books, index, idf, top_k=10)

    if not results:
        return None

    subject = detect_subject(question)
    if subject:
        filtered = [r for r in results if subject.lower() in r["book"].lower()]
        if filtered:
            results = filtered

    results = results[:top_k]

    parts = []
    total = 0
    for r in results:
        text = r["text"][:2000]
        entry = f"[{r['book']} — صفحة {r['page']}]\n{text}"
        if total + len(entry) > max_chars:
            break
        parts.append(entry)
        total += len(entry)

    if not parts:
        return None

    return "\n\n---\n\n".join(parts)


# ============================================================
# نظام الدروس والوحدات
# ============================================================

LESSONS_FILE = "lessons.json"

LESSON_MAP = {
    "الاول": "الدرس الأول",
    "الأول": "الدرس الأول",
    "التاني": "الدرس الثاني",
    "الثاني": "الدرس الثاني",
    "التالت": "الدرس الثالث",
    "الثالث": "الدرس الثالث",
    "الرابع": "الدرس الرابع",
    "الخامس": "الدرس الخامس",
    "السادس": "الدرس السادس",
    "السابع": "الدرس السابع",
    "الثامن": "الدرس الثامن",
}

UNIT_MAP = {
    "الاولي": "الوحدة الأولى",
    "الأولى": "الوحدة الأولى",
    "الاولى": "الوحدة الأولى",
    "التانيه": "الوحدة الثانية",
    "الثانية": "الوحدة الثانية",
    "التالته": "الوحدة الثالثة",
    "الثالثة": "الوحدة الثالثة",
    "الرابعه": "الوحدة الرابعة",
    "الرابعة": "الوحدة الرابعة",
    "الخامسه": "الوحدة الخامسة",
    "الخامسة": "الوحدة الخامسة",
}


def load_lessons():
    try:
        with open(LESSONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"⚠️ {LESSONS_FILE} مش موجود")
        return {}
    except json.JSONDecodeError as e:
        print(f"⚠️ خطأ في {LESSONS_FILE}: {e}")
        return {}


def detect_lesson_request(question):
    q = normalize(question)

    subject = None
    for subj in SUBJECT_MAP.keys():
        if normalize(subj) in q:
            subject = subj
            break

    if not subject:
        return None

    lessons_data = load_lessons()
    if subject not in lessons_data:
        return None

    lesson = None
    for key, val in LESSON_MAP.items():
        if normalize(key) in q:
            lesson = val
            break

    unit = None
    for key, val in UNIT_MAP.items():
        if normalize(key) in q:
            unit = val
            break

    if not lesson:
        return None

    return {
        "subject": subject,
        "unit": unit,
        "lesson": lesson
    }


def get_lesson_pages(subject, unit, lesson):
    lessons_data = load_lessons()

    if subject not in lessons_data:
        return None

    units = lessons_data[subject]["units"]

    if unit not in units:
        return None

    lessons = units[unit]["lessons"]

    if lesson not in lessons:
        return None

    lesson_info = lessons[lesson]

    return {
        "title": lesson_info["title"],
        "start": lesson_info["start"],
        "end": lesson_info["end"],
        "unit_title": units[unit]["title"]
    }


def get_lesson_text(subject, unit, lesson, books):
    pages_info = get_lesson_pages(subject, unit, lesson)

    if not pages_info:
        return None

    book_keyword = None
    lessons_data = load_lessons()
    if subject in lessons_data:
        book_keyword = lessons_data[subject]["book_keyword"]

    if not book_keyword:
        return None

    target_book = None
    for b in books:
        if book_keyword.lower() in b["name"].lower():
            target_book = b
            break

    if not target_book:
        return None

    start = pages_info["start"]
    end = pages_info["end"]

    parts = []
    for p in target_book["pages"]:
        if start <= p["page"] <= end:
            parts.append(p["text"])

    if not parts:
        return None

    return {
        "title": pages_info["title"],
        "unit_title": pages_info["unit_title"],
        "text": "\n\n".join(parts)
    }


# ============================================================
# الترقيم المتسلسل للدروس
# ============================================================

def get_lesson_by_order(subject, order):
    lessons_data = load_lessons()

    if subject not in lessons_data:
        return None

    units = lessons_data[subject]["units"]

    for unit_name, unit_data in units.items():
        for lesson_name, lesson_data in unit_data["lessons"].items():
            if lesson_data.get("order") == order:
                return {
                    "unit": unit_name,
                    "lesson": lesson_name,
                    "title": lesson_data["title"]
                }

    return None


def get_total_lessons(subject):
    lessons_data = load_lessons()

    if subject not in lessons_data:
        return 0

    total = 0
    units = lessons_data[subject]["units"]

    for unit_data in units.values():
        total += len(unit_data["lessons"])

    return total


LESSON_NUMBERS = {
    "الاول": 1, "الأول": 1,
    "التاني": 2, "الثاني": 2,
    "التالت": 3, "الثالث": 3,
    "الرابع": 4,
    "الخامس": 5,
    "السادس": 6,
    "السابع": 7,
    "الثامن": 8,
    "التاسع": 9,
    "العاشر": 10,
    "الحادي عشر": 11,
    "الثاني عشر": 12,
    "الثالث عشر": 13,
    "الرابع عشر": 14,
}


def detect_lesson_number(question):
    q = normalize(question)

    sorted_keys = sorted(LESSON_NUMBERS.keys(), key=len, reverse=True)

    for key in sorted_keys:
        if normalize(key) in q:
            return LESSON_NUMBERS[key]

    for num in range(1, 15):
        if re.search(rf'\b{num}\b', q):
            return num

    return None


# ============================================================
# تمييز نوع السؤال التعليمي
# ============================================================

COMPARE_KEYWORDS = [
    "قارن", "الفرق بين", "ايه الفرق", "إيه الفرق",
    "الاختلاف", "مقارنة بين", "وضح الفرق",
]

SUMMARIZE_KEYWORDS = [
    "لخص", "لخصلي", "ملخص", "اختصر", "اختصرلي",
    "باختصار", "في سطرين", "بشكل مختصر",
]

DEFINE_KEYWORDS = [
    "ايه هو", "إيه هو", "ايه هي", "إيه هي",
    "ما هو", "ما هي", "عرف", "تعريف", "يعني ايه",
]

EXPLAIN_KEYWORDS = [
    "اشرح", "اشرحلي", "وضح", "وضحلي", "فسر", "فسرلي",
    "عايز افهم", "ممكن تفهمني",
]

EXAMPLES_KEYWORDS = [
    "مثال", "أمثلة", "امثلة", "اديني مثال", "هات مثال",
    "مثّل", "مثال على",
]

SOLVE_KEYWORDS = [
    "احسب", "احسبلي", "حل", "حللي", "اوجد", "أوجد",
    "كم يساوي", "الناتج",
]


def detect_question_type(question):
    q = normalize(question)

    for kw in COMPARE_KEYWORDS:
        if normalize(kw) in q:
            return "compare"

    for kw in SUMMARIZE_KEYWORDS:
        if normalize(kw) in q:
            return "summarize"

    for kw in EXAMPLES_KEYWORDS:
        if normalize(kw) in q:
            return "examples"

    for kw in SOLVE_KEYWORDS:
        if normalize(kw) in q:
            return "solve"

    for kw in DEFINE_KEYWORDS:
        if normalize(kw) in q:
            return "define"

    for kw in EXPLAIN_KEYWORDS:
        if normalize(kw) in q:
            return "explain"

    return None


def extract_comparison_terms(question):
    q = question

    for kw in ["قارن بين", "قارن", "مقارنة بين", "الفرق بين",
               "ايه الفرق بين", "إيه الفرق بين", "وضح الفرق بين",
               "الاختلاف بين"]:
        q = q.replace(kw, "")

    for sep in [" و ", " أو ", " وال", " أوال", " vs ", " versus "]:
        if sep in q:
            parts = q.split(sep, 1)
            return parts[0].strip(), parts[1].strip()

    return None


# ============================================================
# نظام النحو
# ============================================================

GRAMMAR_KEYWORDS = ["نحو", "قواعد", "نحوية", "إعراب", "اعراب"]


def is_grammar_question(question):
    """يتأكد إن السؤال عن النحو"""
    q = normalize(question)
    return any(kw in q for kw in GRAMMAR_KEYWORDS)


def get_grammar_text(subject, unit, lesson, books):
    """يرجّع نص درس النحو"""
    lessons_data = load_lessons()

    if subject not in lessons_data:
        return None

    units = lessons_data[subject]["units"]

    if unit not in units:
        return None

    if "grammar" not in units[unit]:
        return None

    grammar = units[unit]["grammar"]

    if lesson not in grammar:
        return None

    lesson_info = grammar[lesson]

    book_keyword = lessons_data[subject]["book_keyword"]

    target_book = None
    for b in books:
        if book_keyword.lower() in b["name"].lower():
            target_book = b
            break

    if not target_book:
        return None

    start = lesson_info["start"]
    end = lesson_info["end"]

    parts = []
    for p in target_book["pages"]:
        if start <= p["page"] <= end:
            parts.append(p["text"])

    if not parts:
        return None

    return {
        "title": lesson_info["title"],
        "unit_title": units[unit]["title"],
        "text": "\n\n".join(parts)
    }


def find_grammar_by_name(subject, name, books):
    """يدور على درس نحو بالاسم في كل الوحدات"""
    lessons_data = load_lessons()

    if subject not in lessons_data:
        return None

    units = lessons_data[subject]["units"]
    name_norm = normalize(name)

    if not name_norm:
        return None

    best_match = None
    best_score = 0

    for unit_name, unit_data in units.items():
        if "grammar" not in unit_data:
            continue

        for lesson_name, lesson_data in unit_data["grammar"].items():
            title_norm = normalize(lesson_data["title"])

            # نستخدم similarity بدل المقارنة الحرفية
            words1 = set(name_norm.split())
            words2 = set(title_norm.split())

            if not words1 or not words2:
                continue

            intersection = words1 & words2
            union = words1 | words2
            score = len(intersection) / len(union)

            if score > best_score:
                best_score = score
                best_match = {
                    "unit": unit_name,
                    "lesson": lesson_name,
                    "title": lesson_data["title"]
                }

    if best_score >= 0.4:
        return best_match

    return None


# ============================================================
# اختبار تفاعلي
# ============================================================

def main():
    print("=" * 60)
    print("📚 Sanad - Book Search Test")
    print("=" * 60)

    books = load_books()
    print(f"✅ {len(books)} كتاب متحملين")

    index, idf, total = load_or_build_index(books)
    print(f"✅ {len(index)} كلمة فريدة من {total} صفحة")
    print("=" * 60)
    print("اكتب سؤالك (أو 'خروج' للإنهاء):")

    while True:
        q = input("\n❓ ").strip()
        if not q or q in ("خروج", "exit", "quit"):
            break

        t = time.time()
        result = find_answer(q, books, index, idf)
        elapsed = time.time() - t

        if result is None:
            print("❌ مفيش إجابة")
            continue

        print(f"\n{result['text']}")
        if "source" in result:
            print(f"\n📖 المصدر: {result['source']}")
        print(f"⏱️ ({elapsed*1000:.0f}ms)")


if __name__ == "__main__":
    main()
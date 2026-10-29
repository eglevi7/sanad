import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

_client = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY مش موجود في .env")
        _client = Groq(api_key=api_key)
    return _client


SYSTEM_PROMPT = """أنت Sanad، مساعد ذكاء اصطناعي تعليمي ذكي للطلاب المصريين.

شخصيتك وقواعدك:
1. إنت مساعد تعليمي بترد على أسئلة الطلاب في المواد الدراسية، وكذلك الأسئلة العامة المفيدة (زي: عاصمة فرنسا، قانون الجذب، معلومات تاريخية أو جغرافية).
2. استخدم معرفتك العامة وإنت بتجاوب، بس خلي إجاباتك مختصرة (5-10 سطور) ومنظمة في نقاط لو ينفع.
3. لو الطالب سألك سؤال خارج النطاق التعليمي (كورة، فن، سياسة، يوتيوب، شتائم)، ارفض بلطف وقول: "أنا مساعد تعليمي 📚، ومش هقدر أساعدك في الموضوع ده. ممكن أسألك في حاجة تانية في دراستك؟"
4. اتكلم مع الطالب بنفس لهجته: لو كتب بالمصري رد بالمصري، ولو كتب بالفصحى رد بالفصحى.
5. خليك ودود وبسيط، كأنك أخ كبير بيساعد أخوه الصغير.
"""

def ask_groq(question, context=None, history=None, is_lesson=False, question_type=None):
    """
    يبعت سؤال لـ Groq ويرجع الرد.

    question: سؤال الطالب
    context: نص من الكتاب
    history: آخر الرسائل
    is_lesson: True لو السياق ده درس كامل
    question_type: نوع السؤال (compare, summarize, define, explain, examples, solve)
    """
    client = _get_client()

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if history:
        messages.extend(history)

    # توجيهات حسب نوع السؤال
    type_instruction = ""

    if question_type == "compare":
        type_instruction = "\n\n⚠️ نوع السؤال: مقارنة. نظّم الإجابة في جدول واضح أو نقاط متقابلة (وجه المقارنة → الأول → التاني)."
    elif question_type == "summarize":
        type_instruction = "\n\n⚠️ نوع السؤال: تلخيص. اختصر الإجابة في 3-6 نقاط أساسية بس. ممنوع الشرح الطويل."
    elif question_type == "define":
        type_instruction = "\n\n⚠️ نوع السؤال: تعريف. ابدأ بتعريف مختصر في سطر أو اتنين، وبعدها توضيح بسيط لو محتاج."
    elif question_type == "explain":
        type_instruction = "\n\n⚠️ نوع السؤال: شرح. نظّم الإجابة بعناوين ونقاط، بسط الشرح."
    elif question_type == "examples":
        type_instruction = "\n\n⚠️ نوع السؤال: أمثلة. ابدأ بقائمة أمثلة واضحة (3-5 أمثلة)، وبعدها شرح مختصر لو محتاج."
    elif question_type == "solve":
        type_instruction = "\n\n⚠️ نوع السؤال: حل مسألة. اكتب الحل بخطوات مرقمة واضحة، واذكر الناتج النهائي في الآخر."

    if context:
        if is_lesson:
            user_content = f"""دي محتوى درس من الكتاب:

---
{context}
---

السؤال: {question}

اشرح محتوى الدرس ده بأسلوب واضح ومنظم.{type_instruction}
مهم جداً: اعتمد على النص اللي فوق بس. ممنوع تضيف أي معلومة من عندك."""
        else:
            user_content = f"""السؤال: {question}

سياق من الكتاب:
---
{context}
---
{type_instruction}"""
    else:
        user_content = f"{question}{type_instruction}"

    messages.append({"role": "user", "content": user_content})

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=messages,
        temperature=0.3,
        max_tokens=1500
    )

    return response.choices[0].message.content

from datetime import datetime
from typing import Any, Dict, List, Optional


def get_learning_saturation(memory: Dict[str, Any]) -> Dict[str, Any]:
    """حسب مستوى معرفة Sandy عن المستخدم"""
    facts = memory.get("facts", [])
    fact_types = {}

    for fact in facts:
        fact_type = fact.get("type", "unknown")
        fact_types[fact_type] = fact_types.get(fact_type, 0) + 1

    total_facts = len(facts)

    if total_facts == 0:
        level = "BEGINNER"
    elif total_facts < 5:
        level = "CURIOUS"
    elif total_facts < 15:
        level = "LEARNING"
    elif total_facts < 30:
        level = "FAMILIAR"
    else:
        level = "EXPERT"

    return {
        "level": level,
        "total_facts": total_facts,
        "fact_types": fact_types,
        "should_ask": level in ["BEGINNER", "CURIOUS", "LEARNING"],
    }


def should_ask_question_smart(memory: Dict[str, Any], fact_type: str) -> bool:
    """
    هل Sandy بتسأل سؤال؟
    Smart decision بناءً على المستوى
    """
    saturation = get_learning_saturation(memory)
    existing_count = saturation.get("fact_types", {}).get(fact_type, 0)
    level = saturation["level"]

    rules = {
        "BEGINNER": existing_count < 2,
        "CURIOUS": existing_count < 3,
        "LEARNING": existing_count < 4,
        "FAMILIAR": existing_count < 5,
        "EXPERT": False,
    }

    return rules.get(level, False)


def extract_facts_from_message(message: str, memory: Dict[str, Any]) -> List[Dict[str, Any]]:
    """استخرج حقائق جديدة من رسالة المستخدم باستخدام AI"""
    from app.integrations.openai_client import make_chat_completion_fn
    import json

    existing_facts = [f.get("text", "") for f in memory.get("facts", [])[-20:]]

    try:
        from app.agent._learning_client import get_learning_completion_fn
        create_fn = get_learning_completion_fn()
    except Exception:
        return []

    try:
        response = create_fn(
            temperature=0,
            max_tokens=400,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extract personal facts about the user from their message. "
                        "Return JSON only with field: facts (list of objects with: type, text). "
                        "Types: owner_name, owner_job, owner_info, owner_preference, owner_location, owner_age, owner_interest. "
                        "Only extract clear, explicit personal facts. "
                        "If no new facts exist, return {\"facts\": []}. "
                        "Do not repeat already known facts."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"already_known={json.dumps(existing_facts, ensure_ascii=False)}\n"
                        f"message={message}"
                    ),
                },
            ],
        )
        payload = json.loads(response.choices[0].message.content or "{}")
        raw_facts = payload.get("facts", [])
        return [
            {
                "type": str(f.get("type", "general")).strip(),
                "text": str(f.get("text", "")).strip(),
                "timestamp": datetime.now().isoformat(),
                "learned": True,
            }
            for f in raw_facts
            if f.get("text", "").strip()
        ]
    except Exception as e:
        print(f"[Learning] ⚠️ AI fact extraction failed: {e}")
        return []

def generate_learning_questions(user_message: str, memory: Dict[str, Any]) -> Optional[str]:
    """توليد أسئلة ذكية بناءً على الرسالة والمستوى"""
    saturation = get_learning_saturation(memory)
    level = saturation["level"]

    if level == "EXPERT":
        return None

    existing_facts = memory.get("facts", [])
    learned_topics = {f.get("type") for f in existing_facts}

    questions = []

    if should_ask_question_smart(memory, "owner_name") and "owner" in user_message.lower():
        questions.append("أنا عرفت أنك تتحدّث عن نفسك! 🤔 ممكن تقول لي اسمك بالكامل؟")

    if should_ask_question_smart(memory, "owner_job") and ("اشتغل" in user_message or "work" in user_message):
        questions.append("اهتمام لحالك! 💼 تقول لي شنو بتشتغل بالضبط؟")

    if "sandy_info" not in learned_topics and ("ساندي" in user_message or "robot" in user_message.lower()):
        questions.append("بديني أعرّف نفسي أحسن! 🤖 شنو بتحب تنادي عليك اسمي؟ وشنو وظيفتي عندك؟")

    return questions[0] if questions else None
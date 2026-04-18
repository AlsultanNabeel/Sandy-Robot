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
    """استخرج حقائق جديدة من رسالة المستخدم"""
    facts = []

    patterns = {
        "سمي|اسمي|اسمي هو|أنا اسمي": "owner_name",
        "اشتغل|وظيفتي|اشتغل في|أعمل في": "owner_job",
        "عمري|سني|اسكن|أسكن في": "owner_info",
        "أحب|بحب|يعجبني": "owner_preference",
        "ساندي|اسمك|اسمي": "sandy_info",
    }

    for pattern, fact_type in patterns.items():
        if any(word in message for word in pattern.split("|")):
            facts.append(
                {
                    "type": fact_type,
                    "text": message,
                    "timestamp": datetime.now().isoformat(),
                    "learned": True,
                }
            )

    return facts


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
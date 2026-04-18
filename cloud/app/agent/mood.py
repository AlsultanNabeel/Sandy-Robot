import json
from datetime import datetime
from typing import Any, Dict, Optional


def infer_mood_and_style_from_ai(
    user_message: str,
    memory: Dict[str, Any],
    create_chat_completion_fn,
) -> Optional[Dict[str, Any]]:
    """Use AI to infer Sandy's mood/style from the latest user message."""
    try:
        previous_state = memory.get("sandy_state", {})
        previous_mood = previous_state.get("mood", "neutral")

        response = create_chat_completion_fn(
            temperature=0,
            max_tokens=180,
            response_format={"type": "json_object"},
            prefer_azure=True,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an emotion/context classifier for Sandy, an assistant with memory and personality. "
                        "Analyze the FULL meaning of the user's message, not just keywords. "
                        "Return strict JSON only with fields: "
                        "mood, style, directed_at_sandy, confidence. "
                        "Allowed moods: happy, sad, angry, bored, neutral, excited, romantic, shy, tired, serious. "
                        "Allowed styles: normal, caring, romantic, playful, serious, excited, shy. "
                        "Rules: "
                        "1) If the user is telling a story about something else, do NOT treat it as directly addressed to Sandy. "
                        "2) If words like 'sorry' or 'I love you' appear inside a story, do not automatically map them to caring/romantic unless clearly addressed to Sandy. "
                        "3) Prefer the OVERALL emotional meaning of the message. "
                        "4) Return only JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"previous_mood={previous_mood}\n"
                        f"user_message={user_message}"
                    ),
                },
            ],
        )

        payload = json.loads(response.choices[0].message.content or "{}")

        mood = str(payload.get("mood", "neutral")).strip().lower()
        style = str(payload.get("style", "normal")).strip().lower()
        directed_at_sandy = bool(payload.get("directed_at_sandy", False))
        confidence = float(payload.get("confidence", 0.0) or 0.0)

        allowed_moods = {
            "happy", "sad", "angry", "bored", "neutral",
            "excited", "romantic", "shy", "tired", "serious",
        }
        allowed_styles = {
            "normal", "caring", "romantic", "playful",
            "serious", "excited", "shy",
        }

        if mood not in allowed_moods:
            mood = "neutral"
        if style not in allowed_styles:
            style = "normal"

        return {
            "mood": mood,
            "style": style,
            "directed_at_sandy": directed_at_sandy,
            "confidence": confidence,
        }

    except Exception as e:
        print(f"[MoodAI] ⚠️ Failed to infer mood/style: {e}")
        return None


def update_sandy_state(
    memory: Dict[str, Any],
    user_message: str,
    create_chat_completion_fn,
) -> None:
    """Update Sandy mood/state based on the latest user message."""
    now = datetime.now()
    state = memory.get("sandy_state", {})

    last_time = datetime.fromisoformat(
        state.get("last_user_message_time", now.isoformat())
    )
    last_msg = state.get("last_message", "")
    repeat_count = state.get("repeat_count", 0)
    snapped = state.get("snapped", False)
    previous_mood = state.get("mood", "neutral")

    if user_message.strip() == last_msg.strip():
        repeat_count += 1
    else:
        repeat_count = 0
        snapped = False

    ai_result = infer_mood_and_style_from_ai(
        user_message,
        memory,
        create_chat_completion_fn=create_chat_completion_fn,
    )

    mood = previous_mood
    style = state.get("style", "normal")
    directed_at_sandy = False

    if ai_result and ai_result.get("confidence", 0) >= 0.65:
        mood = ai_result.get("mood", "neutral")
        style = ai_result.get("style", "normal")
        directed_at_sandy = ai_result.get("directed_at_sandy", False)
    else:
        hours_since_last = (now - last_time).total_seconds() / 3600
        lowered_message = (user_message or "").lower()

        if hours_since_last > 24:
            mood = "angry"
        elif hours_since_last > 6:
            mood = "sad"
        else:
            mood = "neutral"

        style = "normal"

        if any(word in lowered_message for word in ["واو", "رائع", "روعة", "متحمس", "متحمسة", "مبسوطة", "مبسوط", "excited"]):
            mood = "excited"
            style = "excited"

        elif any(word in lowered_message for word in ["بحبك", "اشتقت", "حبي", "love you", "missed you"]):
            mood = "romantic"
            style = "romantic"
            directed_at_sandy = True

        elif any(word in lowered_message for word in ["آسف", "سوري", "sorry"]):
            mood = "happy"
            style = "caring"
            directed_at_sandy = True

        elif any(word in lowered_message for word in ["استحيت", "محرج", "خجلان", "خجلانة", "shy"]):
            mood = "shy"
            style = "shy"

        elif any(word in lowered_message for word in ["تعبان", "تعبانة", "نعسان", "نعسانة", "مرهق", "مرهقة", "tired"]):
            mood = "tired"
            style = "normal"

        elif any(word in lowered_message for word in ["ركز", "مهم", "بسرعة", "رسمي", "جاد", "serious"]):
            mood = "serious"
            style = "serious"

    if repeat_count >= 3 and mood not in ["romantic", "excited"]:
        mood = "bored"
        style = "serious"
        if repeat_count >= 6:
            snapped = True

    state.update({
        "mood": mood,
        "style": style,
        "directed_at_sandy": directed_at_sandy,
        "last_user_message_time": now.isoformat(),
        "repeat_count": repeat_count,
        "last_message": user_message,
        "snapped": snapped,
        "last_mood_change": (
            now.isoformat()
            if mood != previous_mood
            else state.get("last_mood_change", now.isoformat())
        ),
    })

    memory["sandy_state"] = state


def get_sandy_reply(
    user_message: str,
    memory: Dict[str, Any],
    default_reply: str,
) -> str:
    """Return Sandy reply; currently passes through the default reply."""
    return default_reply
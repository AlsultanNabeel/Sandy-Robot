from typing import Any, Callable, Dict, Optional

from app.utils.text import (
    extract_reaction_and_clean_text,
    prepare_tts_text,
)
from app.integrations.google_tts import synthesize_voice_with_google
from app.integrations.azure_speech import synthesize_voice_with_azure


def _remove_emojis(text: str) -> str:
    try:
        import emoji
        return emoji.replace_emoji(text, replace="")
    except ImportError:
        return text


def send_text_and_voice_reply(
    chat_id: int,
    text: str,
    *,
    telegram_bot: Any,
    agent_memory: Optional[Dict[str, Any]] = None,
    reply_to_message_id: Optional[int] = None,
    set_last_assistant_reaction_fn: Optional[Callable[[Optional[str]], None]] = None,
    google_tts_voice: str = "",
    google_tts_language_code: str = "ar-XA",
    mood_tts_voices: Optional[Dict[str, str]] = None,
    azure_speech_available: bool = False,
    azure_speech_key: str = "",
    azure_speech_region: str = "",
    azure_speech_voice: str = "",
) -> None:
    # بتبعت رسالة نصية للمستخدم، ولو فيه صوت بتبعت كمان رد صوتي
    text = str(text or "[think] صار خلل وما رجع نص واضح.")

    # استخرج الرياكشن من الرد (إذا موجود)
    reaction, text_without_reaction = extract_reaction_and_clean_text(text)

    # حفظ الرياكشن في متغير خارجي (للهاردوير لاحقاً) إذا تم تمرير setter
    if set_last_assistant_reaction_fn:
        try:
            set_last_assistant_reaction_fn(reaction)
        except Exception as e:
            print(f"[Voice] ⚠️ Failed to store reaction: {e}")

    telegram_bot.send_message(
        chat_id,
        text_without_reaction,
        reply_to_message_id=reply_to_message_id,
        parse_mode=None,
    )

    # إزالة الإيموجي من النص الصوتي حتى لا تُقرأ كنص والروابط أيضًا
    tts_text = prepare_tts_text(text_without_reaction)
    tts_text = _remove_emojis(tts_text)

    print(f"[DEBUG] Trying Google TTS for: {tts_text}")

    agent_memory = agent_memory or {}
    current_state = agent_memory.get("sandy_state", {})
    current_mood = current_state.get("mood", "neutral")
    current_style = current_state.get("style", "normal")

    print(f"[DEBUG] Voice mood='{current_mood}' style='{current_style}'")

    audio_bytes = synthesize_voice_with_google(
        tts_text,
        mood=current_mood,
        style=current_style,
        google_tts_voice=google_tts_voice,
        google_tts_language_code=google_tts_language_code,
        mood_tts_voices=mood_tts_voices,
    )

    if audio_bytes:
        print("[DEBUG] Google TTS succeeded. Sending Google voice reply.")
        source = "Google TTS"
    else:
        print("[DEBUG] Google TTS failed. Trying Azure TTS...")
        audio_bytes = synthesize_voice_with_azure(
            tts_text,
            azure_speech_available=azure_speech_available,
            azure_speech_key=azure_speech_key,
            azure_speech_region=azure_speech_region,
            azure_speech_voice=azure_speech_voice,
        )
        if audio_bytes:
            print("[DEBUG] Azure TTS succeeded. Sending Azure voice reply.")
            source = "Azure TTS"
        else:
            print("[DEBUG] Both Google and Azure TTS failed. No voice reply will be sent.")
            source = None

    if audio_bytes:
        try:
            telegram_bot.send_voice(chat_id, audio_bytes, timeout=120)
            print(f"[DEBUG] Voice sent via Telegram. Source: {source}")
        except Exception as e:
            print(f"[Telegram] ⚠️ Voice reply failed: {e}")
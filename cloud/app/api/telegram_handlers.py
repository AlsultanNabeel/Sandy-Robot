import io
import threading
from collections import deque
from typing import Any, Callable, Dict, Optional


_recent_message_keys = deque(maxlen=500)
_recent_message_set = set()
_recent_message_lock = threading.Lock()
_authorized_user_chat_id: Optional[str] = None


def configure_telegram_handler_state(*, sandy_user_chat_id: str) -> None:
    global _authorized_user_chat_id
    _authorized_user_chat_id = str(sandy_user_chat_id)


def _is_duplicate_telegram_message(message) -> bool:
    key = f"{message.chat.id}:{message.message_id}"
    with _recent_message_lock:
        if key in _recent_message_set:
            return True

        if len(_recent_message_keys) == _recent_message_keys.maxlen:
            old = _recent_message_keys.popleft()
            _recent_message_set.discard(old)

        _recent_message_keys.append(key)
        _recent_message_set.add(key)

    return False


def _is_authorized_user(message) -> bool:
    if _authorized_user_chat_id is None:
        return False
    return str(message.from_user.id) == _authorized_user_chat_id


def register_basic_telegram_handlers(
    *,
    telegram_bot: Any,
    agent: Any,
    sandy_user_chat_id: str,
    is_image_generation_request_fn: Callable[[str], bool],
    extract_image_prompt_fn: Callable[[str], str],
    generate_image_with_azure_fn: Callable[..., Optional[bytes]],
    analyze_image_with_azure_fn: Callable[..., str],
    download_telegram_file_bytes_fn: Callable[..., Any],
    transcribe_audio_with_azure_fn: Callable[..., Optional[str]],
    create_chat_completion_fn: Callable[..., Any],
    send_text_and_voice_reply_fn: Callable[..., None],
    set_last_assistant_reaction_fn: Optional[Callable[[Optional[str]], None]] = None,
    handle_image_message_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    persist_agent_session_fn: Optional[Callable[[], None]] = None,
    google_tts_voice: str = "",
    google_tts_language_code: str = "ar-XA",
    mood_tts_voices: Optional[Dict[str, str]] = None,
    azure_speech_available: bool = False,
    azure_speech_key: str = "",
    azure_speech_region: str = "",
    azure_speech_voice: str = "",
    azure_openai_client: Any = None,
    azure_openai_image_deployment: Optional[str] = None,
    azure_openai_vision_deployment: Optional[str] = None,
    azure_openai_chat_deployment: Optional[str] = None,
    azure_openai_stt_deployment: Optional[str] = None,
    openai_model: Optional[str] = None,
) -> None:
    configure_telegram_handler_state(sandy_user_chat_id=sandy_user_chat_id)

    @telegram_bot.message_handler(commands=["start", "help"])
    def handle_start(message):
        response = """[love] أهلاً  ! 💫
أنا ساندي، وكيلك الذكي الجديد!
الآن بأشتغل 24/7 بدون ما تحتاج تشغّل اللابتوب.

بتقدر:
🔍 تسأليني أي حاجة
📧 أرسل رسائل وإيميلات
📅 أدير مهامك وتذكيراتك
🤖 أتحكم بـ Sandy
💾 أتذكر كل شي عنك

جرّب: "صباح الخير!" أو "إبحثي عن..."
"""
        telegram_bot.reply_to(message, response)

    @telegram_bot.message_handler(commands=["image", "img"])
    def handle_image_command(message):
        try:
            if _is_duplicate_telegram_message(message):
                return
            if not _is_authorized_user(message):
                telegram_bot.reply_to(message, "معاف، بس المستخدم بيقدر يتكلم معي 🔒")
                return

            chat_id = message.chat.id
            result = None
            if handle_image_message_fn is not None:
                result = handle_image_message_fn(
                    message.text or "",
                    session=agent.session,
                    create_chat_completion_fn=create_chat_completion_fn,
                    generate_image_with_azure_fn=generate_image_with_azure_fn,
                    azure_openai_client=azure_openai_client,
                    azure_openai_image_deployment=azure_openai_image_deployment,
                    size="512x512",
                )

            if result is None:
                prompt = extract_image_prompt_fn(message.text or "")
                if not prompt:
                    telegram_bot.reply_to(
                        message,
                        "[think] اكتب وصف الصورة بعد الأمر. مثال: /image قطة كرتونية تلبس نظارات",
                    )
                    return

                telegram_bot.send_chat_action(chat_id, "upload_photo")
                image_bytes = generate_image_with_azure_fn(
                    prompt,
                    azure_openai_client=azure_openai_client,
                    azure_openai_image_deployment=azure_openai_image_deployment,
                )
                if not image_bytes:
                    telegram_bot.reply_to(
                        message,
                        "[think] ما قدرت أولد الصورة. تأكد من AZURE_OPENAI_IMAGE_DEPLOYMENT.",
                    )
                    return

                result = {
                    "handled": True,
                    "success": True,
                    "image_bytes": image_bytes,
                    "caption": f"[happy] تفضّل ✨\nالوصف: {prompt}",
                    "reply_text": "[happy] ولدت الصورة بنجاح ✨ إذا بدك أعدل الستايل ابعتلي وصف جديد.",
                }

            if result.get("needs_followup"):
                if persist_agent_session_fn is not None:
                    persist_agent_session_fn()
                telegram_bot.reply_to(message, result.get("reply_text") or "[think] وضّحلي أكثر الصورة اللي بدك ياها.")
                return

            if not result.get("success"):
                telegram_bot.reply_to(message, result.get("reply_text") or "[think] ما قدرت أولد الصورة حالياً.")
                return

            telegram_bot.send_chat_action(chat_id, "upload_photo")
            photo_file = io.BytesIO(result["image_bytes"])
            photo_file.name = "sandy_generated.png"
            telegram_bot.send_photo(
                chat_id,
                photo_file,
                caption=result.get("caption") or "[happy] هاي الصورة ✨",
            )

            if persist_agent_session_fn is not None:
                persist_agent_session_fn()

            telegram_bot.reply_to(
                message,
                result.get("reply_text") or "جهزت الصورة.",
            )
        except Exception as e:
            print(f"[Error] Image command handler: {e}")
            telegram_bot.reply_to(message, "[think] صار خلل أثناء توليد الصورة.")

    @telegram_bot.message_handler(content_types=["photo"])
    def handle_photo(message):
        try:
            if _is_duplicate_telegram_message(message):
                return
            if not _is_authorized_user(message):
                telegram_bot.reply_to(message, "معاف، بس المستخدم بيقدر يتكلم معي 🔒")
                return

            chat_id = message.chat.id
            telegram_bot.send_chat_action(chat_id, "typing")

            photo = message.photo[-1] if message.photo else None
            if not photo:
                telegram_bot.reply_to(message, "[think] ما وصلتني الصورة بشكل صحيح.")
                return

            downloaded = download_telegram_file_bytes_fn(telegram_bot, photo.file_id)
            if not downloaded:
                telegram_bot.reply_to(message, "[think] ما قدرت أحمّل الصورة من تيليجرام.")
                return

            image_bytes, _ = downloaded
            prompt = message.caption or "حللي الصورة باختصار وقدمي أهم الملاحظات."
            analysis = analyze_image_with_azure_fn(
                image_bytes,
                prompt,
                create_chat_completion_fn=create_chat_completion_fn,
                azure_openai_vision_deployment=azure_openai_vision_deployment,
                azure_openai_chat_deployment=azure_openai_chat_deployment,
                openai_model=openai_model,
            )
            telegram_bot.send_message(
                chat_id,
                analysis,
                reply_to_message_id=message.message_id,
                parse_mode=None,
            )
        except Exception as e:
            print(f"[Error] Photo handler: {e}")
            telegram_bot.reply_to(message, "[think] صار خلل أثناء تحليل الصورة.")

    @telegram_bot.message_handler(content_types=["video"])
    def handle_video(message):
        try:
            if _is_duplicate_telegram_message(message):
                return
            if not _is_authorized_user(message):
                telegram_bot.reply_to(message, "معاف، بس المستخدم بيقدر يتكلم معي 🔒")
                return

            chat_id = message.chat.id
            telegram_bot.send_chat_action(chat_id, "typing")

            thumb = getattr(message.video, "thumbnail", None) or getattr(message.video, "thumb", None)
            if not thumb:
                telegram_bot.send_message(
                    chat_id,
                    "[think] وصل الفيديو، لكن بدون Thumbnail للتحليل البصري. ابعته كصورة أو فيديو فيه معاينة.",
                    reply_to_message_id=message.message_id,
                    parse_mode=None,
                )
                return

            downloaded = download_telegram_file_bytes_fn(telegram_bot, thumb.file_id)
            if not downloaded:
                telegram_bot.reply_to(message, "[think] ما قدرت أحمّل معاينة الفيديو.")
                return

            image_bytes, _ = downloaded
            prompt = message.caption or "حللي محتوى الفيديو اعتماداً على لقطة المعاينة وقدمي وصف مختصر."
            analysis = analyze_image_with_azure_fn(
                image_bytes,
                prompt,
                create_chat_completion_fn=create_chat_completion_fn,
                azure_openai_vision_deployment=azure_openai_vision_deployment,
                azure_openai_chat_deployment=azure_openai_chat_deployment,
                openai_model=openai_model,
            )
            telegram_bot.send_message(
                chat_id,
                analysis,
                reply_to_message_id=message.message_id,
                parse_mode=None,
            )
        except Exception as e:
            print(f"[Error] Video handler: {e}")
            telegram_bot.reply_to(message, "[think] صار خلل أثناء تحليل الفيديو.")

    @telegram_bot.message_handler(content_types=["voice", "audio"])
    def handle_voice_or_audio(message):
        try:
            if _is_duplicate_telegram_message(message):
                return
            if not _is_authorized_user(message):
                telegram_bot.reply_to(message, "معاف، بس المستخدم بيقدر يتكلم معي 🔒")
                return

            chat_id = message.chat.id
            telegram_bot.send_chat_action(chat_id, "typing")

            media_obj = message.voice if message.content_type == "voice" else message.audio
            if not media_obj:
                telegram_bot.reply_to(message, "[think] ما قدرت أقرأ الملف الصوتي.")
                return

            downloaded = download_telegram_file_bytes_fn(telegram_bot, media_obj.file_id)
            if not downloaded:
                telegram_bot.reply_to(message, "[think] ما قدرت أحمّل الصوت من تيليجرام.")
                return

            audio_bytes, file_path = downloaded
            transcript = transcribe_audio_with_azure_fn(
                audio_bytes,
                azure_speech_available=azure_speech_available,
                azure_speech_key=azure_speech_key,
                azure_speech_region=azure_speech_region,
                file_name=file_path,
            )
            if not transcript:
                telegram_bot.reply_to(message, "[think] ما قدرت أحول الصوت لنص. تأكد من إعداد Azure STT.")
                return

            print(f"[Telegram] Voice transcript: {transcript}")
            response = agent.think(transcript)
            send_text_and_voice_reply_fn(
                chat_id,
                response,
                telegram_bot=telegram_bot,
                agent_memory=agent.memory,
                reply_to_message_id=message.message_id,
                set_last_assistant_reaction_fn=set_last_assistant_reaction_fn,
                google_tts_voice=google_tts_voice,
                google_tts_language_code=google_tts_language_code,
                mood_tts_voices=mood_tts_voices,
                azure_speech_available=azure_speech_available,
                azure_speech_key=azure_speech_key,
                azure_speech_region=azure_speech_region,
                azure_speech_voice=azure_speech_voice,
            )
        except Exception as e:
            print(f"[Error] Voice handler: {e}")
            telegram_bot.reply_to(message, "[think] صار خلل أثناء تحليل الصوت.")

    @telegram_bot.message_handler(content_types=["text"])
    def handle_message(message):
        try:
            print(f"[DEBUG] Received message from chat_id: {message.chat.id}")
            if _is_duplicate_telegram_message(message):
                print(f"[Telegram] Duplicate ignored: chat={message.chat.id}, msg={message.message_id}")
                return

            user_message = (message.text or "").strip()
            chat_id = message.chat.id

            if not _is_authorized_user(message):
                telegram_bot.reply_to(message, "معاف، بس المستخدم بيقدر يتكلم معي 🔒")
                return

            if not user_message:
                telegram_bot.reply_to(message, "[think] ما وصلني نص الرسالة.")
                return

            image_result = None
            if handle_image_message_fn is not None:
                image_result = handle_image_message_fn(
                    user_message,
                    session=agent.session,
                    create_chat_completion_fn=create_chat_completion_fn,
                    generate_image_with_azure_fn=generate_image_with_azure_fn,
                    azure_openai_client=azure_openai_client,
                    azure_openai_image_deployment=azure_openai_image_deployment,
                )

            if image_result is None and is_image_generation_request_fn(user_message):
                prompt = extract_image_prompt_fn(user_message)
                if not prompt:
                    telegram_bot.reply_to(message, "[think] اكتب وصف واضح للصورة اللي بدك ياها.")
                    return

                image_bytes = generate_image_with_azure_fn(
                    prompt,
                    azure_openai_client=azure_openai_client,
                    azure_openai_image_deployment=azure_openai_image_deployment,
                )
                if not image_bytes:
                    telegram_bot.reply_to(
                        message,
                        "[think] ما قدرت أولد الصورة حالياً. تأكد من إعداد Azure image deployment."
                    )
                    return

                image_result = {
                    "handled": True,
                    "success": True,
                    "image_bytes": image_bytes,
                    "caption": f"[happy] هاي الصورة اللي طلبتها ✨\nالوصف: {prompt}",
                    "reply_text": "[happy] جاهزة 👌 إذا بدك نسخة ثانية بستايل مختلف احكيلي الوصف الجديد.",
                }

            if image_result and image_result.get("handled"):
                if image_result.get("needs_followup"):
                    if persist_agent_session_fn is not None:
                        persist_agent_session_fn()
                    telegram_bot.reply_to(message, image_result.get("reply_text") or "[think] وضّحلي أكثر الصورة اللي بدك ياها.")
                    return

                if not image_result.get("success"):
                    telegram_bot.reply_to(message, image_result.get("reply_text") or "[think] ما قدرت أولد الصورة حالياً.")
                    return

                telegram_bot.send_chat_action(chat_id, "upload_photo")
                photo_file = io.BytesIO(image_result["image_bytes"])
                photo_file.name = "sandy_generated.png"
                telegram_bot.send_photo(
                    chat_id,
                    photo_file,
                    caption=image_result.get("caption") or "[happy] هاي الصورة اللي طلبتها ✨",
                    reply_to_message_id=message.message_id,
                )
                if persist_agent_session_fn is not None:
                    persist_agent_session_fn()
                send_text_and_voice_reply_fn(
                    chat_id,
                    image_result.get("reply_text") or "[happy] جاهزة ✨",
                    telegram_bot=telegram_bot,
                    agent_memory=agent.memory,
                    reply_to_message_id=message.message_id,
                    set_last_assistant_reaction_fn=set_last_assistant_reaction_fn,
                    google_tts_voice=google_tts_voice,
                    google_tts_language_code=google_tts_language_code,
                    mood_tts_voices=mood_tts_voices,
                    azure_speech_available=azure_speech_available,
                    azure_speech_key=azure_speech_key,
                    azure_speech_region=azure_speech_region,
                    azure_speech_voice=azure_speech_voice,
                )
                return

            telegram_bot.send_chat_action(chat_id, "typing")
            print(f"[Telegram] Message from {message.from_user.first_name}: {user_message}")
            response = agent.think(user_message)

            send_text_and_voice_reply_fn(
                chat_id,
                response,
                telegram_bot=telegram_bot,
                agent_memory=agent.memory,
                reply_to_message_id=message.message_id,
                set_last_assistant_reaction_fn=set_last_assistant_reaction_fn,
                google_tts_voice=google_tts_voice,
                google_tts_language_code=google_tts_language_code,
                mood_tts_voices=mood_tts_voices,
                azure_speech_available=azure_speech_available,
                azure_speech_key=azure_speech_key,
                azure_speech_region=azure_speech_region,
                azure_speech_voice=azure_speech_voice,
            )
        except Exception as e:
            import traceback
            print(f"[Error] Telegram handler: {e}")
            traceback.print_exc()
            telegram_bot.reply_to(message, f"[اعتذر] حدث خطأ: {str(e)}")
import json
import re
from datetime import datetime
from typing import Any, Dict, Optional


def _safe_json_loads(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            return {}
    return {}


_DIRECT_COMMAND_RE = re.compile(r"^(?:/image|/img)\s*", flags=re.IGNORECASE)


def _default_image_state() -> Dict[str, Any]:
    return {
        "active_image": None,
        "history": [],
        "pending_image_action": None,
    }


def ensure_image_state(session: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(session, dict):
        return _default_image_state()
    image_state = session.get("image_state")
    if not isinstance(image_state, dict):
        image_state = _default_image_state()
        session["image_state"] = image_state
    image_state.setdefault("active_image", None)
    image_state.setdefault("history", [])
    image_state.setdefault("pending_image_action", None)
    return image_state


def _extract_direct_command_prompt(user_message: str) -> str:
    return _DIRECT_COMMAND_RE.sub("", (user_message or "").strip()).strip()


def _fallback_new_image_prompt(text: str) -> str:
    return (text or "").strip()


def _fallback_edit_image_prompt(text: str, active_image: Optional[Dict[str, Any]]) -> str:
    previous_prompt = str((active_image or {}).get("generation_prompt", "") or "").strip()
    text = (text or "").strip()

    if previous_prompt:
        return (
            f"Keep the same overall style, composition, and main subject from this previous image prompt: "
            f"{previous_prompt}. "
            f"Apply this user change/request: {text}. "
            f"Only change what the user asked for."
        )

    return text


def plan_image_action_with_ai(
    user_message: str,
    *,
    session: Optional[Dict[str, Any]],
    create_chat_completion_fn=None,
) -> Dict[str, Any]:
    text = (user_message or "").strip()
    if not text or create_chat_completion_fn is None:
        return {"handled": False}

    image_state = ensure_image_state(session)
    active_image = image_state.get("active_image") or {}
    pending_image_action = image_state.get("pending_image_action") or {}
    direct_prompt = _extract_direct_command_prompt(text)
    is_direct_command = bool(_DIRECT_COMMAND_RE.match(text))

    if is_direct_command:
        if not direct_prompt:
            return {
                "handled": True,
                "action": "clarify",
                "needs_followup": True,
                "followup_question": "اكتب وصف الصورة بعد الأمر. مثال: /image قطة كرتونية تلبس نظارات خضرا",
                "generation_prompt": "",
                "short_caption_ar": "",
            }
        return {
            "handled": True,
            "action": "generate_new",
            "needs_followup": False,
            "followup_question": "",
            "generation_prompt": direct_prompt,
            "short_caption_ar": direct_prompt,
        }

    try:
        response = create_chat_completion_fn(
            temperature=0,
            max_tokens=500,
            response_format={"type": "json_object"},
            prefer_azure=True,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Sandy's image-intent planner. Return strict JSON only. "
                        "Decide whether the user is asking to create a new image, continue/modify the last generated image, "
                        "or is not talking about images at all. "
                        "Output fields exactly: handled (bool), action (string), generation_prompt (string), "
                        "short_caption_ar (string), needs_followup (bool), followup_question (string). "
                        "Valid action values: none, generate_new, edit_last, variation, clarify. "
                        "Rules: "
                        "1) If the message is ordinary chat and not about image generation/continuation, handled=false. "
                        "2) If there is an active image and the user says things like make it, change it, same one but, remove, add, "
                        "خليها, نفس الصورة, بدّل, رجّع, غيّر, then handled=true and usually action=edit_last or variation. "
                        "3) The generation_prompt must be a fully self-contained English prompt ready for image generation. "
                        "4) If modifying the last image, preserve the previous style, composition, and subject identity unless the user explicitly changes them. "
                        "5) If there is no active image and the message is too vague for a new image, handled=true, action=clarify, needs_followup=true. "
                        "6) short_caption_ar should be a very short Arabic description of the intended image. "
                        "7) Never require the user to say draw/ارسم explicitly. Infer intent from context. "
                        "8) If pending_image_action exists and the new message is an answer to that pending question, resolve it. "
                        "9) If user wants a direct edit of an uploaded real photo, still treat it as handled=true only if there is active generated image context; otherwise ask a short clarification question because current tool path regenerates from prompt context."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"active_image={json.dumps(active_image, ensure_ascii=False)}\n"
                        f"pending_image_action={json.dumps(pending_image_action, ensure_ascii=False)}\n"
                        f"message={text}"
                    ),
                },
            ],
        )
        payload = _safe_json_loads(response.choices[0].message.content or "{}")
    except Exception as e:
        print(f"[ImagePlanner] ⚠️ Planner failed: {e}")
        return {"handled": False}

    handled = bool(payload.get("handled", False))
    action = str(payload.get("action", "none") or "none").strip().lower()
    if action not in {"none", "generate_new", "edit_last", "variation", "clarify"}:
        action = "none"

    generation_prompt = str(payload.get("generation_prompt", "") or "").strip()
    short_caption_ar = str(payload.get("short_caption_ar", "") or "").strip()
    needs_followup = bool(payload.get("needs_followup", False))
    followup_question = str(payload.get("followup_question", "") or "").strip()

    if handled:
        if action == "clarify":
            if active_image and text:
                action = "edit_last"
                generation_prompt = _fallback_edit_image_prompt(text, active_image)
                short_caption_ar = short_caption_ar or text
                needs_followup = False
                followup_question = ""
            elif text and len(text.split()) >= 2:
                action = "generate_new"
                generation_prompt = _fallback_new_image_prompt(text)
                short_caption_ar = short_caption_ar or text
                needs_followup = False
                followup_question = ""

        elif action in {"edit_last", "variation"} and not generation_prompt and active_image and text:
            generation_prompt = _fallback_edit_image_prompt(text, active_image)
            short_caption_ar = short_caption_ar or text
            needs_followup = False
            followup_question = ""

    return {
        "handled": handled,
        "action": action,
        "generation_prompt": generation_prompt,
        "short_caption_ar": short_caption_ar,
        "needs_followup": needs_followup,
        "followup_question": followup_question,
    }


def render_image_reply_with_ai(
    *,
    create_chat_completion_fn,
    user_message: str,
    plan: Optional[Dict[str, Any]] = None,
    success: bool,
    fallback_text: str,
) -> str:
    if create_chat_completion_fn is None:
        return fallback_text

    plan = plan or {}

    try:
        response = create_chat_completion_fn(
            temperature=0.7,
            max_tokens=120,
            prefer_azure=True,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Sandy. "
                        "Write one short natural Arabic reply for the user after an image action. "
                        "Do not use any tags like [happy], [think], [sad], or emojis unless very light and natural. "
                        "Do not sound robotic. "
                        "If success is true, sound warm and confident. "
                        "If success is false, sound brief, clear, and helpful. "
                        "Return only the final Arabic reply text."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"user_message={user_message}\n"
                        f"success={success}\n"
                        f"action={plan.get('action', '')}\n"
                        f"short_caption_ar={plan.get('short_caption_ar', '')}\n"
                        f"fallback={fallback_text}"
                    ),
                },
            ],
        )
        text = (response.choices[0].message.content or "").strip()
        text = re.sub(r"\[(happy|think|sad|angry|calm|excited)\]\s*", "", text, flags=re.IGNORECASE).strip()
        return text or fallback_text
    except Exception as e:
        print(f"[ImageReply] ⚠️ AI reply render failed: {e}")
        return fallback_text
    
    

def handle_image_message(
    user_message: str,
    *,
    session: Optional[Dict[str, Any]],
    create_chat_completion_fn,
    generate_image_with_azure_fn,
    azure_openai_client: Any,
    azure_openai_image_deployment: Optional[str],
    size: str = "512x512",
) -> Dict[str, Any]:
    image_state = ensure_image_state(session)
    plan = plan_image_action_with_ai(
        user_message,
        session=session,
        create_chat_completion_fn=create_chat_completion_fn,
    )

    if not plan.get("handled"):
        return {"handled": False}

    if plan.get("needs_followup") or not plan.get("generation_prompt"):
        image_state["pending_image_action"] = {
            "last_user_message": (user_message or "").strip(),
            "asked_at": datetime.now().isoformat(),
            "followup_question": plan.get("followup_question", "").strip(),
        }
        followup_text = plan.get("followup_question") or "شو الشكل أو التعديل اللي بدك ياه بالضبط؟"

        return {
            "handled": True,
            "success": False,
            "needs_followup": True,
            "reply_text": render_image_reply_with_ai(
                create_chat_completion_fn=create_chat_completion_fn,
                user_message=user_message,
                plan=plan,
                success=False,
                fallback_text=followup_text,
            ),
        }

    image_bytes = generate_image_with_azure_fn(
        plan["generation_prompt"],
        azure_openai_client=azure_openai_client,
        azure_openai_image_deployment=azure_openai_image_deployment,
        size=size,
    ) 
    if not image_bytes:
        fallback_text = "ما قدرت أولد الصورة حاليًا. جرّب تغيّر الوصف شوي أو أعد المحاولة."

        return {
            "handled": True,
            "success": False,
            "needs_followup": False,
            "reply_text": render_image_reply_with_ai(
                create_chat_completion_fn=create_chat_completion_fn,
                user_message=user_message,
                plan=plan, 
                success=False,
                fallback_text=fallback_text,
            ),
        }

    now_iso = datetime.now().isoformat()
    previous_active = image_state.get("active_image")
    current_entry = {
        "user_request": (user_message or "").strip(),
        "generation_prompt": plan["generation_prompt"],
        "short_caption_ar": plan.get("short_caption_ar") or (user_message or "").strip(),
        "action": plan.get("action", "generate_new"),
        "created_at": now_iso,
        "derived_from": (previous_active or {}).get("created_at") if previous_active else None,
    }

    history = image_state.get("history", [])
    if isinstance(history, list):
        history.append(current_entry)
        image_state["history"] = history[-12:]
    else:
        image_state["history"] = [current_entry]

    image_state["active_image"] = current_entry
    image_state["pending_image_action"] = None

    action = plan.get("action", "generate_new")
    if action == "edit_last":
        fallback_text = "تمام، عدّلت الصورة على نفس السياق."
    elif action == "variation":
        fallback_text = "جهزت نسخة جديدة بنفس الفكرة."
    else:
        fallback_text = "جهزت الصورة."

    reply_text = render_image_reply_with_ai(
        create_chat_completion_fn=create_chat_completion_fn,
        user_message=user_message,
        plan=plan,
        success=True,
        fallback_text=fallback_text,
    )

    return {
        "handled": True,
        "success": True,
        "needs_followup": False,
        "reply_text": reply_text,
        "image_bytes": image_bytes,
        "caption": current_entry["short_caption_ar"],
        "plan": plan,
    }
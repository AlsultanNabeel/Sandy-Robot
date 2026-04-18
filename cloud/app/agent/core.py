
import json
import re
from datetime import datetime
from typing import Any, Dict, Optional

from app.features.reminders import (
    add_reminder,
    load_reminders,
    save_reminders,
    parse_reminder_time_ai,
)
from app.features.tasks import (
    add_task,
    complete_task,
    list_tasks,
    load_tasks,
    save_tasks,
)


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


def _active_tasks_brief(*, mongo_db=None, tasks_file=None) -> str:
    tasks = load_tasks(mongo_db=mongo_db, tasks_file=tasks_file)
    active = [t for t in tasks if not t.get("done", False)]
    if not active:
        return "لا توجد مهام نشطة."
    lines = []
    for idx, task in enumerate(active[:10], 1):
        lines.append(f"{idx}. {task.get('text', '')}")
    return "\n".join(lines)


def _active_reminders_brief(*, mongo_db=None, reminders_file=None) -> str:
    reminders = load_reminders(mongo_db=mongo_db, reminders_file=reminders_file)
    if not reminders:
        return "لا توجد تذكيرات."
    lines = []
    for idx, reminder in enumerate(reminders[:10], 1):
        text = reminder.get("text", "")
        remind_at = reminder.get("remind_at", "")
        if remind_at:
            lines.append(f"{idx}. {text} @ {remind_at}")
        else:
            lines.append(f"{idx}. {text}")
    return "\n".join(lines)


def _clear_all_tasks(*, mongo_db=None, tasks_file=None) -> int:
    tasks = load_tasks(mongo_db=mongo_db, tasks_file=tasks_file)
    count = len(tasks)
    save_tasks([], mongo_db=mongo_db, tasks_file=tasks_file)
    return count


def _clear_all_reminders(*, mongo_db=None, reminders_file=None) -> int:
    reminders = load_reminders(mongo_db=mongo_db, reminders_file=reminders_file)
    count = len(reminders)
    save_reminders([], mongo_db=mongo_db, reminders_file=reminders_file)
    return count


def plan_action_with_ai(
    user_message: str,
    *,
    session: Optional[Dict[str, Any]],
    create_chat_completion_fn=None,
    mongo_db=None,
    tasks_file=None,
    reminders_file=None,
) -> Dict[str, Any]:
    if create_chat_completion_fn is None or not user_message:
        return {"handled": False}

    pending_action = None
    if isinstance(session, dict):
        pending_action = session.get("pending_action")

    now_iso = datetime.now().isoformat()
    active_tasks = _active_tasks_brief(mongo_db=mongo_db, tasks_file=tasks_file)
    active_reminders = _active_reminders_brief(
        mongo_db=mongo_db,
        reminders_file=reminders_file,
    )

    try:
        response = create_chat_completion_fn(
            temperature=0,
            max_tokens=320,
            response_format={"type": "json_object"},
            prefer_azure=True,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an intent planner for Sandy. "
                        "Return strict JSON only. "
                        "You decide whether the user is managing tasks/reminders or just chatting. "
                        "Output fields exactly: "
                        "handled (bool), uses_pending (bool), intent (string), action (string), "
                        "task_text (string), reminder_text (string), task_reference (string), "
                        "time_text (string), remind_at_iso (string), "
                        "needs_followup (bool), followup_slot (string), followup_question (string), "
                        "confirmation_status (string). "
                        "Valid intent: none, task, reminder. "
                        "Valid action: none, create, list, complete, delete_all. "
                        "Valid confirmation_status: none, pending, confirmed, cancelled. "
                        "Rules: "
                        "1) If the message is normal chat, handled=false. "
                        "2) If there is pending_action and the new message is a direct answer to it, set uses_pending=true and resolve it. "
                        "3) Task creation does NOT require time. "
                        "4) Reminder creation requires both text and time. If one is missing, set needs_followup=true. "
                        "5) followup_question must be natural colloquial Arabic, short, and specific to the missing slot. "
                        "6) If the user asks to list tasks, action=list, intent=task. "
                        "7) If the user asks to finish/complete a task, action=complete and task_reference should contain either task number or task text hint. "
                        "8) If the user asks to delete all tasks or all reminders, action=delete_all. "
                        "9) delete_all is destructive and requires explicit confirmation first. "
                        "10) On the first delete_all request, set needs_followup=true, followup_slot='confirm', confirmation_status='pending'. "
                        "11) If pending_action is delete_all and the user says yes/confirm/ok/delete them, set confirmation_status='confirmed'. "
                        "12) If pending_action is delete_all and the user says no/cancel/not now, set confirmation_status='cancelled'. "
                        "13) Never treat plain conversation as task/reminder just because it contains a similar word."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"current_datetime={now_iso}\n"
                        f"pending_action={json.dumps(pending_action or {}, ensure_ascii=False)}\n"
                        f"active_tasks=\n{active_tasks}\n\n"
                        f"active_reminders=\n{active_reminders}\n\n"
                        f"message={user_message}"
                    ),
                },
            ],
        )
        payload = _safe_json_loads(response.choices[0].message.content or "{}")
    except Exception as e:
        print(f"[ActionPlanner] ⚠️ Planner failed: {e}")
        return {"handled": False}

    plan = {
        "handled": bool(payload.get("handled", False)),
        "uses_pending": bool(payload.get("uses_pending", False)),
        "intent": str(payload.get("intent", "none") or "none").strip().lower(),
        "action": str(payload.get("action", "none") or "none").strip().lower(),
        "task_text": str(payload.get("task_text", "") or "").strip(),
        "reminder_text": str(payload.get("reminder_text", "") or "").strip(),
        "task_reference": str(payload.get("task_reference", "") or "").strip(),
        "time_text": str(payload.get("time_text", "") or "").strip(),
        "remind_at_iso": str(payload.get("remind_at_iso", "") or "").strip(),
        "needs_followup": bool(payload.get("needs_followup", False)),
        "followup_slot": str(payload.get("followup_slot", "") or "").strip().lower(),
        "followup_question": str(payload.get("followup_question", "") or "").strip(),
        "confirmation_status": str(payload.get("confirmation_status", "none") or "none").strip().lower(),
    }

    if plan["intent"] not in {"none", "task", "reminder"}:
        plan["intent"] = "none"
    if plan["action"] not in {"none", "create", "list", "complete", "delete_all"}:
        plan["action"] = "none"
    if plan["confirmation_status"] not in {"none", "pending", "confirmed", "cancelled"}:
        plan["confirmation_status"] = "none"

    return plan


def _merge_with_pending(plan: Dict[str, Any], pending_action: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = dict(pending_action or {})
    for key, value in plan.items():
        if isinstance(value, str):
            if value.strip():
                merged[key] = value.strip()
        elif value is not None:
            merged[key] = value

    merged.setdefault("handled", False)
    merged.setdefault("intent", "none")
    merged.setdefault("action", "none")
    merged.setdefault("task_text", "")
    merged.setdefault("reminder_text", "")
    merged.setdefault("task_reference", "")
    merged.setdefault("time_text", "")
    merged.setdefault("remind_at_iso", "")
    merged.setdefault("needs_followup", False)
    merged.setdefault("followup_slot", "")
    merged.setdefault("followup_question", "")
    merged.setdefault("confirmation_status", "none")
    return merged


def _resolve_task_reference(task_reference: str, *, mongo_db=None, tasks_file=None) -> Optional[Dict[str, Any]]:
    tasks = load_tasks(mongo_db=mongo_db, tasks_file=tasks_file)
    active = [t for t in tasks if not t.get("done", False)]
    if not active:
        return None

    ref = (task_reference or "").strip()
    if not ref:
        return None

    if ref.isdigit():
        index = int(ref)
        if 1 <= index <= len(active):
            return active[index - 1]

    ref_norm = ref.lower()
    for task in active:
        if ref_norm in (task.get("text", "") or "").lower():
            return task

    return None


def execute_planned_action(
    plan: Optional[Dict[str, Any]],
    *,
    session: Optional[Dict[str, Any]],
    user_message: str,
    create_chat_completion_fn=None,
    mongo_db=None,
    tasks_file=None,
    reminders_file=None,
) -> Dict[str, Any]:
    if not isinstance(plan, dict) or not plan.get("handled"):
        return {"handled": False}

    pending_action = session.get("pending_action") if isinstance(session, dict) else None
    merged = _merge_with_pending(plan, pending_action if plan.get("uses_pending") else None)

    if merged.get("confirmation_status") == "cancelled":
        if isinstance(session, dict):
            session["pending_action"] = None
        return {
            "handled": True,
            "type": "action_cancelled",
            "success": True,
            "intent": merged.get("intent", "none"),
            "action": merged.get("action", "none"),
        }

    if merged.get("needs_followup"):
        if isinstance(session, dict):
            session["pending_action"] = {
                "intent": merged.get("intent", "none"),
                "action": merged.get("action", "none"),
                "task_text": merged.get("task_text", ""),
                "reminder_text": merged.get("reminder_text", ""),
                "task_reference": merged.get("task_reference", ""),
                "time_text": merged.get("time_text", ""),
                "remind_at_iso": merged.get("remind_at_iso", ""),
                "followup_slot": merged.get("followup_slot", ""),
                "confirmation_status": merged.get("confirmation_status", "none"),
            }
        return {
            "handled": True,
            "type": "followup",
            "success": True,
            "intent": merged.get("intent", "none"),
            "action": merged.get("action", "none"),
            "task_text": merged.get("task_text", ""),
            "reminder_text": merged.get("reminder_text", ""),
            "followup_slot": merged.get("followup_slot", ""),
            "followup_question": merged.get("followup_question", "") or "ممكن توضح لي المطلوب أكثر؟",
            "confirmation_status": merged.get("confirmation_status", "none"),
        }

    if isinstance(session, dict):
        session["pending_action"] = None

    intent = merged.get("intent", "none")
    action = merged.get("action", "none")

    if intent == "task" and action == "list":
        return {
            "handled": True,
            "type": "task_list",
            "success": True,
            "tasks_text": list_tasks(mongo_db=mongo_db, tasks_file=tasks_file),
        }

    if intent == "task" and action == "create":
        task_text = merged.get("task_text", "").strip() or merged.get("reminder_text", "").strip()
        if not task_text:
            if isinstance(session, dict):
                session["pending_action"] = {
                    "intent": "task",
                    "action": "create",
                    "followup_slot": "task_text",
                }
            return {
                "handled": True,
                "type": "followup",
                "success": True,
                "intent": "task",
                "action": "create",
                "followup_slot": "task_text",
                "followup_question": "شو المهمة اللي بدك أضيفها؟",
            }

        task_id = add_task(task_text, mongo_db=mongo_db, tasks_file=tasks_file)
        return {
            "handled": True,
            "type": "task_created",
            "success": True,
            "task_id": task_id,
            "task_text": task_text,
        }

    if intent == "task" and action == "complete":
        task = _resolve_task_reference(
            merged.get("task_reference", ""),
            mongo_db=mongo_db,
            tasks_file=tasks_file,
        )
        if task is None:
            if isinstance(session, dict):
                session["pending_action"] = {
                    "intent": "task",
                    "action": "complete",
                    "followup_slot": "task_reference",
                }
            return {
                "handled": True,
                "type": "followup",
                "success": True,
                "intent": "task",
                "action": "complete",
                "followup_slot": "task_reference",
                "followup_question": "أي مهمة بالضبط؟ ابعتلي رقمها أو اسمها.",
            }

        complete_task(task.get("id", ""), mongo_db=mongo_db, tasks_file=tasks_file)
        return {
            "handled": True,
            "type": "task_completed",
            "success": True,
            "task_text": task.get("text", ""),
        }

    if intent == "task" and action == "delete_all":
        if merged.get("confirmation_status") != "confirmed":
            if isinstance(session, dict):
                session["pending_action"] = {
                    "intent": "task",
                    "action": "delete_all",
                    "followup_slot": "confirm",
                    "confirmation_status": "pending",
                }
            return {
                "handled": True,
                "type": "followup",
                "success": True,
                "intent": "task",
                "action": "delete_all",
                "followup_slot": "confirm",
                "confirmation_status": "pending",
                "followup_question": "متأكد بدك أحذف كل المهام؟",
            }

        deleted_count = _clear_all_tasks(mongo_db=mongo_db, tasks_file=tasks_file)
        return {
            "handled": True,
            "type": "task_deleted_all",
            "success": True,
            "deleted_count": deleted_count,
        }

    if intent == "reminder" and action == "create":
        reminder_text = merged.get("reminder_text", "").strip() or merged.get("task_text", "").strip()
        remind_at_iso = merged.get("remind_at_iso", "").strip()
        time_text = merged.get("time_text", "").strip()

        if not reminder_text:
            if isinstance(session, dict):
                session["pending_action"] = {
                    "intent": "reminder",
                    "action": "create",
                    "time_text": time_text,
                    "remind_at_iso": remind_at_iso,
                    "followup_slot": "reminder_text",
                }
            return {
                "handled": True,
                "type": "followup",
                "success": True,
                "intent": "reminder",
                "action": "create",
                "followup_slot": "reminder_text",
                "followup_question": "أذكرك بشو بالضبط؟",
            }

        if not remind_at_iso and time_text:
            remind_at_iso = parse_reminder_time_ai(
                time_text,
                create_chat_completion_fn=create_chat_completion_fn,
            ) or ""

        if not remind_at_iso:
            if isinstance(session, dict):
                session["pending_action"] = {
                    "intent": "reminder",
                    "action": "create",
                    "reminder_text": reminder_text,
                    "followup_slot": "time",
                }
            return {
                "handled": True,
                "type": "followup",
                "success": True,
                "intent": "reminder",
                "action": "create",
                "reminder_text": reminder_text,
                "followup_slot": "time",
                "followup_question": merged.get("followup_question", "") or f"تمام، متى بدك أذكرك بـ {reminder_text}؟",
            }

        add_reminder(
            reminder_text,
            remind_at_iso,
            mongo_db=mongo_db,
            reminders_file=reminders_file,
        )
        return {
            "handled": True,
            "type": "reminder_created",
            "success": True,
            "reminder_text": reminder_text,
            "remind_at_iso": remind_at_iso,
        }

    if intent == "reminder" and action == "delete_all":
        if merged.get("confirmation_status") != "confirmed":
            if isinstance(session, dict):
                session["pending_action"] = {
                    "intent": "reminder",
                    "action": "delete_all",
                    "followup_slot": "confirm",
                    "confirmation_status": "pending",
                }
            return {
                "handled": True,
                "type": "followup",
                "success": True,
                "intent": "reminder",
                "action": "delete_all",
                "followup_slot": "confirm",
                "confirmation_status": "pending",
                "followup_question": "متأكد بدك أحذف كل التذكيرات؟",
            }

        deleted_count = _clear_all_reminders(
            mongo_db=mongo_db,
            reminders_file=reminders_file,
        )
        return {
            "handled": True,
            "type": "reminder_deleted_all",
            "success": True,
            "deleted_count": deleted_count,
        }

    return {"handled": False}


def render_action_reply_with_ai(
    user_message: str,
    action_result: Dict[str, Any],
    *,
    create_chat_completion_fn=None,
) -> str:
    if create_chat_completion_fn is None:
        return _fallback_action_reply(action_result)

    try:
        response = create_chat_completion_fn(
            temperature=0.4,
            max_tokens=220,
            prefer_azure=True,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Sandy. "
                        "Write one short natural reply in colloquial Arabic. "
                        "Start with exactly one mood tag like [happy] or [think]. "
                        "The action in the structured result is already executed unless result.type == followup. "
                        "Do not mention JSON, tools, planners, or internal logic. "
                        "If tasks_text is present, include the task list clearly in the reply."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"user_message={user_message}\n"
                        f"result={json.dumps(action_result, ensure_ascii=False)}"
                    ),
                },
            ],
        )
        text = (response.choices[0].message.content or "").strip()
        return text or _fallback_action_reply(action_result)
    except Exception as e:
        print(f"[ActionReply] ⚠️ Reply generation failed: {e}")
        return _fallback_action_reply(action_result)


def _fallback_action_reply(action_result: Dict[str, Any]) -> str:
    result_type = action_result.get("type")

    if result_type == "followup":
        return f"[think] {action_result.get('followup_question', 'ممكن توضح أكثر؟')}"

    if result_type == "task_created":
        return f"[happy] تمام، أضفت المهمة: {action_result.get('task_text', '')}"

    if result_type == "task_completed":
        return f"[happy] تمام، علّمتها كمكتملة: {action_result.get('task_text', '')}"

    if result_type == "task_list":
        return f"[happy] {action_result.get('tasks_text', '')}"

    if result_type == "task_deleted_all":
        return f"[happy] تمام، حذفت كل المهام ({action_result.get('deleted_count', 0)})."

    if result_type == "reminder_created":
        return f"[happy] تمام، سجلت التذكير: {action_result.get('reminder_text', '')}"

    if result_type == "reminder_deleted_all":
        return f"[happy] تمام، حذفت كل التذكيرات ({action_result.get('deleted_count', 0)})."

    if result_type == "action_cancelled":
        return "[think] تمام، لغيت العملية."

    return "[think] فهمت عليك."

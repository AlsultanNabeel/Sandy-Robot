import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from app.utils.files import read_json_file, write_json_file




# بترجع كل التذكيرات (من MongoDB أو ملف)
def load_reminders(mongo_db=None, reminders_file: Optional[Path] = None):
    """Load reminders from MongoDB or disk"""

    if mongo_db is not None:
        try:
            reminders = list(mongo_db["reminders"].find({"type": "reminder"}))
            for reminder in reminders:
                reminder.pop("_id", None)
                reminder.pop("type", None)
            if reminders:
                print("[Reminders] ✅ Loaded from MongoDB")
                return reminders

            if reminders_file:
                json_reminders = read_json_file(reminders_file, [])
                if isinstance(json_reminders, list) and json_reminders:
                    mongo_db["reminders"].delete_many({"type": "reminder"})
                    for reminder in json_reminders:
                        doc = {**reminder, "type": "reminder"}
                        mongo_db["reminders"].insert_one(doc)
                    print("[Reminders] 🔁 Migrated JSON -> MongoDB")
                    return json_reminders

            print("[Reminders] ✅ MongoDB is source of truth (0 reminders)")
            return []
        except Exception as e:
            print(f"[Reminders] ⚠️ MongoDB error: {e}")

    if reminders_file:
        reminders_json = _read_json_file(reminders_file, [])
        if isinstance(reminders_json, list) and reminders_json:
            print("[Reminders] 📄 Loaded from JSON file")
            return reminders_json

    return []

# بتخزن كل التذكيرات (في MongoDB أو ملف)
def save_reminders(reminders, mongo_db=None, reminders_file: Optional[Path] = None):
    """Save reminders to MongoDB or disk"""

    if mongo_db is not None:
        try:
            mongo_db["reminders"].delete_many({"type": "reminder"})
            if reminders:
                for reminder in reminders:
                    doc = {**reminder, "type": "reminder"}
                    mongo_db["reminders"].insert_one(doc)
            print("[Reminders] ✅ Saved to MongoDB")
            return
        except Exception as e:
            print(f"[Reminders] ⚠️ MongoDB save error: {e}")

    if reminders_file:
        try:
            if write_json_file(reminders_file, reminders):
                print("[Reminders] 📄 Saved to JSON file")
        except Exception as e:
            print(f"[Reminders] Error saving reminders: {e}")

 

# بتضيف تذكير جديد (وتحاول تحلل الوقت تلقائياً لو مش محدد)
def add_reminder(text, remind_at=None, mongo_db=None, reminders_file: Optional[Path] = None):
    """Add a new reminder with automatic time parsing"""
    reminders = load_reminders(mongo_db=mongo_db, reminders_file=reminders_file)

    if not remind_at:
        remind_at = parse_reminder_time(text)

    reminder = {
        "id": str(datetime.now().timestamp()),
        "text": text,
        "created_at": datetime.now().isoformat(),
        "remind_at": remind_at,
    }
    reminders.append(reminder)
    save_reminders(reminders, mongo_db=mongo_db, reminders_file=reminders_file)

    if remind_at:
        print(f"[Reminders] 🔔 تذكير جديد: {text} بـ {remind_at}")
    else:
        print(f"[Reminders] 🔔 تذكير جديد: {text} (بدون وقت محدد)")

    return reminder["id"]

# بتشيك إذا فيه تذكيرات لازم تنبعت وبتبعتها تلقائياً
def check_reminders(
    mongo_db=None,
    reminders_file: Optional[Path] = None,
    send_message_fn=None,
    user_chat_id=None,
):
    """Check if any reminders need to be sent and send them via Telegram"""
    try:
        reminders = load_reminders(mongo_db=mongo_db, reminders_file=reminders_file)
        now = datetime.now()

        print(f"[Scheduler] 🔔 Checking {len(reminders)} reminders at {now.strftime('%H:%M:%S')}")

        pending = []
        remaining = []

        for reminder in reminders:
            if reminder.get("remind_at"):
                try:
                    remind_time = datetime.fromisoformat(reminder["remind_at"])
                    time_diff = (now - remind_time).total_seconds()

                    print(f"[Scheduler] Reminder: '{reminder.get('text', '')[:40]}' at {remind_time.strftime('%H:%M:%S')}, diff={time_diff:.0f}s")

                    if -5 <= time_diff <= 120:
                        if time_diff >= 0:
                            pending.append(reminder)
                        else:
                            remaining.append(reminder)
                    else:
                        remaining.append(reminder)
                except Exception as e:
                    print(f"[Scheduler] ❌ Error parsing time: {e}")
                    remaining.append(reminder)
            else:
                remaining.append(reminder)

        if pending:
            print(f"[Scheduler] 📤 Found {len(pending)} pending reminders to send!")

            for reminder in pending:
                message_text = f"🔔 تذكير: {reminder.get('text', '')}"

                if send_message_fn and user_chat_id:
                    try:
                        chat_id = int(user_chat_id)
                        send_message_fn(chat_id, message_text, parse_mode=None)
                        print(f"[Reminder] ✅ أرسلت: {message_text}")
                    except Exception as e:
                        print(f"[Reminder] ❌ خطأ بالإرسال: {type(e).__name__}: {e}")
                else:
                    print("[Reminder] ⚠️ Missing send_message_fn or user_chat_id")

            save_reminders(remaining, mongo_db=mongo_db, reminders_file=reminders_file)
            return f"🔔 تم إرسال {len(pending)} تذكير!"

        return None

    except Exception as e:
        print(f"[Scheduler] ❌ Critical error: {e}")
        return None


# بتحول الأرقام العربية/الفارسية لأرقام انجليزية عشان التحليل
def normalize_arabic_digits(text: str) -> str:
    """Normalize Arabic/Persian digits to ASCII digits for regex parsing."""
    if not text:
        return text
    translation = str.maketrans(
        "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹",
        "01234567890123456789"
    )
    return text.translate(translation)




# بتطلع نص التذكير الصافي من رسالة المستخدم
def extract_reminder_text(message: str) -> str:
    """Extract clean reminder payload from user message."""
    text = message or ""
    # Remove common reminder verbs
    text = re.sub(r'(ممكن\s+)?(ت?ذكريني|ت?ذكرني|فكريني|فكرني)', '', text)
    # Remove time expressions handled by parser
    text = re.sub(r'(على|عال|ع\s*الساعة|الساعة)\s*\d{1,2}:\d{2}', '', text)
    text = re.sub(r'(بعد|كمان)\s*\d+\s*(دقيقة|دقايق|ساعه|ساعة|ساعات)', '', text)
    # Remove wrappers/quotes and filler connectors
    text = re.sub(r'\b(انو|إنو|انه|أنه|ب|about)\b', ' ', text)
    text = text.replace('"', ' ').replace("'", ' ')
    text = re.sub(r'\s+', ' ', text).strip(' ؟?،,.')
    return text



# بتحلل الوقت من رسالة التذكير (يدوي)
def parse_reminder_time(message: str) -> Optional[str]:
    """Parse time from reminder message
    Examples:
    - "ذكرني على 10:14 بشي" -> 10:14
    - "ذكرني بعد 30 دقيقة" -> current_time + 30 min
    """
    now = datetime.now()
    message = normalize_arabic_digits(message)
    
    # Pattern 1: "على/عال/الساعة HH:MM" (at specific time)
    match = re.search(r'(?:على|عال|ع\s*الساعة|الساعة|\bال\b)?\s*(\d{1,2}):(\d{2})', message)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        try:
            if hour > 23 or minute > 59:
                return None

            # Try 24h interpretation first.
            candidate_times = [now.replace(hour=hour, minute=minute, second=0, microsecond=0)]

            # If user writes 12h style (e.g., 8:49 in evening), also try +12h.
            if hour <= 12:
                hour_12h = (hour % 12) + 12
                candidate_times.append(now.replace(hour=hour_12h, minute=minute, second=0, microsecond=0))

            # Keep only future candidates; if none, push next-day for first candidate.
            future_candidates = [t for t in candidate_times if t >= now]
            if future_candidates:
                reminder_time = min(future_candidates, key=lambda t: (t - now).total_seconds())
            else:
                reminder_time = candidate_times[0] + timedelta(days=1)
            
            iso_time = reminder_time.isoformat()
            print(f"[Parse] ⏰ Parsed time: {iso_time} (Now: {now.isoformat()})")
            return iso_time
        except Exception as e:
            print(f"[Parse] ❌ Error parsing time: {e}")
            pass
    
    # Pattern 2: "بعد X دقيقة" variants (after X minutes)
    match = re.search(r'(بعد|كمان)\s*(\d+)\s*(دقيقة|دقيقه|دقائق|دقايق|minute|minutes|min)', message, flags=re.IGNORECASE)
    if match:
        minutes = int(match.group(2))
        reminder_time = now + timedelta(minutes=minutes)
        iso_time = reminder_time.isoformat()
        print(f"[Parse] ⏰ Parsed time (after {minutes}min): {iso_time}")
        return iso_time
    
    # Pattern 3: "بعد X ساعة" variants (after X hours)
    match = re.search(r'(بعد|كمان)\s*(\d+)\s*(ساعة|ساعه|ساعات|hour|hours|hr|hrs)', message, flags=re.IGNORECASE)
    if match:
        hours = int(match.group(2))
        reminder_time = now + timedelta(hours=hours)
        iso_time = reminder_time.isoformat()
        print(f"[Parse] ⏰ Parsed time (after {hours}hrs): {iso_time}")
        return iso_time

    print(f"[Parse] ⚠️ Could not parse reminder time from: {message!r}")
    
    return None



# بتستخدم الذكاء الاصطناعي عشان تكتشف إذا الرسالة فيها نية تذكير وتطلع التفاصيل
def extract_reminder_intent_ai(user_message: str, create_chat_completion_fn=None):
    if create_chat_completion_fn is None:
        return None

    try:
        response = create_chat_completion_fn(
            temperature=0,
            max_tokens=160,
            response_format={"type": "json_object"},
            prefer_azure=True,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You extract reminder intents from Arabic/English user messages. "
                        "Return strict JSON only with fields: "
                        "is_reminder (boolean), reminder_text (string), "
                        "time_expression (string), confidence (0..1). "
                        "If user asks status/count of reminders/tasks, set is_reminder=false."
                    )
                },
                {
                    "role": "user",
                    "content": user_message
                }
            ]
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
        return {
            "is_reminder": bool(data.get("is_reminder", False)),
            "reminder_text": str(data.get("reminder_text", "") or "").strip(),
            "time_expression": str(data.get("time_expression", "") or "").strip(),
            "confidence": float(data.get("confidence", 0.0) or 0.0)
        }
    except Exception as e:
        print(f"[ReminderAI] ⚠️ Intent extraction failed: {e}")
        return None
    

# بتخلي الذكاء الاصطناعي يخطط تذكير كامل (نص ووقت ورد)
def plan_reminder_with_ai(user_message: str, create_chat_completion_fn=None):
    if create_chat_completion_fn is None:
        return None
    if not user_message:
        return None

    now_iso = datetime.now().isoformat()
    try:
        response = create_chat_completion_fn(
            temperature=0,
            max_tokens=260,
            response_format={"type": "json_object"},
            prefer_azure=True,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a reminder intent planner for an Arabic assistant. "
                        "Return strict JSON only with fields: "
                        "is_reminder (bool), should_create (bool), reminder_text (string), "
                        "remind_at_iso (string), assistant_reply (string), confidence (0..1). "
                        "Rules: "
                        "1) If user did not request creating a reminder, set is_reminder=false and should_create=false. "
                        "2) If user requested a reminder and time+content are clear, set should_create=true and output remind_at_iso in valid ISO datetime (future). "
                        "3) If user requested reminder but details are missing/ambiguous, set should_create=false and produce assistant_reply in natural friendly colloquial Arabic that addresses the exact user sentence (NOT template). "
                        "4) assistant_reply must start with one mood tag like [happy] or [think]. "
                        "5) Never treat normal conversation as reminder."
                    )
                },
                {
                    "role": "user",
                    "content": f"current_datetime={now_iso}\nmessage={user_message}"
                }
            ]
        )

        payload = json.loads(response.choices[0].message.content or "{}")
        remind_at_iso = str(payload.get("remind_at_iso", "") or "").strip()

        if remind_at_iso:
            dt_val = datetime.fromisoformat(remind_at_iso)
            if dt_val < datetime.now():
                dt_val = datetime.now() + timedelta(minutes=1)
            remind_at_iso = dt_val.isoformat()

        return {
            "is_reminder": bool(payload.get("is_reminder", False)),
            "should_create": bool(payload.get("should_create", False)),
            "reminder_text": str(payload.get("reminder_text", "") or "").strip(),
            "remind_at_iso": remind_at_iso,
            "assistant_reply": str(payload.get("assistant_reply", "") or "").strip(),
            "confidence": float(payload.get("confidence", 0.0) or 0.0)
        }
    except Exception as e:
        print(f"[ReminderAI] ⚠️ Planner failed: {e}")
        return None
    
    

# بتستخدم الذكاء الاصطناعي لتحليل الوقت من رسالة التذكير
def parse_reminder_time_ai(user_message: str, create_chat_completion_fn=None):
    if create_chat_completion_fn is None:
        return None
    if not user_message:
        return None

    now = datetime.now()
    now_iso = now.isoformat()
    try:
        response = create_chat_completion_fn(
            temperature=0,
            max_tokens=140,
            response_format={"type": "json_object"},
            prefer_azure=True,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Convert reminder time expressions to JSON only. "
                        "Return fields: success (boolean), remind_at_iso (string), reason (string). "
                        "If no time can be inferred, set success=false. "
                        "Use the provided current datetime as reference and output full ISO format."
                    )
                },
                {
                    "role": "user",
                    "content": f"current_datetime={now_iso}\ntext={user_message}"
                }
            ]
        )
        payload = json.loads(response.choices[0].message.content or "{}")
        if not payload.get("success"):
            print(f"[ParseAI] ⚠️ Could not parse time: {payload.get('reason', 'unknown')}")
            return None

        iso_value = str(payload.get("remind_at_iso", "")).strip()
        if not iso_value:
            return None

        dt_value = datetime.fromisoformat(iso_value)
        if dt_value < now:
            dt_value = now + timedelta(minutes=1)

        final_iso = dt_value.isoformat()
        print(f"[ParseAI] ⏰ Parsed by AI: {final_iso}")
        return final_iso
    except Exception as e:
        print(f"[ParseAI] ⚠️ Fallback parser failed: {e}")
        return None
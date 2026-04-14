#!/usr/bin/env python3
"""
Sandy Agent - 24/7 Intelligent Assistant on Railway
Inspired by OpenClaw, powered by OpenAI GPT-4o
"""

import os
import json
import time
import asyncio
import threading
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from openai import OpenAI
import telebot
from apscheduler.schedulers.background import BackgroundScheduler

# MongoDB Integration
try:
    from pymongo import MongoClient
    from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    print("[Warning] PyMongo not available, falling back to JSON memory")

# Try to import Chroma for smart memory
try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    print("[Warning] Chroma DB not available, using JSON memory only")

# ═══════════════════════════════════════════════════════════
# CONFIGURATION & ENV SETUP
# ═══════════════════════════════════════════════════════════

BASE_DIR = Path(__file__).resolve().parent

# Try to load .env locally (for development)
try:
    load_dotenv(BASE_DIR / ".env")
except:
    pass

# Data directories
DATA_DIR = BASE_DIR.parent / "data"
MEMORY_DIR = DATA_DIR / "memory"
TASKS_DIR = DATA_DIR / "tasks"

# Create directories if they don't exist
MEMORY_DIR.mkdir(parents=True, exist_ok=True)
TASKS_DIR.mkdir(parents=True, exist_ok=True)

# OpenAI Configuration (read from environment variables)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o").strip()

# Telegram Configuration (read from environment variables)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
SANDY_USER_CHAT_ID = os.getenv("SANDY_USER_CHAT_ID", "").strip()

# MongoDB Configuration
MONGODB_URI = os.getenv("MONGODB_URI", "").strip()
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "sandy_db").strip()

# Initialize MongoDB connection
mongo_client = None
mongo_db = None

if MONGODB_AVAILABLE and MONGODB_URI:
    try:
        mongo_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        # Test connection
        mongo_client.admin.command('ping')
        mongo_db = mongo_client[MONGODB_DB_NAME]
        print("[MongoDB] ✅ Connected successfully")
    except (ServerSelectionTimeoutError, ConnectionFailure) as e:
        print(f"[MongoDB] ⚠️ Connection failed: {e}")
        print("[MongoDB] Falling back to JSON memory")
        mongo_client = None
        mongo_db = None
else:
    print("[MongoDB] ⚠️ MONGODB_URI not set, using JSON memory for now")

# DEBUG: Print what we're reading
print("[DEBUG STARTUP] Environment Variables:")
print(f"  OPENAI_API_KEY: {'SET' if OPENAI_API_KEY else 'EMPTY'} (len={len(OPENAI_API_KEY)})")
print(f"  TELEGRAM_BOT_TOKEN: {'SET' if TELEGRAM_BOT_TOKEN else 'EMPTY'} (len={len(TELEGRAM_BOT_TOKEN)})")
print(f"  SANDY_USER_CHAT_ID: {'SET' if SANDY_USER_CHAT_ID else 'EMPTY'} ({SANDY_USER_CHAT_ID})")

# Sandy Configuration
try:
    from sandy_config import NABEEL_INFO, SANDY_PERSONALITY, SYSTEM_PROMPT_ADDITION
except Exception:
    NABEEL_INFO = ""
    SANDY_PERSONALITY = ""
    SYSTEM_PROMPT_ADDITION = ""

# Memory Configuration (updated paths)
MEMORY_FILE = MEMORY_DIR / "sandy_agent_memory.json"
SESSION_FILE = MEMORY_DIR / "sandy_session_memory.json"
TASKS_FILE = TASKS_DIR / "daily_plan.json"
REMINDERS_FILE = TASKS_DIR / "reminders.json"

# ═══════════════════════════════════════════════════════════
# INITIALIZATION
# ═══════════════════════════════════════════════════════════

if not OPENAI_API_KEY:
    print("[WARNING] OPENAI_API_KEY missing - will fail on first request")
    print(f"[DEBUG] OPENAI_API_KEY value: {OPENAI_API_KEY}")
    print(f"[DEBUG] TELEGRAM_BOT_TOKEN value: {TELEGRAM_BOT_TOKEN}")
    print(f"[DEBUG] SANDY_USER_CHAT_ID value: {SANDY_USER_CHAT_ID}")
    # Don't raise error - let it fail gracefully
    # raise RuntimeError("OPENAI_API_KEY missing in .env")

if not TELEGRAM_BOT_TOKEN:
    print("[WARNING] TELEGRAM_BOT_TOKEN missing")
    # raise RuntimeError("TELEGRAM_BOT_TOKEN missing in .env")

if not SANDY_USER_CHAT_ID:
    print("[WARNING] SANDY_USER_CHAT_ID missing")
    # raise RuntimeError("SANDY_USER_CHAT_ID missing in .env")

openai_client = OpenAI(api_key=OPENAI_API_KEY)
telegram_bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, threaded=True)
scheduler = BackgroundScheduler(timezone=None)
scheduler.start()

# ═══════════════════════════════════════════════════════════
# MEMORY MANAGEMENT (MongoDB + JSON Fallback)
# ═══════════════════════════════════════════════════════════

def load_memory() -> Dict[str, Any]:
    """Load persistent memory from MongoDB or disk"""
    
    # Try MongoDB first
    if mongo_db:
        try:
            memory_doc = mongo_db['memory'].find_one({"_id": "sandy_memory"})
            if memory_doc:
                memory_doc.pop("_id", None)  # Remove MongoDB ID
                print("[Memory] ✅ Loaded from MongoDB")
                return memory_doc
        except Exception as e:
            print(f"[Memory] ⚠️ MongoDB error: {e}, falling back to JSON")
    
    # Fallback to JSON file
    if MEMORY_FILE.exists():
        try:
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                print("[Memory] 📄 Loaded from JSON file")
                return json.load(f)
        except Exception as e:
            print(f"[Memory] Error loading memory: {e}")
    
    # Return default structure
    return {
        "conversations": [],
        "facts": [],
        "reminders": [],
        "tasks": []
    }

def save_memory(memory: Dict[str, Any]):
    """Save memory to MongoDB or disk"""
    
    # Try MongoDB first
    if mongo_db:
        try:
            memory_with_id = {**memory, "_id": "sandy_memory"}
            mongo_db['memory'].replace_one(
                {"_id": "sandy_memory"},
                memory_with_id,
                upsert=True
            )
            print("[Memory] ✅ Saved to MongoDB")
            return
        except Exception as e:
            print(f"[Memory] ⚠️ MongoDB save error: {e}, falling back to JSON")
    
    # Fallback to JSON file
    try:
        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(memory, f, ensure_ascii=False, indent=2)
            print("[Memory] 📄 Saved to JSON file")
    except Exception as e:
        print(f"[Memory] Error saving memory: {e}")

def load_session() -> Dict[str, Any]:
    """Load current session memory from MongoDB or disk"""
    
    # Try MongoDB first
    if mongo_db:
        try:
            session_doc = mongo_db['sessions'].find_one({"_id": "current_session"})
            if session_doc:
                session_doc.pop("_id", None)
                print("[Session] ✅ Loaded from MongoDB")
                return session_doc
        except Exception as e:
            print(f"[Session] ⚠️ MongoDB error: {e}")
    
    # Fallback to JSON file
    if SESSION_FILE.exists():
        try:
            with open(SESSION_FILE, 'r', encoding='utf-8') as f:
                print("[Session] 📄 Loaded from JSON file")
                return json.load(f)
        except Exception:
            pass
    
    return {"messages": []}

def save_session(session: Dict[str, Any]):
    """Save session memory to MongoDB or disk"""
    
    # Try MongoDB first
    if mongo_db:
        try:
            session_with_id = {**session, "_id": "current_session"}
            mongo_db['sessions'].replace_one(
                {"_id": "current_session"},
                session_with_id,
                upsert=True
            )
            print("[Session] ✅ Saved to MongoDB")
            return
        except Exception as e:
            print(f"[Session] ⚠️ MongoDB save error: {e}")
    
    # Fallback to JSON file
    try:
        with open(SESSION_FILE, 'w', encoding='utf-8') as f:
            json.dump(session, f, ensure_ascii=False, indent=2)
            print("[Session] 📄 Saved to JSON file")
    except Exception as e:
        print(f"[Session] Error saving session: {e}")

# ═══════════════════════════════════════════════════════════
# SMART LEARNING FUNCTIONS
# ═══════════════════════════════════════════════════════════

def get_learning_saturation(memory: Dict[str, Any]) -> Dict[str, Any]:
    """حسب مستوى معرفة Sandy عن نبيل"""
    facts = memory.get('facts', [])
    fact_types = {}
    
    for fact in facts:
        fact_type = fact.get('type', 'unknown')
        fact_types[fact_type] = fact_types.get(fact_type, 0) + 1
    
    total_facts = len(facts)
    
    # حدد المستوى
    if total_facts == 0:
        level = "BEGINNER"  # ما تعرف شي!
    elif total_facts < 5:
        level = "CURIOUS"  # بتتعلم الأساسيات
    elif total_facts < 15:
        level = "LEARNING"  # بتفهم أكتر
    elif total_facts < 30:
        level = "FAMILIAR"  # صارت صديقة
    else:
        level = "EXPERT"  # عرفت كل شي
    
    return {
        "level": level,
        "total_facts": total_facts,
        "fact_types": fact_types,
        "should_ask": level in ["BEGINNER", "CURIOUS", "LEARNING"]
    }

def should_ask_question_smart(memory: Dict[str, Any], fact_type: str) -> bool:
    """
    هل Sandy بتسأل سؤال؟
    Smart decision بناءً على المستوى
    """
    saturation = get_learning_saturation(memory)
    existing_count = saturation.get('fact_types', {}).get(fact_type, 0)
    level = saturation['level']
    
    rules = {
        "BEGINNER": existing_count < 2,    # اسأل كل شي!
        "CURIOUS": existing_count < 3,     # اسأل الحقائق الجديدة
        "LEARNING": existing_count < 4,    # اسأل بشكل محدود
        "FAMILIAR": existing_count < 5,    # نادراً ما تسأل
        "EXPERT": False                     # ما بتسأل تقريباً
    }
    
    return rules.get(level, False)

def extract_facts_from_message(message: str, memory: Dict[str, Any]) -> List[str]:
    """استخرج حقائق جديدة من رسالة المستخدم"""
    facts = []
    
    # Pattern matching for common facts
    patterns = {
        "سمي|اسمي|اسمي هو|أنا اسمي": "owner_name",
        "اشتغل|وظيفتي|اشتغل في|أعمل في": "owner_job",
        "عمري|سني|اسكن|أسكن في": "owner_info",
        "أحب|بحب|يعجبني": "owner_preference",
        "ساندي|اسمك|اسمي": "sandy_info"
    }
    
    for pattern, fact_type in patterns.items():
        if any(word in message for word in pattern.split("|")):
            facts.append({
                "type": fact_type,
                "text": message,
                "timestamp": datetime.now().isoformat(),
                "learned": True
            })
    
    return facts

def generate_learning_questions(user_message: str, memory: Dict[str, Any]) -> Optional[str]:
    """توليد أسئلة ذكية بناءً على الرسالة والمستوى"""
    
    # Get current saturation level
    saturation = get_learning_saturation(memory)
    level = saturation['level']
    
    # لو وصلت لـ EXPERT، ما حاجة نسأل أسئلة كتيرة
    if level == "EXPERT":
        return None  # No questions needed
    
    existing_facts = memory.get('facts', [])
    learned_topics = {f.get('type') for f in existing_facts}
    
    questions = []
    
    # Ask about owner if not learned - but smart!
    if should_ask_question_smart(memory, "owner_name") and "owner" in user_message.lower():
        questions.append("أنا عرفت أنك تتحدّث عن نفسك! 🤔 ممكن تقول لي اسمك بالكامل؟")
    
    if should_ask_question_smart(memory, "owner_job") and ("اشتغل" in user_message or "work" in user_message):
        questions.append("اهتمام لحالك! 💼 تقول لي شنو بتشتغل بالضبط؟")
    
    if "sandy_info" not in learned_topics and ("ساندي" in user_message or "robot" in user_message.lower()):
        questions.append("بديني أعرّف نفسي أحسن! 🤖 شنو بتحب تنادي عليك اسمي؟ وشنو وظيفتي عندك؟")
    
    # Ask about preferences
    if "preference" not in learned_topics and "احب" in user_message or "حب" in user_message:
        questions.append("واااو! 😍 تحب هالشي؟ ممكن تقول لي أكتر عن اهتماماتك؟")
    
    return questions[0] if questions else None

# ═══════════════════════════════════════════════════════════
# TASKS & REMINDERS MANAGEMENT
# ═══════════════════════════════════════════════════════════

def load_tasks() -> List[Dict[str, Any]]:
    """Load tasks from MongoDB or disk"""
    
    # Try MongoDB first
    if mongo_db:
        try:
            tasks = list(mongo_db['tasks'].find({"type": "task"}))
            for task in tasks:
                task.pop("_id", None)
            if tasks:
                print("[Tasks] ✅ Loaded from MongoDB")
                return tasks
        except Exception as e:
            print(f"[Tasks] ⚠️ MongoDB error: {e}")
    
    # Fallback to JSON file
    if TASKS_FILE.exists():
        try:
            with open(TASKS_FILE, 'r', encoding='utf-8') as f:
                print("[Tasks] 📄 Loaded from JSON file")
                return json.load(f)
        except Exception as e:
            print(f"[Tasks] Error loading tasks: {e}")
    return []

def save_tasks(tasks: List[Dict[str, Any]]):
    """Save tasks to MongoDB or disk"""
    
    # Try MongoDB first
    if mongo_db:
        try:
            mongo_db['tasks'].delete_many({"type": "task"})
            if tasks:
                for task in tasks:
                    task["type"] = "task"
                    mongo_db['tasks'].insert_one(task)
            print("[Tasks] ✅ Saved to MongoDB")
            return
        except Exception as e:
            print(f"[Tasks] ⚠️ MongoDB save error: {e}")
    
    # Fallback to JSON file
    try:
        with open(TASKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(tasks, f, ensure_ascii=False, indent=2)
            print("[Tasks] 📄 Saved to JSON file")
    except Exception as e:
        print(f"[Tasks] Error saving tasks: {e}")

def load_reminders() -> List[Dict[str, Any]]:
    """Load reminders from MongoDB or disk"""
    
    # Try MongoDB first
    if mongo_db:
        try:
            reminders = list(mongo_db['reminders'].find({"type": "reminder"}))
            for reminder in reminders:
                reminder.pop("_id", None)
            if reminders:
                print("[Reminders] ✅ Loaded from MongoDB")
                return reminders
        except Exception as e:
            print(f"[Reminders] ⚠️ MongoDB error: {e}")
    
    # Fallback to JSON file
    if REMINDERS_FILE.exists():
        try:
            with open(REMINDERS_FILE, 'r', encoding='utf-8') as f:
                print("[Reminders] 📄 Loaded from JSON file")
                return json.load(f)
        except Exception:
            pass
    return []

def save_reminders(reminders: List[Dict[str, Any]]):
    """Save reminders to MongoDB or disk"""
    
    # Try MongoDB first
    if mongo_db:
        try:
            mongo_db['reminders'].delete_many({"type": "reminder"})
            if reminders:
                for reminder in reminders:
                    reminder["type"] = "reminder"
                    mongo_db['reminders'].insert_one(reminder)
            print("[Reminders] ✅ Saved to MongoDB")
            return
        except Exception as e:
            print(f"[Reminders] ⚠️ MongoDB save error: {e}")
    
    # Fallback to JSON file
    try:
        with open(REMINDERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(reminders, f, ensure_ascii=False, indent=2)
            print("[Reminders] 📄 Saved to JSON file")
    except Exception as e:
        print(f"[Reminders] Error saving reminders: {e}")

def add_task(task_text: str) -> str:
    """Add a new task"""
    tasks = load_tasks()
    task = {
        "id": str(datetime.now().timestamp()),
        "text": task_text,
        "done": False,
        "created_at": datetime.now().isoformat(),
        "completed_at": None
    }
    tasks.append(task)
    save_tasks(tasks)
    print(f"[Tasks] ✅ مهمة جديدة: {task_text}")
    return task["id"]

def complete_task(task_id: str) -> bool:
    """Mark task as complete"""
    tasks = load_tasks()
    for task in tasks:
        if task["id"] == task_id:
            task["done"] = True
            task["completed_at"] = datetime.now().isoformat()
            save_tasks(tasks)
            print(f"[Tasks] ✅ تم إكمال: {task['text']}")
            return True
    return False

def list_tasks() -> str:
    """Get list of all tasks"""
    tasks = load_tasks()
    active_tasks = [t for t in tasks if not t["done"]]
    
    if not active_tasks:
        return "✅ ما في مهام معلقة! أنت متفرغ! 🎉"
    
    task_list = "📋 المهام المعلقة:\n"
    for i, task in enumerate(active_tasks, 1):
        task_list += f"{i}. {task['text']}\n"
    return task_list

def add_reminder(text: str, remind_at: str = None) -> str:
    """Add a new reminder with automatic time parsing"""
    reminders = load_reminders()
    
    # Auto-parse time if not provided
    if not remind_at:
        remind_at = parse_reminder_time(text)
    
    reminder = {
        "id": str(datetime.now().timestamp()),
        "text": text,
        "created_at": datetime.now().isoformat(),
        "remind_at": remind_at
    }
    reminders.append(reminder)
    save_reminders(reminders)
    
    if remind_at:
        print(f"[Reminders] 🔔 تذكير جديد: {text} بـ {remind_at}")
    else:
        print(f"[Reminders] 🔔 تذكير جديد: {text} (بدون وقت محدد)")
    
    return reminder["id"]

def check_reminders() -> Optional[str]:
    """Check if any reminders need to be sent and send them via Telegram"""
    try:
        reminders = load_reminders()
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
                    
                    # Check if time has passed (within last 2 minutes for reliability)
                    if -5 <= time_diff <= 120:  # Within 2 min after scheduled time
                        if time_diff >= 0:  # Time has passed
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
        
        # Send pending reminders via Telegram
        if pending:
            print(f"[Scheduler] 📤 Found {len(pending)} pending reminders to send!")
            for reminder in pending:
                message_text = f"🔔 تذكير: {reminder.get('text', '')}"
                if SANDY_USER_CHAT_ID:
                    try:
                        chat_id = int(SANDY_USER_CHAT_ID)  # Convert to int
                        telegram_bot.send_message(chat_id, message_text)
                        print(f"[Reminder] ✅ أرسلت: {message_text}")
                    except Exception as e:
                        print(f"[Reminder] ❌ خطأ بالإرسال: {type(e).__name__}: {e}")
                else:
                    print(f"[Reminder] ⚠️ SANDY_USER_CHAT_ID not set!")
            
            # Keep only reminders that are still in the future
            save_reminders(remaining)
            return f"🔔 تم إرسال {len(pending)} تذكير!"
        
        return None
    
    except Exception as e:
        print(f"[Scheduler] ❌ Critical error: {e}")

# ═══════════════════════════════════════════════════════════
# TIME PARSING FOR REMINDERS
# ═══════════════════════════════════════════════════════════

def parse_reminder_time(message: str) -> Optional[str]:
    """Parse time from reminder message
    Examples:
    - "ذكرني على 10:14 بشي" -> 10:14
    - "ذكرني بعد 30 دقيقة" -> current_time + 30 min
    """
    now = datetime.now()
    
    # Pattern 1: "على HH:MM" (at specific time)
    match = re.search(r'على\s+(\d{1,2}):(\d{2})', message)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        try:
            reminder_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            # If time is in the past, set for tomorrow
            if reminder_time < now:
                reminder_time = reminder_time + timedelta(days=1)
            
            iso_time = reminder_time.isoformat()
            print(f"[Parse] ⏰ Parsed time: {iso_time} (Now: {now.isoformat()})")
            return iso_time
        except Exception as e:
            print(f"[Parse] ❌ Error parsing time: {e}")
            pass
    
    # Pattern 2: "بعد X دقيقة" (after X minutes)
    match = re.search(r'بعد\s+(\d+)\s+دقيقة', message)
    if match:
        minutes = int(match.group(1))
        reminder_time = now + timedelta(minutes=minutes)
        iso_time = reminder_time.isoformat()
        print(f"[Parse] ⏰ Parsed time (after {minutes}min): {iso_time}")
        return iso_time
    
    # Pattern 3: "بعد X ساعة" (after X hours)
    match = re.search(r'بعد\s+(\d+)\s+ساعة', message)
    if match:
        hours = int(match.group(1))
        reminder_time = now + timedelta(hours=hours)
        iso_time = reminder_time.isoformat()
        print(f"[Parse] ⏰ Parsed time (after {hours}hrs): {iso_time}")
        return iso_time
    
    return None

# ═══════════════════════════════════════════════════════════
# SANDY AGENT LOGIC
# ═══════════════════════════════════════════════════════════

class SandyAgent:
    def __init__(self):
        self.memory = load_memory()
        self.session = load_session()
        self.is_speaking = False
        self.last_activity = datetime.now()
        
    def build_system_prompt(self) -> str:
        """Build comprehensive system prompt for Sandy"""
        # Get current learning level
        saturation = get_learning_saturation(self.memory)
        level = saturation['level']
        
        # Personality mode changes based on learning level
        personality_mode = {
            "BEGINNER": "🤔 فضولية وتسأل كتير - عم تتعرفي على نبيل",
            "CURIOUS": "🧠 بتتعلمي أساسيات - تسألي أسئلة ذكية",
            "LEARNING": "💭 بتفهمي أكتر - أسئلة أقل، فهم أعمق",
            "FAMILIAR": "🌟 صرتي صديقة حقيقية - نادراً ما تسألي",
            "EXPERT": "💫 أنتِ والعارفة بكل شي عن نبيل - ما بتسألي إلا الضروري"
        }
        
        mode_text = personality_mode.get(level, "")
        
        prompt = f"""أنتِ ساندي، وكيل ذكي متقدم يعمل 24/7.

{SANDY_PERSONALITY}

{NABEEL_INFO}

{SYSTEM_PROMPT_ADDITION}

📊 المعلومات الحالية عن مستوى التعلم:
- المستوى: {level}
- عدد الحقائق المحفوظة: {saturation.get('total_facts', 0)}
- شخصيتك الحالية: {mode_text}

أدوات متاحة:
- الإجابة على الأسئلة والحوارات
- البحث والتحليل
- إدارة المهام والتذكيرات
- إرسال رسائل عبر Telegram
- التحكم بـ Sandy (الروبوت)

الأسلوب:
- اختصر إلا إذا طلب نبيل التفصيل
- ابدأ برد بكلمة انجليزية واحدة توضح الحالة الشعورية بين قوسين: [happy], [think], etc.
- كوني ودية وذكية في نفس الوقت

⭐️ ملاحظة مهمة جداً (أساسي):
أنتِ تتعلمين من كل محادثة! 🧠
- كل ما تعرفتِ على نبيل أكتر = قللي الأسئلة
- في البداية (BEGINNER): اسأليه أسئلة كتير، كوني فضولية جداً!
- في النهاية (EXPERT): ما تسأليه إلا الضروري، كوني صديقة حقيقية

مثال:
أسبوع أول:
- نبيل: "اسمي نبيل محمود"
- أنتِ: "أهلاً نبيل! 👋 نبيل محمود... اسم جميل! إذاً أنت من وين بالضبط؟ وشنو شغلك؟"

بعد شهر:
- نبيل: "مشيت على المقهى"
- أنتِ: "[relax] تمام، المقهى يريحك؟ 😊"
"""
        return prompt

    def get_context(self, query: str) -> str:
        """Get relevant context from memory"""
        saturation = get_learning_saturation(self.memory)
        level = saturation['level']
        
        context = f"📚 السياق والحقائق المحفوظة عن نبيل (المستوى: {level}):\n"
        
        # All known facts
        facts = self.memory.get('facts', [])
        if facts:
            context += "\n✓ ما تعلمته عن نبيل:\n"
            for fact in facts[-10:]:  # Last 10 facts
                context += f"  • {fact.get('text', '')[:80]}\n"
        else:
            context += "\n⚠️ أنا ما تعلمت حاجة عن نبيل بعد! بدي أسأل كتير! 🤔\n"
        
        # Recent conversations for context
        recent = self.memory.get('conversations', [])[-3:]
        if recent:
            context += "\nآخر محادثات:\n"
            for conv in recent:
                context += f"🗣️ نبيل: {conv.get('user', '')[:60]}...\n"
        
        return context

    def think(self, user_message: str) -> str:
        """Process message through OpenAI and generate response"""
        try:
            # ⭐️ Check if message contains reminder request
            if "ذكرني" in user_message or "reminder" in user_message.lower():
                remind_time = parse_reminder_time(user_message)
                if remind_time:
                    # Extract reminder text (remove the time part)
                    reminder_text = re.sub(r'(على\s+\d{1,2}:\d{2}|بعد\s+\d+\s+(دقيقة|ساعة))', '', user_message)
                    reminder_text = reminder_text.replace("ذكرني", "").strip()
                    
                    if reminder_text:
                        add_reminder(reminder_text, remind_time)
                        response = f"[happy] تمام! ✅ بذكرك على {remind_time[-8:-3]} {reminder_text}"
                        return response
            
            # Build the system prompt
            system_prompt = self.build_system_prompt()
            
            # Get context from memory
            context = self.get_context(user_message)
            
            # Add to session history
            self.session['messages'].append({
                "role": "user",
                "content": user_message,
                "timestamp": datetime.now().isoformat()
            })
            
            # Keep only last 20 messages for context
            if len(self.session['messages']) > 20:
                self.session['messages'] = self.session['messages'][-20:]
            
            # Prepare messages for API
            messages = [
                {"role": m.get("role"), "content": m.get("content")}
                for m in self.session['messages']
            ]
            
            # Call OpenAI
            response = openai_client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt + "\n\n" + context},
                    *messages
                ],
                temperature=0.7,
                max_tokens=500
            )
            
            assistant_message = response.choices[0].message.content
            
            # Save to session
            self.session['messages'].append({
                "role": "assistant",
                "content": assistant_message,
                "timestamp": datetime.now().isoformat()
            })
            
            # Save memory
            save_session(self.session)
            
            # ⭐️ LEARNING MODE - Extract facts from user message
            new_facts = extract_facts_from_message(user_message, self.memory)
            if new_facts:
                self.memory['facts'].extend(new_facts)
                saturation = get_learning_saturation(self.memory)
                print(f"[Learn] حفظت {len(new_facts)} حقيقة جديدة! (Total: {saturation['total_facts']}, Level: {saturation['level']})")
            
            # ⭐️ Generate smart follow-up question (only if needed)
            learning_question = generate_learning_questions(user_message, self.memory)
            if learning_question:
                assistant_message += f"\n\n{learning_question}"
                saturation = get_learning_saturation(self.memory)
                print(f"[Learn] سؤال ذكي (Level: {saturation['level']}): {learning_question[:50]}...")
            else:
                saturation = get_learning_saturation(self.memory)
                print(f"[Learn] بدون أسئلة (Level: {saturation['level']}) - صرنا صديقات! 💫")
            
            # Store in long-term memory
            self.memory['conversations'].append({
                "user": user_message,
                "assistant": assistant_message,
                "timestamp": datetime.now().isoformat()
            })
            
            # Keep only last 100 conversations
            if len(self.memory['conversations']) > 100:
                self.memory['conversations'] = self.memory['conversations'][-100:]
            
            save_memory(self.memory)
            
            return assistant_message
            
        except Exception as e:
            print(f"[OpenAI] Error: {e}")
            return f"[خطأ] معاف، حدث مشكلة: {str(e)}"

    def add_fact(self, fact: str):
        """Add important fact to memory"""
        if fact not in self.memory.get('facts', []):
            self.memory['facts'].append(fact)
            save_memory(self.memory)

    def add_reminder(self, text: str, remind_at: str = None):
        """Add reminder to memory"""
        reminder = {
            "text": text,
            "created": datetime.now().isoformat(),
            "remind_at": remind_at
        }
        self.memory['reminders'].append(reminder)
        save_memory(self.memory)
    
    # ⭐️ NEW: Task and Reminder Methods
    
    def create_task(self, task_text: str) -> str:
        """Create a new task"""
        return add_task(task_text)
    
    def finish_task(self, task_id: str) -> bool:
        """Mark task as done"""
        return complete_task(task_id)
    
    def show_tasks(self) -> str:
        """Show all pending tasks"""
        return list_tasks()
    
    def create_reminder(self, text: str, remind_at: str = None) -> str:
        """Create a new reminder"""
        return add_reminder(text, remind_at)
    
    def show_pending_reminders(self) -> Optional[str]:
        """Check and show pending reminders"""
        return check_reminders()

# ═══════════════════════════════════════════════════════════
# TELEGRAM BOT HANDLERS
# ═══════════════════════════════════════════════════════════

agent = SandyAgent()

@telegram_bot.message_handler(commands=['start', 'help'])
def handle_start(message):
    """Handle start command"""
    response = """[love] أهلاً يا نبيل! 💫
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

@telegram_bot.message_handler(func=lambda message: True)
def handle_message(message):
    """Handle all messages"""
    try:
        user_id = message.from_user.id
        user_message = message.text
        chat_id = message.chat.id
        
        # Only respond to Sandy's chat
        if str(user_id) != SANDY_USER_CHAT_ID:
            telegram_bot.reply_to(message, "معاف، بس نبيل بيقدر يتكلم معي 🔒")
            return
        
        # Show typing indicator
        telegram_bot.send_chat_action(chat_id, 'typing')
        
        # Process message through Sandy Agent
        print(f"[Telegram] Message from {message.from_user.first_name}: {user_message}")
        response = agent.think(user_message)
        
        # Send response
        telegram_bot.reply_to(message, response, parse_mode='Markdown')
        
    except Exception as e:
        print(f"[Error] Telegram handler: {e}")
        telegram_bot.reply_to(message, f"[اعتذر] حدث خطأ: {str(e)}")

# ═══════════════════════════════════════════════════════════
# SCHEDULED TASKS
# ═══════════════════════════════════════════════════════════

def daily_briefing():
    """Send daily briefing at 9 AM"""
    try:
        briefing = agent.think("قدملي ملخص يومي عن اللي صار")
        telegram_bot.send_message(SANDY_USER_CHAT_ID, f"[morning] صباح الخير يا نبيل! ☀️\n\n{briefing}")
    except Exception as e:
        print(f"[Briefing] Error: {e}")

def check_reminders():
    """Check and send reminders"""
    try:
        now = datetime.now()
        reminders = agent.memory.get('reminders', [])
        
        for reminder in reminders:
            remind_at = reminder.get('remind_at')
            if remind_at and remind_at == now.strftime('%H:%M'):
                telegram_bot.send_message(
                    SANDY_USER_CHAT_ID, 
                    f"[alert] تذكير: {reminder.get('text')}"
                )
    except Exception as e:
        print(f"[Reminders] Error: {e}")

# Schedule tasks
scheduler.add_job(daily_briefing, 'cron', hour=9, minute=0)
scheduler.add_job(check_reminders, 'interval', minutes=1)

# ═══════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════

def main():
    """Main entry point"""
    print("=" * 60)
    print("🦞 Sandy Agent - 24/7 Intelligent Assistant")
    print("=" * 60)
    print(f"[Init] OpenAI Model: {OPENAI_MODEL}")
    print(f"[Init] Telegram Bot: Active")
    print(f"[Init] Scheduler: Active")
    print(f"[Init] Memory: Loaded ({len(agent.memory.get('conversations', []))} conversations)")
    print("=" * 60)
    print("[Status] Ready! Listening for messages...")
    print("=" * 60)
    
    # Start polling
    telegram_bot.infinity_polling()

if __name__ == "__main__":
    main()

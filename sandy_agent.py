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
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from openai import OpenAI
import telebot
from apscheduler.schedulers.background import BackgroundScheduler

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

# OpenAI Configuration (read from environment variables)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o").strip()

# Telegram Configuration (read from environment variables)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
SANDY_USER_CHAT_ID = os.getenv("SANDY_USER_CHAT_ID", "").strip()

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

# Memory Configuration
MEMORY_FILE = BASE_DIR / "sandy_agent_memory.json"
SESSION_FILE = BASE_DIR / "sandy_session_memory.json"

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
# MEMORY MANAGEMENT
# ═══════════════════════════════════════════════════════════

def load_memory() -> Dict[str, Any]:
    """Load persistent memory from disk"""
    if MEMORY_FILE.exists():
        try:
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[Memory] Error loading memory: {e}")
    return {
        "conversations": [],
        "facts": [],
        "reminders": [],
        "tasks": []
    }

def save_memory(memory: Dict[str, Any]):
    """Save memory to disk"""
    try:
        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(memory, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Memory] Error saving memory: {e}")

def load_session() -> Dict[str, Any]:
    """Load current session memory"""
    if SESSION_FILE.exists():
        try:
            with open(SESSION_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {"messages": []}

def save_session(session: Dict[str, Any]):
    """Save session memory"""
    try:
        with open(SESSION_FILE, 'w', encoding='utf-8') as f:
            json.dump(session, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Session] Error saving session: {e}")

# ═══════════════════════════════════════════════════════════
# SMART LEARNING FUNCTIONS
# ═══════════════════════════════════════════════════════════

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
    """توليد أسئلة ذكية بناءً على الرسالة"""
    
    # Check if we're missing owner info
    existing_facts = memory.get('facts', [])
    learned_topics = {f.get('type') for f in existing_facts}
    
    questions = []
    
    # Ask about owner if not learned
    if "owner_name" not in learned_topics and "owner" in user_message.lower():
        questions.append("أنا عرفت أنك تتحدّث عن نفسك! 🤔 ممكن تقول لي اسمك بالكامل؟")
    
    if "owner_job" not in learned_topics and ("اشتغل" in user_message or "work" in user_message):
        questions.append("اهتمام لحالك! 💼 تقول لي شنو بتشتغل بالضبط؟")
    
    if "sandy_info" not in learned_topics and ("ساندي" in user_message or "robot" in user_message.lower()):
        questions.append("بديني أعرّف نفسي أحسن! 🤖 شنو بتحب تنادي عليك اسمي؟ وشنو وظيفتي عندك؟")
    
    # Ask about preferences
    if "preference" not in learned_topics and "احب" in user_message or "حب" in user_message:
        questions.append("واااو! 😍 تحب هالشي؟ ممكن تقول لي أكتر عن اهتماماتك؟")
    
    return questions[0] if questions else None

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
        prompt = f"""أنتِ ساندي، وكيل ذكي متقدم يعمل 24/7.

{SANDY_PERSONALITY}

{NABEEL_INFO}

{SYSTEM_PROMPT_ADDITION}

المعلومات الحالية:
- الوقت الحالي: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- عدد السجلات المحفوظة: {len(self.memory.get('conversations', []))}

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
- إذا قال نبيل معلومة جديدة عنه أو عن نفسه = اسأليه أسئلة متابعة لتعليق المعلومة
- إذا مافهمتِ شيء = اسأليه! ولا تتردّدي!
- الأسئلة الذكية = أفضل من الإجابات السريعة
- كوني فضولية وتعلمي عن اهتماماته وأسراره وشخصيته
- كل معلومة تتعلميها = تحفظيها في رأسك براح أبدياً

مثال:
- نبيل: "اسمي نبيل محمود"
- أنتِ: "أهلاً نبيل! 👋 نبيل محمود... اسم جميل! إذاً أنت من وين بالضبط؟ وشنو الشيء اللي يخليك سعيد؟"
"""
        return prompt

    def get_context(self, query: str) -> str:
        """Get relevant context from memory"""
        context = "السياق والحقائق المحفوظة عن نبيل:\n"
        
        # All known facts
        facts = self.memory.get('facts', [])
        if facts:
            context += "\nما تعلمته عن نبيل:\n"
            for fact in facts[-10:]:  # Last 10 facts
                context += f"✓ {fact.get('text', '')[:80]}\n"
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
                print(f"[Learn] حفظت {len(new_facts)} حقيقة جديدة!")
            
            # ⭐️ Generate smart follow-up question
            learning_question = generate_learning_questions(user_message, self.memory)
            if learning_question:
                assistant_message += f"\n\n{learning_question}"
                print(f"[Learn] سؤال ذكي: {learning_question[:50]}...")
            
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

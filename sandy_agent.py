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
    raise RuntimeError("OPENAI_API_KEY missing in .env")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN missing in .env")

if not SANDY_USER_CHAT_ID:
    raise RuntimeError("SANDY_USER_CHAT_ID missing in .env")

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
"""
        return prompt

    def get_context(self, query: str) -> str:
        """Get relevant context from memory"""
        context = "السياق المحفوظ:\n"
        
        # Recent conversations
        recent = self.memory.get('conversations', [])[-5:]
        if recent:
            context += "\nآخر محادثات:\n"
            for conv in recent:
                context += f"- {conv.get('text', '')[:100]}\n"
        
        # Important facts
        facts = self.memory.get('facts', [])[:3]
        if facts:
            context += "\nحقائق مهمة:\n"
            for fact in facts:
                context += f"- {fact}\n"
        
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

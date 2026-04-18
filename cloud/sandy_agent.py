#!/usr/bin/env python3
"""
Sandy Agent - 24/7 Intelligent Assistant on Railway
Inspired by OpenClaw, powered by OpenAI GPT-4o
"""

import os
import json
from pydoc import text
import time
import asyncio
import threading
import re
import io
import base64
import tempfile
import requests
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from openai import OpenAI, AzureOpenAI
import telebot
from apscheduler.schedulers.background import BackgroundScheduler
import certifi
from app.features.research import (
    detect_research_type,
    extract_requested_result_count,
    detect_research_preference,
    is_research_request,
    is_research_followup_request,
    deduplicate_research_results,
    summarize_research_results,
    build_winner_summary,
    filter_research_results,
    rank_research_results,
    is_official_source_url,
    extract_structured_page_data,
    normalize_education_page_data,
    run_research_pipeline,
)
from app.features.tasks import (
    add_task,
    complete_task,
    list_tasks,
)
from app.features.reminders import (
    add_reminder,
    check_reminders,
    plan_reminder_with_ai,
)
from cloud.app.utils import text

from app.agent.memory import (
    load_memory,
    save_memory,
    load_session,
    save_session,
)
from cloud.app.agent.learning import (
    get_learning_saturation,
    extract_facts_from_message,
    generate_learning_questions,
)
from cloud.app.agent.mood import (
    update_sandy_state,
    get_sandy_reply,
)
from app.agent.learning import (
    get_learning_saturation,
    extract_facts_from_message,
    generate_learning_questions,
)
from app.agent.mood import (
    update_sandy_state,
    get_sandy_reply,
)
from app.integrations.openai_client import make_chat_completion_fn
from app.integrations.mongodb_store import init_mongo_connection
from app.integrations.exa_client import search_exa, get_exa_page_content
from app.features.images import (
    is_image_generation_request,
    extract_image_prompt,
)
from app.integrations.telegram_api import download_telegram_file_bytes
from app.integrations.azure_speech import (
    transcribe_audio_with_azure,
)
from app.features.vision import (
    analyze_image_with_azure,
    generate_image_with_azure,
)
from app.features.voice import send_text_and_voice_reply
from app.api.telegram_handlers import (
    _is_duplicate_telegram_message,
    _is_authorized_user,
    register_basic_telegram_handlers,
)
from app.api.telegram_runtime import (
    prepare_telegram_polling,
    set_telegram_webhook,
)
from app.api.webhook import create_telegram_webhook_app

# Try to import Chroma for smart memory
try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    print("[Warning] Chroma DB not available, using JSON memory only")

# Try to import Azure Speech SDK for text-to-speech
try:
    import azure.cognitiveservices.speech as speechsdk
    AZURE_SPEECH_AVAILABLE = True
except ImportError:
    speechsdk = None
    AZURE_SPEECH_AVAILABLE = False
    print("[Warning] Azure Speech SDK not available. To enable: pip install azure-cognitiveservices-speech")


# Try to import Google Cloud Text-to-Speech
try:
    from google.cloud import texttospeech
    GOOGLE_TTS_AVAILABLE = True
except ImportError:
    texttospeech = None
    GOOGLE_TTS_AVAILABLE = False
    print("[Warning] Google Cloud Text-to-Speech not available. To enable: pip install google-cloud-texttospeech")


GOOGLE_TTS_VOICE = os.getenv("GOOGLE_TTS_VOICE", "ar-XA-Chirp3-HD-Sulafat").strip()
GOOGLE_TTS_LANGUAGE_CODE = os.getenv("GOOGLE_TTS_LANGUAGE_CODE", "ar-XA").strip()
MOOD_TTS_VOICES = {
    "happy": os.getenv("GOOGLE_TTS_VOICE_HAPPY", "ar-XA-Chirp3-HD-Sulafat").strip(),
    "sad": os.getenv("GOOGLE_TTS_VOICE_SAD", "ar-XA-Chirp3-HD-Zephyr").strip(),
    "angry": os.getenv("GOOGLE_TTS_VOICE_ANGRY", "ar-XA-Chirp3-HD-Despina").strip(),
    "bored": os.getenv("GOOGLE_TTS_VOICE_BORED", "ar-XA-Chirp3-HD-Aoede").strip(),
    "neutral": os.getenv("GOOGLE_TTS_VOICE_NEUTRAL", "ar-XA-Chirp3-HD-Sulafat").strip(),
    "excited": os.getenv("GOOGLE_TTS_VOICE_EXCITED", "ar-XA-Chirp3-HD-Vindemiatrix").strip(),
    "romantic": os.getenv("GOOGLE_TTS_VOICE_ROMANTIC", "ar-XA-Chirp3-HD-Sulafat").strip(),
    "shy": os.getenv("GOOGLE_TTS_VOICE_SHY", "ar-XA-Chirp3-HD-Zephyr").strip(),
    "tired": os.getenv("GOOGLE_TTS_VOICE_TIRED", "ar-XA-Chirp3-HD-Aoede").strip(),
    "serious": os.getenv("GOOGLE_TTS_VOICE_SERIOUS", "ar-XA-Chirp3-HD-Despina").strip(),
}

# ═══════════════════════════════════════════════════════════
# CONFIGURATION & ENV SETUP

# إذا كان GOOGLE_CREDENTIALS_JSON موجود، اكتب محتواه إلى sandy-gcloud-key.json واستخدمه تلقائياً
if os.getenv("GOOGLE_CREDENTIALS_JSON"):
    with open("sandy-gcloud-key.json", "w") as f:
        f.write(os.getenv("GOOGLE_CREDENTIALS_JSON"))
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.abspath("sandy-gcloud-key.json")
# ═══════════════════════════════════════════════════════════

BASE_DIR = Path(__file__).resolve().parent

# Try to load .env locally (for development)
try:
    # أولاً حمّل من جذر المشروع (الأولوية للجذر)
    load_dotenv(BASE_DIR.parent / ".env")
    # ثم حمّل من مجلد cloud/ إذا وجد (يسمح بالكتابة فوق)
    load_dotenv(BASE_DIR / ".env")
except Exception:
    pass

# تحديد وضع التشغيل بناءً على متغير صريح
APP_ENV = os.getenv("APP_ENV", "prod").lower()  # "local" أو "prod"
RUN_MODE = os.getenv("RUN_MODE", "webhook").lower()  # "polling" أو "webhook"

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

# Azure OpenAI Configuration
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview").strip()
AZURE_OPENAI_CHAT_DEPLOYMENT = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "").strip()
AZURE_OPENAI_VISION_DEPLOYMENT = os.getenv("AZURE_OPENAI_VISION_DEPLOYMENT", "").strip()
AZURE_OPENAI_STT_DEPLOYMENT = os.getenv("AZURE_OPENAI_STT_DEPLOYMENT", "").strip()
AZURE_OPENAI_IMAGE_DEPLOYMENT = os.getenv("AZURE_OPENAI_IMAGE_DEPLOYMENT", "").strip()

# EXA Configuration
EXA_API_KEY = os.getenv("EXA_API_KEY", "").strip()
WEB_RESEARCH_PROVIDER = os.getenv("WEB_RESEARCH_PROVIDER", "exa").strip()
WEB_RESEARCH_MAX_CANDIDATES = int(os.getenv("WEB_RESEARCH_MAX_CANDIDATES", "30").strip())

# Azure Speech Configuration
AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY", "").strip()
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION", "").strip()
AZURE_SPEECH_VOICE = os.getenv("AZURE_SPEECH_VOICE", "ar-EG-SalmaNeural").strip()

# Telegram Configuration (read from environment variables)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
SANDY_USER_CHAT_ID = os.getenv("SANDY_USER_CHAT_ID", "").strip()

# MongoDB Configuration
MONGODB_URI = os.getenv("MONGODB_URI", "").strip()
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "sany-db").strip()
mongo_client, mongo_db = init_mongo_connection(
    MONGODB_URI,
    MONGODB_DB_NAME,
)



# DEBUG: Print what we're reading
print("[DEBUG STARTUP] Environment Variables:")
print(f"  OPENAI_API_KEY: {'SET' if OPENAI_API_KEY else 'EMPTY'} (len={len(OPENAI_API_KEY)})")
print(f"  TELEGRAM_BOT_TOKEN: {'SET' if TELEGRAM_BOT_TOKEN else 'EMPTY'} (len={len(TELEGRAM_BOT_TOKEN)})")
print(f"  SANDY_USER_CHAT_ID: {'SET' if SANDY_USER_CHAT_ID else 'EMPTY'} ({SANDY_USER_CHAT_ID})")

# Sandy Configuration
try:
    from sandy_config import SANDY_PERSONALITY, SYSTEM_PROMPT_ADDITION
except Exception:
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
azure_openai_client = None
if AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY:
    try:
        azure_openai_client = AzureOpenAI(
            api_key=AZURE_OPENAI_API_KEY,
            api_version=AZURE_OPENAI_API_VERSION,
            azure_endpoint=AZURE_OPENAI_ENDPOINT
        )
        print("[Azure OpenAI] ✅ Connected")
    except Exception as e:
        print(f"[Azure OpenAI] ⚠️ Failed to initialize: {e}")

create_chat_completion = make_chat_completion_fn(
    openai_client=openai_client,
    azure_openai_client=azure_openai_client,
    openai_model=OPENAI_MODEL,
    azure_chat_deployment=AZURE_OPENAI_CHAT_DEPLOYMENT,
)

telegram_bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, threaded=True)
scheduler = BackgroundScheduler(timezone=None)
scheduler.start()

LAST_ASSISTANT_REACTION = None

def _set_last_assistant_reaction(reaction: Optional[str]):
    global LAST_ASSISTANT_REACTION
    LAST_ASSISTANT_REACTION = reaction


# ═══════════════════════════════════════════════════════════
# SANDY AGENT LOGIC
# ═══════════════════════════════════════════════════════════

# كلاس الوكيل الذكي ساندي: فيه كل المنطق الأساسي للذاكرة، المزاج، الردود، المهام والتذكيرات

class SandyAgent:
    def __init__(self):
        self.memory = load_memory(memory_file=MEMORY_FILE, mongo_db=mongo_db)
        self.session = load_session(session_file=SESSION_FILE, mongo_db=mongo_db)
        self.is_speaking = False
        self.last_activity = datetime.now()
        self.last_research_results = []
        self.last_research_type = "general"

    def build_system_prompt(self) -> str:
        """Build comprehensive system prompt for Sandy, including current mood and its reason."""
        saturation = get_learning_saturation(self.memory)
        level = saturation['level']
        personality_mode = {
            "BEGINNER": "🤔 فضولية وتسأل كتير - عم تتعرفي على المستخدم",
            "CURIOUS": "🧠 بتتعلمي أساسيات - تسألي أسئلة ذكية",
            "LEARNING": "💭 بتفهمي أكتر - أسئلة أقل، فهم أعمق",
            "FAMILIAR": "🌟 صرتي صديقة حقيقية - نادراً ما تسألي",
            "EXPERT": "💫 أنتِ والعارفة بكل شي عن المستخدم - ما بتسألي إلا الضروري"
        }
        mode_text = personality_mode.get(level, "")

        state = self.memory.get("sandy_state", {})
        mood = state.get("mood", "happy")
        snapped = state.get("snapped", False)
        mood_reason = ""
        if snapped:
            mood_reason = "(ملل شديد بسبب تكرار نفس الرسالة كثيرًا)"
        elif mood == "angry":
            mood_reason = "(زعلانة لأنك لم تتواصل منذ فترة طويلة)"
        elif mood == "sad":
            mood_reason = "(حزينة لأنك تأخرت في التواصل)"
        elif mood == "bored":
            mood_reason = "(ملل بسبب تكرار نفس الطلب عدة مرات)"
        elif mood == "happy":
            mood_reason = "(مزاج جيد)"

        prompt = f"""أنتِ ساندي، وكيل ذكي متقدم يعمل 24/7.

{SANDY_PERSONALITY}

{SYSTEM_PROMPT_ADDITION}

📊 المعلومات الحالية عن مستوى التعلم:
- المستوى: {level}
- عدد الحقائق المحفوظة: {saturation.get('total_facts', 0)}
- شخصيتك الحالية: {mode_text}

🧠 مزاج ساندي الحالي: {mood} {mood_reason}

تعليمات المزاج:
- يجب أن يكون ردك واقعيًا ويعكس هذا المزاج بوضوح
- إذا كان المزاج angry أو sad أو bored أو snapped، عبري عن السبب في الرد
- لا تكتبي نفس الجملة كل مرة، بل نوعي في التعبير حسب السياق

أدوات متاحة:
- الإجابة على الأسئلة والحوارات
- البحث والتحليل
- إدارة المهام والتذكيرات
- إرسال رسائل عبر Telegram
- التحكم بـ Sandy (الروبوت)

الأسلوب:
- اختصر إلا إذا طلب المستخدم التفصيل
- ابدأ برد بكلمة انجليزية واحدة توضح الحالة الشعورية بين قوسين: [happy], [think], etc.
- كوني ودية وذكية في نفس الوقت
"""
        return prompt

    def get_context(self, query: str) -> str:
        """Get relevant context from memory"""
        saturation = get_learning_saturation(self.memory)
        level = saturation['level']

        context = f"📚 السياق والحقائق المحفوظة عن المستخدم (المستوى: {level}):\n"

        facts = self.memory.get('facts', [])
        if facts:
            context += "\n✓ ما تعلمته عن المستخدم:\n"
            for fact in facts[-10:]:
                context += f"  • {fact.get('text', '')[:80]}\n"
        else:
            context += "\n⚠️ أنا ما تعلمت حاجة عن المستخدم بعد! بدي أسأل كتير! 🤔\n"

        recent = self.memory.get('conversations', [])[-3:]
        if recent:
            context += "\nآخر محادثات:\n"
            for conv in recent:
                context += f"🗣️ المستخدم: {conv.get('user', '')[:60]}...\n"

        return context

    def think(self, user_message: str) -> str:
        """Process message through OpenAI and generate response, with mood/memory logic"""
        try:
            update_sandy_state(
                self.memory,
                user_message,
                create_chat_completion_fn=create_chat_completion,
            )           
            save_memory(self.memory, memory_file=MEMORY_FILE, mongo_db=mongo_db)

            if is_research_followup_request(user_message) and self.last_research_results:
                requested_count = extract_requested_result_count(user_message, default=5)
                preference = detect_research_preference(user_message)
                print(f"[DEBUG] requested_count={requested_count}")
                print(f"[DEBUG] preference={preference}")

                research_results = filter_research_results(self.last_research_results, preference)
                research_results = rank_research_results(research_results, preference)
                print(f"[DEBUG] results_after_filtering={len(research_results)}")

                if research_results:
                    self.last_research_results = research_results

                if preference.get("best_only") or preference.get("cheapest_only"):
                    winner_text = build_winner_summary(research_results, preference)
                    return str(winner_text or "[think] ما قدرت أحدد أفضل خيار من النتائج السابقة.")

                summary_text = summarize_research_results(
                    research_results,
                    requested_count=requested_count
                )
                return str(summary_text or "[think] ما قدرت أرتب النتائج السابقة بشكل واضح.")

            if is_research_request(user_message):
                research_type = detect_research_type(user_message)
                requested_count = extract_requested_result_count(user_message, default=5)
                preference = detect_research_preference(user_message)

                research_results = run_research_pipeline(
                    user_message,
                    research_type=research_type,
                    requested_count=max(requested_count * 2, requested_count),
                    search_exa_fn=search_exa,
                    get_exa_page_content_fn=get_exa_page_content,
                    create_chat_completion_fn=create_chat_completion,
                    exa_api_key=EXA_API_KEY,
                    web_research_max_candidates=WEB_RESEARCH_MAX_CANDIDATES,
                )

                research_results = deduplicate_research_results(research_results)
                research_results = filter_research_results(research_results, preference)
                research_results = rank_research_results(research_results, preference)

                self.last_research_results = research_results
                self.last_research_type = research_type

                if (preference.get("best_only") or preference.get("cheapest_only")) and extract_requested_result_count(user_message, default=5) == 1:
                    requested_count = 1

                if preference.get("best_only") or preference.get("cheapest_only"):
                    winner_text = build_winner_summary(research_results, preference)
                    return str(winner_text or "[think] لقيت نتائج، لكن ما قدرت أحدد الفائز بشكل واضح.")

                if preference.get("no_ielts") and not research_results:
                    return "[think] ما لقيت نتائج مؤكدة من المصادر الحالية تقول بوضوح إن البرنامج لا يطلب IELTS أو TOEFL. إذا بدك، أقدر أوسّع البحث أو أرجع لك البرامج التي شرط اللغة فيها غير واضح."

                summary_text = summarize_research_results(
                    research_results,
                    requested_count=requested_count
                )
                return str(summary_text or "[think] البحث اشتغل، لكن ما قدرت أرتب النتيجة كنص واضح.")

            reminder_plan = plan_reminder_with_ai(
                user_message,
                create_chat_completion_fn=create_chat_completion,
            )
            if reminder_plan and reminder_plan.get("is_reminder"):
                reminder_text = reminder_plan.get("reminder_text", "")
                remind_at = reminder_plan.get("remind_at_iso", "")
                should_create = reminder_plan.get("should_create", False)
                assistant_reply = reminder_plan.get("assistant_reply", "")

                if should_create and reminder_text and remind_at:
                   add_reminder(reminder_text, remind_at, mongo_db=mongo_db, reminders_file=REMINDERS_FILE)
                   return get_sandy_reply(
                        user_message,
                        self.memory,
                        f"[happy] تمام ✅ سجلت التذكير: {reminder_text}"
                    )

                if assistant_reply:
                    return get_sandy_reply(user_message, self.memory, assistant_reply)
                return get_sandy_reply(user_message, self.memory, "[think] فهمت إنك بتحكي عن تذكير، بس بدي تفاصيل أدق شوي حتى أسجله بشكل صحيح.")

            system_prompt = self.build_system_prompt()
            context = self.get_context(user_message)

            self.session['messages'].append({
                "role": "user",
                "content": user_message,
                "timestamp": datetime.now().isoformat()
            })

            if len(self.session['messages']) > 20:
                self.session['messages'] = self.session['messages'][-20:]

            messages = [
                {"role": m.get("role"), "content": m.get("content")}
                for m in self.session['messages']
            ]

            response = create_chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt + "\n\n" + context},
                    *messages
                ],
                temperature=0.7,
                max_tokens=500,
                prefer_azure=True
            )

            assistant_message = response.choices[0].message.content

            self.session['messages'].append({
                "role": "assistant",
                "content": assistant_message,
                "timestamp": datetime.now().isoformat()
            })

            save_session(self.session, session_file=SESSION_FILE, mongo_db=mongo_db)

            new_facts = extract_facts_from_message(user_message, self.memory)
            if new_facts:
                self.memory['facts'].extend(new_facts)
                saturation = get_learning_saturation(self.memory)
                print(f"[Learn] حفظت {len(new_facts)} حقيقة جديدة! (Total: {saturation['total_facts']}, Level: {saturation['level']})")

            learning_question = generate_learning_questions(user_message, self.memory)
            if learning_question:
                assistant_message += f"\n\n{learning_question}"
                saturation = get_learning_saturation(self.memory)
                print(f"[Learn] سؤال ذكي (Level: {saturation['level']}): {learning_question[:50]}...")
            else:
                saturation = get_learning_saturation(self.memory)
                print(f"[Learn] بدون أسئلة (Level: {saturation['level']}) - صرنا صديقات! 💫")

            self.memory['conversations'].append({
                "user": user_message,
                "assistant": assistant_message,
                "timestamp": datetime.now().isoformat()
            })

            if len(self.memory['conversations']) > 100:
                self.memory['conversations'] = self.memory['conversations'][-100:]

            save_memory(self.memory, memory_file=MEMORY_FILE, mongo_db=mongo_db)

            return get_sandy_reply(user_message, self.memory, assistant_message)

        except Exception as e:
            import traceback
            print(f"[OpenAI] Error: {e}")
            traceback.print_exc()
            return f"[خطأ] معاف، حدث مشكلة: {str(e)}"

    def add_fact(self, fact: str):
        """Add important fact to memory"""
        if fact not in self.memory.get('facts', []):
            self.memory['facts'].append(fact)
            save_memory(self.memory, memory_file=MEMORY_FILE, mongo_db=mongo_db)


def create_task(self, task_text: str) -> str:
    """Create a new task"""
    return add_task(task_text, mongo_db=mongo_db, tasks_file=TASKS_FILE)

def finish_task(self, task_id: str) -> bool:
    """Mark task as done"""
    return complete_task(task_id, mongo_db=mongo_db, tasks_file=TASKS_FILE)

def show_tasks(self) -> str:
    """Show all pending tasks"""
    return list_tasks(mongo_db=mongo_db, tasks_file=TASKS_FILE)

def create_reminder(self, text: str, remind_at: str = None) -> str:
    """Create a new reminder"""
    add_reminder(text, remind_at, mongo_db=mongo_db, reminders_file=REMINDERS_FILE)
    return f"[happy] تمام ✅ سجلت التذكير: {text}"

def show_pending_reminders(self) -> Optional[str]:
    """Check and show pending reminders"""
    return check_reminders(mongo_db=mongo_db, reminders_file=REMINDERS_FILE)

# ═══════════════════════════════════════════════════════════
# TELEGRAM BOT HANDLERS
# ═══════════════════════════════════════════════════════════

agent = SandyAgent()

register_basic_telegram_handlers(
    telegram_bot=telegram_bot,
    agent=agent,
    sandy_user_chat_id=SANDY_USER_CHAT_ID,
    extract_image_prompt_fn=extract_image_prompt,
    generate_image_with_azure_fn=generate_image_with_azure,
    send_text_and_voice_reply_fn=send_text_and_voice_reply,
    set_last_assistant_reaction_fn=_set_last_assistant_reaction,
    google_tts_voice=GOOGLE_TTS_VOICE,
    google_tts_language_code=GOOGLE_TTS_LANGUAGE_CODE,
    mood_tts_voices=MOOD_TTS_VOICES,
    azure_speech_available=AZURE_SPEECH_AVAILABLE,
    azure_speech_key=AZURE_SPEECH_KEY,
    azure_speech_region=AZURE_SPEECH_REGION,
    azure_speech_voice=AZURE_SPEECH_VOICE,
    azure_openai_client=azure_openai_client,
    azure_openai_image_deployment=AZURE_OPENAI_IMAGE_DEPLOYMENT,
    analyze_image_with_azure_fn=analyze_image_with_azure,
    download_telegram_file_bytes_fn=download_telegram_file_bytes,
    create_chat_completion_fn=create_chat_completion,
    azure_openai_vision_deployment=AZURE_OPENAI_VISION_DEPLOYMENT,
    azure_openai_chat_deployment=AZURE_OPENAI_CHAT_DEPLOYMENT,
    openai_model=OPENAI_MODEL,
    transcribe_audio_with_azure_fn=transcribe_audio_with_azure,
    azure_openai_stt_deployment=AZURE_OPENAI_STT_DEPLOYMENT,
    is_image_generation_request_fn=is_image_generation_request,
    )

# Guard against duplicated Telegram deliveries/restarts.
_recent_message_keys = deque(maxlen=500)
_recent_message_set = set()
_recent_message_lock = threading.Lock()

# بتشيك إذا رسالة تيليجرام وصلت قبل هيك عشان ما تتكرر المعالجة

def _is_duplicate_telegram_message(message) -> bool:
    """Return True if this Telegram message has already been processed recently."""
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

# بتتأكد إذا المستخدم المرسل هو المستخدم أو شخص مصرح له

def _is_authorized_user(message) -> bool:
    return str(message.from_user.id) == SANDY_USER_CHAT_ID


# ═══════════════════════════════════════════════════════════
# SCHEDULED TASKS
# ═══════════════════════════════════════════════════════════

# كل يوم الصبح (9 صباحاً) ساندي بتبعت ملخص يومي تلقائي
def daily_briefing():
    """Send daily briefing at 9 AM"""
    try:
        briefing = agent.think("قدملي ملخص يومي عن اللي صار")
        telegram_bot.send_message(SANDY_USER_CHAT_ID, f"[morning] صباح الخير  ! ☀️\n\n{briefing}", parse_mode=None)
    except Exception as e:
        print(f"[Briefing] Error: {e}")

# Schedule tasks
scheduler.add_job(daily_briefing, 'cron', hour=9, minute=0)
scheduler.add_job(
    lambda: check_reminders(
        mongo_db=mongo_db,
        reminders_file=REMINDERS_FILE,
        send_message_fn=telegram_bot.send_message,
        user_chat_id=SANDY_USER_CHAT_ID,
    ),
    'interval',
    minutes=1
)
# ═══════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════

# نقطة التشغيل الرئيسية للوكيل ساندي
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

    # منطق التشغيل الجديد بناءً على APP_ENV أو RUN_MODE
    if APP_ENV == "local" or RUN_MODE == "polling":
        print("[Mode] Local development: Telegram polling mode (APP_ENV=local or RUN_MODE=polling)")
        # تجاهل RAILWAY_URL تمامًا في الوضع المحلي
        prepare_telegram_polling(telegram_bot)
        while True:
            try:
                telegram_bot.infinity_polling(
                    skip_pending=False,
                    timeout=30,
                    long_polling_timeout=30,
                    allowed_updates=["message"]
                )
            except Exception as e:
                msg = str(e)
                if "Error code: 409" in msg or "terminated by other getUpdates request" in msg:
                    print("[Telegram] ⚠️ Polling conflict (409). Retrying in 5s...")
                else:
                    print(f"[Telegram] ❌ Polling crashed: {e}")
            time.sleep(5)
    else:
        print("[Mode] Production/Server: Webhook mode (APP_ENV=prod/RUN_MODE=webhook)")
        # فقط في الإنتاج يستخدم RAILWAY_URL وFlask webhook


# ═══════════════════════════════════════════════════════════
# FLASK WEBHOOK MODE (RAILWAY/PRODUCTION)
# ═══════════════════════════════════════════════════════════

TELEGRAM_SECRET_TOKEN = os.getenv("TELEGRAM_SECRET_TOKEN", "").strip()
RAILWAY_URL = os.getenv("RAILWAY_URL", "").strip()
WEBHOOK_PATH = f"/webhook/{TELEGRAM_SECRET_TOKEN}" if TELEGRAM_SECRET_TOKEN else "/webhook"

app = create_telegram_webhook_app(
    telegram_bot=telegram_bot,
    webhook_path=WEBHOOK_PATH,
    telegram_secret_token=TELEGRAM_SECRET_TOKEN,
)

if __name__ == "__main__":
    if APP_ENV == "local" or RUN_MODE == "polling":
        # لا تستدعي set_telegram_webhook إطلاقًا في الوضع المحلي
        main()
    else:
        # في الإنتاج فقط: استخدم webhook
        set_telegram_webhook(
            telegram_bot,
            TELEGRAM_BOT_TOKEN,
            RAILWAY_URL,
            WEBHOOK_PATH,
            TELEGRAM_SECRET_TOKEN,
        )
        port = int(os.environ.get("PORT", 8080))
        app.run(host="0.0.0.0", port=port)

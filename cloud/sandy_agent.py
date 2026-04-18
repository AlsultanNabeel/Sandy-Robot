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
from app.utils.text import (
    extract_reaction_and_clean_text,
    prepare_tts_text,
)
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
from app.integrations.google_tts import synthesize_voice_with_google
from app.integrations.azure_speech import (
    transcribe_audio_with_azure,
    synthesize_voice_with_azure,
)



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

# ========== SANDY PERSONALITY ENGINE ==========



# هاي الدالة بتاخد النص الخام من الصفحة وبتخلي الذكاء الاصطناعي يطلع منه معلومات مرتبة ومختصرة حسب نوع البحث.
def extract_structured_page_data(page_content: Dict[str, Any], research_type: str = "general") -> Dict[str, Any]:
    if not page_content:
        return {}

    page_text = (page_content.get("text", "") or "").strip()
    page_title = page_content.get("title", "")
    page_url = page_content.get("url", "")

    effective_research_type = research_type

    education_hints = [
        "master", "masters", "máster", "universitario", "universidad", "university",
        "robotics", "robótica", "robotica", "automática", "automatica",
        "admission", "credits", "ects", "preinscripción", "preinscripcion"
    ]

    combined_text = f"{page_title}\n{page_url}\n{page_text[:2000]}".lower()

    if research_type == "general" and any(hint in combined_text for hint in education_hints):
        effective_research_type = "education"

    if not page_text:
        return {}

    if effective_research_type == "education":
        extraction_instruction = """
Extract the following fields from this official education/program page:
- institution_name
- program_name
- degree_level
- country
- city
- language_of_instruction
- admission_requirements
- english_requirement
- requires_ielts_or_toefl (true/false/unknown)
- tuition
- deadline
- application_url
- official_program_url
- summary

Return valid JSON only.
"""
    elif effective_research_type == "travel":
        extraction_instruction = """
Extract the following fields from this travel/hotel/visa page:
- place_name
- country
- city
- type
- price
- booking_link
- visa_info
- important_requirements
- summary

Return valid JSON only.
"""
    elif effective_research_type == "product":
        extraction_instruction = """
Extract the following fields from this product page:
- product_name
- brand
- price
- currency
- availability
- key_features
- pros
- cons
- official_url
- summary

Return valid JSON only.
"""
    elif effective_research_type == "news":
        extraction_instruction = """
Extract the following fields from this news page:
- headline
- publisher
- published_date
- key_points
- summary
- source_url

Return valid JSON only.
"""
    else:
        extraction_instruction = """
Extract the following fields from this page:
- title
- main_entity
- important_requirements
- price_or_cost
- relevant_dates
- official_link
- summary

Return valid JSON only.
"""

    try:
        response = create_chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": extraction_instruction
                },
                {
                    "role": "user",
                    "content": f"PAGE TITLE: {page_title}\nPAGE URL: {page_url}\n\nPAGE TEXT:\n{page_text[:12000]}"
                }
            ],
            temperature=0,
            max_tokens=900,
            response_format={"type": "json_object"},
            prefer_azure=True
        )

        parsed = json.loads(response.choices[0].message.content or "{}")
        return parsed

    except Exception as e:
        print(f"[Research] ❌ Structured extraction failed for {page_url}: {e}")
        return {
            "title": page_title,
            "official_link": page_url,
            "summary": (page_text[:700] + "...") if len(page_text) > 700 else page_text
        }


def normalize_education_page_data(page_data: Dict[str, Any], source_url: str = "") -> Dict[str, Any]:
    if not isinstance(page_data, dict):
        return {}

    cleaned = dict(page_data)

    def clean_value(value: Any) -> str:
        return str(value or "").strip()

    institution_name = clean_value(cleaned.get("institution_name"))
    program_name = clean_value(cleaned.get("program_name"))
    degree_level = clean_value(cleaned.get("degree_level"))
    country = clean_value(cleaned.get("country"))
    city = clean_value(cleaned.get("city"))
    language_of_instruction = clean_value(cleaned.get("language_of_instruction"))
    admission_requirements = clean_value(cleaned.get("admission_requirements"))
    english_requirement = clean_value(cleaned.get("english_requirement"))
    requires_ielts_or_toefl = clean_value(cleaned.get("requires_ielts_or_toefl"))
    tuition = clean_value(cleaned.get("tuition"))
    deadline = clean_value(cleaned.get("deadline"))
    application_url = clean_value(cleaned.get("application_url"))
    official_program_url = clean_value(cleaned.get("official_program_url"))
    summary = clean_value(cleaned.get("summary"))

    # توحيد القيم المجهولة
    unknown_values = {
        "unknown", "not specified", "not specified.", "n/a", "none",
        "no especificado", "no especificado en la página.", "no especificado en la pagina.",
        "desconocido"
    }

    if language_of_instruction.lower() in unknown_values:
        language_of_instruction = ""
    if requires_ielts_or_toefl.lower() in unknown_values:
        requires_ielts_or_toefl = ""
    if tuition.lower() in unknown_values:
        tuition = ""
    if deadline.lower() in unknown_values:
        deadline = ""

    # تصحيح أسماء دول/مدن غير منطقية لبعض جامعات إسبانيا
    source_url_lower = source_url.lower()
    institution_lower = institution_name.lower()

    if (
        "valencia" in institution_lower
        or "universitat politècnica de valència" in institution_lower
        or "upv.es" in source_url_lower
    ):
        if country.lower() not in {"spain", "españa", "espana", ""}:
            country = "Spain"
        if city.lower() not in {"valencia", ""}:
            city = "Valencia"

    if (
        "universidad de alicante" in institution_lower
        or "ua.es" in source_url_lower
    ):
        if country.lower() not in {"spain", "españa", "espana", ""}:
            country = "Spain"
        if city.lower() not in {"alicante", ""}:
            city = "Alicante"

    if (
        "carlos iii" in institution_lower
        or "uc3m.es" in source_url_lower
    ):
        if country.lower() not in {"spain", "españa", "espana", ""}:
            country = "Spain"

    cleaned["institution_name"] = institution_name
    cleaned["program_name"] = program_name
    cleaned["degree_level"] = degree_level
    cleaned["country"] = country
    cleaned["city"] = city
    cleaned["language_of_instruction"] = language_of_instruction
    cleaned["admission_requirements"] = admission_requirements
    cleaned["english_requirement"] = english_requirement
    cleaned["requires_ielts_or_toefl"] = requires_ielts_or_toefl
    cleaned["tuition"] = tuition
    cleaned["deadline"] = deadline
    cleaned["application_url"] = application_url
    cleaned["official_program_url"] = official_program_url
    cleaned["summary"] = summary

    return cleaned




# بتدور على برامج جامعية، بتفلتر النتائج الرسمية، وبتسحب معلومات عن كل برنامج
def run_research_pipeline(user_query: str, research_type: str = "general", requested_count: int = 5) -> List[Dict[str, Any]]:
    print(f"[Research] 🔍 Starting {research_type} research for: {user_query}")

    exa_results = search_exa(
        user_query,
        exa_api_key=EXA_API_KEY,
        num_results=WEB_RESEARCH_MAX_CANDIDATES
    )
    if not exa_results:
        return []

    candidates = []

    for item in exa_results:
        url = item.get("url", "")
        if not url:
            continue

        if is_official_source_url(url, research_type=research_type):
            candidates.append(item)

    # إذا الفلترة كانت شديدة وما رجع شيء، خذ fallback بعد انتهاء اللوب
    if not candidates:
        print("[Research] ⚠️ No official-looking candidates found after filtering")

        soft_candidates = []
        soft_blocked = [
            "educations.com",
            "educations.es",
            "mastersportal.com",
            "masterstudies.com",
            "findamasters.com",
            "studyportals.com",
            "financialmagazine.es",
            "universoptimum.com",
            "yaq.es",
            "edurank.org",
            "erudera.com",
            "topuniversities.com",
            "timeshighereducation.com",
            "shiksha.com",
        ]

        for item in exa_results:
            url = item.get("url", "").lower()
            if not url:
                continue
            if any(bad in url for bad in soft_blocked):
                continue
            soft_candidates.append(item)

        candidates = soft_candidates[: max(requested_count * 2, requested_count)]

    extracted_results = []
    

    if research_type == "education":
        extraction_prompt = """
Extract the following fields from this page in a clear structured way:
- institution_name
- program_name
- degree_level
- country
- city
- language_of_instruction
- admission_requirements
- english_requirement
- requires_ielts_or_toefl (true/false/unknown)
- tuition
- deadline
- application_url
- official_program_url
- summary

Return the result as structured data.
"""
    elif research_type == "travel":
        extraction_prompt = """
Extract the following fields from this page in a clear structured way:
- place_name
- country
- city
- type
- price
- booking_link
- visa_info
- important_requirements
- summary

Return the result as structured data.
"""
    elif research_type == "product":
        extraction_prompt = """
Extract the following fields from this page in a clear structured way:
- product_name
- brand
- price
- currency
- availability
- key_features
- pros
- cons
- official_url
- summary

Return the result as structured data.
"""
    elif research_type == "news":
        extraction_prompt = """
Extract the following fields from this page in a clear structured way:
- headline
- publisher
- published_date
- key_points
- summary
- source_url

Return the result as structured data.
"""
    else:
        extraction_prompt = """
Extract the following fields from this page in a clear structured way:
- title
- main_entity
- important_requirements
- price_or_cost
- relevant_dates
- official_link
- summary

Return the result as structured data.
"""

    for item in candidates[: max(requested_count * 2, requested_count)]:
        url = item.get("url", "")
        page_content = get_exa_page_content(
            url,
            exa_api_key=EXA_API_KEY,
        )
        page_data = extract_structured_page_data(page_content, research_type=research_type)

        if research_type == "education":
            page_data = normalize_education_page_data(page_data, source_url=url)

        print(f"[Research] Parsed structured data keys for {url}: {list(page_data.keys()) if isinstance(page_data, dict) else 'N/A'}")

        extracted_results.append({
            "source_title": item.get("title", ""),
            "source_url": url,
            "exa_snippet": item.get("text", ""),
            "page_content": page_content,
            "page_data": page_data
        })

    deduped_results = deduplicate_research_results(extracted_results)

    print(f"[Research] ✅ Finished research with {len(extracted_results)} extracted results")
    print(f"[Research] ✅ After deduplication: {len(deduped_results)} unique results")

    return deduped_results



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

from flask import Flask, request, abort

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



# بتحلل صورة باستخدام Azure/OpenAI وبتعطيك وصف مختصر بالعربي
def analyze_image_with_azure(image_bytes: bytes, prompt: str) -> str:
    """Analyze image bytes using Azure/OpenAI multimodal chat."""
    if not image_bytes:
        return "[think] ما قدرت أحلل الصورة حالياً."

    try:
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:image/jpeg;base64,{image_b64}"
        model_hint = AZURE_OPENAI_VISION_DEPLOYMENT or AZURE_OPENAI_CHAT_DEPLOYMENT or OPENAI_MODEL

        response = create_chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "حلل الصورة بدقة وباختصار باللغة العربية مع نقاط عملية."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}}
                    ]
                }
            ],
            temperature=0.2,
            max_tokens=450,
            prefer_azure=True,
            model_hint=model_hint
        )
        return (response.choices[0].message.content or "[think] تم التحليل لكن ما في وصف واضح.").strip()
    except Exception as e:
        print(f"[Azure Vision] ❌ Analysis failed: {e}")
        return "[think] صار خلل أثناء تحليل الصورة. جرب مرة ثانية."

# بتولد صورة جديدة باستخدام Azure OpenAI حسب الوصف اللي تعطيه

def generate_image_with_azure(prompt: str, size: str = "1024x1024") -> Optional[bytes]:
    """Generate image with Azure OpenAI and return image bytes."""
    if not prompt:
        return None

    if azure_openai_client is None or not AZURE_OPENAI_IMAGE_DEPLOYMENT:
        print("[Azure Image] ⚠️ Missing Azure OpenAI client or image deployment")
        return None

    try:
        result = azure_openai_client.images.generate(
            model=AZURE_OPENAI_IMAGE_DEPLOYMENT,
            prompt=prompt,
            size=size
        )

        if not getattr(result, "data", None):
            print("[Azure Image] ⚠️ Empty image response")
            return None

        first = result.data[0]

        # Prefer base64 payload when available
        if getattr(first, "b64_json", None):
            return base64.b64decode(first.b64_json)

        # Fallback: download image from URL
        if getattr(first, "url", None):
            response = requests.get(first.url, timeout=30)
            if response.status_code == 200:
                return response.content
            print(f"[Azure Image] ⚠️ URL download failed with {response.status_code}")

    except Exception as e:
        print(f"[Azure Image] ❌ Generation failed: {e}")

    return None


# بتبعت رسالة نصية للمستخدم، ولو فيه صوت بتبعت كمان رد صوتي
def send_text_and_voice_reply(chat_id: int, text: str, reply_to_message_id: Optional[int] = None):
    # بتبعت رسالة نصية للمستخدم، ولو فيه صوت بتبعت كمان رد صوتي
    text = str(text or "[think] صار خلل وما رجع نص واضح.")
    # استخرج الرياكشن من الرد (إذا موجود)
    reaction, text_without_reaction = extract_reaction_and_clean_text(text)
    # حفظ الرياكشن في متغير عالمي (للهاردوير لاحقاً)
    global LAST_ASSISTANT_REACTION
    LAST_ASSISTANT_REACTION = reaction
    # توثيق: هذا المتغير مهم لتمرير الرياكشن للهاردوير (الشاشة) مستقبلاً

    telegram_bot.send_message(chat_id, text_without_reaction, reply_to_message_id=reply_to_message_id, parse_mode=None)

    # إزالة الإيموجي من النص الصوتي حتى لا تُقرأ كنص والروابط ايضا
    def remove_emojis(s):
        try:
            import emoji
            return emoji.replace_emoji(s, replace="")
        except ImportError:
            return s
    tts_text = prepare_tts_text(text_without_reaction)
    tts_text = remove_emojis(tts_text)

    print(f"[DEBUG] Trying Google TTS for: {tts_text}")

    current_state = agent.memory.get("sandy_state", {})
    current_mood = current_state.get("mood", "neutral")
    current_style = current_state.get("style", "normal")

    print(f"[DEBUG] Voice mood='{current_mood}' style='{current_style}'")

    audio_bytes = synthesize_voice_with_google(
        tts_text,
        mood=current_mood,
        style=current_style,
        google_tts_voice=GOOGLE_TTS_VOICE,
        google_tts_language_code=GOOGLE_TTS_LANGUAGE_CODE,
        mood_tts_voices=MOOD_TTS_VOICES,
    )

    if audio_bytes:
        print("[DEBUG] Google TTS succeeded. Sending Google voice reply.")
        source = "Google TTS"
    else:
        print("[DEBUG] Google TTS failed. Trying Azure TTS...")
        audio_bytes = synthesize_voice_with_azure(
            tts_text,
            azure_speech_available=AZURE_SPEECH_AVAILABLE,
            azure_speech_key=AZURE_SPEECH_KEY,
            azure_speech_region=AZURE_SPEECH_REGION,
            azure_speech_voice=AZURE_SPEECH_VOICE,
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
                    requested_count=max(requested_count * 2, requested_count)
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

# هاندلر أمر /start و /help: بيعرف ساندي عن نفسها
@telegram_bot.message_handler(commands=['start', 'help'])
def handle_start(message):
    # أول ما المستخدم يكتب /start، ساندي بتعرف عن نفسها وبتشرح شو بتقدر تعمل
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

# هاندلر أمر /image أو /img: بيولد صورة ويرجعها
@telegram_bot.message_handler(commands=['image', 'img'])
def handle_image_command(message):
    # لما المستخدم يطلب صورة بـ /image، هون ساندي بتولد صورة وترجعها
    try:
        if _is_duplicate_telegram_message(message):
            return
        if not _is_authorized_user(message):
            telegram_bot.reply_to(message, "معاف، بس المستخدم بيقدر يتكلم معي 🔒")
            return

        chat_id = message.chat.id
        prompt = extract_image_prompt(message.text or "")
        if not prompt:
            telegram_bot.reply_to(
                message,
                "[think] اكتب وصف الصورة بعد الأمر. مثال: /image قطة كرتونية تلبس نظارات"
            )
            return

        telegram_bot.send_chat_action(chat_id, 'upload_photo')
        image_bytes = generate_image_with_azure(prompt)
        if not image_bytes:
            telegram_bot.reply_to(
                message,
                "[think] ما قدرت أولد الصورة. تأكد من AZURE_OPENAI_IMAGE_DEPLOYMENT."
            )
            return

        photo_file = io.BytesIO(image_bytes)
        photo_file.name = "sandy_generated.png"
        telegram_bot.send_photo(chat_id, photo_file, caption=f"[happy] تفضّل ✨\nالوصف: {prompt}")
        send_text_and_voice_reply(chat_id, "[happy] ولدت الصورة بنجاح ✨ إذا بدك أعدل الستايل ابعتلي وصف جديد.", reply_to_message_id=message.message_id)
    except Exception as e:
        print(f"[Error] Image command handler: {e}")
        telegram_bot.reply_to(message, "[think] صار خلل أثناء توليد الصورة.")

# هاندلر استقبال صورة: بيحللها باستخدام Azure AI
@telegram_bot.message_handler(content_types=['photo'])
def handle_photo(message):
    # لو المستخدم بعت صورة، ساندي بتحللها باستخدام Azure AI
    try:
        if _is_duplicate_telegram_message(message):
            return
        if not _is_authorized_user(message):
            telegram_bot.reply_to(message, "معاف، بس المستخدم بيقدر يتكلم معي 🔒")
            return

        chat_id = message.chat.id
        telegram_bot.send_chat_action(chat_id, 'typing')

        photo = message.photo[-1] if message.photo else None
        if not photo:
            telegram_bot.reply_to(message, "[think] ما وصلتني الصورة بشكل صحيح.")
            return

        downloaded = download_telegram_file_bytes(telegram_bot, photo.file_id)
        if not downloaded:
            telegram_bot.reply_to(message, "[think] ما قدرت أحمّل الصورة من تيليجرام.")
            return

        image_bytes, _ = downloaded
        prompt = message.caption or "حللي الصورة باختصار وقدمي أهم الملاحظات."
        analysis = analyze_image_with_azure(image_bytes, prompt)
        telegram_bot.send_message(chat_id, analysis, reply_to_message_id=message.message_id, parse_mode=None)
    except Exception as e:
        print(f"[Error] Photo handler: {e}")
        telegram_bot.reply_to(message, "[think] صار خلل أثناء تحليل الصورة.")

# هاندلر استقبال فيديو: بيحلل صورة المعاينة (thumbnail) للفيديو
@telegram_bot.message_handler(content_types=['video'])
def handle_video(message):
    """Analyze video via preview thumbnail to avoid heavy processing errors."""
    try:
        if _is_duplicate_telegram_message(message):
            return
        if not _is_authorized_user(message):
            telegram_bot.reply_to(message, "معاف، بس المستخدم بيقدر يتكلم معي 🔒")
            return

        chat_id = message.chat.id
        telegram_bot.send_chat_action(chat_id, 'typing')

        thumb = getattr(message.video, 'thumbnail', None) or getattr(message.video, 'thumb', None)
        if not thumb:
            telegram_bot.send_message(
                chat_id,
                "[think] وصل الفيديو، لكن بدون Thumbnail للتحليل البصري."
                " ابعته كصورة أو فيديو فيه معاينة.",
                reply_to_message_id=message.message_id,
                parse_mode=None
            )
            return

        downloaded = download_telegram_file_bytes(telegram_bot, thumb.file_id)
        if not downloaded:
            telegram_bot.reply_to(message, "[think] ما قدرت أحمّل معاينة الفيديو.")
            return

        image_bytes, _ = downloaded
        prompt = message.caption or "حللي محتوى الفيديو اعتماداً على لقطة المعاينة وقدمي وصف مختصر."
        analysis = analyze_image_with_azure(image_bytes, prompt)
        telegram_bot.send_message(chat_id, analysis, reply_to_message_id=message.message_id, parse_mode=None)
    except Exception as e:
        print(f"[Error] Video handler: {e}")
        telegram_bot.reply_to(message, "[think] صار خلل أثناء تحليل الفيديو.")

# هاندلر استقبال صوت أو ملف صوتي: بيحول الصوت لنص ويرد عليه
@telegram_bot.message_handler(content_types=['voice', 'audio'])
def handle_voice_or_audio(message):
    """Transcribe audio with Azure, then respond with text + voice."""
    try:
        if _is_duplicate_telegram_message(message):
            return
        if not _is_authorized_user(message):
            telegram_bot.reply_to(message, "معاف، بس المستخدم بيقدر يتكلم معي 🔒")
            return

        chat_id = message.chat.id
        telegram_bot.send_chat_action(chat_id, 'typing')

        media_obj = message.voice if message.content_type == 'voice' else message.audio
        if not media_obj:
            telegram_bot.reply_to(message, "[think] ما قدرت أقرأ الملف الصوتي.")
            return

        downloaded = download_telegram_file_bytes(telegram_bot, media_obj.file_id)
        if not downloaded:
            telegram_bot.reply_to(message, "[think] ما قدرت أحمّل الصوت من تيليجرام.")
            return

        audio_bytes, file_path = downloaded
        transcript = transcribe_audio_with_azure(
            audio_bytes,
            azure_openai_client=azure_openai_client,
            azure_openai_stt_deployment=AZURE_OPENAI_STT_DEPLOYMENT,
            file_name=file_path,
        )
        if not transcript:
            telegram_bot.reply_to(message, "[think] ما قدرت أحول الصوت لنص. تأكد من إعداد Azure STT.")
            return

        print(f"[Telegram] Voice transcript: {transcript}")
        response = agent.think(transcript)
        send_text_and_voice_reply(chat_id, response, reply_to_message_id=message.message_id)
    except Exception as e:
        print(f"[Error] Voice handler: {e}")
        telegram_bot.reply_to(message, "[think] صار خلل أثناء تحليل الصوت.")

# هاندلر استقبال أي رسالة نصية: المنطق الرئيسي للردود
@telegram_bot.message_handler(content_types=['text'])
def handle_message(message):
    """Handle all messages"""
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

        # Image generation path (text command)
        if is_image_generation_request(user_message):
            prompt = extract_image_prompt(user_message)
            if not prompt:
                telegram_bot.reply_to(message, "[think] اكتب وصف واضح للصورة اللي بدك ياها.")
                return

            telegram_bot.send_chat_action(chat_id, 'upload_photo')
            image_bytes = generate_image_with_azure(prompt)
            if not image_bytes:
                telegram_bot.reply_to(
                    message,
                    "[think] ما قدرت أولد الصورة حالياً. تأكد من إعداد Azure image deployment."
                )
                return

            photo_file = io.BytesIO(image_bytes)
            photo_file.name = "sandy_generated.png"
            telegram_bot.send_photo(
                chat_id,
                photo_file,
                caption=f"[happy] هاي الصورة اللي طلبتها ✨\nالوصف: {prompt}",
                reply_to_message_id=message.message_id
            )
            send_text_and_voice_reply(chat_id, "[happy] جاهزة 👌 إذا بدك نسخة ثانية بستايل مختلف احكيلي الوصف الجديد.", reply_to_message_id=message.message_id)
            return
        
        # Show typing indicator
        telegram_bot.send_chat_action(chat_id, 'typing')
        
        # Process message through Sandy Agent
        print(f"[Telegram] Message from {message.from_user.first_name}: {user_message}")
        response = agent.think(user_message)

        send_text_and_voice_reply(chat_id, response, reply_to_message_id=message.message_id)
        
    except Exception as e:
        import traceback
        print(f"[Error] Telegram handler: {e}")
        traceback.print_exc()
        telegram_bot.reply_to(message, f"[اعتذر] حدث خطأ: {str(e)}")


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
# بتجهز البوت لوضع polling المحلي (بتشيل أي webhook)

def prepare_telegram_polling():
    try:
        telegram_bot.remove_webhook()
        print("[Telegram] Webhook removed for local polling mode.")
    except Exception as e:
        print(f"[Telegram] Failed to remove webhook: {e}")

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
        prepare_telegram_polling()
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

app = Flask(__name__)

@app.route(WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():
    # تحقق من التوكن السري (Telegram header)
    if TELEGRAM_SECRET_TOKEN:
        header_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if header_token != TELEGRAM_SECRET_TOKEN:
            abort(403)
    if request.method == "POST":
        try:
            telegram_bot.process_new_updates([
                telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
            ])
        except Exception as e:
            print(f"[Webhook] ❌ Error: {e}")
        return "OK", 200
    return "Method Not Allowed", 405

def set_telegram_webhook():
    if not TELEGRAM_BOT_TOKEN or not RAILWAY_URL:
        print("[Webhook] TELEGRAM_BOT_TOKEN or RAILWAY_URL not set!")
        return
    webhook_url = RAILWAY_URL
    if not webhook_url.startswith("http"):
        webhook_url = "https://" + webhook_url
    webhook_url = webhook_url.rstrip("/") + WEBHOOK_PATH
    print(f"[Webhook] Setting webhook to: {webhook_url}")
    telegram_bot.remove_webhook()
    telegram_bot.set_webhook(
        url=webhook_url,
        secret_token=TELEGRAM_SECRET_TOKEN if TELEGRAM_SECRET_TOKEN else None
    )

if __name__ == "__main__":
    if APP_ENV == "local" or RUN_MODE == "polling":
        # لا تستدعي set_telegram_webhook إطلاقًا في الوضع المحلي
        main()
    else:
        # في الإنتاج فقط: استخدم webhook
        set_telegram_webhook()
        port = int(os.environ.get("PORT", 8080))
        app.run(host="0.0.0.0", port=port)

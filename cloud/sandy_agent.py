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
import io
import base64
import tempfile
from pymongo import results
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

# MongoDB Integration (Optional - requires MONGODB_URI env var)
try:
    from pymongo import MongoClient
    from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    print("[Warning] PyMongo not available. To enable: pip install pymongo>=4.6.0")

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
# بتحول النص لصوت باستخدام Google TTS حسب المزاج والستايل، وبترجع الصوت كـ bytes

def synthesize_voice_with_google(text: str, mood: str = "neutral", style: str = "normal") -> Optional[bytes]:
    # بتحول النص لصوت باستخدام Google TTS حسب المزاج والستايل، وبترجع الصوت كـ bytes
    if not text or not GOOGLE_TTS_AVAILABLE:
        return None

    try:
        client = texttospeech.TextToSpeechClient()
        synthesis_input = texttospeech.SynthesisInput(text=text)

        selected_voice = MOOD_TTS_VOICES.get(mood, GOOGLE_TTS_VOICE)

        if style == "romantic":
            selected_voice = MOOD_TTS_VOICES.get("romantic", selected_voice)
        elif style == "caring":
            if mood in ["sad", "angry", "neutral"]:
                selected_voice = MOOD_TTS_VOICES.get("sad", selected_voice)
        elif style == "serious":
            selected_voice = MOOD_TTS_VOICES.get("serious", selected_voice)
        elif style == "excited":
            selected_voice = MOOD_TTS_VOICES.get("excited", selected_voice)
        elif style == "shy":
            selected_voice = MOOD_TTS_VOICES.get("shy", selected_voice)
        elif style == "playful":
            selected_voice = MOOD_TTS_VOICES.get("happy", selected_voice)

        print(f"[Google TTS] Using mood='{mood}' voice='{selected_voice}'")

        voice = texttospeech.VoiceSelectionParams(
            language_code=GOOGLE_TTS_LANGUAGE_CODE,
            name=selected_voice,
            ssml_gender=texttospeech.SsmlVoiceGender.FEMALE,
        )

        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16
        )

        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config,
        )

        return response.audio_content

    except Exception as e:
        print(f"[Google TTS] ❌ Error: {e}")
        return None


# ========== SANDY PERSONALITY ENGINE ==========
# بتخلي الذكاء الاصطناعي يحزر مزاج ساندي وستايلها من رسالة المستخدم والسياق

def infer_mood_and_style_from_ai(user_message: str, memory: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    # بتخلي الذكاء الاصطناعي يحزر مزاج ساندي وستايلها من رسالة المستخدم والسياق
    try:
        previous_state = memory.get("sandy_state", {})
        previous_mood = previous_state.get("mood", "neutral")

        response = create_chat_completion(
            temperature=0,
            max_tokens=180,
            response_format={"type": "json_object"},
            prefer_azure=True,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an emotion/context classifier for Sandy, an assistant with memory and personality. "
                        "Analyze the FULL meaning of the user's message, not just keywords. "
                        "Return strict JSON only with fields: "
                        "mood, style, directed_at_sandy, confidence. "
                        "Allowed moods: happy, sad, angry, bored, neutral, excited, romantic, shy, tired, serious. "
                        "Allowed styles: normal, caring, romantic, playful, serious, excited, shy. "
                        "Rules: "
                        "1) If the user is telling a story about something else, do NOT treat it as directly addressed to Sandy. "
                        "2) If words like 'sorry' or 'I love you' appear inside a story, do not automatically map them to caring/romantic unless clearly addressed to Sandy. "
                        "3) Prefer the OVERALL emotional meaning of the message. "
                        "4) Return only JSON."
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"previous_mood={previous_mood}\n"
                        f"user_message={user_message}"
                    )
                }
            ]
        )

        payload = json.loads(response.choices[0].message.content or "{}")

        mood = str(payload.get("mood", "neutral")).strip().lower()
        style = str(payload.get("style", "normal")).strip().lower()
        directed_at_sandy = bool(payload.get("directed_at_sandy", False))
        confidence = float(payload.get("confidence", 0.0) or 0.0)

        allowed_moods = {"happy", "sad", "angry", "bored", "neutral", "excited", "romantic", "shy", "tired", "serious"}
        allowed_styles = {"normal", "caring", "romantic", "playful", "serious", "excited", "shy"}

        if mood not in allowed_moods:
            mood = "neutral"
        if style not in allowed_styles:
            style = "normal"

        return {
            "mood": mood,
            "style": style,
            "directed_at_sandy": directed_at_sandy,
            "confidence": confidence
        }

    except Exception as e:
        print(f"[MoodAI] ⚠️ Failed to infer mood/style: {e}")
        return None

# بتبحث في الإنترنت عن أي شيء بدك إياه وترجع النتائج بشكل مبسط

def search_exa(query: str, num_results: int = 10) -> List[Dict[str, Any]]:
    # بتبحث في الإنترنت عن أي شيء بدك إياه وترجع النتائج بشكل مبسط
    if not EXA_API_KEY:
        print("[Exa] ⚠️ EXA_API_KEY missing")
        return []

    try:
        url = "https://api.exa.ai/search"
        headers = {
            "x-api-key": EXA_API_KEY,
            "Content-Type": "application/json",
        }
        payload = {
            "query": query,
            "numResults": num_results,
            "type": "auto",
            "contents": {
                "text": True
            }
        }

        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()

        results = []
        for item in data.get("results", []):
            results.append({
                "title": str(item.get("title") or "").strip(),
                "url": str(item.get("url") or "").strip(),
                "text": str(item.get("text") or "").strip(),
                "published_date": str(item.get("publishedDate") or "").strip(),
            })
        print(f"[Exa] ✅ Found {len(results)} results for query: {query}")
        return results

    except Exception as e:
        print(f"[Exa] ❌ Search failed: {e}")
        return []



# هاي الدالة بتجيب محتوى الصفحة نفسها من Exa بعد ما نعرف الرابط، عشان نقدر نحلل التفاصيل بدل ما نعتمد فقط على العنوان والـ snippet.
def get_exa_page_content(url: str) -> Dict[str, Any]:
    if not EXA_API_KEY:
        print("[Exa] ⚠️ EXA_API_KEY missing")
        return {}

    try:
        api_url = "https://api.exa.ai/contents"
        headers = {
            "x-api-key": EXA_API_KEY,
            "Content-Type": "application/json",
        }
        payload = {
            "urls": [url],
            "text": True
        }

        response = requests.post(api_url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()

        results = data.get("results", [])
        if not results:
            return {}

        item = results[0]
        return {
            "url": str(item.get("url") or "").strip(),
            "title": str(item.get("title") or "").strip(),
            "text": str(item.get("text") or "").strip(),
        }

    except Exception as e:
        print(f"[Exa] ❌ Contents fetch failed for {url}: {e}")
        return {}



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



# دالة تحدد نوع البحث قب البحث
def detect_research_type(message: str) -> str:
    text = (message or "").strip().lower()

    education_triggers = [
        "جامعة", "جامعات", "ماجستير", "ماجيستير", "ماستر", "بكالوريوس", "دكتوراه",
        "منحة", "قبول", "تقديم", "admission", "university", "universidad",
        "master", "masters", "phd", "bachelor", "degree",
        "ielts", "toefl",
        "روبوت", "روبوتكس", "robotics", "automation", "automatica", "robótica", "robotica"
    ]

    travel_triggers = [
        "سافر", "سفر", "فندق", "رحلة", "تأشيرة", "فيزا", "hotel", "trip", "travel", "visa"
    ]

    product_triggers = [
        "اشتري", "اشتريلي", "منتج", "منتجات", "سعر", "مقارنة أسعار",
        "buy", "price", "product", "products", "compare"
    ]

    news_triggers = [
        "خبر", "أخبار", "اليوم", "آخر", "اخر", "latest", "news", "update", "updates"
    ]

    if any(word in text for word in education_triggers):
        return "education"

    if any(word in text for word in travel_triggers):
        return "travel"

    if any(word in text for word in product_triggers):
        return "product"

    if any(word in text for word in news_triggers):
        return "news"

    return "general"


# هاي الدالة بتحاول تفهم من كلام المستخدم كم نتيجة بده بالزبط، وإذا ما حدد عدد بترجع رقم افتراضي.
def extract_requested_result_count(message: str, default: int = 5) -> int:
    text = (message or "").strip().lower()

    arabic_number_words = {
        "واحد": 1,
        "وحدة": 1,
        "واحدة": 1,
        "اثنين": 2,
        "اتنين": 2,
        "اثنتين": 2,
        "ثلاثة": 3,
        "ثلاث": 3,
        "اربعة": 4,
        "اربع": 4,
        "أربع": 4,
        "أربعة": 4,
        "خمسة": 5,
        "ستة": 6,
        "سبعة": 7,
        "ثمانية": 8,
        "تسعة": 9,
        "عشرة": 10,
    }

    # أولاً: لو فيه رقم مكتوب مباشرة
    match = re.search(r"\b(\d+)\b", text)
    if match:
        try:
            value = int(match.group(1))
            return max(1, min(value, 20))
        except Exception:
            pass

    # ثانياً: لو العدد مكتوب كلمات
    for word, value in arabic_number_words.items():
        if word in text:
            return value

    # ثالثاً: لو الطلب بصيغة مفردة واضحة
    single_result_triggers = [
        "أفضل جامعة",
        "افضل جامعة",
        "أرخص جامعة",
        "ارخص جامعة",
        "جامعة وحدة",
        "جامعة واحدة",
        "صفحة وحدة",
        "صفحة واحدة",
        "أفضل صفحة",
        "افضل صفحة",
        "أرخص صفحة",
        "ارخص صفحة",
        "best university",
        "cheapest university",
        "one university",
        "single university",
        "one page",
        "single page",
        "best page",
        "cheapest page",
    ]

    lowered = text.lower()
    if any(trigger.lower() in lowered for trigger in single_result_triggers):
        return 1

    return default


# هاي الدالة بتحاول تميز إذا الرابط غالباً رسمي أو تابع لجهة أصلية، وبتستبعد روابط التجميع والمواقع العامة.
def is_official_source_url(url: str, research_type: str = "general") -> bool:
    if not url:
        return False

    lowered_url = url.lower()

    blocked_domains = [
        "educations.com",
        "educations.es",
        "mastersportal.com",
        "masterstudies.com",
        "findamasters.com",
        "studyportals.com",
        "bachelorstudies.com",
        "phdstudies.com",
        "financialmagazine.es",
        "universoptimum.com",
        "yaq.es",
        "linkedin.com",
        "facebook.com",
        "instagram.com",
        "youtube.com",
        "medium.com",
        "reddit.com",
        "quora.com",
        "wikipedia.org",
        "topuniversities.com",
        "timeshighereducation.com",
        "shiksha.com",
        "ielts.org",
        "ielts.idp.com",
    ]

    if any(domain in lowered_url for domain in blocked_domains):
        return False

    if research_type == "education":
        official_hints = [
            ".edu", ".ac.", ".ac.uk",
            "universidad", "university",
            "/master", "/masters", "/graduate", "/admissions", "/program",
            "/postgrado", "/estudio", "/degree", "/degrees"
        ]

        # إذا الرابط فيه مؤشرات أكاديمية/برامج، اعتبره مرشح رسمي
        if any(hint in lowered_url for hint in official_hints):
            return True

        # إذا الدومين يبدو تابعًا لموقع رسمي أوروبي/جامعي وليس من المواقع المحظورة
        if lowered_url.startswith("https://www.") or lowered_url.startswith("https://"):
            if ".es/" in lowered_url or lowered_url.endswith(".es") or ".edu/" in lowered_url:
                return True

        return False

    if research_type == "travel":
        official_hints = [
            ".gov", ".gob", ".eu",
            "official", "visit", "tourism",
            "booking.com", "airbnb.com", "expedia.com"
        ]
        return any(hint in lowered_url for hint in official_hints)

    if research_type == "product":
        official_hints = [
            "amazon.", "mediamarkt.", "coolblue.", "bol.", "apple.", "sony.", "dell.", "ikea."
        ]
        return any(hint in lowered_url for hint in official_hints)

    if research_type == "news":
        official_hints = [
            ".com", ".org", ".net"
        ]
        return any(hint in lowered_url for hint in official_hints)

    return True

# هاي الدالة بتنظف الرابط بشكل بسيط حتى نقدر نكتشف إذا نفس الصفحة مكررة بنسخة لغة ثانية أو بصيغة مختلفة.
def normalize_result_url(url: str) -> str:
    url = str(url or "").strip().lower()
    url = url.rstrip("/")

    replacements = [
        "/en",
        "/es",
        "/ar",
        "/fr",
        "/de",
        "/ca",
        "/eu"
    ]

    for suffix in replacements:
        if url.endswith(suffix):
            url = url[: -len(suffix)]

    # شيل query params إذا موجودة
    url = url.split("?")[0]

    return url



# هاي الدالة بتنظف اسم البرنامج عشان نقدر نكشف التكرار حتى لو الاسم طالع بلغة ثانية أو بصياغة مختلفة شوي.
def normalize_program_name(name: str) -> str:
    name = str(name or "").strip().lower()

    replacements = {
        "robótica": "robotics",
        "robotica": "robotics",
        "automatización": "automation",
        "automatizacion": "automation",
        "automática": "automation",
        "automatica": "automation",
        "máster": "master",
        "master's": "master",
        "masters": "master",
    }

    for old, new in replacements.items():
        name = name.replace(old, new)

    name = re.sub(r"[^a-z0-9\s]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


# هاي الدالة بتبني مفتاح تقريبي للنتيجة حتى نعرف إذا نفس الجامعة/البرنامج طالع أكثر من مرة.
def build_result_dedup_key(item: Dict[str, Any]) -> str:
    page_data = item.get("page_data", {}) or {}

    institution = str(page_data.get("institution_name") or "").strip().lower()
    program = normalize_program_name(page_data.get("program_name") or item.get("source_title") or "")
    source_url = normalize_result_url(item.get("source_url") or "")
    source_domain = ""

    try:
        from urllib.parse import urlparse
        parsed = urlparse(source_url)
        source_domain = parsed.netloc.replace("www.", "").strip().lower()
        source_path = parsed.path.strip().lower()
    except Exception:
        source_domain = ""
        source_path = ""

    if institution and program:
        return f"{institution}::{program}"

    if source_domain and program:
        return f"{source_domain}::{program}"

    if source_domain and source_path:
        return f"{source_domain}::{source_path}"

    if source_url:
        return source_url

    return normalize_program_name(item.get("source_title") or "")


# هاي الدالة بتشيل النتائج المكررة، مثل نفس الجامعة أو نفس البرنامج إذا طلع بأكثر من رابط أو لغة.
def deduplicate_research_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    unique_results = []
    seen_keys = set()

    for item in results:
        key = build_result_dedup_key(item)
        if not key:
            continue

        if key in seen_keys:
            continue

        seen_keys.add(key)
        unique_results.append(item)

    return unique_results

    

    # هاي الدالة بتفهم حالة IELTS/TOEFL بشكل أوضح: مؤكد لا، مؤكد نعم، أو غير واضح.
def classify_ielts_requirement(value: str) -> str:
    text = str(value or "").strip().lower()

    if text in ["false", "no", "لا", "not required", "not needed"]:
        return "no"

    if text in ["true", "yes", "نعم", "required", "needed"]:
        return "yes"

    return "unknown"


# هاي الدالة بتفلتر النتائج حسب طلب المستخدم، مثل بدون IELTS أو فقط الإنجليزية.
def filter_research_results(results: List[Dict[str, Any]], preference: Dict[str, Any]) -> List[Dict[str, Any]]:
    filtered = []

    for item in results:
        page_data = item.get("page_data", {}) or {}

        language_of_instruction = str(page_data.get("language_of_instruction") or "").strip().lower()
        requires_ielts_or_toefl = str(page_data.get("requires_ielts_or_toefl") or "").strip().lower()
        ielts_status = classify_ielts_requirement(requires_ielts_or_toefl)
        source_url = str(item.get("source_url") or "").strip().lower()

        if preference.get("english_only"):
            if "english" not in language_of_instruction and "الإنجليزية" not in language_of_instruction and "الانجليزية" not in language_of_instruction:
                continue

        if preference.get("no_ielts"):
            if ielts_status != "no":
                continue

        if preference.get("official_only"):
            if not is_official_source_url(source_url, research_type="education"):
                continue

        filtered.append(item)

    return filtered



# هاي الدالة بتحاول تطلع رقم تقريبي من حقل الرسوم حتى نقدر نرتب الأرخص بشكل أحسن.
# هاي الدالة بتحاول تطلع رقم من الرسوم، وإذا ما قدرت بترجع رقم كبير جدًا بدل ما ترجع None أو تخرب الفرز.
def parse_tuition_value(tuition_text: str) -> float:
    text = str(tuition_text or "").strip().lower()

    if not text:
        return 999999999.0

    cleaned = (
        text.replace(",", "")
        .replace("€", "")
        .replace("$", "")
        .replace("eur", "")
        .replace("usd", "")
    )

    match = re.search(r'(\d+(?:\.\d+)?)', cleaned)
    if not match:
        return 999999999.0

    try:
        return float(match.group(1))
    except Exception:
        return 999999999.0


# هاي الدالة بترتب النتائج بشكل بسيط حسب طلب المستخدم: أفضل أو أرخص.
def rank_research_results(results: List[Dict[str, Any]], preference: Dict[str, Any]) -> List[Dict[str, Any]]:
    def result_score(item: Dict[str, Any]) -> tuple:
        page_data = item.get("page_data", {}) or {}

        source_url = str(item.get("source_url") or "").strip().lower()
        institution = str(page_data.get("institution_name") or "").strip()
        program = str(page_data.get("program_name") or "").strip()
        tuition = str(page_data.get("tuition") or "").strip().lower()
        tuition_value = parse_tuition_value(tuition)
        ielts_status = classify_ielts_requirement(page_data.get("requires_ielts_or_toefl") or "")

        official_score = 1 if is_official_source_url(source_url, research_type="education") else 0
        metadata_score = 0
        if institution:
            metadata_score += 1
        if program:
            metadata_score += 1
        if tuition:
            metadata_score += 1

        if preference.get("cheapest_only"):
            return (
                int(tuition_value),
                -int(official_score),
                -int(metadata_score)
            )

        if preference.get("no_ielts"):
            ielts_rank = {
                "no": 2,
                "unknown": 1,
                "yes": 0
            }.get(ielts_status, 0)

            return (
                int(official_score),
                int(ielts_rank),
                int(metadata_score)
            )

        return (
            int(official_score),
            int(metadata_score)
        )
    
    if preference.get("cheapest_only"):
        return sorted(results, key=result_score)

    return sorted(results, key=result_score, reverse=True)



# هاي الدالة بتختار أفضل نتيجة وحدة وبتعطي سبب مختصر وواضح ليش انختارت.
def build_winner_summary(results: List[Dict[str, Any]], preference: Dict[str, Any]) -> str:
    if not results:
        return "[think] ما لقيت نتيجة واضحة أقدر أختارها كأفضل خيار."

    def localize_value(value: Any, field_type: str = "") -> str:
        if isinstance(value, dict):
            if field_type == "deadline":
                parts = []
                for k, v in value.items():
                    key = str(k).replace("_", " ").strip()
                    val = str(v).strip()
                    if val:
                        parts.append(f"{key}: {val}")
                return " | ".join(parts) if parts else "غير مذكور بوضوح"
            value = str(value)

        if isinstance(value, list):
            value = " | ".join(str(x).strip() for x in value if str(x).strip())

        value = str(value or "").strip()
        lowered = value.lower()

        unknown_values = {
            "unknown",
            "not specified",
            "not specified.",
            "not specified in the provided text",
            "not specified in the provided text.",
            "n/a",
            "none",
            "no especificado",
            "no especificado en la página",
            "no especificado en la página.",
            "no especificado en la pagina",
            "no especificado en la pagina.",
            "desconocido"
        }

        if field_type == "deadline" and value.startswith("{") and value.endswith("}"):
            try:
                parsed = json.loads(value.replace("'", '"'))
                if isinstance(parsed, dict):
                    parts = []
                    for k, v in parsed.items():
                        key = str(k).replace("_", " ").strip()
                        val = str(v).strip()
                        if val:
                            parts.append(f"{key}: {val}")
                    return " | ".join(parts) if parts else "غير مذكور بوضوح"
            except Exception:
                pass

        if lowered in unknown_values:
            if field_type == "tuition":
                return "غير مذكورة بوضوح"
            if field_type == "deadline":
                return "غير مذكور بوضوح"
            return "غير واضح"

        if lowered in {"yes", "true", "required"}:
            return "نعم"

        if lowered in {"no", "false", "not required"}:
            return "لا"

        return value

    winner = results[0]
    page_data = winner.get("page_data", {}) or {}

    title = (
        page_data.get("program_name")
        or page_data.get("product_name")
        or page_data.get("place_name")
        or page_data.get("headline")
        or page_data.get("title")
        or winner.get("source_title")
        or "بدون عنوان"
    )

    institution = str(page_data.get("institution_name") or "").strip()
    summary = str(page_data.get("summary") or "").strip()
    url = str(page_data.get("official_program_url") or winner.get("source_url") or "").strip()

    language_of_instruction = localize_value(page_data.get("language_of_instruction"), "language")
    requires_ielts_or_toefl = localize_value(page_data.get("requires_ielts_or_toefl"), "ielts")
    tuition = localize_value(page_data.get("tuition"), "tuition")
    deadline = localize_value(page_data.get("deadline"), "deadline")

    reasons = []

    if preference.get("best_only"):
        reasons.append("اخترته لأنه من أوضح وأقوى النتائج الرسمية المتوفرة")
    if preference.get("cheapest_only"):
        reasons.append("اخترته لأنه ظهر كأفضل خيار متاح من ناحية الرسوم أو وضوح تكلفة الدراسة")
    if preference.get("no_ielts"):
        reasons.append("اخترته لأنه يبدو الأنسب من ناحية شرط IELTS/TOEFL")
    if preference.get("english_only"):
        reasons.append("اخترته لأنه مناسب من ناحية لغة الدراسة")

    if language_of_instruction and language_of_instruction != "غير واضح":
        reasons.append(f"لغة الدراسة: {language_of_instruction}")
    if requires_ielts_or_toefl and requires_ielts_or_toefl != "غير واضح":
        reasons.append(f"IELTS/TOEFL: {requires_ielts_or_toefl}")
    if tuition and tuition != "غير مذكورة بوضوح":
        reasons.append(f"الرسوم: {tuition}")
    if deadline and deadline != "غير مذكور بوضوح":
        reasons.append(f"الموعد النهائي: {deadline}")

    lines = ["[think] اخترت لك هذا الخيار:\n"]
    lines.append(f"البرنامج: {str(title).strip()}")

    if institution:
        lines.append(f"الجامعة: {institution}")

    if summary:
        lines.append(f"الملخص: {summary}")

    if reasons:
        lines.append("سبب الاختيار:")
        for reason in reasons:
            lines.append(f"- {reason}")

    if url:
        lines.append(f"الرابط: {url}")

    return "\n".join(lines)


# هاي الدالة بتحاول تفهم شو نوع الفلترة أو المقارنة اللي بدها ياها من كلام المستخدم.
def detect_research_preference(message: str) -> Dict[str, Any]:
    text = str(message or "").strip().lower()

    return {
        "best_only": any(x in text for x in [
            "أفضل", "افضل", "best", "top", "الأقوى", "الاقوى"
        ]),
        "cheapest_only": any(x in text for x in [
            "أرخص", "ارخص", "cheapest", "lowest price", "lowest tuition"
        ]),
        "no_ielts": any(x in text for x in [
            "بدون ielts", "ما يطلب ielts", "بدون توفل", "ما يطلب توفل",
            "بدون toefl", "no ielts", "no toefl"
        ]),
        "english_only": any(x in text for x in [
            "بالانجليزي", "بالإنجليزي", "باللغة الإنجليزية",
            "english", "english only", "in english"
        ]),
        "official_only": any(x in text for x in [
            "رسمي", "رسمية", "official", "official only"
        ]),
    }


# بتدور على برامج جامعية، بتفلتر النتائج الرسمية، وبتسحب معلومات عن كل برنامج
def run_research_pipeline(user_query: str, research_type: str = "general", requested_count: int = 5) -> List[Dict[str, Any]]:
    print(f"[Research] 🔍 Starting {research_type} research for: {user_query}")

    exa_results = search_exa(user_query, num_results=WEB_RESEARCH_MAX_CANDIDATES)
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
        page_content = get_exa_page_content(url)
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



# هاي الدالة بتعرف إذا المستخدم عم يبني على نتائج البحث السابقة بدل ما يبدأ بحث جديد من الصفر.
def is_research_followup_request(message: str) -> bool:
    text = str(message or "").strip().lower()

    triggers = [
        "من هدول", "من بينهم", "من النتائج", "فيهم", "منهم",
        "which of these", "from these", "among them", "among these"
    ]

    return any(t in text for t in triggers)


# بتشيك إذا الرسالة فيها طلب بحث أو مقارنة جامعات أو منح
def is_research_request(message: str) -> bool:
    text = (message or "").strip().lower()

    triggers = [
        "ابحث", "ابحثي", "دوري", "دورلي", "research", "find",
        "جامعة", "جامعات", "ماجستير", "masters", "robotics",
        "قارن", "قارنة", "منحة", "قبول", "admission", "ielts", "toefl"
    ]

    return any(t in text for t in triggers)


# بيلخص نتائج البحث الجامعي بشكل بسيط للمستخدم

def summarize_research_results(results: List[Dict[str, Any]], requested_count: int = 5) -> str:
    def localize_display_value(value: Any, field_type: str = "") -> str:
        if isinstance(value, dict):
            if field_type == "deadline":
                parts = []
                for k, v in value.items():
                    key = str(k).replace("_", " ").strip()
                    val = str(v).strip()
                    if val:
                        parts.append(f"{key}: {val}")
                return " | ".join(parts) if parts else "غير مذكور بوضوح"
            value = str(value)

        if isinstance(value, list):
            value = " | ".join(str(x).strip() for x in value if str(x).strip())

        value = str(value or "").strip()
        lowered = value.lower()
        # إذا القيمة جاية كنص على شكل dict مثل "{'phase_0': '...'}"
        if field_type == "deadline" and value.startswith("{") and value.endswith("}"):
            try:
                parsed = json.loads(value.replace("'", '"'))
                if isinstance(parsed, dict):
                    parts = []
                    for k, v in parsed.items():
                        key = str(k).replace("_", " ").strip()
                        val = str(v).strip()
                        if val:
                            parts.append(f"{key}: {val}")
                    return " | ".join(parts) if parts else "غير مذكور بوضوح"
            except Exception:
                pass

        unknown_values = {
            "unknown",
            "not specified",
            "not specified.",
            "not specified in the provided text",
            "not specified in the provided text.",
            "n/a",
            "none",
            "no especificado",
            "no especificado en la página",
            "no especificado en la página.",
            "no especificado en la pagina",
            "no especificado en la pagina.",
            "desconocido"
        }

        if lowered in unknown_values:
            if field_type == "tuition":
                return "غير مذكورة بوضوح"
            if field_type == "deadline":
                return "غير مذكور بوضوح"
            return "غير واضح"

        if lowered in {"yes", "true", "required"}:
            return "نعم"

        if lowered in {"no", "false", "not required"}:
            return "لا"

        return value

    if not results:
        return "[think] ما لقيت نتائج واضحة من البحث حالياً."

    lines = ["[think] رتبت لك النتائج بشكل أوضح، وحاولت أعتمد على المصادر الرسمية قدر الإمكان:\n"]

    for i, item in enumerate(results[:requested_count], 1):
        page_data = item.get("page_data", {}) or {}

        title = (
            page_data.get("program_name")
            or page_data.get("product_name")
            or page_data.get("place_name")
            or page_data.get("headline")
            or page_data.get("title")
            or item.get("source_title")
            or "بدون عنوان"
        )

        institution = page_data.get("institution_name") or ""
        summary = page_data.get("summary") or ""
        url = item.get("source_url") or ""

        degree_level = page_data.get("degree_level") or ""
        country = page_data.get("country") or ""
        city = page_data.get("city") or ""
        language_of_instruction = page_data.get("language_of_instruction") or ""
        requires_ielts_or_toefl = page_data.get("requires_ielts_or_toefl") or ""
        tuition = page_data.get("tuition") or ""
        deadline = page_data.get("deadline") or ""
        application_url = page_data.get("application_url") or ""
        official_program_url = page_data.get("official_program_url") or ""

        title = str(title).strip()
        institution = str(institution).strip()
        summary = str(summary).strip()
        url = str(url).strip()
        degree_level = str(degree_level).strip()
        country = str(country).strip()
        city = str(city).strip()
        language_of_instruction = localize_display_value(language_of_instruction, "language")
        requires_ielts_or_toefl = localize_display_value(requires_ielts_or_toefl, "ielts")
        tuition = localize_display_value(tuition, "tuition")
        deadline = localize_display_value(deadline, "deadline")
        application_url = localize_display_value(application_url, "url")
        official_program_url = localize_display_value(official_program_url, "url")

        lines.append(f"{i}. {title}")

        if institution:
            lines.append(f"الجامعة: {institution}")

        meta_parts = []
        if degree_level:
            meta_parts.append(f"الدرجة: {degree_level}")
        if country:
            meta_parts.append(f"الدولة: {country}")
        if city:
            meta_parts.append(f"المدينة: {city}")

        if meta_parts:
            lines.append(" | ".join(meta_parts))

        if summary:
            lines.append(f"الملخص: {summary}")
            
        important_points = []

        important_points.append(
            f"لغة الدراسة: {localize_display_value(language_of_instruction, 'language') if language_of_instruction else 'غير واضحة'}"
        )
        important_points.append(
            f"IELTS/TOEFL: {localize_display_value(requires_ielts_or_toefl, 'ielts') if requires_ielts_or_toefl else 'غير واضح'}"
        )
        important_points.append(
            f"الرسوم: {localize_display_value(tuition, 'tuition') if tuition else 'غير مذكورة بوضوح'}"
        )
        important_points.append(
            f"الموعد النهائي: {localize_display_value(deadline, 'deadline') if deadline else 'غير مذكور بوضوح'}"
        )

        if important_points:
            lines.append("نقاط مهمة:")
            for point in important_points:
                lines.append(f"- {point}")

        if official_program_url:
            lines.append(f"رابط البرنامج: {official_program_url}")
        if application_url:
            lines.append(f"رابط التقديم: {application_url}")
        elif not official_program_url and url:
            lines.append(f"الرابط: {url}")

        lines.append("")

    return "\n".join(lines)  



# بتحدث مزاج وحالة ساندي حسب الرسالة، أول شي بتجرب AI، وإذا فشل بتستخدم قواعد بسيطة

def update_sandy_state(memory: Dict[str, Any], user_message: str) -> None:
    # بتحدث مزاج وحالة ساندي حسب الرسالة، أول شي بتجرب AI، وإذا فشل بتستخدم قواعد بسيطة
    now = datetime.now()
    state = memory.get("sandy_state", {})

    last_time = datetime.fromisoformat(state.get("last_user_message_time", now.isoformat()))
    last_msg = state.get("last_message", "")
    repeat_count = state.get("repeat_count", 0)
    snapped = state.get("snapped", False)
    previous_mood = state.get("mood", "neutral")

    # Repeat detection
    if user_message.strip() == last_msg.strip():
        repeat_count += 1
    else:
        repeat_count = 0
        snapped = False

    ai_result = infer_mood_and_style_from_ai(user_message, memory)

    mood = previous_mood
    style = state.get("style", "normal")
    directed_at_sandy = False

    if ai_result and ai_result.get("confidence", 0) >= 0.65:
        mood = ai_result.get("mood", "neutral")
        style = ai_result.get("style", "normal")
        directed_at_sandy = ai_result.get("directed_at_sandy", False)
    else:
        # Fallback logic فقط إذا AI فشل
        hours_since_last = (now - last_time).total_seconds() / 3600

        lowered_message = (user_message or "").lower()

        if hours_since_last > 24:
            mood = "angry"
        elif hours_since_last > 6:
            mood = "sad"
        else:
            mood = "neutral"

        style = "normal"

        if any(word in lowered_message for word in ["واو", "رائع", "روعة", "متحمس", "متحمسة", "مبسوطة", "مبسوط", "excited"]):
            mood = "excited"
            style = "excited"

        elif any(word in lowered_message for word in ["بحبك", "اشتقت", "حبي", "love you", "missed you"]):
            mood = "romantic"
            style = "romantic"
            directed_at_sandy = True

        elif any(word in lowered_message for word in ["آسف", "سوري", "sorry"]):
            mood = "happy"
            style = "caring"
            directed_at_sandy = True

        elif any(word in lowered_message for word in ["استحيت", "محرج", "خجلان", "خجلانة", "shy"]):
            mood = "shy"
            style = "shy"

        elif any(word in lowered_message for word in ["تعبان", "تعبانة", "نعسان", "نعسانة", "مرهق", "مرهقة", "tired"]):
            mood = "tired"
            style = "normal"

        elif any(word in lowered_message for word in ["ركز", "مهم", "بسرعة", "رسمي", "جاد", "serious"]):
            mood = "serious"
            style = "serious"

    # Repetition override
    if repeat_count >= 3 and mood not in ["romantic", "excited"]:
        mood = "bored"
        style = "serious"
        if repeat_count >= 6:
            snapped = True

    state.update({
        "mood": mood,
        "style": style,
        "directed_at_sandy": directed_at_sandy,
        "last_user_message_time": now.isoformat(),
        "repeat_count": repeat_count,
        "last_message": user_message,
        "snapped": snapped,
        "last_mood_change": now.isoformat() if mood != previous_mood else state.get("last_mood_change", now.isoformat())
    })

    memory["sandy_state"] = state


# بتولد رد ساندي حسب المزاج والحالة، بس حالياً بترجع الرد الافتراضي

def get_sandy_reply(user_message: str, memory: Dict[str, Any], default_reply: str) -> str:
    # بتولد رد ساندي حسب المزاج والحالة، بس حالياً بترجع الرد الافتراضي
    return default_reply


import emoji


# بتطلع الرياكشن (زي [happy]) من أول الرد وبتشيله من النص

def extract_reaction_and_clean_text(text: str):
    """
    استخراج الرياكشن (مثل [happy]) من بداية الرد، وحفظه في متغير منفصل.
    هذا المتغير مهم لتمريره للهاردوير (الشاشة) مستقبلاً.
    يرجع (reaction, text_without_reaction)
    """
    reaction = None
    cleaned = str(text or "").strip()

    match = re.match(r"^\[([a-zA-Z_]+)\]\s*", cleaned)
    if match:
        reaction = match.group(1)
        cleaned = cleaned[match.end():].strip()

    return reaction, cleaned


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



# Initialize MongoDB connection
mongo_client = None
mongo_db = None

if MONGODB_AVAILABLE and MONGODB_URI:
    def _connect_mongo(uri: str) -> Optional[MongoClient]:
        """Build Mongo client with Atlas-friendly TLS defaults for cloud runtimes."""
        base_kwargs = {
            "serverSelectionTimeoutMS": 20000,
            "connectTimeoutMS": 20000,
            "socketTimeoutMS": 20000,
            "retryWrites": True,
            "maxPoolSize": 10,
            "minPoolSize": 1,
            "appname": "sandy-railway-agent"
        }

        # Preferred path: validate Atlas certificate chain using certifi bundle.
        client = MongoClient(
            uri,
            tls=True,
            tlsCAFile=certifi.where(),
            **base_kwargs
        )
        client.admin.command('ping')
        return client

    try:
        mongo_client = _connect_mongo(MONGODB_URI)
        mongo_db = mongo_client[MONGODB_DB_NAME]
        print(f"[MongoDB] ✅ Connected successfully (db={MONGODB_DB_NAME})")
    except Exception as first_error:
        print(f"[MongoDB] ⚠️ Primary TLS connection failed: {first_error}")
        try:
            # Last-resort compatibility mode for edge runtime TLS issues.
            mongo_client = MongoClient(
                MONGODB_URI,
                serverSelectionTimeoutMS=20000,
                connectTimeoutMS=20000,
                socketTimeoutMS=20000,
                tls=True,
                tlsAllowInvalidCertificates=True,
                retryWrites=True,
                maxPoolSize=10,
                minPoolSize=1,
                appname="sandy-railway-agent-fallback"
            )
            mongo_client.admin.command('ping')
            mongo_db = mongo_client[MONGODB_DB_NAME]
            print(f"[MongoDB] ✅ Connected with fallback TLS mode (db={MONGODB_DB_NAME})")
        except Exception as second_error:
            print(f"[MongoDB] ⚠️ Connection failed: {second_error}")
            print("[MongoDB] Hint: check Atlas Network Access allowlist and URI credentials")
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

telegram_bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, threaded=True)
scheduler = BackgroundScheduler(timezone=None)
scheduler.start()

def _chat_client_and_model(prefer_azure: bool = True, model_hint: Optional[str] = None):
    """Select chat client/model with Azure-first strategy when configured."""
    if prefer_azure and azure_openai_client is not None:
        model_name = model_hint or AZURE_OPENAI_CHAT_DEPLOYMENT or OPENAI_MODEL
        return azure_openai_client, model_name
    return openai_client, (model_hint or OPENAI_MODEL)

def create_chat_completion(messages: List[Dict[str, Any]], temperature: float = 0.7,
                           max_tokens: int = 500, response_format: Optional[Dict[str, Any]] = None,
                           prefer_azure: bool = True, model_hint: Optional[str] = None):
    """Unified chat completion helper for Azure/OpenAI with optional structured output."""
    client, model_name = _chat_client_and_model(prefer_azure=prefer_azure, model_hint=model_hint)
    kwargs = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    return client.chat.completions.create(**kwargs)

def download_telegram_file_bytes(file_id: str) -> Optional[tuple]:
    """Download telegram file bytes. Returns (bytes, file_path) or None."""
    try:
        file_info = telegram_bot.get_file(file_id)
        data = telegram_bot.download_file(file_info.file_path)
        return data, file_info.file_path
    except Exception as e:
        print(f"[Telegram] ❌ File download failed: {e}")
        return None

def transcribe_audio_with_azure(audio_bytes: bytes, file_name: str = "voice.ogg") -> Optional[str]:
    """Transcribe audio bytes using Azure OpenAI transcription deployment."""
    if azure_openai_client is None or not AZURE_OPENAI_STT_DEPLOYMENT:
        print("[Azure STT] ⚠️ Missing Azure OpenAI client or STT deployment")
        return None

    suffix = Path(file_name).suffix or ".ogg"
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(audio_bytes)
            temp_path = tmp.name

        with open(temp_path, "rb") as f:
            result = azure_openai_client.audio.transcriptions.create(
                model=AZURE_OPENAI_STT_DEPLOYMENT,
                file=f
            )
        transcript = (getattr(result, "text", "") or "").strip()
        if transcript:
            print(f"[Azure STT] ✅ Transcript: {transcript[:80]}")
            return transcript
    except Exception as e:
        print(f"[Azure STT] ❌ Transcription failed: {e}")
    finally:
        if temp_path and Path(temp_path).exists():
            try:
                Path(temp_path).unlink()
            except Exception:
                pass
    return None

# بتحول النص لصوت باستخدام Azure TTS وبتعطيك الصوت كـ wav

def synthesize_voice_with_azure(text: str) -> Optional[bytes]:
    # بتحول النص لصوت باستخدام Azure TTS وبتعطيك الصوت كـ wav
    if not text:
        return None
    if not AZURE_SPEECH_AVAILABLE or not AZURE_SPEECH_KEY or not AZURE_SPEECH_REGION:
        print("[Azure TTS] ⚠️ Speech SDK/key/region not configured")
        return None

    temp_path = None
    try:
        speech_config = speechsdk.SpeechConfig(subscription=AZURE_SPEECH_KEY, region=AZURE_SPEECH_REGION)
        speech_config.speech_synthesis_voice_name = AZURE_SPEECH_VOICE
        # أعلى جودة متاحة: 48Khz/192Kbps Mono PCM
        speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Riff16Khz16BitMonoPcm
        )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            temp_path = tmp.name

        audio_config = speechsdk.audio.AudioOutputConfig(filename=temp_path)
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
        result = synthesizer.speak_text_async(text).get()

        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted and Path(temp_path).exists():
            with open(temp_path, "rb") as f:
                audio_bytes = f.read()
            print("[Azure TTS] ✅ Voice generated (48Khz/192Kbps)")
            return audio_bytes

        print(f"[Azure TTS] ❌ Synthesis failed: {result.reason}")
    except Exception as e:
        print(f"[Azure TTS] ❌ Error: {e}")
    finally:
        if temp_path and Path(temp_path).exists():
            try:
                Path(temp_path).unlink()
            except Exception:
                pass
    return None

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

# بتشيك إذا المستخدم طلب رسم أو توليد صورة

def is_image_generation_request(message: str) -> bool:
    """Detect if user asks for image generation."""
    text = (message or "").strip().lower()
    triggers = [
        "ارسم", "رسمة", "صمم صورة", "ولّد صورة", "generate image", "draw"
    ]
    return any(t in text for t in triggers)

# بتطلع وصف الصورة من رسالة المستخدم بعد ما يشيل الأمر أو الكلمات المفتاحية

def extract_image_prompt(message: str) -> str:
    """Extract prompt text for image generation."""
    text = (message or "").strip()
    text = re.sub(r'^(?:/image|/img)\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'(?:ارسم|رسمة|صمم صورة|ول\s*د صورة|ولّد صورة|generate image|draw)\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# هاي الدالة بتحول الأرقام المكتوبة لنسخة منطوقة حسب لغة النص، لكن فقط للصوت، أما الكتابة الأصلية بتضل زي ما هي.
def localize_numbers_for_tts(text: str) -> str:
    text = str(text or "").strip()

    def looks_arabic(s: str) -> bool:
        return bool(re.search(r'[\u0600-\u06FF]', s))

    arabic_numbers = {
        "1": "واحد",
        "2": "اثنين",
        "3": "ثلاثة",
        "4": "أربعة",
        "5": "خمسة",
        "6": "ستة",
        "7": "سبعة",
        "8": "ثمانية",
        "9": "تسعة",
        "10": "عشرة",
    }

    english_numbers = {
        "1": "one",
        "2": "two",
        "3": "three",
        "4": "four",
        "5": "five",
        "6": "six",
        "7": "seven",
        "8": "eight",
        "9": "nine",
        "10": "ten",
    }

    number_map = arabic_numbers if looks_arabic(text) else english_numbers

    for num, spoken in sorted(number_map.items(), key=lambda x: len(x[0]), reverse=True):
        text = re.sub(
            rf'(?<![A-Za-z\u0600-\u06FF0-9]){re.escape(num)}(?![A-Za-z\u0600-\u06FF0-9])',
            spoken,
            text
        )

    return text


# هاي الدالة بتجهز النص قبل ما ينقرأ صوتياً: بتحذف الروابط، بتخفف القوائم الطويلة، وبدل ما يقرأ اللينكات بتحكي للمستخدم إنو الروابط مرفقة بالرسالة.
def prepare_tts_text(text: str) -> str:
    """
    Clean text before sending it to TTS:
    - remove URLs
    - shorten long lists
    - add a friendly note instead of reading raw links
    """
    if not text:
        return ""

    cleaned = text

    # Remove URLs
    cleaned = re.sub(r'https?://\S+', '', cleaned)

    # Remove excessive blank lines
    cleaned = re.sub(r'\n\s*\n+', '\n\n', cleaned)

    # If original text had links, mention that links are attached in the message
    if re.search(r'https?://\S+', text):
        cleaned = cleaned.strip()
        if cleaned:
            cleaned += "\n\nالروابط مرفقة في الرسالة."
        else:
            cleaned = "تم تجهيز النتيجة، الروابط مرفقة في الرسالة."

    # Optional: shorten very long result lists
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if len(lines) > 8:
        cleaned = "\n".join(lines[:8]) + "\n\nباقي التفاصيل والروابط موجودة في الرسالة."

    cleaned = localize_numbers_for_tts(cleaned)
    return cleaned.strip()


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
        style=current_style
    )

    if audio_bytes:
        print("[DEBUG] Google TTS succeeded. Sending Google voice reply.")
        source = "Google TTS"
    else:
        print("[DEBUG] Google TTS failed. Trying Azure TTS...")
        audio_bytes = synthesize_voice_with_azure(tts_text)
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
# MEMORY MANAGEMENT (MongoDB + JSON Fallback)
# ═══════════════════════════════════════════════════════════

# بتقرأ ملف JSON بأمان وبترجع الديفولت لو صار خطأ

def _read_json_file(path: Path, default: Any) -> Any:
    """Read JSON file safely and return default on any failure."""
    if not path.exists():
        return default
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[JSON] Error reading {path.name}: {e}")
        return default

# بترجع ذاكرة ساندي (من MongoDB أو من ملف)

def load_memory() -> Dict[str, Any]:
    """Load persistent memory from MongoDB or disk"""
    default_memory = {
        "conversations": [],
        "facts": [],
        "reminders": [],
        "tasks": [],
        "sandy_state": {
            "mood": "happy",  # happy, sad, angry, bored, neutral
            "last_user_message_time": datetime.now().isoformat(),
            "repeat_count": 0,
            "last_message": "",
            "snapped": False,  # هل انفجرت من التكرار
            "last_mood_change": datetime.now().isoformat(),
            "custom_facts": []  # تفضيلات أو أشياء خاصة يتعلمها عنك
        }
    }
    
    # Try MongoDB first
    if mongo_db is not None:
        try:
            memory_doc = mongo_db['memory'].find_one({"_id": "sandy_memory"})
            if memory_doc:
                memory_doc.pop("_id", None)  # Remove MongoDB ID
                print("[Memory] ✅ Loaded from MongoDB")
                return memory_doc

            # One-time migration path: seed Mongo from JSON if available.
            json_memory = _read_json_file(MEMORY_FILE, None)
            if isinstance(json_memory, dict):
                mongo_db['memory'].replace_one(
                    {"_id": "sandy_memory"},
                    {**json_memory, "_id": "sandy_memory"},
                    upsert=True
                )
                print("[Memory] 🔁 Migrated JSON -> MongoDB")
                return json_memory

            print("[Memory] ✅ MongoDB is source of truth (new memory)")
            return default_memory
        except Exception as e:
            print(f"[Memory] ⚠️ MongoDB error: {e}, falling back to JSON")
    
    # Fallback to JSON file
    memory_json = _read_json_file(MEMORY_FILE, None)
    if isinstance(memory_json, dict):
        print("[Memory] 📄 Loaded from JSON file")
        return memory_json
    
    # Return default structure
    return default_memory

# بتخزن ذاكرة ساندي (في MongoDB أو ملف)

def save_memory(memory: Dict[str, Any]):
    """Save memory to MongoDB or disk"""
    
    # Try MongoDB first
    if mongo_db is not None:
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

# بترجع جلسة المحادثة الحالية (من MongoDB أو ملف)

def load_session() -> Dict[str, Any]:
    """Load current session memory from MongoDB or disk"""
    default_session = {"messages": []}
    
    # Try MongoDB first
    if mongo_db is not None:
        try:
            session_doc = mongo_db['sessions'].find_one({"_id": "current_session"})
            if session_doc:
                session_doc.pop("_id", None)
                print("[Session] ✅ Loaded from MongoDB")
                return session_doc

            json_session = _read_json_file(SESSION_FILE, None)
            if isinstance(json_session, dict):
                mongo_db['sessions'].replace_one(
                    {"_id": "current_session"},
                    {**json_session, "_id": "current_session"},
                    upsert=True
                )
                print("[Session] 🔁 Migrated JSON -> MongoDB")
                return json_session

            print("[Session] ✅ MongoDB is source of truth (new session)")
            return default_session
        except Exception as e:
            print(f"[Session] ⚠️ MongoDB error: {e}")
    
    # Fallback to JSON file
    session_json = _read_json_file(SESSION_FILE, None)
    if isinstance(session_json, dict):
        print("[Session] 📄 Loaded from JSON file")
        return session_json
    
    return default_session

# بتخزن جلسة المحادثة الحالية (في MongoDB أو ملف)

def save_session(session: Dict[str, Any]):
    """Save session memory to MongoDB or disk"""
    
    # Try MongoDB first
    if mongo_db is not None:
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

# بتحدد مستوى معرفة ساندي عن المستخدم (مبتدئ، فضولي...)

def get_learning_saturation(memory: Dict[str, Any]) -> Dict[str, Any]:
    """حسب مستوى معرفة Sandy عن المستخدم"""
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

# بتقرر إذا ساندي لازم تسأل سؤال جديد حسب مستوى المعرفة

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

# بتستخرج حقائق جديدة من رسالة المستخدم لو فيها معلومة مهمة

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

# بتولد سؤال ذكي للمستخدم حسب الرسالة ومستوى المعرفة

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
    # تم تعطيل الرد التلقائي على كلمة "احب" أو "حب" بناءً على طلب المستخدم
    
    return questions[0] if questions else None

# ═══════════════════════════════════════════════════════════
# TASKS & REMINDERS MANAGEMENT
# ═══════════════════════════════════════════════════════════

# بترجع كل المهام (من MongoDB أو ملف)

def load_tasks() -> List[Dict[str, Any]]:
    """Load tasks from MongoDB or disk"""
    
    # Try MongoDB first
    if mongo_db is not None:
        try:
            tasks = list(mongo_db['tasks'].find({"type": "task"}))
            for task in tasks:
                task.pop("_id", None)
            if tasks:
                print("[Tasks] ✅ Loaded from MongoDB")
                return tasks

            json_tasks = _read_json_file(TASKS_FILE, [])
            if isinstance(json_tasks, list) and json_tasks:
                mongo_db['tasks'].delete_many({"type": "task"})
                for task in json_tasks:
                    task["type"] = "task"
                    mongo_db['tasks'].insert_one(task)
                    task.pop("type", None)
                print("[Tasks] 🔁 Migrated JSON -> MongoDB")
                return json_tasks

            print("[Tasks] ✅ MongoDB is source of truth (0 tasks)")
            return []
        except Exception as e:
            print(f"[Tasks] ⚠️ MongoDB error: {e}")
    
    # Fallback to JSON file
    tasks_json = _read_json_file(TASKS_FILE, [])
    if isinstance(tasks_json, list) and tasks_json:
        print("[Tasks] 📄 Loaded from JSON file")
        return tasks_json
    return []

# بتخزن كل المهام (في MongoDB أو ملف)

def save_tasks(tasks: List[Dict[str, Any]]):
    """Save tasks to MongoDB or disk"""
    
    # Try MongoDB first
    if mongo_db is not None:
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

# بترجع كل التذكيرات (من MongoDB أو ملف)

def load_reminders() -> List[Dict[str, Any]]:
    """Load reminders from MongoDB or disk"""
    
    # Try MongoDB first
    if mongo_db is not None:
        try:
            reminders = list(mongo_db['reminders'].find({"type": "reminder"}))
            for reminder in reminders:
                reminder.pop("_id", None)
            if reminders:
                print("[Reminders] ✅ Loaded from MongoDB")
                return reminders

            json_reminders = _read_json_file(REMINDERS_FILE, [])
            if isinstance(json_reminders, list) and json_reminders:
                mongo_db['reminders'].delete_many({"type": "reminder"})
                for reminder in json_reminders:
                    reminder["type"] = "reminder"
                    mongo_db['reminders'].insert_one(reminder)
                    reminder.pop("type", None)
                print("[Reminders] 🔁 Migrated JSON -> MongoDB")
                return json_reminders

            print("[Reminders] ✅ MongoDB is source of truth (0 reminders)")
            return []
        except Exception as e:
            print(f"[Reminders] ⚠️ MongoDB error: {e}")
    
    # Fallback to JSON file
    reminders_json = _read_json_file(REMINDERS_FILE, [])
    if isinstance(reminders_json, list) and reminders_json:
        print("[Reminders] 📄 Loaded from JSON file")
        return reminders_json
    return []

# بتخزن كل التذكيرات (في MongoDB أو ملف)

def save_reminders(reminders: List[Dict[str, Any]]):
    """Save reminders to MongoDB or disk"""
    
    # Try MongoDB first
    if mongo_db is not None:
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

# بتضيف مهمة جديدة وترجع رقمها

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

# بتعلم على المهمة إنها اكتملت

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

# بترجع قائمة بكل المهام المعلقة

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

# بتضيف تذكير جديد (وتحاول تحلل الوقت تلقائياً لو مش محدد)

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

# بتشيك إذا فيه تذكيرات لازم تنبعت وبتبعتها تلقائياً

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
                        telegram_bot.send_message(chat_id, message_text, parse_mode=None)
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

# بتستخدم الذكاء الاصطناعي عشان تكتشف إذا الرسالة فيها نية تذكير وتطلع التفاصيل

def extract_reminder_intent_ai(message: str) -> Optional[Dict[str, Any]]:
    """Use AI to detect reminder intent with structured output.

    Returns dict with keys:
      is_reminder: bool
      reminder_text: str
      time_expression: str
      confidence: float
    """
    try:
        response = create_chat_completion(
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
                    "content": message
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

def plan_reminder_with_ai(message: str) -> Optional[Dict[str, Any]]:
    """AI-only reminder planner.

    Returns JSON dict with:
      is_reminder: bool
      should_create: bool
      reminder_text: str
      remind_at_iso: str
      assistant_reply: str
      confidence: float
    """
    if not message:
        return None

    now_iso = datetime.now().isoformat()
    try:
        response = create_chat_completion(
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
                    "content": f"current_datetime={now_iso}\nmessage={message}"
                }
            ]
        )

        payload = json.loads(response.choices[0].message.content or "{}")
        remind_at_iso = str(payload.get("remind_at_iso", "") or "").strip()
        # Normalize/validate returned datetime if present
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

# بتستخدم الذكاء الاصطناعي لتحليل الوقت من رسالة التذكير

def parse_reminder_time_ai(message: str) -> Optional[str]:
    """Use AI to parse reminder time into ISO timestamp based on current server time."""
    if not message:
        return None

    now = datetime.now()
    now_iso = now.isoformat()
    try:
        response = create_chat_completion(
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
                    "content": f"current_datetime={now_iso}\ntext={message}"
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

        # Validate produced value can be parsed by Python.
        dt_value = datetime.fromisoformat(iso_value)
        if dt_value < now:
            # Guardrail: do not schedule in the past.
            dt_value = now + timedelta(minutes=1)
        final_iso = dt_value.isoformat()
        print(f"[ParseAI] ⏰ Parsed by AI: {final_iso}")
        return final_iso
    except Exception as e:
        print(f"[ParseAI] ⚠️ Fallback parser failed: {e}")
        return None

# ═══════════════════════════════════════════════════════════
# SANDY AGENT LOGIC
# ═══════════════════════════════════════════════════════════

# كلاس الوكيل الذكي ساندي: فيه كل المنطق الأساسي للذاكرة، المزاج، الردود، المهام والتذكيرات

class SandyAgent:
    def __init__(self):
        self.memory = load_memory()
        self.session = load_session()
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
            update_sandy_state(self.memory, user_message)
            save_memory(self.memory)

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

            reminder_plan = plan_reminder_with_ai(user_message)
            if reminder_plan and reminder_plan.get("is_reminder"):
                reminder_text = reminder_plan.get("reminder_text", "")
                remind_at = reminder_plan.get("remind_at_iso", "")
                should_create = reminder_plan.get("should_create", False)
                assistant_reply = reminder_plan.get("assistant_reply", "")

                if should_create and reminder_text and remind_at:
                    add_reminder(reminder_text, remind_at)
                    if assistant_reply:
                        return get_sandy_reply(user_message, self.memory, assistant_reply)
                    return get_sandy_reply(user_message, self.memory, f"[happy] تمام ✅ سجلت التذكير: {reminder_text}")

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

            save_session(self.session)

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

            save_memory(self.memory)

            return get_sandy_reply(user_message, self.memory, assistant_message)

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

        downloaded = download_telegram_file_bytes(photo.file_id)
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

        downloaded = download_telegram_file_bytes(thumb.file_id)
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

        downloaded = download_telegram_file_bytes(media_obj.file_id)
        if not downloaded:
            telegram_bot.reply_to(message, "[think] ما قدرت أحمّل الصوت من تيليجرام.")
            return

        audio_bytes, file_path = downloaded
        transcript = transcribe_audio_with_azure(audio_bytes, file_path)
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
scheduler.add_job(check_reminders, 'interval', minutes=1)

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

import os
# منع ظهور تحذيرات جوجل (gRPC) المزعجة في التيرمنال
os.environ["GRPC_VERBOSITY"] = "ERROR"
os.environ["GLOG_minloglevel"] = "2"
import io
import re
import json
import time
import uuid
import queue
import asyncio
import shutil
import threading
import tempfile
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import signal
import base64
import google.generativeai as genai





import requests
import edge_tts
import speech_recognition as sr
import telebot
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from dotenv import load_dotenv
from openai import OpenAI
from pydub import AudioSegment

try:
    import sandy_camera_iot_ready as sandy_camera
except Exception as e:
    sandy_camera = None
    print(f"Camera helper import warning: {e}")

try:
    from sandy_config import NABEEL_INFO, SANDY_PERSONALITY, SYSTEM_PROMPT_ADDITION
except Exception:
    NABEEL_INFO = ""
    SANDY_PERSONALITY = ""
    SYSTEM_PROMPT_ADDITION = ""

try:
    from sandy_memory_v2 import recall as memory_recall, summarize_and_store
except Exception as e:
    print(f"Memory import warning: {e}")
    def memory_recall(query: str, n_topics: int = 5, n_raw: int = 3) -> str:
        return ""
    def summarize_and_store(user_text: str, ai_reply: str):
        return None

# =========================
# Paths / config
# =========================
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
SESSION_FILE = BASE_DIR / "sandy_session_memory.json"
PLAN_FILE = BASE_DIR / "daily_plan.json"
REMINDERS_FILE = BASE_DIR / "reminders.json"
CAM_CONFIG_FILE = BASE_DIR / "sandy_camera_config.json"

load_dotenv(ENV_PATH)

# Camera helper is imported before .env is loaded; refresh its runtime config now.
if sandy_camera and hasattr(sandy_camera, "reload_camera_config"):
    try:
        sandy_camera.reload_camera_config()
    except Exception as e:
        print(f"Camera helper reload warning: {e}")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
GEMINI_MODEL_NAME = "models/gemini-2.5-flash"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
SANDY_IP = os.getenv("SANDY_IP", "192.168.8.100").strip()
CAM_IP = os.getenv("CAM_IP", "").strip()
SANDY_USER_CHAT_ID = os.getenv("SANDY_USER_CHAT_ID", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
VOICE_NAME = os.getenv("SANDY_TTS_VOICE", "ar-LB-LaylaNeural")
TTS_RATE = os.getenv("SANDY_TTS_RATE", "+15%")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
CAM_HTTP_USER_DEFAULT = os.getenv("CAM_HTTP_USER", "nabeel").strip() or "nabeel"
CAM_HTTP_PASS_DEFAULT = os.getenv("CAM_HTTP_PASS", "").strip()
CAM_CONTROL_TOKEN_DEFAULT = os.getenv("CAM_CONTROL_TOKEN", "").strip()
CAM_SNAPSHOT_TOKEN_DEFAULT = os.getenv("CAM_SNAPSHOT_TOKEN", "").strip()
CAM_SECRET_PASSPHRASE_DEFAULT = os.getenv("CAM_SECRET_PASSPHRASE", "").strip()
CAM_FACES_DB_DEFAULT = os.getenv("CAM_FACES_DB", "faces/faces_db.pkl").strip() or "faces/faces_db.pkl"
LISTEN_TIMEOUT = int(os.getenv("LISTEN_TIMEOUT", "5"))
LISTEN_PHRASE_LIMIT = int(os.getenv("LISTEN_PHRASE_LIMIT", "12"))
USE_MIC = os.getenv("USE_MIC", "1").strip() == "1"
SANDY_COMMAND_MODE = os.getenv("SANDY_COMMAND_MODE", "cloud").strip().lower()
if SANDY_COMMAND_MODE not in {"cloud", "http"}:
    SANDY_COMMAND_MODE = "cloud"
    
ARDUINO_CLIENT_ID = os.getenv("ARDUINO_CLIENT_ID", "").strip()
ARDUINO_CLIENT_SECRET = os.getenv("ARDUINO_CLIENT_SECRET", "").strip()
SANDY_DEVICE_ID = (
    os.getenv("SANDY_DEVICE_ID", "").strip()
    or os.getenv("SANDY_MAIN_DEVICE_ID", "").strip()
)
CAMERA_DEVICE_ID = os.getenv("CAMERA_DEVICE_ID", "").strip()
ARDUINO_ORG_ID = os.getenv("ARDUINO_ORG_ID", "").strip()
SANDY_THING_ID = os.getenv("SANDY_THING_ID", "").strip()
SANDY_BEHAVIOR_MODEL = os.getenv("SANDY_BEHAVIOR_MODEL", OPENAI_MODEL).strip() or OPENAI_MODEL
ENABLE_SCREEN_HTTP = os.getenv("SANDY_ENABLE_SCREEN_HTTP", "0").strip() == "1"
ENABLE_BASE_MOTION = os.getenv("SANDY_ENABLE_BASE_MOTION", "0").strip() == "1"
SANDY_DEBUG = os.getenv("SANDY_DEBUG", "0").strip() == "1"
SANDY_FACE_MIN_INTERVAL_SEC = float(os.getenv("SANDY_FACE_MIN_INTERVAL_SEC", "0.10"))
CAM_EYE_AUTO_CLOSE_SEC = max(5, int(os.getenv("CAM_EYE_AUTO_CLOSE_SEC", "20")))
_GEMINI_DISABLED = False
CAM_AUTO_CLOSE_JOB_ID = "camera_auto_close_job"
NETWORK_RETRY_COUNT = max(1, int(os.getenv("SANDY_NETWORK_RETRY_COUNT", "3")))
NETWORK_RETRY_DELAY_SEC = max(0.2, float(os.getenv("SANDY_NETWORK_RETRY_DELAY_SEC", "1.2")))
REQUEST_RESCHEDULE_MAX = max(1, int(os.getenv("SANDY_REQUEST_RESCHEDULE_MAX", "4")))
REQUEST_RESCHEDULE_DELAY_SEC = max(1.0, float(os.getenv("SANDY_REQUEST_RESCHEDULE_DELAY_SEC", "3.0")))
HEALTH_CHECK_RETRIES = max(1, int(os.getenv("SANDY_HEALTH_CHECK_RETRIES", "2")))
REQUEST_REBOOT_SETTLE_SEC = max(5.0, float(os.getenv("SANDY_REQUEST_REBOOT_SETTLE_SEC", "8.0")))
REQUEST_ALLOW_HARD_REBOOT = os.getenv("SANDY_REQUEST_ALLOW_HARD_REBOOT", "1").strip() == "1"


def _camera_env_config() -> Dict[str, Any]:
    return {
        "cam_ip": os.getenv("CAM_IP", "").strip(),
        "snapshot_token": CAM_SNAPSHOT_TOKEN_DEFAULT,
        "control_token": CAM_CONTROL_TOKEN_DEFAULT,
        "http_user": CAM_HTTP_USER_DEFAULT,
        "http_pass": CAM_HTTP_PASS_DEFAULT,
        "secret_passphrase": CAM_SECRET_PASSPHRASE_DEFAULT,
        "faces_db": CAM_FACES_DB_DEFAULT,
    }


def _camera_runtime_config() -> Dict[str, Any]:
    return _camera_env_config()

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY missing in .env")

client = OpenAI(api_key=OPENAI_API_KEY)
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, threaded=True) if TELEGRAM_BOT_TOKEN else None
scheduler = BackgroundScheduler(timezone=None)
scheduler.start()
recognizer = sr.Recognizer()

is_speaking = False
_last_speech_end_time = 0.0
last_esp_ok = True
current_expression = "idle"
current_expression_until = 0.0
current_expression_source = "boot"
current_overlay = ""
current_overlay_source = ""
current_face_cmd = ""
current_servo_angle = 90
_last_face_cmd = ""
_last_face_ts = 0.0
behavior_context: Dict[str, Any] = {"owner_visible": False, "last_seen_name": "unknown", "camera_search_enabled": False}

# Sequential execution controls (single active command pipeline).
_command_execution_lock = threading.RLock()
_request_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()
_request_worker_started = False
_request_worker_lock = threading.Lock()
_request_busy = threading.Event()

SUPPORTED_EXPRESSIONS = {
    "idle", "happy", "big_happy", "curious", "think", "talk", "alert", "surprised",
    "sleepy", "bored", "yawn", "sad", "angry", "smirk", "cute", "excited", "shy", "confused",
    "empathetic", "love", "cry", "wink", "kiss", "heart_eyes", "calm"
}

EMOJI_TO_MOOD_MAP = {
    "😊": "happy",
    "🙂": "happy",
    "😄": "big_happy",
    "😂": "big_happy",
    "😢": "sad",
    "😭": "cry",
    "😠": "angry",
    "😡": "angry",
    "🤔": "think",
    "🤨": "curious",
    "😮": "surprised",
    "😲": "surprised",
    "😴": "sleepy",
    "😒": "bored",
    "🥰": "love",
    "😍": "heart_eyes",
    "😉": "wink",
    "😘": "kiss",
    "👍": "happy", # يمكن تغييرها إلى calm لاحقاً
    "👌": "happy",
}

EXPRESSION_ALIASES = {
    "laugh": "big_happy",
    "laughing": "big_happy",
    "funny": "happy",
    "joy": "happy",
    "empathy": "empathetic",
    "playful": "smirk",
    "neutral": "idle",
    "listen": "curious",
    "listening": "curious",
    "thinking": "think",
    "speaking": "talk",
    "loving": "love",
    "heart-eyes": "heart_eyes",
    "heart eyes": "heart_eyes",
}

SYSTEM_PROMPT = """
أنتِ ساندي، مساعدة روبوتية عربية لطيفة وذكية وقريبة من القلب.
تكلمين المستخدم بالعربية الطبيعية، بوضوح وباختصار غالباً.
أنتِ لستِ مجرد شات؛ أنتِ شريكة يومية تساعد في التنظيم والتذكير والرد العملي.

قواعد مهمة:
- **ابدئي ردك دائماً بكلمة إنجليزية واحدة تصف حالتك الشعورية بين قوسين مربعين. مثال: `[happy]` أو `[sad]` أو `[curious]`.**
- تذكري سياق آخر الرسائل الموجودة في الذاكرة القصيرة.
- إذا طُلب منك تنفيذ فعل مادي أو على الروبوت، استخدمي الأداة المناسبة.
- لا تدّعي تنفيذ شيء لم ينجح. إذا فشل الاتصال أخبريه بصراحة.
- عند السؤال العادي، أجيبي بشكل طبيعي بدون ذكر الأدوات.
- عندما يوجد سؤال متابعة، اربطيه بالكلام السابق بدل أن تبدئي من الصفر.
- أنتِ تتحكمين بالسلوك لا بالكلمات الحرفية فقط: افهمي النية والسياق ثم اختاري التعبير أو الحركة أو السؤال الأنسب.
- عند وجود فرصة للتفاعل الطبيعي، اختاري مشاعر مناسبة مثل الفرح أو التعاطف أو الفضول بدل البقاء دائماً على وضع محايد.
""".strip()

_EXTRA_PROMPT_PARTS = []
if SANDY_PERSONALITY and str(SANDY_PERSONALITY).strip():
    _EXTRA_PROMPT_PARTS.append(str(SANDY_PERSONALITY).strip())
if SYSTEM_PROMPT_ADDITION and str(SYSTEM_PROMPT_ADDITION).strip():
    _EXTRA_PROMPT_PARTS.append(str(SYSTEM_PROMPT_ADDITION).strip())
if NABEEL_INFO and str(NABEEL_INFO).strip():
    _EXTRA_PROMPT_PARTS.append("معلومات عن نبيل:\n" + str(NABEEL_INFO).strip())
if _EXTRA_PROMPT_PARTS:
    SYSTEM_PROMPT = SYSTEM_PROMPT + "\n\n" + "\n\n".join(_EXTRA_PROMPT_PARTS)

CORE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "move_neck",
            "description": "تحريك رقبة ساندي إلى اليسار أو اليمين أو المنتصف أو زاوية محددة.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["left", "right", "center"]},
                    "angle": {"type": "integer", "minimum": 1, "maximum": 180}
                },
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_distance",
            "description": "قراءة المسافة الحالية من حساس المسافة على الروبوت.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False}
        }
    },

    {
        "type": "function",
        "function": {
            "name": "capture_and_describe",
            "description": "التقاط صورة من الكاميرا ووصفها باختصار.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_task",
            "description": "إضافة مهمة إلى خطة المستخدم اليومية.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "عرض المهام الحالية.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "وضع علامة تم على مهمة حسب رقمها.",
            "parameters": {
                "type": "object",
                "properties": {"index": {"type": "integer", "minimum": 1}},
                "required": ["index"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_reminder",
            "description": "إضافة تذكير بتاريخ ووقت محددين بصيغة YYYY-MM-DD HH:MM.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "when": {"type": "string", "description": "مثال: 2026-04-03 21:30"}
                },
                "required": ["text", "when"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_eyes",
            "description": "تشغيل الكاميرا وفتح العيون.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "close_eyes",
            "description": "إطفاء الكاميرا وإغلاق العيون.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "look_ahead",
            "description": "طلب لقطة واحدة من أمام ساندي أو وصف قصير لما أمامها.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_full_mode",
            "description": "تفعيل أو إيقاف الوضع الكامل لساندي.",
            "parameters": {
                "type": "object",
                "properties": {"enabled": {"type": "boolean"}},
                "required": ["enabled"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_camera_status",
            "description": "قراءة حالة الكاميرا الحالية.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_expression",
            "description": "تغيير تعبير وجه ساندي أو حالتها العاطفية لفترة قصيرة أو متوسطة.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string"},
                    "hold_seconds": {"type": "number", "minimum": 0.2, "maximum": 20}
                },
                "required": ["expression"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scan_for_owner",
            "description": "تحريك رقبة ساندي والبحث بصرياً عن المستخدم أو شخص محدد.",
            "parameters": {
                "type": "object",
                "properties": {"target_name": {"type": "string"}},
                "additionalProperties": False
            }
        }
    },
     {
        "type": "function",
        "function": {
            "name": "learn_face",
            "description": "التقاط صورة لشخص يقف أمام الكاميرا وحفظ وجهه باسم محدد.",
            "parameters": {
                "type": "object",
                "properties": {"person_name": {"type": "string"}},
                "required": ["person_name"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_task",
            "description": "حذف مهمة من القائمة نهائياً حسب رقمها.",
            "parameters": {
                "type": "object",
                "properties": {"index": {"type": "integer", "minimum": 1}},
                "required": ["index"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_reminders",
            "description": "عرض جميع التذكيرات المجدولة حالياً.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_reminder",
            "description": "إلغاء وحذف تذكير مجدول حسب رقمه.",
            "parameters": {
                "type": "object",
                "properties": {"index": {"type": "integer", "minimum": 1}},
                "required": ["index"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_photo_to_telegram",
            "description": "التقاط صورة وإرسالها فوراً إلى هاتف المستخدم عبر تليجرام.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scan_room_to_telegram",
            "description": "تحريك رقبة الروبوت لثلاث زوايا مختلفة (يمين، وسط، يسار) والتقاط 3 صور وإرسالها للمستخدم عبر تليجرام لمسح الغرفة.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False}
        }
    },
    ]

BASE_MOTION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "move_base",
            "description": "إرسال أمر حركة إلى قاعدة ساندي إذا كانت الحركة الأرضية مفعلة عبر SANDY_ENABLE_BASE_MOTION=1.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["forward", "backward", "left", "right", "stop"]},
                    "duration_ms": {"type": "integer", "minimum": 150, "maximum": 4000},
                    "speed": {"type": "number", "minimum": 0.1, "maximum": 1.0}
                },
                "required": ["action"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "come_to_user",
            "description": "البحث عن المستخدم بصرياً ثم محاولة الاقتراب منه إذا كانت الحركة الأرضية مفعلة.",
            "parameters": {
                "type": "object",
                "properties": {"target_name": {"type": "string"}},
                "additionalProperties": False
            }
        }
    }
]
SCREEN_HTTP_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "show_text",
            "description": "عرض نص قصير على الشاشة إذا كان مسار HTTP القديم مفعلاً فعليًا.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string", "maxLength": 120}},
                "required": ["text"],
                "additionalProperties": False
            }
        }
    }
]

TOOLS = CORE_TOOLS \
    + (SCREEN_HTTP_TOOLS if (SANDY_COMMAND_MODE == "http" and ENABLE_SCREEN_HTTP) else []) \
    + (BASE_MOTION_TOOLS if ENABLE_BASE_MOTION else [])

DIRECT_CLOUD_COMMANDS = {
    "LOOK_LEFT", "LOOK_RIGHT", "CENTER",
    "FACE_IDLE", "FACE_THINK", "FACE_SPEAK", "FACE_LISTEN", "FACE_ALERT",
    "FACE_HAPPY", "FACE_BIG_HAPPY", "FACE_SURPRISED", "FACE_SLEEPY", "FACE_BORED",
    "FACE_YAWN", "FACE_SAD", "FACE_ANGRY", "FACE_SMIRK", "FACE_CUTE",
    "FACE_EXCITED", "FACE_SHY", "FACE_CONFUSED", "FACE_EMPATHETIC", "FACE_LOVE",
    "FACE_CRY", "FACE_WINK", "FACE_KISS", "FACE_HEART_EYES", "FACE_CALM", "BUZZER_STARTUP",
      "BUZZER_WAKE", "BUZZER_SLEEP", "BUZZER_SAD", "BUZZER_ALERT", "BUZZER_ERROR", "BUZZER_STOP",

}

_state_lock = threading.RLock()
_hardware_io_lock = threading.Lock()
_face_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=128)
_servo_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=64)
_runtime_stop = threading.Event()
_runtime_started = False
_speech_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=8)
_speech_lock = threading.RLock()
_current_player_proc: Optional[subprocess.Popen] = None
_speech_generation = 0

INTERRUPT_PHRASES = {
    "وقف", "وقفي", "اسكت", "اسكتي", "توقفي", "توقف",
    "استني", "لحظة", "انتظر",
    "stop", "wait", "hold on",
}

INTERRUPT_ARM_DELAY_SEC = 0.25
_audio_interrupt_event = threading.Event()
_interrupt_guard_lock = threading.RLock()
_tts_playback_started_at = 0.0


def _request_audio_interrupt():
    _audio_interrupt_event.set()


def _clear_audio_interrupt():
    _audio_interrupt_event.clear()


def _audio_interrupt_requested() -> bool:
    return _audio_interrupt_event.is_set()


def _mark_tts_started():
    global _tts_playback_started_at
    with _interrupt_guard_lock:
        _tts_playback_started_at = time.time()


def _mark_tts_stopped():
    global _tts_playback_started_at
    with _interrupt_guard_lock:
        _tts_playback_started_at = 0.0


def _interrupt_is_armed() -> bool:
    with _interrupt_guard_lock:
        if not _tts_playback_started_at:
            return False
        return (time.time() - _tts_playback_started_at) >= INTERRUPT_ARM_DELAY_SEC


def debug_print(*args):
    if SANDY_DEBUG:
        print(*args)


def normalize_expression(expression: Optional[str]) -> str:
    raw = str(expression or "idle").strip().lower().replace(" ", "_")
    raw = EXPRESSION_ALIASES.get(raw, raw)
    return raw if raw in SUPPORTED_EXPRESSIONS else "idle"


def _queue_face_refresh(force: bool = False):
    try:
        _face_queue.put_nowait({"force": bool(force)})
    except queue.Full:
        pass


def _queue_servo_event(event: Dict[str, Any]):
    try:
        _servo_queue.put_nowait(event)
    except queue.Full:
        pass


def _refresh_expression_expiry_locked(now: Optional[float] = None):
    global current_expression, current_expression_until, current_expression_source
    ts = time.time() if now is None else now
    if current_expression_until and ts >= current_expression_until and not is_speaking:
        current_expression = "idle"
        current_expression_until = 0.0
        current_expression_source = "timer"


def _face_cmd_for_expression(expression: str) -> str:
    mapping = {
        "idle": "FACE_IDLE",
        "happy": "FACE_HAPPY",
        "big_happy": "FACE_BIG_HAPPY",
        "curious": "FACE_LISTEN",
        "think": "FACE_THINK",
        "talk": "FACE_SPEAK",
        "alert": "FACE_ALERT",
        "surprised": "FACE_SURPRISED",
        "sleepy": "FACE_SLEEPY",
        "bored": "FACE_BORED",
        "yawn": "FACE_YAWN",
        "sad": "FACE_SAD",
        "angry": "FACE_ANGRY",
        "smirk": "FACE_SMIRK",
        "cute": "FACE_CUTE",
        "excited": "FACE_EXCITED",
        "shy": "FACE_SHY",
        "confused": "FACE_CONFUSED",
        "empathetic": "FACE_EMPATHETIC",
        "love": "FACE_LOVE",
        "cry": "FACE_CRY",
        "wink": "FACE_WINK",
        "kiss": "FACE_KISS",
        "heart_eyes": "FACE_HEART_EYES",
        "calm": "FACE_CALM",
    }
    return mapping.get(normalize_expression(expression), "FACE_IDLE")


def _desired_face_cmd_locked(now: Optional[float] = None) -> str:
    _refresh_expression_expiry_locked(now)
    overlay_map = {
        "listen": "FACE_LISTEN",
        "think": "FACE_THINK",
        "speak": "FACE_SPEAK",
        "alert": "FACE_ALERT",
    }
    
    # بمجرد أن تتحدث، نعطي الأولوية المطلقة لوجه الكلام المتحرك
    if current_overlay:
        return overlay_map.get(current_overlay, _face_cmd_for_expression(current_expression))
        
    # وعندما تصمت، يظهر تعبير المشاعر
    return _face_cmd_for_expression(current_expression)


def _send_face_cmd_now(face_cmd: str, force: bool = False) -> Optional[str]:
    global _last_face_cmd, _last_face_ts, current_face_cmd
    if not face_cmd:
        return None
    now = time.time()
    if not force and face_cmd == _last_face_cmd and (now - _last_face_ts) < max(0.03, SANDY_FACE_MIN_INTERVAL_SEC):
        return "ok"
    wait_for = SANDY_FACE_MIN_INTERVAL_SEC - (now - _last_face_ts)
    if wait_for > 0:
        time.sleep(wait_for)
    debug_print("DEBUG_FACE_CMD:", face_cmd)
    result = send_esp_cmd(face_cmd)
    debug_print("DEBUG_FACE_RESULT:", result)
    if result:
        _last_face_cmd = face_cmd
        _last_face_ts = time.time()
        current_face_cmd = face_cmd
    return result


def _face_worker():
    while not _runtime_stop.is_set():
        force = False
        try:
            event = _face_queue.get(timeout=0.25)
            if isinstance(event, dict):
                force = bool(event.get("force"))
        except queue.Empty:
            pass
        with _state_lock:
            desired = _desired_face_cmd_locked()
        if desired:
            _send_face_cmd_now(desired, force=force)


def _servo_worker():
    global current_servo_angle
    while not _runtime_stop.is_set():
        try:
            event = _servo_queue.get(timeout=0.25)
        except queue.Empty:
            continue
        try:
            kind = event.get("kind")
            if kind == "angle":
                # فك القفل هنا أيضاً
                angle = int(max(1, min(180, int(event.get("angle", 90)))))
                send_esp_cmd(f"ANGLE_{angle}")
                current_servo_angle = angle
            elif kind == "direction":
                direction = str(event.get("direction", "center")).lower()
                cmd = {"left": "LOOK_LEFT", "right": "LOOK_RIGHT", "center": "CENTER"}.get(direction, "CENTER")
                send_esp_cmd(cmd)
                # تحديث زوايا الاتجاهات لتكون كاملة
                current_servo_angle = {"left": 180, "right": 1, "center": 90}.get(direction, 90)
        except Exception as e:
            print(f"Servo worker error: {e}")


def ensure_runtime_workers():
    global _runtime_started
    if _runtime_started:
        return
    threading.Thread(target=_face_worker, daemon=True, name="sandy-face-worker").start()
    threading.Thread(target=_servo_worker, daemon=True, name="sandy-servo-worker").start()
    threading.Thread(target=_speech_worker, daemon=True, name="sandy-speech-worker").start()
    _runtime_started = True

def _clear_speech_queue():
    while True:
        try:
            _speech_queue.get_nowait()
        except queue.Empty:
            break


def _next_speech_job_id() -> int:
    global _speech_generation
    with _speech_lock:
        _speech_generation += 1
        return _speech_generation


def _is_speech_job_current(job_id: int) -> bool:
    with _speech_lock:
        return job_id == _speech_generation


def interrupt_speaking(clear_queue: bool = True):
    # جمعنا كل المتغيرات هنا في سطر واحد
    global is_speaking, _speech_generation, _active_speech_job_id, _current_player_proc, _last_speech_end_time

    proc = None
    with _speech_lock:
        _speech_generation += 1
        _active_speech_job_id = 0
        is_speaking = False
        _last_speech_end_time = time.time()  # تحديث الوقت فوراً
        proc = _current_player_proc
        _current_player_proc = None

    if clear_queue:
        _clear_speech_queue()

    _clear_audio_interrupt()

    if proc and proc.poll() is None:
        try:
            if os.name != "nt":
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except Exception:
                    proc.kill()
            else:
                proc.kill()
        except Exception:
            pass

    _mark_tts_stopped()
    end_activity("speak", source="tts")
    restore_expression_face(force=True)

    _mark_tts_stopped()
    end_activity("speak", source="tts")
    restore_expression_face(force=True)

def _is_interrupt_text(text: str) -> bool:
    raw = str(text or "").strip().lower()
    if not raw:
        return False

    if raw in INTERRUPT_PHRASES:
        return True

    return any(word in raw.split() for word in INTERRUPT_PHRASES)    

def _mark_tts_started():
    global _tts_playback_started_at
    with _interrupt_guard_lock:
        _tts_playback_started_at = time.time()


def _mark_tts_stopped():
    global _tts_playback_started_at
    with _interrupt_guard_lock:
        _tts_playback_started_at = 0.0


def _interrupt_is_armed() -> bool:
    with _interrupt_guard_lock:
        if not _tts_playback_started_at:
            return False
        return (time.time() - _tts_playback_started_at) >= INTERRUPT_ARM_DELAY_SEC
    
    
def _speech_worker():
    global is_speaking, _active_speech_job_id, _current_player_proc

    while not _runtime_stop.is_set():
        try:
            job = _speech_queue.get(timeout=0.25)
        except queue.Empty:
            continue

        job_id = int(job.get("job_id", 0))
        text = str(job.get("text", "")).strip()
        chat_id = job.get("chat_id")
        send_voice = bool(job.get("send_voice", False))

        if not text or not _is_speech_job_current(job_id):
            continue

        out = BASE_DIR / f"sandy_reply_{job_id}.mp3"

        try:
            _clear_audio_interrupt()

            with _speech_lock:
                _active_speech_job_id = job_id
                is_speaking = True

            print(f"Sandy: {text}")

           # --- بلوك ElevenLabs الفخم لعيون نبيل ---
            try:
                import requests

                if not ELEVENLABS_API_KEY or not ELEVENLABS_VOICE_ID:
                    raise RuntimeError("ELEVENLABS_API_KEY or ELEVENLABS_VOICE_ID missing in .env")

                url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
                
                headers = {
                    "Accept": "audio/mpeg",
                    "Content-Type": "application/json",
                    "xi-api-key": ELEVENLABS_API_KEY
                }
                
                payload = {
                    "text": text,
                    "model_id": "eleven_multilingual_v2", # أفضل موديل للعربي والإنجليزي معاً 🌍
                    "voice_settings": {
                    "stability": 0.35,      # كل ما قللنا هاد، بصير الصوت فيه "نفس" ومشاعر أكتر وأنعم 🎙️
                    "similarity_boost": 0.85, # هاد بيخلي نبرة Bella الأصلية أوضح وأنعم بكتير ✨
                    "style": 0.2,           # بيعطي "دلال" ونعومة في الكلام 💋
                    "use_speaker_boost": True
                }
                }

                response = requests.post(url, json=payload, headers=headers)
                
                if response.status_code == 200:
                    with open(out, "wb") as f:
                        f.write(response.content)
                else:
                    print(f"ElevenLabs Error: {response.status_code} - {response.text}")
                    continue
                    
            except Exception as e:
                print(f"ElevenLabs Connection Error: {e}")
                continue
            # --- نهاية بلوك ElevenLabs --

            begin_activity("speak", source="tts")

            if SANDY_COMMAND_MODE == "http" and ENABLE_SCREEN_HTTP:
                show_text_on_screen(text[:100])

            player = find_player()
            if player and _is_speech_job_current(job_id):
                if os.name != "nt":
                    proc = subprocess.Popen(
                        player + [str(out)],
                        start_new_session=True,
                    )
                else:
                    proc = subprocess.Popen(player + [str(out)])

                with _speech_lock:
                    if _is_speech_job_current(job_id):
                        _current_player_proc = proc
                        _mark_tts_started()
                    else:
                        _current_player_proc = None

                while proc.poll() is None and not _runtime_stop.is_set():
                    time.sleep(0.03)

                    if _audio_interrupt_requested():
                        try:
                            if os.name != "nt":
                                try:
                                    os.killpg(proc.pid, signal.SIGKILL)
                                except Exception:
                                    proc.kill()
                            else:
                                proc.kill()
                        except Exception:
                            pass
                        break

                    if not _is_speech_job_current(job_id):
                        try:
                            if os.name != "nt":
                                try:
                                    os.killpg(proc.pid, signal.SIGKILL)
                                except Exception:
                                    proc.kill()
                            else:
                                proc.kill()
                        except Exception:
                            pass
                        break

                with _speech_lock:
                    if _current_player_proc is proc:
                        _current_player_proc = None

            if send_voice and bot and chat_id and _is_speech_job_current(job_id):
                with open(out, "rb") as vf:
                    bot.send_voice(chat_id, vf)

        except Exception as e:
            print(f"General TTS Worker Error: {e}")

        finally:
            should_clear = False

            with _speech_lock:
                if _active_speech_job_id == job_id:
                    _active_speech_job_id = 0
                    should_clear = True

            if should_clear:
                _mark_tts_stopped()
                _clear_audio_interrupt()
                end_activity("speak", source="tts")
                restore_expression_face(force=True)
                
                with _speech_lock:
                    is_speaking = False
                    global _last_speech_end_time
                    _last_speech_end_time = time.time()

            try:
                if out.exists():
                    out.unlink()
            except Exception:
                pass



def set_expression(expression: str, hold_seconds: float = 0.0, source: str = "system") -> bool:
    global current_expression, current_expression_until, current_expression_source
    expression = normalize_expression(expression)
    with _state_lock:
        current_expression = expression
        current_expression_source = source
        current_expression_until = time.time() + max(0.0, float(hold_seconds or 0.0)) if hold_seconds else 0.0
    _queue_face_refresh(force=True)
    return True


def begin_activity(activity: str, source: str = "system"):
    global current_overlay, current_overlay_source
    with _state_lock:
        current_overlay = str(activity or "").strip().lower()
        current_overlay_source = source
    _queue_face_refresh(force=True)


def end_activity(activity: Optional[str] = None, source: str = "system"):
    global current_overlay, current_overlay_source
    with _state_lock:
        if activity is None or current_overlay == str(activity).strip().lower():
            current_overlay = ""
            current_overlay_source = source
    _queue_face_refresh(force=True)


def restore_expression_face(force: bool = False):
    with _state_lock:
        _refresh_expression_expiry_locked()
    _queue_face_refresh(force=force)


def set_face(face_cmd: str, force: bool = False, source: str = "legacy") -> Optional[str]:
    face_cmd = str(face_cmd or "").strip().upper()
    expression_map = {
        "FACE_IDLE": "idle",
        "FACE_THINK": "think",
        "FACE_SPEAK": "talk",
        "FACE_LISTEN": "curious",
        "FACE_ALERT": "alert",
        "FACE_HAPPY": "happy",
        "FACE_BIG_HAPPY": "big_happy",
        "FACE_SURPRISED": "surprised",
        "FACE_SAD": "sad",
        "FACE_ANGRY": "angry",
        "FACE_SMIRK": "smirk",
        "FACE_CUTE": "cute",
        "FACE_EXCITED": "excited",
        "FACE_SHY": "shy",
        "FACE_CONFUSED": "confused",
    }
    if face_cmd in expression_map:
        set_expression(expression_map[face_cmd], source=source)
        return "ok"
    return _send_face_cmd_now(face_cmd, force=force)


def _heuristic_behavior_plan(user_text: str, reply_text: str) -> Dict[str, Any]:
    text = f"{user_text}\n{reply_text}".lower()
    expression = "idle"
    hold_seconds = 1.8
    if any(k in text for k in ["نكت", "مضحك", "اضحك", "ضحك", "هههه", "haha", "lol"]):
        expression = "big_happy"
        hold_seconds = 3.0
    elif any(k in text for k in ["زعلان", "حزين", "مقهور", "تعبان", "موجوع", "مدايق", "مكتئب", "sad"]):
        expression = "sad"
        hold_seconds = 3.0
    elif any(k in text for k in ["مصدوم", "مش معقول", "مفاج", "surprise"]):
        expression = "surprised"
        hold_seconds = 2.2
    elif any(k in text for k in ["بحبك", "يا روحي", "شكرا", "يسلمو", "thanks", "thank you"]):
        expression = "cute"
        hold_seconds = 2.0
    elif any(k in text for k in ["ليش", "كيف", "وين", "شو", "مين", "مش فاهم", "confused"]):
        expression = "curious"
        hold_seconds = 1.6
    elif any(k in text for k in ["متحمس", "يلا", "هيا", "خلينا", "ممتاز", "روع"]):
        expression = "excited"
        hold_seconds = 2.3
    return {"expression": expression, "hold_seconds": hold_seconds}


def infer_behavior_plan(user_text: str, reply_text: str) -> Dict[str, Any]:
    prompt = {
        "role": "system",
        "content": (
            "حلل الحالة العاطفية التفاعلية لساندي. أعد JSON فقط بالمفاتيح: expression و hold_seconds. "
            "expression يجب أن تكون واحدة من: idle,happy,big_happy,curious,think,talk,alert,surprised,sleepy,bored,yawn,sad,angry,smirk,cute,excited,shy,confused. "
            "اختر تعبيرًا يناسب مضمون كلام المستخدم وطبيعة رد ساندي. إذا لا يوجد شيء واضح اختر idle. hold_seconds رقم بين 0 و 8. لا تضف أي نص خارج JSON."
        ),
    }
    try:
        resp = client.chat.completions.create(
            model=SANDY_BEHAVIOR_MODEL,
            messages=[prompt, {"role": "user", "content": f"USER:\n{user_text}\n\nASSISTANT:\n{reply_text}"}],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        raw = (resp.choices[0].message.content or "{}").strip()
        data = json.loads(raw)
        expression = normalize_expression(data.get("expression"))
        hold_seconds = max(0.0, min(8.0, float(data.get("hold_seconds", 1.8))))
        return {"expression": expression, "hold_seconds": hold_seconds}
    except Exception as e:
        debug_print(f"Behavior planner fallback: {e}")
        return _heuristic_behavior_plan(user_text, reply_text)


def apply_behavior_plan(user_text: str, reply_text: str):
    plan = infer_behavior_plan(user_text, reply_text)
    expression = normalize_expression(plan.get("expression"))
    hold_seconds = float(plan.get("hold_seconds", 1.8))
    if expression and expression != "talk":
        set_expression(expression, hold_seconds=hold_seconds, source="planner")

# =========================
# Utilities
# =========================
def load_json(path: Path, default: Any):
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path: Path, data: Any):
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_session_memory() -> List[Dict[str, str]]:
    return load_json(SESSION_FILE, [])


def append_memory(role: str, content: str):
    memory = get_session_memory()
    memory.append({"role": role, "content": content, "ts": now_str()})
    memory = memory[-14:]
    save_json(SESSION_FILE, memory)


def build_memory_text() -> str:
    memory = get_session_memory()
    if not memory:
        return "لا يوجد سياق سابق محفوظ."
    lines = []
    for item in memory[-10:]:
        lines.append(f"[{item.get('ts','')}] {item['role']}: {item['content']}")
    return "\n".join(lines)


def _normalize_plan_item(item: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(item, dict):
        return None

    # الصيغة الجديدة
    if "text" in item:
        text = str(item.get("text", "")).strip()
        if not text:
            return None
        return {
            "id": str(item.get("id") or uuid.uuid4()),
            "text": text,
            "done": bool(item.get("done", False)),
            "created_at": str(item.get("created_at") or item.get("time") or now_str()),
            "completed_at": item.get("completed_at"),
        }

    # الصيغة القديمة
    task_text = str(item.get("task", "")).strip()
    if not task_text:
        return None

    status = str(item.get("status", "pending")).strip().lower()
    done = status in {"done", "completed", "complete", "true", "1"}

    return {
        "id": str(item.get("id") or uuid.uuid4()),
        "text": task_text,
        "done": done,
        "created_at": str(item.get("time") or item.get("created_at") or now_str()),
        "completed_at": item.get("completed_at") if done else None,
    }


def plans() -> List[Dict[str, Any]]:
    raw = load_json(PLAN_FILE, [])
    if not isinstance(raw, list):
        raw = []

    normalized: List[Dict[str, Any]] = []
    changed = False

    for item in raw:
        norm = _normalize_plan_item(item)
        if norm:
            normalized.append(norm)
            if norm != item:
                changed = True
        else:
            changed = True

    if changed:
        save_json(PLAN_FILE, normalized)

    return normalized


def save_plans(data: List[Dict[str, Any]]):
    normalized: List[Dict[str, Any]] = []
    for item in data:
        norm = _normalize_plan_item(item)
        if norm:
            normalized.append(norm)
    save_json(PLAN_FILE, normalized)


def _normalize_reminder_item(item: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(item, dict):
        return None

    text = str(item.get("text") or item.get("task") or item.get("message") or "").strip()
    when = str(item.get("when") or item.get("time") or item.get("at") or "").strip()

    if not text or not when:
        return None

    try:
        datetime.strptime(when, "%Y-%m-%d %H:%M")
    except ValueError:
        return None

    return {
        "id": str(item.get("id") or uuid.uuid4()),
        "text": text,
        "when": when,
    }


def reminders() -> List[Dict[str, Any]]:
    raw = load_json(REMINDERS_FILE, [])
    if not isinstance(raw, list):
        raw = []

    normalized: List[Dict[str, Any]] = []
    changed = False

    for item in raw:
        norm = _normalize_reminder_item(item)
        if norm:
            normalized.append(norm)
            if norm != item:
                changed = True
        else:
            changed = True

    if changed:
        save_json(REMINDERS_FILE, normalized)

    return normalized


def save_reminders(data: List[Dict[str, Any]]):
    normalized: List[Dict[str, Any]] = []
    for item in data:
        norm = _normalize_reminder_item(item)
        if norm:
            normalized.append(norm)
    save_json(REMINDERS_FILE, normalized)


def find_player() -> Optional[List[str]]:
    for candidate in (["afplay"], ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"], ["mpg123"]):
        if shutil.which(candidate[0]):
            return candidate
    return None

# =========================
# Arduino IoT Cloud helpers
# =========================
_arduino_token_cache: Dict[str, Any] = {"token": "", "expires_at": 0.0}
_arduino_properties_cache: Dict[str, Dict[str, Any]] = {}

def _arduino_enabled() -> bool:
    return bool(ARDUINO_CLIENT_ID and ARDUINO_CLIENT_SECRET and SANDY_DEVICE_ID)

def _arduino_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {_arduino_token_cache.get('token', '')}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

def _arduino_get_token() -> Optional[str]:
    now = time.time()
    token = _arduino_token_cache.get("token", "")
    if token and now < float(_arduino_token_cache.get("expires_at", 0)) - 30:
        return token
    if not _arduino_enabled():
        return None
    try:
        r = requests.post(
            "https://api2.arduino.cc/iot/v1/clients/token",
            data={
                "grant_type": "client_credentials",
                "client_id": ARDUINO_CLIENT_ID,
                "client_secret": ARDUINO_CLIENT_SECRET,
                "audience": "https://api2.arduino.cc/iot",
            },
            headers={"content-type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        token = data.get("access_token", "")
        if token:
            _arduino_token_cache["token"] = token
            _arduino_token_cache["expires_at"] = now + int(data.get("expires_in", 3600))
            return token
    except Exception as e:
        print(f"Arduino token error: {e}")
    return None

def _arduino_list_properties(device_id: str) -> Any:
    if not _arduino_get_token() or not device_id:
        return []
    try:
        r = requests.get(
            f"https://api2.arduino.cc/iot/v2/devices/{device_id}/properties",
            headers=_arduino_headers(),
            params={"show_deleted": "false"},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"Arduino list properties error: {e}")
        return []

def _arduino_property_map(device_id: str, refresh: bool = False) -> Dict[str, Dict[str, Any]]:
    cache_key = device_id or "default"
    cached = _arduino_properties_cache.get(cache_key)
    if cached and not refresh and time.time() - float(cached.get("ts", 0)) < 300:
        return cached.get("map", {})

    props = _arduino_list_properties(device_id)
    debug_print("DEBUG_PROPS_RAW:", props)

    items = []
    if isinstance(props, list):
        items = props
    elif isinstance(props, dict):
        for key in ("data", "properties", "results", "items"):
            value = props.get(key)
            if isinstance(value, list):
                items = value
                break

    mapping: Dict[str, Dict[str, Any]] = {}
    for p in items:
        if not isinstance(p, dict):
            continue
        for raw_name in [p.get("name"), p.get("variable_name"), p.get("variableName"), p.get("identifier")]:
            name = str(raw_name or "").strip()
            if name:
                mapping[name] = p

    debug_print("DEBUG_PROP_KEYS:", list(mapping.keys()))
    _arduino_properties_cache[cache_key] = {"ts": time.time(), "map": mapping}
    return mapping

def _arduino_read_property(device_id: str, prop_name: str) -> Any:
    prop = _arduino_property_map(device_id).get(prop_name)
    if not prop:
        return None
    return prop.get("last_value", prop.get("value"))

def _arduino_update_properties(device_id: str, values: Dict[str, Any]) -> bool:
    if not _arduino_get_token() or not device_id or not values:
        return False

    headers = _arduino_headers()
    if ARDUINO_ORG_ID:
        headers["X-Organization"] = ARDUINO_ORG_ID

    prop_map = _arduino_property_map(device_id, refresh=True)
    ok = True

    for name, value in values.items():
        prop = prop_map.get(name)
        if not prop:
            print(f"Arduino property missing: {name}")
            ok = False
            continue

        permission = str(prop.get("permission") or prop.get("permissions") or "").upper()
        if permission in {"READ", "READ_ONLY", "READONLY"}:
            debug_print(f"Skipping READ-only property: {name}")
            ok = False
            continue

        prop_id = str(prop.get("id", "")).strip()
        thing_id = str(prop.get("thing_id") or prop.get("thingId") or SANDY_THING_ID).strip()
        if not prop_id:
            print(f"Arduino property id missing for: {name}")
            ok = False
            continue

        try:
            if thing_id:
                r = requests.put(
                    f"https://api2.arduino.cc/iot/v2/things/{thing_id}/properties/{prop_id}/publish",
                    headers=headers,
                    json={"value": value},
                    timeout=10,
                )
            else:
                r = requests.put(
                    f"https://api2.arduino.cc/iot/v2/devices/{device_id}/properties",
                    headers=headers,
                    json={"properties": [{"name": name, "value": value}]},
                    timeout=10,
                )
            r.raise_for_status()
            debug_print(f"DEBUG_PUBLISH_OK [{name}] status={r.status_code}")
        except Exception as e:
            print(f"Arduino publish property error [{name}]: {e}")
            ok = False

    if ok:
        _arduino_property_map(device_id, refresh=True)
    return ok

def _send_cloud_body_command(cmd: str) -> Optional[str]:
    cmd = (cmd or "").strip()
    if not _arduino_enabled():
        return None

    center = 90

    if cmd.startswith("ANGLE_"):
        try:
            angle = int(cmd.split("_", 1)[1])
        except Exception:
            return None
        return "ok" if _arduino_update_properties(SANDY_DEVICE_ID, {"servoAngle": angle}) else None

    mapping = {
        "LOOK_LEFT": {"servoAngle": center + 30},
        "LOOK_RIGHT": {"servoAngle": center - 30},
        "CENTER": {"servoAngle": center},
        "FACE_IDLE": {"moodState": "idle"},
        "FACE_THINK": {"moodState": "think"},
        "FACE_SPEAK": {"moodState": "talk"},
        "FACE_LISTEN": {"moodState": "curious"},
        "FACE_ALERT": {"moodState": "alert"},
        "FACE_HAPPY": {"moodState": "happy"},
        "FACE_BIG_HAPPY": {"moodState": "big_happy"},
        "FACE_SURPRISED": {"moodState": "surprised"},
        "FACE_SLEEPY": {"moodState": "sleepy"},
        "FACE_BORED": {"moodState": "bored"},
        "FACE_YAWN": {"moodState": "yawn"},
        "FACE_SAD": {"moodState": "sad"},
        "FACE_ANGRY": {"moodState": "angry"},
        "FACE_SMIRK": {"moodState": "smirk"},
        "FACE_CUTE": {"moodState": "cute"},
        "FACE_EXCITED": {"moodState": "excited"},
        "FACE_SHY": {"moodState": "shy"},
        "FACE_CONFUSED": {"moodState": "confused"},
        "FACE_EMPATHETIC": {"moodState": "empathetic"},
        "FACE_LOVE": {"moodState": "love"},
        "FACE_CRY": {"moodState": "cry"},
        "FACE_WINK": {"moodState": "wink"},
        "FACE_KISS": {"moodState": "kiss"},
        "FACE_HEART_EYES": {"moodState": "heart_eyes"},
        "FACE_CALM": {"moodState": "calm"},
        "BUZZER_STARTUP": {"buzzerCommand": "startup"},
        "BUZZER_WAKE": {"buzzerCommand": "wake"},
        "BUZZER_SLEEP": {"buzzerCommand": "sleep"},
        "BUZZER_SAD": {"buzzerCommand": "sad"},
        "BUZZER_ALERT": {"buzzerCommand": "alert"},
        "BUZZER_ERROR": {"buzzerCommand": "error"},
        "BUZZER_STOP": {"buzzerCommand": "stop"},
    }

    values = mapping.get(cmd)
    return "ok" if values and _arduino_update_properties(SANDY_DEVICE_ID, values) else None

# =========================
# ESP32 helpers
# =========================
def esp_base() -> str:
    return f"http://{SANDY_IP}" if SANDY_IP else ""


def _request_with_retries(method: str, url: str, *, retries: Optional[int] = None, delay_sec: Optional[float] = None, **kwargs):
    max_tries = max(1, int(retries or NETWORK_RETRY_COUNT))
    sleep_s = max(0.1, float(delay_sec or NETWORK_RETRY_DELAY_SEC))
    last_err = None
    for attempt in range(max_tries):
        try:
            return requests.request(method.upper(), url, **kwargs)
        except Exception as e:
            last_err = e
            if attempt < max_tries - 1:
                time.sleep(sleep_s)
    if last_err:
        raise last_err
    raise RuntimeError("request failed without explicit exception")


def send_esp_cmd(cmd: str) -> Optional[str]:
    global last_esp_ok

    http_allowed = (SANDY_COMMAND_MODE == "http") and bool(SANDY_IP)
    cloud_allowed = (SANDY_COMMAND_MODE == "cloud")

    with _hardware_io_lock:
        if http_allowed:
            for attempt in range(max(1, NETWORK_RETRY_COUNT)):
                try:
                    r = _request_with_retries(
                        "GET",
                        f"{esp_base()}/cmd",
                        retries=1,
                        delay_sec=NETWORK_RETRY_DELAY_SEC,
                        params={"cmd": cmd},
                        timeout=3,
                    )
                    r.raise_for_status()
                    last_esp_ok = True
                    return r.text.strip()
                except Exception as e:
                    last_esp_ok = False
                    if attempt < max(1, NETWORK_RETRY_COUNT) - 1:
                        time.sleep(NETWORK_RETRY_DELAY_SEC)
                    else:
                        print(f"ESP HTTP Command Error [{cmd}]: {e}")
                        return None

        result = None
        if cloud_allowed:
            for attempt in range(max(1, NETWORK_RETRY_COUNT)):
                result = _send_cloud_body_command(cmd)
                if result:
                    break
                if attempt < max(1, NETWORK_RETRY_COUNT) - 1:
                    time.sleep(NETWORK_RETRY_DELAY_SEC)
        last_esp_ok = bool(result)
        return result


def show_text_on_screen(text: str) -> bool:
    if SANDY_COMMAND_MODE != "http":
        debug_print("Screen text skipped: main board is running in cloud mode.")
        return False
    if not ENABLE_SCREEN_HTTP or not SANDY_IP:
        debug_print("Screen text skipped: HTTP screen path disabled.")
        return False
    try:
        r = requests.post(f"{esp_base()}/show_text", data=text.encode("utf-8"), timeout=2)
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"Screen text error: {e}")
        return False


def get_distance_value() -> Optional[int]:
    if SANDY_IP and SANDY_COMMAND_MODE == "http":
        try:
            r = _request_with_retries("GET", f"{esp_base()}/distance", retries=NETWORK_RETRY_COUNT, delay_sec=NETWORK_RETRY_DELAY_SEC, timeout=2)
            r.raise_for_status()
            return int(float(str(r.text).strip()))
        except Exception as e:
            print(f"Distance HTTP error: {e}")
            return None

    value = _arduino_read_property(SANDY_DEVICE_ID, "distanceCm")
    try:
        return int(float(value)) if value is not None else None
    except Exception:
        return None


def _send_base_motion_command(action: str, duration_ms: int = 800, speed: float = 0.5) -> bool:
    """
    إرسال أمر حركة إلى قاعدة ساندي عبر Arduino IoT Cloud.
    تستخدم نظام الجدولة لإرسال أمر 'stop' تلقائياً بعد انتهاء المدة.
    """
    if not ENABLE_BASE_MOTION:
        print("⚠️ الحركة الأرضية معطلة في ملف .env (SANDY_ENABLE_BASE_MOTION)")
        return False

    if not _arduino_enabled():
        print("⚠️ اتصال Arduino IoT Cloud غير مفعّل.")
        return False

    action = action.strip().lower()
    # التحقق من صحة الأمر
    if action not in {"forward", "backward", "left", "right", "stop"}:
        print(f"⚠️ أمر حركة غير صالح: {action}")
        return False

    print(f"🤖 Sending move command to Cloud: {action} for {duration_ms}ms")
    
    # إرسال أمر الحركة الحقيقي إلى المتغير السحابي baseAction
    move_ok = _arduino_update_properties(SANDY_DEVICE_ID, {"baseAction": action})

    if not move_ok:
        print("❌ فشل إرسال أمر الحركة إلى Cloud")
        return False

    # إذا لم يكن الأمر "stop"، نجدول أمر "stop" ليرسل تلقائياً بعد فترة
    if action != "stop":
        stop_delay_sec = duration_ms / 1000.0
        
        # إنشاء معرف فريد للمهمة لتجنب التداخل
        job_id = f'stop_motion_{uuid.uuid4()}'
        
        # جدولة أمر الإيقاف في المستقبل باستخدام APScheduler
        scheduler.add_job(
            _arduino_update_properties,
            trigger='date',
            run_date=datetime.now() + timedelta(seconds=stop_delay_sec),
            args=[SANDY_DEVICE_ID, {"baseAction": "stop"}],
            id=job_id,
            replace_existing=False
        )
        debug_print(f"Scheduled stop command in {stop_delay_sec}s (Job ID: {job_id})")
    
    return True


# =========================
# Camera / vision
# =========================
def get_cam_snapshot_url() -> Optional[str]:
    config = _camera_runtime_config()
    token = str(config.get("snapshot_token", "")).strip() or str(config.get("control_token", "")).strip()
    if CAM_IP and token:
        return f"http://{CAM_IP}/snapshot?token={token}"
    if CAM_IP:
        return f"http://{CAM_IP}/snapshot"
    return None


def _camera_auth_tuple(cam_cfg: Dict[str, Any]) -> Tuple[str, str]:
    user = str(cam_cfg.get("http_user", CAM_HTTP_USER_DEFAULT) or CAM_HTTP_USER_DEFAULT)
    password = str(cam_cfg.get("http_pass", CAM_HTTP_PASS_DEFAULT) or CAM_HTTP_PASS_DEFAULT)
    return user, password


def _camera_control_token(cam_cfg: Dict[str, Any]) -> str:
    return str(cam_cfg.get("control_token", CAM_CONTROL_TOKEN_DEFAULT) or CAM_CONTROL_TOKEN_DEFAULT)


def capture_and_describe_impl() -> str:
    snap_url = get_cam_snapshot_url()
    if not snap_url:
        return "الكاميرا غير مضبوطة أو غير متصلة."

    cam_cfg = _camera_runtime_config()
    cam_auth = _camera_auth_tuple(cam_cfg)

    if sandy_camera and hasattr(sandy_camera, "open_eyes"):
        try:
            sandy_camera.open_eyes()
        except Exception as e:
            print(f"Camera wake warning: {e}")

    try:
        # جرس الإيقاظ
        requests.get(snap_url, auth=cam_auth, timeout=3)
    except Exception:
        pass
        
    time.sleep(2.0)
        
    try:
        img_response = requests.get(snap_url, auth=cam_auth, timeout=10)
        img_response.raise_for_status()
        img_bytes = img_response.content
    except Exception as e:
        print(f"Camera fetch Error: {e}")
        if not _is_full_mode_active() and sandy_camera and hasattr(sandy_camera, "close_eyes"):
            try:
                sandy_camera.close_eyes()
            except Exception:
                pass
        return "ما قدرت أسحب الصورة من الكاميرا."

    if not _is_full_mode_active():
        _schedule_camera_auto_close(CAM_EYE_AUTO_CLOSE_SEC)

    prompt = "صفي لي ما ترينه في هذه الصورة باختصار شديد (جملة أو جملتين) وباللهجة الشامية. ركزي على الأشياء البارزة."

    if GEMINI_API_KEY:
        try:
            vision_model = genai.GenerativeModel(GEMINI_MODEL_NAME)
            image_part = {"mime_type": "image/jpeg", "data": img_bytes}
            response = vision_model.generate_content([prompt, image_part])
            if response.text:
                return response.text.strip()
        except Exception as e:
            print(f"Gemini Vision failed: {e}")

    try:
        import base64
        base64_image = base64.b64encode(img_bytes).decode('utf-8')
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}", "detail": "low"}}
                ]
            }],
            max_tokens=150
        )
        return (resp.choices[0].message.content or "شفت الصورة بس ما قدرت أوصفها.").strip()
    except Exception as e:
        return "للأسف السيرفرات مشغولة وما قدرت أحلل الصورة حالياً."
    


# =========================
# Tasks / reminders
# =========================
def add_task_impl(text: str) -> str:
    data = plans()
    item = {"id": str(uuid.uuid4()), "text": text.strip(), "done": False, "created_at": now_str()}
    data.append(item)
    save_plans(data)
    return f"أضفت المهمة: {text.strip()}"


def list_tasks_impl() -> str:
    data = plans()
    active = [t for t in data if not t.get("done")]
    if not active:
        return "ما عندك مهام حالياً."
    lines = [f"{i+1}) {t['text']}" for i, t in enumerate(active)]
    return "مهامك الحالية:\n" + "\n".join(lines)


def complete_task_impl(index: int) -> str:
    data = plans()
    active = [t for t in data if not t.get("done")]
    if index < 1 or index > len(active):
        return "رقم المهمة غير صحيح."
    target_id = active[index - 1]["id"]
    for task in data:
        if task["id"] == target_id:
            task["done"] = True
            task["completed_at"] = now_str()
            save_plans(data)
            return f"تم إنجاز المهمة: {task['text']}"
    return "لم أتمكن من تحديث المهمة."


def reminder_job(text: str):
    msg = f"تذكير: {text}"
    begin_activity("alert", source="reminder")
    set_expression("alert", hold_seconds=5.0, source="reminder")
    if SANDY_COMMAND_MODE == "http" and ENABLE_SCREEN_HTTP:
        show_text_on_screen(msg[:100])
    send_esp_cmd("BUZZER_ALERT")
    speak(msg, chat_id=int(SANDY_USER_CHAT_ID) if SANDY_USER_CHAT_ID.isdigit() else None, send_voice=bool(bot and SANDY_USER_CHAT_ID.isdigit()))
    if bot and SANDY_USER_CHAT_ID.isdigit():
        try:
            bot.send_message(int(SANDY_USER_CHAT_ID), msg)
        except Exception as e:
            print(f"Telegram reminder send error: {e}")
    end_activity("alert", source="reminder")
    restore_expression_face(force=True)


def add_reminder_impl(text: str, when: str) -> str:
    try:
        dt = datetime.strptime(when.strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        return "صيغة الوقت غير صحيحة. استخدم YYYY-MM-DD HH:MM"

    if dt <= datetime.now():
        return "وقت التذكير يجب أن يكون في المستقبل."

    reminder_id = str(uuid.uuid4())
    scheduler.add_job(
        reminder_job,
        trigger=DateTrigger(run_date=dt),
        args=[text],
        id=reminder_id,
        replace_existing=True,
    )
    data = reminders()
    data.append({"id": reminder_id, "text": text.strip(), "when": when.strip()})
    save_reminders(data)
    return f"تم ضبط التذكير: {text} عند {when}"


def delete_task_impl(index: int) -> str:
    data = plans()
    active = [t for t in data if not t.get("done")]
    if index < 1 or index > len(active):
        return "رقم المهمة غير صحيح."
    target_id = active[index - 1]["id"]
    new_data = [t for t in data if t["id"] != target_id]
    save_plans(new_data)
    return "تم حذف المهمة بنجاح."

def list_reminders_impl() -> str:
    data = reminders()
    if not data:
        return "ما عندك تذكيرات مبرمجة حالياً."
    lines = [f"{i+1}) {r['text']} - الساعة: {r['when']}" for i, r in enumerate(data)]
    return "تذكيراتك المجدولة:\n" + "\n".join(lines)

def delete_reminder_impl(index: int) -> str:
    data = reminders()
    if index < 1 or index > len(data):
        return "رقم التذكير غير صحيح."
    target_id = data[index - 1]["id"]
    try:
        scheduler.remove_job(target_id) # حذف المنبه من النظام
    except Exception:
        pass
    new_data = [r for r in data if r["id"] != target_id]
    save_reminders(new_data)
    return "تم إلغاء التذكير وحذفه بنجاح."   


def restore_reminders():
    valid_items: List[Dict[str, Any]] = []

    for item in reminders():
        try:
            dt = datetime.strptime(item["when"], "%Y-%m-%d %H:%M")
            if dt > datetime.now():
                scheduler.add_job(
                    reminder_job,
                    trigger=DateTrigger(run_date=dt),
                    args=[item["text"]],
                    id=item["id"],
                    replace_existing=True,
                )
                valid_items.append(item)
        except Exception as e:
            print(f"Restore reminder failed: {e}")

    save_reminders(valid_items)

# =========================
# Speech / audio
# =========================


def speak(text: str, chat_id: Optional[int] = None, send_voice: bool = False):
    text = (text or "").strip()
    if not text:
        return

    job_id = _next_speech_job_id()
    _clear_speech_queue()

    job = {
        "job_id": job_id,
        "text": text,
        "chat_id": chat_id,
        "send_voice": bool(send_voice),
    }

    try:
        _speech_queue.put_nowait(job)
    except queue.Full:
        _clear_speech_queue()
        try:
            _speech_queue.put_nowait(job)
        except queue.Full:
            print("Speech queue is full, dropping speech job.")


def _listen_microphone_once(
    *,
    timeout: float,
    phrase_time_limit: float,
    adjust_duration: float,
    show_face: bool,
) -> Optional[str]:
    try:
        with sr.Microphone() as source:
            if adjust_duration and adjust_duration > 0:
                recognizer.adjust_for_ambient_noise(source, duration=adjust_duration)

            if show_face:
                begin_activity("listen", source="mic")

            audio = recognizer.listen(
                source,
                timeout=timeout,
                phrase_time_limit=phrase_time_limit,
            )

        if show_face:
            begin_activity("think", source="mic")

        text = recognizer.recognize_google(audio, language="ar").strip()
        return text or None

    except sr.WaitTimeoutError:
        return None
    except sr.UnknownValueError:
        return None
    except Exception as e:
        print(f"Mic error: {e}")
        return None
    finally:
        if show_face:
            end_activity(source="mic")
            restore_expression_face(force=True)


def listen_once() -> Optional[str]:
    return _listen_microphone_once(
        timeout=LISTEN_TIMEOUT,
        phrase_time_limit=LISTEN_PHRASE_LIMIT,
        adjust_duration=0.4,
        show_face=True,
    )


def listen_for_interrupt_phrase() -> bool:
    heard = _listen_microphone_once(
        timeout=0.45,
        phrase_time_limit=0.9,
        adjust_duration=0.0,
        show_face=False,
    )

    if not heard:
        return False

    raw = heard.strip()

    if len(raw.split()) > 3:
        return False

    return _is_interrupt_text(raw)

# =========================
# Tool implementations
# =========================
def move_neck_impl(direction: Optional[str] = None, angle: Optional[int] = None) -> str:
    if angle is not None:
        # فك القفل: السماح بالزوايا من 1 إلى 180
        safe_angle = int(max(1, min(180, int(angle))))
        _queue_servo_event({"kind": "angle", "angle": safe_angle})
        return f"تمام، بحرك رقبتي على {safe_angle} درجة."
    desired = (direction or "center").strip().lower()
    if desired not in {"left", "right", "center"}:
        desired = "center"
    _queue_servo_event({"kind": "direction", "direction": desired})
    return "تمام، بحرك رقبتي."


def get_distance_impl() -> str:
    value = get_distance_value()
    if value is None:
        return "لم أتمكن من قراءة المسافة حالياً."
    return f"المسافة الحالية تقريباً {value} سم."


def show_text_impl(text: str) -> str:
    if SANDY_COMMAND_MODE != "http" or not ENABLE_SCREEN_HTTP:
        return "ميزة عرض النص على الشاشة غير مفعلة في الوضع الحالي."
    ok = show_text_on_screen(text)
    return "تم عرض النص على الشاشة." if ok else "لم أتمكن من عرض النص على الشاشة."


def set_expression_impl(expression: str, hold_seconds: float = 0.0) -> str:
    expression = normalize_expression(expression)
    set_expression(expression, hold_seconds=float(hold_seconds or 0.0), source="tool")
    return f"تمام، غيرت تعبيري إلى {expression}."


def open_eyes_impl() -> str:
    if sandy_camera and hasattr(sandy_camera, "open_eyes"):
        ok = sandy_camera.open_eyes()
        if ok:
            restore_expression_face(force=True)
            _schedule_camera_auto_close(CAM_EYE_AUTO_CLOSE_SEC)
        return "فتحت عيوني." if ok else "ما قدرت أفتح عيوني حالياً."
    return "وحدة الكاميرا غير جاهزة داخل البايثون."


def close_eyes_impl() -> str:
    if sandy_camera and hasattr(sandy_camera, "close_eyes"):
        ok = sandy_camera.close_eyes()
        return "سكرت عيوني." if ok else "ما قدرت أسكر عيوني حالياً."
    return "وحدة الكاميرا غير جاهزة داخل البايثون."


def _is_full_mode_active() -> bool:
    if not sandy_camera or not hasattr(sandy_camera, "get_remote_status"):
        return False
    try:
        status = sandy_camera.get_remote_status()
        if isinstance(status, dict):
            return bool(status.get("fullModeEnabled"))
    except Exception:
        return False
    return False


def _camera_auto_close_job():
    if _is_full_mode_active():
        return
    if sandy_camera and hasattr(sandy_camera, "close_eyes"):
        try:
            sandy_camera.close_eyes()
        except Exception as e:
            print(f"Camera auto-close warning: {e}")


def _schedule_camera_auto_close(seconds: Optional[int] = None):
    delay = int(seconds or CAM_EYE_AUTO_CLOSE_SEC)
    try:
        scheduler.remove_job(CAM_AUTO_CLOSE_JOB_ID)
    except Exception:
        pass
    scheduler.add_job(
        _camera_auto_close_job,
        trigger=DateTrigger(run_date=datetime.fromtimestamp(time.time() + delay)),
        id=CAM_AUTO_CLOSE_JOB_ID,
        replace_existing=True,
    )


def _cancel_camera_auto_close():
    try:
        scheduler.remove_job(CAM_AUTO_CLOSE_JOB_ID)
    except Exception:
        pass


def look_ahead_impl() -> str:
    try:
        begin_activity("think", source="vision")
        if sandy_camera and hasattr(sandy_camera, "look_ahead"):
            result = sandy_camera.look_ahead(speak_func=None)
            if isinstance(result, str) and result.strip():
                return f"شفت قدامي: {result.strip()}"
            return "شفت اللي قدامي."
        return capture_and_describe_impl()
    finally:
        end_activity("think", source="vision")
        restore_expression_face(force=True)


def _capture_snapshot_frame(cam_auth: Tuple[str, str], snap_url: str, timeout: float = 10.0) -> Optional[bytes]:
    for attempt in range(max(1, NETWORK_RETRY_COUNT)):
        try:
            response = _request_with_retries(
                "GET",
                snap_url,
                retries=1,
                delay_sec=NETWORK_RETRY_DELAY_SEC,
                auth=cam_auth,
                timeout=timeout,
            )
            response.raise_for_status()
            if len(response.content) < 2048:
                return None
            return response.content
        except Exception:
            if attempt < max(1, NETWORK_RETRY_COUNT) - 1:
                time.sleep(NETWORK_RETRY_DELAY_SEC)
            else:
                raise


def _camera_health_ok() -> bool:
    snap_url = get_cam_snapshot_url()
    if not snap_url:
        return False
    cam_cfg = _camera_runtime_config()
    cam_auth = _camera_auth_tuple(cam_cfg)
    for _ in range(max(1, HEALTH_CHECK_RETRIES)):
        try:
            payload = _capture_snapshot_frame(cam_auth, snap_url, timeout=3.0)
            if payload:
                return True
        except Exception:
            time.sleep(0.4)
    return False


def _esp_health_ok() -> bool:
    if SANDY_COMMAND_MODE == "http":
        if not SANDY_IP:
            return False
        try:
            r = _request_with_retries("GET", f"{esp_base()}/distance", retries=HEALTH_CHECK_RETRIES, delay_sec=0.5, timeout=2)
            r.raise_for_status()
            return True
        except Exception:
            return False

    if SANDY_COMMAND_MODE == "cloud":
        if not _arduino_enabled() or not _arduino_get_token():
            return False
        for _ in range(max(1, HEALTH_CHECK_RETRIES)):
            try:
                _arduino_property_map(SANDY_DEVICE_ID, refresh=True)
                value = _arduino_read_property(SANDY_DEVICE_ID, "servoAngle")
                if value is not None:
                    return True
            except Exception:
                pass
            time.sleep(0.5)
    return False


def _esp_hard_reboot() -> bool:
    if not REQUEST_ALLOW_HARD_REBOOT:
        return False
    if not CAM_IP:
        return False

    reboot_url = f"http://{CAM_IP}/control"
    token = _camera_control_token(_camera_runtime_config())
    params = {"action": "reboot"}
    if token:
        params["token"] = token

    try:
        r = _request_with_retries(
            "GET",
            reboot_url,
            retries=2,
            delay_sec=0.5,
            params=params,
            timeout=4,
            auth=_camera_auth_tuple(_camera_runtime_config()),
        )
        if r is not None:
            try:
                r.raise_for_status()
            except Exception:
                pass
        return True
    except Exception as e:
        print(f"ESP reboot error: {e}")
        return False


def _infer_required_resources(text: str) -> Dict[str, bool]:
    low = str(text or "").lower()
    camera_cues = ["صو", "صورة", "تصوير", "بانوراما", "فيديو", "كاميرا", "عيون", "امسح", "مسح"]
    esp_cues = ["لف", "زاوية", "رقبة", "سيرفو", "بازر", "buzzer", "حساس", "مسافة", "distance", "وجه", "screen"]
    return {
        "camera": any(c in low for c in camera_cues),
        "esp": any(c in low for c in esp_cues),
    }


def _wait_resources_ready(text: str) -> Tuple[bool, Optional[str]]:
    needed = _infer_required_resources(text)
    if not needed["camera"] and not needed["esp"]:
        return (True, None)

    reboot_attempted = False
    max_cycles = max(1, REQUEST_RESCHEDULE_MAX)

    for cycle in range(max_cycles + 1):
        cam_ok = True if not needed["camera"] else _camera_health_ok()
        esp_ok = True if not needed["esp"] else _esp_health_ok()
        if cam_ok and esp_ok:
            return (True, None)

        problems: List[str] = []
        if needed["camera"] and not cam_ok:
            problems.append("الكاميرا")
        if needed["esp"] and not esp_ok:
            problems.append("ESP32")
        reason = " و ".join(problems) if problems else "الموارد"

        if cycle < max_cycles - 1:
            time.sleep(REQUEST_RESCHEDULE_DELAY_SEC * (cycle + 1))
            continue

        if not reboot_attempted and REQUEST_ALLOW_HARD_REBOOT and (needed["camera"] or needed["esp"]):
            if _esp_hard_reboot():
                reboot_attempted = True
                time.sleep(REQUEST_REBOOT_SETTLE_SEC)
                continue

        return (False, reason)

    return (False, "الموارد")


def _wait_for_servo_angle(target_angle: int, timeout_sec: float = 8.0, stable_reads: int = 2) -> bool:
    safe_target = int(max(1, min(180, int(target_angle))))
    deadline = time.time() + max(1.5, float(timeout_sec))
    consecutive_matches = 0

    while time.time() < deadline:
        if _arduino_enabled():
            cloud_angle = _arduino_read_property(SANDY_DEVICE_ID, "servoAngle")
            try:
                if cloud_angle is not None and abs(int(cloud_angle) - safe_target) <= 2:
                    consecutive_matches += 1
                    if consecutive_matches >= max(1, int(stable_reads)):
                        return True
                else:
                    consecutive_matches = 0
            except Exception:
                consecutive_matches = 0
        else:
            if abs(int(current_servo_angle) - safe_target) <= 2:
                consecutive_matches += 1
                if consecutive_matches >= max(1, int(stable_reads)):
                    return True
            else:
                consecutive_matches = 0
        time.sleep(0.12)

    return False


def _wait_camera_motion_settled(
    cam_auth: Tuple[str, str],
    snap_url: str,
    max_wait_sec: float = 7.0,
    require_motion: bool = False,
) -> bool:
    try:
        cv2 = __import__("cv2")
        np = __import__("numpy")
    except Exception:
        return False

    deadline = time.time() + max(1.5, float(max_wait_sec))
    prev_gray = None
    moving_observed = False
    stable_count = 0
    diff_threshold = 4.5

    while time.time() < deadline:
        try:
            frame_bytes = _capture_snapshot_frame(cam_auth, snap_url, timeout=3.0)
            if not frame_bytes:
                time.sleep(0.15)
                continue
            buf = np.frombuffer(frame_bytes, dtype=np.uint8)
            img = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
            if img is None:
                time.sleep(0.15)
                continue
        except Exception:
            time.sleep(0.15)
            continue

        if prev_gray is None:
            prev_gray = img
            time.sleep(0.12)
            continue

        diff = cv2.absdiff(prev_gray, img)
        mean_diff = float(diff.mean())
        prev_gray = img

        if mean_diff > diff_threshold:
            moving_observed = True
            stable_count = 0
        else:
            stable_count += 1

        if moving_observed and stable_count >= 3:
            return True
        if (not require_motion) and (not moving_observed) and stable_count >= 5:
            return True

        time.sleep(0.12)

    return False


def _move_neck_and_wait(angle: int, wait_sec: float = 1.0):
    global current_servo_angle
    safe_angle = int(max(1, min(180, int(angle))))
    send_esp_cmd(f"ANGLE_{safe_angle}")
    reached = _wait_for_servo_angle(safe_angle, timeout_sec=max(1.2, float(wait_sec) * 3.2), stable_reads=2)
    if reached:
        current_servo_angle = safe_angle
        return

    current_servo_angle = safe_angle
    time.sleep(max(0.15, float(wait_sec) * 0.3))


def _capture_sweep_frames(
    cam_auth: Tuple[str, str],
    snap_url: str,
    start_angle: int,
    end_angle: int,
    *,
    step: int = 12,
    settle_sec: float = 0.35,
) -> List[bytes]:
    frames: List[bytes] = []
    start = int(max(1, min(180, start_angle)))
    end = int(max(1, min(180, end_angle)))
    stride = max(1, int(step))

    if start <= end:
        points = list(range(start, end + 1, stride))
        if points[-1] != end:
            points.append(end)
    else:
        points = list(range(start, end - 1, -stride))
        if points[-1] != end:
            points.append(end)

    for angle in points:
        _move_neck_and_wait(angle, wait_sec=settle_sec)
        try:
            frame = _capture_snapshot_frame(cam_auth, snap_url, timeout=8)
            if frame:
                frames.append(frame)
        except Exception as e:
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            if status_code == 423 and sandy_camera and hasattr(sandy_camera, "open_eyes"):
                print(f"Sweep frame 423 at angle {angle}, waking camera and retrying...")
                try:
                    sandy_camera.open_eyes()
                    time.sleep(0.8)
                    retry_frame = _capture_snapshot_frame(cam_auth, snap_url, timeout=8)
                    if retry_frame:
                        frames.append(retry_frame)
                        continue
                except Exception as retry_error:
                    print(f"Sweep retry failed at angle {angle}: {retry_error}")
            print(f"Sweep frame error at angle {angle}: {e}")

    return frames


def _compute_panorama_angles(
    start_angle: int,
    end_angle: int,
    shots: int = 3,
    edge_margin: int = 14,
    include_edges: bool = True,
) -> List[int]:
    start = int(max(1, min(180, start_angle)))
    end = int(max(1, min(180, end_angle)))
    count = max(2, int(shots))

    lo = min(start, end)
    hi = max(start, end)
    margin = 0 if include_edges else max(0, int(edge_margin))
    if (hi - lo) <= (margin * 2):
        margin = 0

    inner_lo = lo + margin
    inner_hi = hi - margin
    if inner_hi <= inner_lo:
        inner_lo, inner_hi = lo, hi

    if count == 1:
        return [int(round((inner_lo + inner_hi) / 2.0))]

    step = float(inner_hi - inner_lo) / float(count - 1)
    points = [int(round(inner_lo + (i * step))) for i in range(count)]

    # Preserve order and keep unique angles only.
    seen = set()
    unique_points = []
    for p in points:
        clamped = int(max(1, min(180, p)))
        if clamped in seen:
            continue
        seen.add(clamped)
        unique_points.append(clamped)

    return unique_points


def _capture_panorama_frames(
    cam_auth: Tuple[str, str],
    snap_url: str,
    *,
    start_angle: int,
    end_angle: int,
    shots: int = 3,
    settle_sec: float = 0.32,
) -> List[bytes]:
    frames: List[bytes] = []
    angles = _compute_panorama_angles(start_angle, end_angle, shots=shots, include_edges=True)
    print(f"Panorama angles: {angles}")
    previous_target = None

    for angle in angles:
        needs_motion = previous_target is None or abs(int(angle) - int(previous_target)) >= 4
        _move_neck_and_wait(angle, wait_sec=settle_sec)

        # Confirm hardware-reported servo angle when available.
        if _arduino_enabled():
            _wait_for_servo_angle(angle, timeout_sec=2.0, stable_reads=3)

        # Additional visual confirmation to ensure servo movement settled before capture.
        settled = _wait_camera_motion_settled(
            cam_auth,
            snap_url,
            max_wait_sec=2.1,
            require_motion=needs_motion,
        )
        if needs_motion and (not settled):
            # Retry one more settle cycle to avoid taking a frame while still moving.
            _move_neck_and_wait(angle, wait_sec=max(0.38, float(settle_sec)))
            _wait_camera_motion_settled(cam_auth, snap_url, max_wait_sec=1.2, require_motion=False)
        try:
            frame = _capture_snapshot_frame(cam_auth, snap_url, timeout=8)
            if frame:
                frames.append(frame)
                previous_target = angle
        except Exception as e:
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            if status_code == 423 and sandy_camera and hasattr(sandy_camera, "open_eyes"):
                try:
                    sandy_camera.open_eyes()
                    time.sleep(0.7)
                    retry_frame = _capture_snapshot_frame(cam_auth, snap_url, timeout=8)
                    if retry_frame:
                        frames.append(retry_frame)
                        continue
                except Exception as retry_error:
                    print(f"Panorama retry failed at angle {angle}: {retry_error}")
            print(f"Panorama frame error at angle {angle}: {e}")

    return frames


def _build_scan_video(frames: List[bytes], output_base_path: Path, fps: int = 8) -> Optional[Path]:
    if not frames:
        return None

    try:
        cv2 = __import__("cv2")
        np = __import__("numpy")
    except Exception as e:
        print(f"Video build dependency error: {e}")
        return None

    first_frame = None
    for frame_bytes in frames:
        buffer = np.frombuffer(frame_bytes, dtype=np.uint8)
        image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
        if image is not None:
            first_frame = image
            break

    if first_frame is None:
        return None

    height, width = first_frame.shape[:2]
    candidates = [
        ("MJPG", ".avi"),
        ("XVID", ".avi"),
    ]

    for codec, ext in candidates:
        out_path = output_base_path.with_suffix(ext)
        try:
            if out_path.exists():
                out_path.unlink(missing_ok=True)
            fourcc = cv2.VideoWriter_fourcc(*codec)
            writer = cv2.VideoWriter(str(out_path), fourcc, float(max(1, fps)), (width, height))
            if not writer.isOpened():
                continue

            try:
                for frame_bytes in frames:
                    buffer = np.frombuffer(frame_bytes, dtype=np.uint8)
                    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
                    if image is None:
                        continue
                    if image.shape[1] != width or image.shape[0] != height:
                        image = cv2.resize(image, (width, height))
                    writer.write(image)
            finally:
                writer.release()

            if out_path.exists() and out_path.stat().st_size > 4096:
                return out_path
        except Exception as e:
            print(f"Video build fallback error [{codec}{ext}]: {e}")
            try:
                out_path.unlink(missing_ok=True)
            except Exception:
                pass

    return None


def _build_panorama_image(frames: List[bytes], output_base_path: Path) -> Optional[Path]:
    if not frames or len(frames) < 2:
        return None

    try:
        cv2 = __import__("cv2")
        np = __import__("numpy")
    except Exception as e:
        print(f"Panorama dependency error: {e}")
        return None

    images = []
    for frame_bytes in frames:
        try:
            buffer = np.frombuffer(frame_bytes, dtype=np.uint8)
            image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
            if image is not None:
                images.append(image)
        except Exception:
            pass

    if len(images) < 2:
        return None

    # Reverse visual order: first captured frame on the right, next frames to its left.
    ordered_images = list(reversed(images))

    panorama = None

    # Prefer true stitching so output appears as one coherent panorama.
    try:
        stitcher = cv2.Stitcher_create(cv2.Stitcher_PANORAMA)
        status, stitched = stitcher.stitch(ordered_images)
        if status == 0 and stitched is not None and stitched.size > 0:
            panorama = stitched
    except Exception as e:
        print(f"Panorama stitch warning: {e}")

    # Fallback: blended horizontal join if stitcher fails.
    if panorama is None:
        base_height = ordered_images[0].shape[0]
        base_width = ordered_images[0].shape[1]
        norm_images = []
        for img in ordered_images:
            if img.shape[0] != base_height or img.shape[1] != base_width:
                img = cv2.resize(img, (base_width, base_height), interpolation=cv2.INTER_LINEAR)
            norm_images.append(img)

        overlap_ratio = 0.14
        overlap_px = int(max(12, min(base_width - 1, base_width * overlap_ratio)))
        panorama_width = (base_width * len(norm_images)) - (overlap_px * (len(norm_images) - 1))
        blend = np.zeros((base_height, panorama_width, 3), dtype=np.float32)
        weight = np.zeros((base_height, panorama_width, 1), dtype=np.float32)

        x_offset = 0
        for img in norm_images:
            left = x_offset
            right = x_offset + base_width
            blend[:, left:right, :] += img.astype(np.float32)
            weight[:, left:right, :] += 1.0
            x_offset += (base_width - overlap_px)

        weight[weight == 0.0] = 1.0
        panorama = (blend / weight).clip(0, 255).astype(np.uint8)

    # Keep panorama dimensions within Telegram limits.
    max_width = 9000
    max_height = 4500
    if panorama.shape[1] > max_width or panorama.shape[0] > max_height:
        scale = min(
            float(max_width) / float(max(1, panorama.shape[1])),
            float(max_height) / float(max(1, panorama.shape[0])),
        )
        new_w = max(1, int(panorama.shape[1] * scale))
        new_h = max(1, int(panorama.shape[0] * scale))
        panorama = cv2.resize(panorama, (new_w, new_h), interpolation=cv2.INTER_AREA)

    out_path = output_base_path.with_suffix(".jpg")
    try:
        cv2.imwrite(str(out_path), panorama, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if out_path.exists() and out_path.stat().st_size > 4096:
            return out_path
    except Exception as e:
        print(f"Panorama save error: {e}")

    return None


def _camera_keep_awake_begin(allow_full_mode: bool = True) -> bool:
    if not sandy_camera:
        return False
    if not allow_full_mode:
        return False
    if _is_full_mode_active():
        return False
    if hasattr(sandy_camera, "enable_full_mode"):
        try:
            sandy_camera.enable_full_mode()
            return True
        except Exception as e:
            print(f"Camera keep-awake begin warning: {e}")
    return False


def _camera_keep_awake_end(was_enabled: bool):
    if not sandy_camera or not was_enabled:
        return
    if hasattr(sandy_camera, "disable_full_mode"):
        try:
            sandy_camera.disable_full_mode()
        except Exception as e:
            print(f"Camera keep-awake end warning: {e}")


def set_full_mode_impl(enabled: bool) -> str:
    enabled = bool(enabled)
    cam_ok = False
    if sandy_camera:
        try:
            if enabled and hasattr(sandy_camera, "enable_full_mode"):
                sandy_camera.enable_full_mode()
                cam_ok = True
            elif (not enabled) and hasattr(sandy_camera, "disable_full_mode"):
                sandy_camera.disable_full_mode()
                cam_ok = True
        except Exception as e:
            print(f"Full mode camera error: {e}")
    body_ok = _arduino_update_properties(SANDY_DEVICE_ID, {"autonomousMode": enabled}) if _arduino_enabled() else False
    set_expression("alert" if enabled else "idle", hold_seconds=3.0 if enabled else 0.0, source="mode")
    restore_expression_face(force=True)
    if cam_ok or body_ok:
        return "فعّلت الوضع الكامل." if enabled else "وقفت الوضع الكامل."
    return "ما قدرت أغيّر الوضع الكامل حالياً."


def get_camera_status_impl() -> str:
    if sandy_camera and hasattr(sandy_camera, "get_remote_status"):
        try:
            status = sandy_camera.get_remote_status()
            return json.dumps(status, ensure_ascii=False) if isinstance(status, dict) else str(status)
        except Exception as e:
            return f"تعذر قراءة حالة الكاميرا: {e}"
    return "وحدة الكاميرا غير جاهزة داخل البايثون."


def _owner_visible_from_text(text: str, target_name: str) -> bool:
    raw = str(text or "").lower()
    needles = [target_name.lower(), "نبيل", "nabeel", "وجه", "person", "شخص"]
    return any(n in raw for n in needles)


def scan_for_owner_impl(target_name: Optional[str] = None) -> str:
    target_name = (target_name or behavior_context.get("last_seen_name") or "نبيل").strip() or "نبيل"
    behavior_context["camera_search_enabled"] = True
    set_expression("curious", hold_seconds=5.0, source="scan")
    findings: List[str] = []
    for direction in ("center", "left", "right", "center"):
        _queue_servo_event({"kind": "direction", "direction": direction})
        time.sleep(0.55)
        seen = look_ahead_impl()
        findings.append(f"{direction}: {seen}")
        if _owner_visible_from_text(seen, target_name):
            behavior_context["owner_visible"] = True
            behavior_context["last_seen_name"] = target_name
            set_expression("happy", hold_seconds=3.0, source="scan")
            return f"أيوه، أظن إني شايف {target_name}. {seen}"
    behavior_context["owner_visible"] = False
    return f"مسحت المكان بس لسا ما تأكدت إني شايف {target_name}.\n" + "\n".join(findings[-3:])


def learn_face_impl(person_name: str) -> str:
    if sandy_camera and hasattr(sandy_camera, "learn_new_face"):
        begin_activity("think", source="vision")
        set_expression("curious", hold_seconds=4.0, source="tool")
        ok, msg = sandy_camera.learn_new_face(person_name)
        if ok:
            set_expression("happy", hold_seconds=3.0, source="tool")
        end_activity("think", source="vision")
        restore_expression_face(force=True)
        return msg
    return "وحدة الكاميرا غير جاهزة لحفظ الوجوه."


def move_base_impl(action: str, duration_ms: int = 700, speed: float = 0.6) -> str:
    action = str(action or "stop").strip().lower()
    duration_ms = int(max(150, min(4000, int(duration_ms or 700))))
    # السرعة لا تستخدم حالياً في الأردوينو البسيط لكننا نحتفظ بها للتحسين مستقبلاً
    speed = float(max(0.1, min(1.0, float(speed or 0.6))))
    
    if not ENABLE_BASE_MOTION:
        return "الحركة الأرضية معطلة حالياً من الإعدادات."
        
    begin_activity("alert", source="motion") # تغيير تعبير الوجه للتنبيه أثناء الحركة
    
    # استدعاء الدالة الفعالة
    ok = _send_base_motion_command(action, duration_ms=duration_ms, speed=speed)
    
    # لا ننهي النشاط هنا لأن أمر الإيقاف مجدول وسيتم استعادة الوجه تلقائياً
    
    if ok:
        if action == "stop":
            return "تمام، وقفت الحركة."
        return f"تمام، عم أتحرك {action} لمدة {duration_ms} مللي ثانية."
    else:
        end_activity("alert", source="motion")
        return "صار مشكلة وما قدرت أبعت أمر الحركة للروبوت."

def come_to_user_impl(target_name: Optional[str] = None) -> str:
    target_name = (target_name or behavior_context.get("last_seen_name") or "نبيل").strip() or "نبيل"
    
    # أولاً، نبحث عن المستخدم بصرياً
    scan_result = scan_for_owner_impl(target_name=target_name)
    
    if not ENABLE_BASE_MOTION:
        return scan_result + "\n(بس الحركة الأرضية معطلة بالإعدادات، ما بقدر أقرب)."

    # إذا وجدناه، نتحرك للأمام قليلاً
    if behavior_context.get("owner_visible"):
        # نتحرك للأمام لمدة ثانية واحدة بسرعة متوسطة
        ok = _send_base_motion_command("forward", duration_ms=1000, speed=0.5)
        if ok:
            return scan_result + "\nأوكي شفتك، عم قرب عليك!"
        else:
            return scan_result + "\nشفتك، بس فشل إرسال أمر الحركة."
            
    return scan_result + "\nقرب شوي عشان أشوفك أوضح وأقدر أجيك."


def send_photo_to_telegram_impl() -> str:
    if not bot or not SANDY_USER_CHAT_ID.isdigit():
        return "مش قادرة أبعت الصورة، إعدادات التليجرام مش جاهزة."
    
    snap_url = get_cam_snapshot_url()
    if not snap_url:
        return "الكاميرا مش متصلة."
        
    cam_cfg = _camera_runtime_config()
    cam_auth = _camera_auth_tuple(cam_cfg)

    _cancel_camera_auto_close()
    # Photo capture is short; keep full_mode off to match normal open-eyes behavior.
    keep_awake = _camera_keep_awake_begin(allow_full_mode=False)

    if sandy_camera and hasattr(sandy_camera, "open_eyes"):
        try:
            sandy_camera.open_eyes()
        except Exception as e:
            print(f"Camera wake warning: {e}")

    try:
        # الطلب الأول: بمثابة "جرس" ليوقظ الكاميرا إذا كانت نائمة
        requests.get(snap_url, auth=cam_auth, timeout=3)
    except Exception:
        pass
        
    time.sleep(2.0) # نعطيها وقت تصحى وتضبط إضاءتها
    
    try:
        # الطلب الحقيقي للصورة
        img = requests.get(snap_url, auth=cam_auth, timeout=10)
        img.raise_for_status()
        
        if len(img.content) < 2048:
            return "الصورة طلعت سودة أو خربانة، شكل الكاميرا لسا بتصحى."
            
        bot.send_photo(int(SANDY_USER_CHAT_ID), img.content, caption="هي الصورة يا روحي! 📸")
        msg = "صورت وبعتلك الصورة عالتليجرام."
    except Exception as e:
        print(f"❌ Telegram Photo Error: {e}")
        msg = "صار مشكلة وما قدرت أبعت الصورة."

    _camera_keep_awake_end(keep_awake)
    if not _is_full_mode_active():
        _schedule_camera_auto_close(CAM_EYE_AUTO_CLOSE_SEC)
        
    return msg


def scan_room_to_telegram_impl(use_video: bool = False) -> str:
    if not bot or not SANDY_USER_CHAT_ID.isdigit():
        return "مش قادرة أبعت النتيجة حالياً."
    
    cam_cfg = _camera_runtime_config()
    cam_auth = _camera_auth_tuple(cam_cfg)

    _cancel_camera_auto_close()
    # Full mode is only needed for longer video scans; panorama stays in normal mode.
    keep_awake = _camera_keep_awake_begin(allow_full_mode=bool(use_video))

    if sandy_camera and hasattr(sandy_camera, "open_eyes"):
        try:
            sandy_camera.open_eyes()
        except Exception as e:
            print(f"Camera wake warning: {e}")

    previous_angle_raw = _arduino_read_property(SANDY_DEVICE_ID, "servoAngle") if _arduino_enabled() else None
    try:
        previous_angle = int(max(1, min(180, int(previous_angle_raw)))) if previous_angle_raw is not None else int(max(1, min(180, int(current_servo_angle))))
    except Exception:
        previous_angle = int(max(1, min(180, int(current_servo_angle))))
    start_angle, mid_angle, end_angle = 1, 90, 180
    mode_label = "فيديو قصير" if use_video else "بانوراما"
    bot.send_message(int(SANDY_USER_CHAT_ID), f"جاري مسح الغرفة... ثواني وببعتلك {mode_label} 🕵️‍♀️")
    
    snap_url = get_cam_snapshot_url()
    if snap_url:
        try:
            # جرس الإيقاظ
            requests.get(snap_url, auth=cam_auth, timeout=3)
        except Exception:
            pass
            
    time.sleep(2.0)

    frames: List[bytes] = []
    if snap_url:
        if use_video:
            _move_neck_and_wait(start_angle, wait_sec=1.0)
            frames.extend(_capture_sweep_frames(cam_auth, snap_url, start_angle, mid_angle, step=12, settle_sec=0.2))
            frames.extend(_capture_sweep_frames(cam_auth, snap_url, mid_angle, end_angle, step=12, settle_sec=0.2))
        else:
            frames.extend(_capture_panorama_frames(
                cam_auth,
                snap_url,
                start_angle=start_angle,
                end_angle=end_angle,
                shots=4,
                settle_sec=0.32,
            ))

    _move_neck_and_wait(previous_angle, wait_sec=1.8)

    video_base_path = Path(tempfile.gettempdir()) / f"sandy_room_scan_{int(time.time())}"
    video_path: Optional[Path] = None
    panorama_path: Optional[Path] = None
    if frames:
        if use_video:
            video_path = _build_scan_video(frames, video_base_path, fps=10)
        else:
            panorama_path = _build_panorama_image(frames, video_base_path)

    if not video_path and not panorama_path:
        _camera_keep_awake_end(keep_awake)
        if not _is_full_mode_active() and sandy_camera and hasattr(sandy_camera, "close_eyes"):
            try:
                sandy_camera.close_eyes()
            except Exception:
                pass
        return "حاولت أمسح الغرفة، لكن ما قدرت أجهز فيديو أو بانوراما."

    msg = None
    if video_path:
        try:
            with open(video_path, "rb") as video_file:
                try:
                    bot.send_video(int(SANDY_USER_CHAT_ID), video_file, caption="هي مسحة سريعة للغرفة بالفيديو! 🎬")
                    msg = "خلصت المسح وبعتلك فيديو قصير للغرفة عالتليجرام."
                except Exception:
                    video_file.seek(0)
                    bot.send_document(int(SANDY_USER_CHAT_ID), video_file, caption="هي مسحة الغرفة (ملف فيديو).")
                    msg = "خلصت المسح وبعتلك الفيديو كملف عالتليجرام."
        except Exception as e:
            print(f"Telegram video send error: {e}")
            msg = "فشل إرسال الفيديو."
        finally:
            try:
                video_path.unlink(missing_ok=True)
            except Exception:
                pass
    elif panorama_path:
        try:
            with open(panorama_path, "rb") as pano_file:
                bot.send_photo(int(SANDY_USER_CHAT_ID), pano_file, caption="هذي بانوراما الغرفة! 🏞️")
                msg = "خلصت المسح وبعتلك بانوراما الغرفة عالتليجرام."
        except Exception as e:
            print(f"Telegram panorama send error: {e}")
            try:
                with open(panorama_path, "rb") as pano_file:
                    bot.send_document(int(SANDY_USER_CHAT_ID), pano_file, caption="هذي بانوراما الغرفة (ملف صورة).")
                msg = "خلصت المسح وبعتلك البانوراما كملف عالتليجرام."
            except Exception as doc_e:
                print(f"Telegram panorama document fallback error: {doc_e}")
                msg = "فشل إرسال البانوراما."
        finally:
            try:
                panorama_path.unlink(missing_ok=True)
            except Exception:
                pass
    else:
        msg = "ما قدرت أنتج أي شي."

    _camera_keep_awake_end(keep_awake)
    if not _is_full_mode_active():
        _schedule_camera_auto_close(CAM_EYE_AUTO_CLOSE_SEC)
    return msg

FUNCTION_MAP = {
    "move_neck": lambda **kw: move_neck_impl(**kw),
    "get_distance": lambda **kw: get_distance_impl(),
    "show_text": lambda **kw: show_text_impl(**kw),
    "capture_and_describe": lambda **kw: capture_and_describe_impl(),
    "open_eyes": lambda **kw: open_eyes_impl(),
    "close_eyes": lambda **kw: close_eyes_impl(),
    "look_ahead": lambda **kw: look_ahead_impl(),
    "set_full_mode": lambda **kw: set_full_mode_impl(**kw),
    "get_camera_status": lambda **kw: get_camera_status_impl(**kw),
    "add_task": lambda **kw: add_task_impl(**kw),
    "list_tasks": lambda **kw: list_tasks_impl(**kw),
    "complete_task": lambda **kw: complete_task_impl(**kw),
    "add_reminder": lambda **kw: add_reminder_impl(**kw),
    "set_expression": lambda **kw: set_expression_impl(**kw),
    "scan_for_owner": lambda **kw: scan_for_owner_impl(**kw),
    "move_base": lambda **kw: move_base_impl(**kw),
    "come_to_user": lambda **kw: come_to_user_impl(**kw),
    "learn_face": lambda **kw: learn_face_impl(**kw),
    "delete_task": lambda **kw: delete_task_impl(**kw),
    "list_reminders": lambda **kw: list_reminders_impl(),
    "delete_reminder": lambda **kw: delete_reminder_impl(**kw),
    "send_photo_to_telegram": lambda **kw: send_photo_to_telegram_impl(),
    "scan_room_to_telegram": lambda **kw: scan_room_to_telegram_impl(),
}

# =========================
# LLM orchestration
# =========================
def build_messages(user_text: str) -> List[Dict[str, Any]]:
    recalled = memory_recall(user_text) if user_text else ""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"الوقت الحالي: {now_str()}"},
        {"role": "system", "content": "سياق المحادثة القصير:\n" + build_memory_text()},
    ]
    if recalled:
        messages.append({"role": "system", "content": "ذاكرة بعيدة ذات صلة:\n" + recalled})
    messages.append({"role": "user", "content": user_text})
    return messages


def _classify_user_intent_ai(text: str) -> Tuple[str, float]:
    content = str(text or "").strip()
    if not content:
        return ("query", 0.5)

    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Classify the Arabic user text intent for a home robot. "
                        "Return strict JSON only with keys: intent, confidence. "
                        "intent must be one of: command, query, statement, mixed. "
                        "Rules: command=execution request. query=asking/explaining. "
                        "statement=narration/report with no execution request. mixed=contains both."
                    ),
                },
                {"role": "user", "content": content},
            ],
            temperature=0,
            max_tokens=40,
        )
        raw = (resp.choices[0].message.content or "").strip()
        data = json.loads(raw)
        intent = str(data.get("intent", "query")).strip().lower()
        confidence = float(data.get("confidence", 0.0))
        if intent not in {"command", "query", "statement", "mixed"}:
            intent = "query"
        confidence = max(0.0, min(1.0, confidence))
        return (intent, confidence)
    except Exception:
        # Conservative fallback: prefer non-execution when uncertain.
        if _looks_like_explanatory_query(content):
            return ("query", 0.7)
        if _has_action_command_cue(content):
            return ("command", 0.55)
        return ("statement", 0.6)


def _openai_chat_only_agent(user_text: str) -> str:
    messages = build_messages(user_text)
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.4,
            max_tokens=450,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"OpenAI Chat-only Error: {e}")
        return ""


def _requires_tool(text: str) -> bool:
    global _GEMINI_DISABLED

    intent, confidence = _classify_user_intent_ai(text)
    if intent == "command":
        return True
    if intent == "mixed":
        return confidence >= 0.45
    # query/statement should never force tool execution.
    return False

    try:
        # سؤال صريح ومباشر لجيميناي لتصنيف الجملة
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"""أنت نظام تصنيف دقيق لروبوت منزلي.
        اقرأ الجملة التالية من المستخدم: "{text}"
        هل المستخدم يطلب تنفيذ "مهمة أو أمر" (مثل تحريك الروبوت، فتح الكاميرا، التقاط صورة، حفظ وجه، إضافة تذكير، قراءة المسافة) أم أنه يطرح سؤالاً عاماً أو يدردش؟
        - إذا كان يطلب تنفيذ مهمة/أمر، أجب فقط بكلمة "COMMAND".
        - إذا كانت مجرد دردشة أو سؤال عام (مثل كيف حالك، من أنت، ماذا تعرف، كيف تعمل)، أجب فقط بكلمة "CHAT".
        """
        response = model.generate_content(prompt)
        result = response.text.strip().upper()
        
        if "COMMAND" in result:
            return True
        return False
        
    except Exception as e:
        error_text = str(e)
        if "API_KEY_INVALID" in error_text or "API key not valid" in error_text:
            _GEMINI_DISABLED = True
            print("Router warning: Gemini disabled because the API key is invalid.")
        else:
            print(f"Router Error: {e}")
        # إذا حصل خطأ في جيميناي، نرسل للـ OpenAI كخطة بديلة
        return True

def _gemini_chat_agent(user_text: str) -> str:
    global _GEMINI_DISABLED
    try:
        # إعطاء جيميناي شخصية ساندي والذاكرة
        sys_prompt = SYSTEM_PROMPT + "\n\nسياق المحادثة:\n" + build_memory_text()
        model = genai.GenerativeModel('gemini-2.5-flash', system_instruction=sys_prompt)
        response = model.generate_content(user_text)
        return response.text.strip()
    except Exception as e:
        error_text = str(e)
        if "API_KEY_INVALID" in error_text or "API key not valid" in error_text:
            _GEMINI_DISABLED = True
            print("Gemini Chat disabled because the API key is invalid.")
        else:
            print(f"Gemini Chat Error: {e}")
        return ""
    

def run_agent(user_text: str) -> str:
    append_memory("user", user_text)

    # توجيه الطلب: هل هو أمر (OpenAI) أم دردشة (Gemini)؟
    is_cmd = _requires_tool(user_text)

    if not is_cmd:
        if GEMINI_API_KEY and not _GEMINI_DISABLED:
            print("🧠 Routing to Gemini (Free Chat)...")
            answer = _gemini_chat_agent(user_text)
            if answer:
                append_memory("assistant", answer)
                try:
                    summarize_and_store(user_text, answer)
                except Exception:
                    pass
                return answer
            print("⚠️ Gemini chat failed, falling back to OpenAI chat-only...")

        answer = _openai_chat_only_agent(user_text)
        if answer:
            append_memory("assistant", answer)
            try:
                summarize_and_store(user_text, answer)
            except Exception:
                pass
            return answer

    print("⚙️ Routing to OpenAI (Tools/Command)...")
    messages = build_messages(user_text)

    direct_tool_outputs: List[str] = []
    direct_tool_names = {
        "open_eyes",
        "close_eyes",
        "capture_and_describe",
        "send_photo_to_telegram",
        "scan_room_to_telegram",
        "look_ahead",
    }

    for _ in range(4):
        try:
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
            )
            msg = resp.choices[0].message
        except Exception as e:
            print(f"OpenAI Error: {e}")
            break

        if getattr(msg, "tool_calls", None):
            messages.append(msg)
            for tc in msg.tool_calls:
                fn_name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except Exception:
                    args = {}
                fn = FUNCTION_MAP.get(fn_name)
                if not fn:
                    tool_result = "الأداة المطلوبة غير موجودة."
                else:
                    try:
                        tool_result = fn(**args)
                    except Exception as e:
                        tool_result = f"Tool error: {e}"
                if fn_name in direct_tool_names and isinstance(tool_result, str) and tool_result.strip():
                    direct_tool_outputs.append(tool_result.strip())
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_result,
                })
            continue

        answer = (msg.content or "").strip()
        if direct_tool_outputs:
            answer = "\n".join(dict.fromkeys(direct_tool_outputs))
        if answer:
            append_memory("assistant", answer)
            try:
                summarize_and_store(user_text, answer)
            except Exception as e:
                print(f"Memory store warning: {e}")
            return answer

    fallback = "صار عندي تشابك داخلي بسيط. جرب احكيلي الطلب مرة ثانية بشكل أقصر."
    if direct_tool_outputs:
        fallback = "\n".join(dict.fromkeys(direct_tool_outputs))
    append_memory("assistant", fallback)
    return fallback


# =========================
# Telegram
# =========================
def should_handle_chat(chat_id: int) -> bool:
    if not SANDY_USER_CHAT_ID:
        return True
    return str(chat_id) == SANDY_USER_CHAT_ID


def convert_ogg_to_wav(src: Path, dst: Path):
    audio = AudioSegment.from_file(src)
    audio.export(dst, format="wav")


def _request_worker_loop():
    while True:
        item = _request_queue.get()
        _request_busy.set()
        try:
            text = str(item.get("text") or "").strip()
            chat_id = item.get("chat_id")
            send_voice = bool(item.get("send_voice", True))
            if not text:
                continue

            ready, reason = _wait_resources_ready(text)
            if not ready:
                if bot and isinstance(chat_id, int):
                    bot.send_message(chat_id, f"الطلب تأجل/فشل مؤقتاً لأن {reason} أوفلاين. جرّب بعد لحظات.")
                continue

            reply = handle_user_text(text, chat_id=chat_id, speak_reply=False)

            if bot and isinstance(chat_id, int):
                bot.send_message(chat_id, reply)
                if send_voice:
                    speak(reply, chat_id=chat_id, send_voice=True)
        except Exception as e:
            try:
                chat_id = item.get("chat_id")
                if bot and isinstance(chat_id, int):
                    bot.send_message(chat_id, f"صار خطأ أثناء تنفيذ الطلب: {e}")
            except Exception:
                pass
        finally:
            _request_queue.task_done()
            if _request_queue.empty():
                _request_busy.clear()


def enqueue_user_request(text: str, chat_id: int, send_voice: bool = True) -> str:
    global _request_worker_started

    text = str(text or "").strip()
    if not text:
        return "ما وصلني طلب واضح."

    with _request_worker_lock:
        queue_size_before = _request_queue.qsize()
        _request_queue.put({"text": text, "chat_id": int(chat_id), "send_voice": bool(send_voice)})

        if not _request_worker_started:
            worker = threading.Thread(target=_request_worker_loop, daemon=True)
            worker.start()
            _request_worker_started = True

    if _request_busy.is_set() or queue_size_before > 0:
        if queue_size_before == 0:
            return "ماشي، ضفت طلبك بالدور التالي وحنفذه بعد ما تخلص المهمة الحالية."
        position = queue_size_before + 1
        return f"ماشي، ضفت طلبك بالدور رقم {position} وحنفذه بعد ما تخلص المهمة الحالية."
    return "ماشي، استلمت طلبك وبلشت التنفيذ الآن."


if bot:
    @bot.message_handler(commands=["start"])
    def tg_start(message):
        if not should_handle_chat(message.chat.id):
            return
        text = "أهلاً، أنا ساندي. ابعتلي رسالة أو فويس، وبقدر كمان أساعدك بالمهام والتذكيرات."
        bot.send_message(message.chat.id, text)

    @bot.message_handler(commands=["tasks"])
    def tg_tasks(message):
        if not should_handle_chat(message.chat.id):
            return
        bot.send_message(message.chat.id, list_tasks_impl())

    @bot.message_handler(commands=["scan"])
    def tg_scan(message):
        if not should_handle_chat(message.chat.id):
            return
        begin_activity("think", source="tg")
        text = capture_and_describe_impl()
        end_activity("think", source="tg")
        restore_expression_face(force=True)
        bot.send_message(message.chat.id, text)

    @bot.message_handler(content_types=["voice"])
    def tg_voice(message):
        if not should_handle_chat(message.chat.id):
            return
        try:
            file_info = bot.get_file(message.voice.file_id)
            raw = bot.download_file(file_info.file_path)
            ogg_path = BASE_DIR / "telegram_voice.ogg"
            wav_path = BASE_DIR / "telegram_voice.wav"
            with open(ogg_path, "wb") as f:
                f.write(raw)
            convert_ogg_to_wav(ogg_path, wav_path)
            with sr.AudioFile(str(wav_path)) as source:
                audio = recognizer.record(source)
            text = recognizer.recognize_google(audio, language="ar")
            status = enqueue_user_request(text, chat_id=message.chat.id, send_voice=True)
            bot.send_message(message.chat.id, status)
        except Exception as e:
            bot.send_message(message.chat.id, f"ما قدرت أفهم الفويس: {e}")

@bot.message_handler(func=lambda m: True, content_types=["text"])
def tg_text(message):
    if not should_handle_chat(message.chat.id):
        return
    status = enqueue_user_request(message.text, chat_id=message.chat.id, send_voice=True)
    bot.send_message(message.chat.id, status)

# =========================
# Main interaction
# =========================
def _split_sequential_commands(text: str) -> List[str]:
    raw = str(text or "").strip()
    if not raw:
        return []

    normalized = raw
    normalized = re.sub(r"\s+(?:وبعدين|بعدين|بعدها|ثم|بعد ذلك|and then|then)\s+", " || ", normalized, flags=re.IGNORECASE)
    normalized = normalized.replace("\n", " || ")
    normalized = normalized.replace(";", " || ")

    parts = [p.strip(" ،,.?!؟") for p in normalized.split("||")]
    parts = [p for p in parts if p]
    return parts if len(parts) > 1 else [raw]


def _looks_like_explanatory_query(text: str) -> bool:
    low = str(text or "").strip().lower()
    if not low:
        return False

    if "؟" in low or "?" in low:
        return True

    starters = [
        "اشرح", "اشرحلي", "اشرح لي", "شو", "شو يعني", "ما معنى", "معنى", "ليش", "كيف", "هل", "متى", "وين",
        "what", "why", "how", "explain", "tell me", "describe",
    ]
    return any(low.startswith(s) for s in starters)


def _has_action_command_cue(text: str) -> bool:
    low = str(text or "").strip().lower()
    cues = [
        "صو", "صورة", "صوري", "صور", "تصوير", "لف", "زاوية", "افتح", "افتحي", "سكر", "سكري", "اغلق", "اغلقي",
        "امسح", "مسح", "بانوراما", "فيديو", "ابعت", "ابعث", "رجع", "ارجع", "روح", "نفذ", "اعمل", "شغل", "اطفي",
    ]
    return any(c in low for c in cues)


def handle_user_text(text: str, chat_id: Optional[int] = None, speak_reply: bool = True, _allow_batch: bool = True) -> str:
    text = (text or "").strip()
    if not text:
        return ""

    raw_reply: Optional[str] = None

    with _command_execution_lock:
        if _allow_batch:
            parts = _split_sequential_commands(text)
            if len(parts) > 1:
                outputs: List[str] = []
                for idx, part in enumerate(parts, start=1):
                    part_reply = handle_user_text(part, chat_id=chat_id, speak_reply=False, _allow_batch=False)
                    outputs.append(f"{idx}. {part_reply}")
                reply = "\n".join(outputs)
                if speak_reply and not is_speaking:
                    speak(reply, chat_id=chat_id, send_voice=False)
                else:
                    restore_expression_face(force=True)
                return reply

        if is_speaking:
            interrupt_speaking(clear_queue=True)

        low = text.lower()
        normalized_digits = low.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
        angle_motion_cues = ["لف", "لفي", "زاوية", "روح", "روحي", "تروح", "رجع", "رجعي", "ارجع", "ارجعي"]
        has_angle_number = re.search(r"\b(\d{1,3})\b", normalized_digits) is not None
        intent_label, intent_conf = _classify_user_intent_ai(text)
        shortcut_allowed = (
            (intent_label == "command" and intent_conf >= 0.5)
            or (intent_label == "mixed" and intent_conf >= 0.45)
        )

        # اختصارات حتمية لتقليل هلوسة نموذج المحادثة في أوامر الكاميرا
        if shortcut_allowed and any(p in low for p in ["افتحي عيون", "افتح عيون", "افتحي عيونك", "افتح عيونك"]):
            reply = open_eyes_impl()
        elif shortcut_allowed and any(p in low for p in ["سكري عيون", "سكر عيون", "سكري عيونك", "سكر عيونك", "اغلقي عيون", "اغلق عيون"]):
            reply = close_eyes_impl()
        elif shortcut_allowed and ("بانوراما" in low or "panorama" in low):
            reply = scan_room_to_telegram_impl(use_video=False)
        elif shortcut_allowed and ("فيديو" in low or "video" in low) and any(p in low for p in ["امسح", "مسح", "غرفة", "الغرفة", "صو", "صورة"]):
            reply = scan_room_to_telegram_impl(use_video=True)
        elif shortcut_allowed and ("صو" in low or "صورة" in low) and any(p in low for p in ["زوايا", "الزوايا", "angles"]):
            angle_tokens = re.findall(r"\b(\d{1,3})\b", normalized_digits)
            parsed_angles: List[int] = []
            seen_angles = set()
            for tok in angle_tokens:
                val = int(max(1, min(180, int(tok))))
                if val in seen_angles:
                    continue
                seen_angles.add(val)
                parsed_angles.append(val)

            if not parsed_angles:
                reply = "ما فهمت الزوايا المطلوبة للتصوير."
            else:
                previous_angle_raw = _arduino_read_property(SANDY_DEVICE_ID, "servoAngle") if _arduino_enabled() else current_servo_angle
                try:
                    previous_angle = int(max(1, min(180, int(previous_angle_raw))))
                except Exception:
                    previous_angle = int(max(1, min(180, int(current_servo_angle))))

                statuses: List[str] = []
                for angle in parsed_angles:
                    _move_neck_and_wait(angle, wait_sec=0.8)
                    snap_url = get_cam_snapshot_url()
                    if snap_url:
                        cam_cfg = _camera_runtime_config()
                        cam_auth = _camera_auth_tuple(cam_cfg)
                        _wait_camera_motion_settled(cam_auth, snap_url, max_wait_sec=2.0, require_motion=True)
                    statuses.append(f"{angle}°: {send_photo_to_telegram_impl()}")

                if parsed_angles and previous_angle != parsed_angles[-1]:
                    _move_neck_and_wait(previous_angle, wait_sec=1.0)

                reply = "نفذت تصوير الزوايا بالتوالي:\n" + "\n".join(statuses)
        elif shortcut_allowed and ("صو" in low or "صورة" in low) and has_angle_number and any(c in low for c in angle_motion_cues):
            angle_match = re.search(r"\b(\d{1,3})\b", normalized_digits)
            angle = int(angle_match.group(1)) if angle_match else current_servo_angle
            angle = int(max(1, min(180, angle)))
            previous_angle_raw = _arduino_read_property(SANDY_DEVICE_ID, "servoAngle") if _arduino_enabled() else current_servo_angle
            try:
                previous_angle = int(max(1, min(180, int(previous_angle_raw))))
            except Exception:
                previous_angle = int(max(1, min(180, int(current_servo_angle))))
            _move_neck_and_wait(angle, wait_sec=0.8)
            snap_url = get_cam_snapshot_url()
            if snap_url:
                cam_cfg = _camera_runtime_config()
                cam_auth = _camera_auth_tuple(cam_cfg)
                _wait_camera_motion_settled(cam_auth, snap_url, max_wait_sec=7.0, require_motion=True)
            move_msg = f"تمام، بحرك رقبتي على {angle} درجة."
            photo_msg = send_photo_to_telegram_impl()
            if previous_angle != angle:
                _move_neck_and_wait(previous_angle, wait_sec=1.0)
                move_msg += " ورجّعتها للزاوية السابقة."
            reply = f"{move_msg}\n{photo_msg}"
        elif shortcut_allowed and has_angle_number and any(c in low for c in angle_motion_cues):
            angle_match = re.search(r"\b(\d{1,3})\b", normalized_digits)
            if angle_match:
                angle = int(max(1, min(180, int(angle_match.group(1)))))
                _move_neck_and_wait(angle, wait_sec=0.7)
                reply = f"تمام، لفّيت الرقبة على {angle} درجة."
            else:
                reply = "حددلي زاوية واضحة عشان ألف الرقبة."
        elif shortcut_allowed and ("امسح" in low or "مسح" in low) and ("غرفة" in low or "الغرفة" in low):
            use_video = any(word in low for word in ["فيديو", "video"])
            reply = scan_room_to_telegram_impl(use_video=use_video)

        if low in ["/tasks", "المهام", "مهامي"]:
            reply = list_tasks_impl()
        elif re.match(r"^(تم|أنجزت|خلصت)\s+\d+$", low):
            idx = int(re.findall(r"\d+", low)[0])
            reply = complete_task_impl(idx)
        elif "reply" not in locals():
            begin_activity("think", source="dialog")
            raw_reply = run_agent(text)
            end_activity("think", source="dialog")

        if raw_reply is not None:
            # استخراج الحالة المزاجية
            mood_match = re.search(r'\[(\w+)\]', raw_reply)

            # تنظيف النص من الإيموجي وحفظ الرد الصافي
            if mood_match:
                clean_text = raw_reply.replace(mood_match.group(0), "")
            else:
                clean_text = raw_reply

            reply = re.sub(r'[^\w\s.,!؟،-]', '', clean_text).strip()

            # حساب وقت بقاء التعبير: وقت الكلام التقريبي + 5 ثواني إضافية
            hold_time = (len(reply) * 0.1) + 5.0

            if mood_match:
                mood_word = mood_match.group(1).lower()
                set_expression(mood_word, hold_seconds=hold_time, source="ai_mood")
            else:
                # إذا لم يرسل الذكاء حالة، نخمنها ولكن بالوقت الطويل الجديد
                plan = infer_behavior_plan(text, reply)
                expression = normalize_expression(plan.get("expression"))
                if expression and expression != "talk":
                    set_expression(expression, hold_seconds=hold_time, source="planner")
            
        if speak_reply and not is_speaking:
            speak(reply, chat_id=chat_id, send_voice=False)
        else:
            restore_expression_face(force=True)

        return reply


def microphone_loop():
    print("ساندي تسمعك يا حبيبها (الوضع الدائم)...")
    while True:
        # 1. القفل الأول: منع فتح المايكروفون أثناء الحديث أو بعده مباشرة (تأخير 0.8 ثانية لتفريغ الصدى)
        if is_speaking or (time.time() - _last_speech_end_time < 0.8):
            time.sleep(0.1)
            continue

        heard = listen_once()
        if not heard:
            continue

        # 2. القفل المزدوج السحري: هل ساندي تكلمت *أثناء* تسجيل هذا الصوت؟ 
        # إذا نعم، فهذا مجرد صدى أو تسجيل ذاتي، نتجاهله فوراً!
        if is_speaking or (time.time() - _last_speech_end_time < 0.8):
            debug_print(f"Ignored self-echo: {heard}")
            continue

        # 3. إذا كان الصوت نظيفاً والمستخدم هو من يتحدث
        print(f"You: {heard}")
        handle_user_text(heard, speak_reply=True)


def start_telegram():
    if not bot:
        print("Telegram disabled: TELEGRAM_BOT_TOKEN not set")
        return
    print("Starting Telegram polling...")
    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=20)
        except Exception as e:
            print(f"Telegram polling error: {e}")
            time.sleep(3)


def boot_robot():
    print("Sandy is waking up...")
    send_esp_cmd("BUZZER_STARTUP")
    if SANDY_COMMAND_MODE == "http" and ENABLE_SCREEN_HTTP:
        show_text_on_screen("ساندي جاهزة")    
    set_expression("idle", source="boot")
    restore_expression_face(force=True)


def ensure_files():
    for path, default in [
        (SESSION_FILE, []),
        (PLAN_FILE, []),
        (REMINDERS_FILE, []),
    ]:
        if not path.exists():
            save_json(path, default)


def main():
    ensure_files()
    ensure_runtime_workers()
    restore_reminders()
    boot_robot()

    if bot:
        threading.Thread(target=start_telegram, daemon=True).start()

    if USE_MIC:
        microphone_loop()
    else:
        print("USE_MIC=0 -> CLI mode. Type and press Enter.")
        while True:
            try:
                text = input("You> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nBye")
                break
            if not text:
                continue
            reply = handle_user_text(text, speak_reply=True)
            print(f"Sandy> {reply}")


if __name__ == "__main__":
    main()

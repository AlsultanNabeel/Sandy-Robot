import os
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
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
SANDY_IP = os.getenv("SANDY_IP", "192.168.8.100").strip()
CAM_IP = os.getenv("CAM_IP", "").strip()
SANDY_USER_CHAT_ID = os.getenv("SANDY_USER_CHAT_ID", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
VOICE_NAME = os.getenv("SANDY_TTS_VOICE", "ar-LB-LaylaNeural")
TTS_RATE = os.getenv("SANDY_TTS_RATE", "+15%")
LISTEN_TIMEOUT = int(os.getenv("LISTEN_TIMEOUT", "5"))
LISTEN_PHRASE_LIMIT = int(os.getenv("LISTEN_PHRASE_LIMIT", "12"))
USE_MIC = os.getenv("USE_MIC", "1").strip() == "1"

SANDY_COMMAND_MODE = os.getenv("SANDY_COMMAND_MODE", "auto").strip().lower()
ARDUINO_CLIENT_ID = os.getenv("ARDUINO_CLIENT_ID", "").strip()
ARDUINO_CLIENT_SECRET = os.getenv("ARDUINO_CLIENT_SECRET", "").strip()
SANDY_DEVICE_ID = os.getenv("SANDY_DEVICE_ID", "9ae4816c-5a9e-43ae-9387-bda18f86dc61").strip()
CAMERA_DEVICE_ID = os.getenv("CAMERA_DEVICE_ID", "").strip()
ARDUINO_ORG_ID = os.getenv("ARDUINO_ORG_ID", "").strip()
SANDY_THING_ID = os.getenv("SANDY_THING_ID", "").strip()
SANDY_BEHAVIOR_MODEL = os.getenv("SANDY_BEHAVIOR_MODEL", OPENAI_MODEL).strip() or OPENAI_MODEL
ENABLE_SCREEN_HTTP = os.getenv("SANDY_ENABLE_SCREEN_HTTP", "0").strip() == "1"
ENABLE_BASE_MOTION = os.getenv("SANDY_ENABLE_BASE_MOTION", "0").strip() == "1"
SANDY_DEBUG = os.getenv("SANDY_DEBUG", "0").strip() == "1"
SANDY_FACE_MIN_INTERVAL_SEC = float(os.getenv("SANDY_FACE_MIN_INTERVAL_SEC", "0.10"))

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY missing in .env")

client = OpenAI(api_key=OPENAI_API_KEY)
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, threaded=True) if TELEGRAM_BOT_TOKEN else None
scheduler = BackgroundScheduler(timezone=None)
scheduler.start()
recognizer = sr.Recognizer()

is_speaking = False
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

SUPPORTED_EXPRESSIONS = {
    "idle", "happy", "big_happy", "curious", "think", "talk", "alert", "surprised",
    "sleepy", "bored", "yawn", "sad", "angry", "smirk", "cute", "excited", "shy", "confused"
}

EXPRESSION_ALIASES = {
    "laugh": "big_happy",
    "laughing": "big_happy",
    "funny": "happy",
    "joy": "happy",
    "empathetic": "sad",
    "empathy": "sad",
    "playful": "smirk",
    "neutral": "idle",
    "listen": "curious",
    "listening": "curious",
    "thinking": "think",
    "speaking": "talk",
    "love": "cute",
}

SYSTEM_PROMPT = """
أنتِ ساندي، مساعدة روبوتية عربية لطيفة وذكية وقريبة من القلب.
تكلمين المستخدم بالعربية الطبيعية، بوضوح وباختصار غالباً.
أنتِ لستِ مجرد شات؛ أنتِ شريكة يومية تساعد في التنظيم والتذكير والرد العملي.

قواعد مهمة:
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

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "move_neck",
            "description": "تحريك رقبة ساندي إلى اليسار أو اليمين أو المنتصف أو زاوية محددة.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["left", "right", "center"]},
                    "angle": {"type": "integer", "minimum": 55, "maximum": 125}
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
            "name": "show_text",
            "description": "عرض نص قصير على شاشة ساندي إذا كان المسار المدعوم متاحاً.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string", "maxLength": 120}},
                "required": ["text"],
                "additionalProperties": False
            }
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
            "name": "move_base",
            "description": "إرسال أمر حركة إلى قاعدة ساندي. قد يكون معطلاً مؤقتاً إذا لم تُركب الموتورات بعد.",
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
            "description": "البحث عن المستخدم بصرياً ثم محاولة الاقتراب منه إذا كانت حركة القاعدة مفعلة.",
            "parameters": {
                "type": "object",
                "properties": {"target_name": {"type": "string"}},
                "additionalProperties": False
            }
        }
    }
]

DIRECT_CLOUD_COMMANDS = {
    "LOOK_LEFT", "LOOK_RIGHT", "CENTER",
    "FACE_IDLE", "FACE_THINK", "FACE_SPEAK", "FACE_LISTEN", "FACE_ALERT",
    "FACE_HAPPY", "FACE_BIG_HAPPY", "FACE_SURPRISED", "FACE_SAD", "FACE_ANGRY",
    "FACE_SMIRK", "FACE_CUTE", "FACE_EXCITED", "FACE_SHY", "FACE_CONFUSED",
}

_state_lock = threading.RLock()
_hardware_io_lock = threading.Lock()
_face_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=128)
_servo_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=64)
_runtime_stop = threading.Event()
_runtime_started = False


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
        "sleepy": "FACE_IDLE",
        "bored": "FACE_IDLE",
        "yawn": "FACE_IDLE",
        "sad": "FACE_SAD",
        "angry": "FACE_ANGRY",
        "smirk": "FACE_SMIRK",
        "cute": "FACE_CUTE",
        "excited": "FACE_EXCITED",
        "shy": "FACE_SHY",
        "confused": "FACE_CONFUSED",
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
    if current_overlay:
        return overlay_map.get(current_overlay, _face_cmd_for_expression(current_expression))
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
                angle = int(max(55, min(125, int(event.get("angle", 90)))))
                send_esp_cmd(f"ANGLE_{angle}")
                current_servo_angle = angle
            elif kind == "direction":
                direction = str(event.get("direction", "center")).lower()
                cmd = {"left": "LOOK_LEFT", "right": "LOOK_RIGHT", "center": "CENTER"}.get(direction, "CENTER")
                send_esp_cmd(cmd)
                current_servo_angle = {"left": 120, "right": 60, "center": 90}.get(direction, 90)
        except Exception as e:
            print(f"Servo worker error: {e}")


def ensure_runtime_workers():
    global _runtime_started
    if _runtime_started:
        return
    threading.Thread(target=_face_worker, daemon=True, name="sandy-face-worker").start()
    threading.Thread(target=_servo_worker, daemon=True, name="sandy-servo-worker").start()
    _runtime_started = True


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


def plans() -> List[Dict[str, Any]]:
    return load_json(PLAN_FILE, [])


def save_plans(data: List[Dict[str, Any]]):
    save_json(PLAN_FILE, data)


def reminders() -> List[Dict[str, Any]]:
    return load_json(REMINDERS_FILE, [])


def save_reminders(data: List[Dict[str, Any]]):
    save_json(REMINDERS_FILE, data)


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
        "FACE_SAD": {"moodState": "sad"},
        "FACE_ANGRY": {"moodState": "angry"},
        "FACE_SMIRK": {"moodState": "smirk"},
        "FACE_CUTE": {"moodState": "cute"},
        "FACE_EXCITED": {"moodState": "excited"},
        "FACE_SHY": {"moodState": "shy"},
        "FACE_CONFUSED": {"moodState": "confused"},
    }

    values = mapping.get(cmd)
    return "ok" if values and _arduino_update_properties(SANDY_DEVICE_ID, values) else None

# =========================
# ESP32 helpers
# =========================
def esp_base() -> str:
    return f"http://{SANDY_IP}" if SANDY_IP else ""


def send_esp_cmd(cmd: str) -> Optional[str]:
    global last_esp_ok

    http_allowed = SANDY_COMMAND_MODE in {"auto", "http"} and bool(SANDY_IP)
    cloud_allowed = SANDY_COMMAND_MODE in {"auto", "cloud"}

    with _hardware_io_lock:
        if http_allowed:
            try:
                r = requests.get(f"{esp_base()}/cmd", params={"cmd": cmd}, timeout=3)
                r.raise_for_status()
                last_esp_ok = True
                return r.text.strip()
            except Exception as e:
                last_esp_ok = False
                print(f"ESP HTTP Command Error [{cmd}]: {e}")
                if SANDY_COMMAND_MODE == "http":
                    return None

        result = _send_cloud_body_command(cmd) if cloud_allowed else None
        last_esp_ok = bool(result)
        return result


def show_text_on_screen(text: str) -> bool:
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
    if SANDY_IP and SANDY_COMMAND_MODE in {"auto", "http"}:
        try:
            r = requests.get(f"{esp_base()}/distance", timeout=2)
            r.raise_for_status()
            return int(float(str(r.text).strip()))
        except Exception as e:
            print(f"Distance HTTP error: {e}")
            if SANDY_COMMAND_MODE == "http":
                return None
    value = _arduino_read_property(SANDY_DEVICE_ID, "distanceCm")
    try:
        return int(float(value)) if value is not None else None
    except Exception:
        return None


def _send_base_motion_command(action: str, duration_ms: int = 800, speed: float = 0.5) -> bool:
    """
    Base motion placeholder.
    الكود المقصود للحركة الأرضية موجود هنا لكنه يبقى غير مفعّل الآن.
    بعد تركيب الموتورات فعلياً أزل التعليق عن مسار الإرسال الذي ستعتمده.
    """
    if not ENABLE_BASE_MOTION:
        return False

    # مثال HTTP لاحقاً:
    # try:
    #     r = requests.post(
    #         f"{esp_base()}/base_move",
    #         json={"action": action, "duration_ms": duration_ms, "speed": speed},
    #         timeout=3,
    #     )
    #     r.raise_for_status()
    #     return True
    # except Exception:
    #     return False

    # مثال Cloud لاحقاً:
    # return _arduino_update_properties(SANDY_DEVICE_ID, {
    #     "baseAction": action,
    #     "baseDurationMs": int(duration_ms),
    #     "baseSpeed": float(speed),
    # })

    return False

# =========================
# Camera / vision
# =========================
def get_cam_snapshot_url() -> Optional[str]:
    config = load_json(CAM_CONFIG_FILE, {})
    token = config.get("snapshot_token", "") if isinstance(config, dict) else ""
    if CAM_IP and token:
        return f"http://{CAM_IP}/snapshot?token={token}"
    if CAM_IP:
        return f"http://{CAM_IP}/snapshot"
    return None


def capture_and_describe_impl() -> str:
    snap_url = get_cam_snapshot_url()
    if not snap_url:
        return "الكاميرا غير مضبوطة بعد."
    try:
        img = requests.get(snap_url, timeout=8)
        img.raise_for_status()
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        tmp.write(img.content)
        tmp.close()

        with open(tmp.name, "rb") as f:
            up = client.files.create(file=f, purpose="vision")

        resp = client.responses.create(
            model=OPENAI_MODEL,
            input=[{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "صف الصورة باختصار شديد وبالعربية. ركز على الأشخاص أو الأشياء المهمة."},
                    {"type": "input_image", "file_id": up.id},
                ],
            }],
        )
        return (resp.output_text or "التقطت الصورة لكن لم أستطع وصفها.").strip()
    except Exception as e:
        return f"فشل التقاط أو تحليل الصورة: {e}"

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
    show_text_on_screen(msg[:100])
    send_esp_cmd("MELODY_CONFIRM")
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
    reminder_id = str(uuid.uuid4())
    scheduler.add_job(reminder_job, trigger=DateTrigger(run_date=dt), args=[text], id=reminder_id, replace_existing=True)
    data = reminders()
    data.append({"id": reminder_id, "text": text, "when": when})
    save_reminders(data)
    return f"تم ضبط التذكير: {text} عند {when}"


def restore_reminders():
    for item in reminders():
        try:
            dt = datetime.strptime(item["when"], "%Y-%m-%d %H:%M")
            if dt > datetime.now():
                scheduler.add_job(reminder_job, trigger=DateTrigger(run_date=dt), args=[item["text"]], id=item["id"], replace_existing=True)
        except Exception as e:
            print(f"Restore reminder failed: {e}")

# =========================
# Speech / audio
# =========================
def speak(text: str, chat_id: Optional[int] = None, send_voice: bool = False):
    global is_speaking
    text = (text or "").strip()
    if not text:
        return
    is_speaking = True
    print(f"Sandy: {text}")
    out = BASE_DIR / "sandy_reply.mp3"
    try:
        async def _gen():
            c = edge_tts.Communicate(text, voice=VOICE_NAME, rate=TTS_RATE)
            await c.save(str(out))
        asyncio.run(_gen())

        begin_activity("speak", source="tts")
        show_text_on_screen(text[:100])

        player = find_player()
        if player:
            subprocess.run(player + [str(out)], check=False)

        if send_voice and bot and chat_id:
            with open(out, "rb") as vf:
                bot.send_voice(chat_id, vf)
    except Exception as e:
        print(f"TTS Error: {e}")
    finally:
        end_activity("speak", source="tts")
        is_speaking = False
        restore_expression_face(force=True)

def listen_once() -> Optional[str]:
    if is_speaking:
        return None
    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.4)
            begin_activity("listen", source="mic")
            audio = recognizer.listen(source, timeout=LISTEN_TIMEOUT, phrase_time_limit=LISTEN_PHRASE_LIMIT)
        begin_activity("think", source="mic")
        text = recognizer.recognize_google(audio, language="ar")
        return text.strip()
    except sr.WaitTimeoutError:
        return None
    except sr.UnknownValueError:
        return None
    except Exception as e:
        print(f"Mic error: {e}")
        return None
    finally:
        end_activity(source="mic")
        restore_expression_face(force=True)

# =========================
# Tool implementations
# =========================
def move_neck_impl(direction: Optional[str] = None, angle: Optional[int] = None) -> str:
    if angle is not None:
        safe_angle = int(max(55, min(125, int(angle))))
        _queue_servo_event({"kind": "angle", "angle": safe_angle})
        return f"تمام، بحرك رقبتي تقريباً على {safe_angle} درجة."
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
        return "فتحت عيوني." if ok else "ما قدرت أفتح عيوني حالياً."
    return "وحدة الكاميرا غير جاهزة داخل البايثون."


def close_eyes_impl() -> str:
    if sandy_camera and hasattr(sandy_camera, "close_eyes"):
        ok = sandy_camera.close_eyes()
        return "سكرت عيوني." if ok else "ما قدرت أسكر عيوني حالياً."
    return "وحدة الكاميرا غير جاهزة داخل البايثون."


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


def move_base_impl(action: str, duration_ms: int = 700, speed: float = 0.6) -> str:
    action = str(action or "stop").strip().lower()
    duration_ms = int(max(150, min(4000, int(duration_ms or 700))))
    speed = float(max(0.1, min(1.0, float(speed or 0.6))))
    if not ENABLE_BASE_MOTION:
        return "الحركة الأرضية غير مفعلة بعد. الكود موجود داخل sandy.py لكنه سيبقى معطلاً حتى تركب الموتورات وتفعّل الربط الحقيقي."
    ok = _send_base_motion_command(action, duration_ms=duration_ms, speed=speed)
    return "تمام، نفذت حركة القاعدة." if ok else "أمرت بالحركة لكن مسار الموتورات غير مكتمل بعد."


def come_to_user_impl(target_name: Optional[str] = None) -> str:
    target_name = (target_name or behavior_context.get("last_seen_name") or "نبيل").strip() or "نبيل"
    scan_result = scan_for_owner_impl(target_name=target_name)
    if not ENABLE_BASE_MOTION:
        return scan_result + "\nأنا أقدر أبحث عنك بصرياً الآن، لكن الحركة الأرضية نفسها ما زالت غير مفعلة حتى يتم تركيب الموتورات وتفعيل الربط."
    if behavior_context.get("owner_visible"):
        ok = _send_base_motion_command("forward", duration_ms=1000, speed=0.45)
        if ok:
            return scan_result + "\nبدأت أقترب منك."
    return scan_result + "\nحاول اقترب شوي أو خليني أشوفك أوضح."


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


def run_agent(user_text: str) -> str:
    append_memory("user", user_text)
    messages = build_messages(user_text)

    for _ in range(4):
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        msg = resp.choices[0].message

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
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_result,
                })
            continue

        answer = (msg.content or "").strip()
        if answer:
            append_memory("assistant", answer)
            try:
                summarize_and_store(user_text, answer)
            except Exception as e:
                print(f"Memory store warning: {e}")
        return answer or "ما قدرت أوصل لرد مناسب حالياً."

    fallback = "صار عندي تشابك داخلي بسيط. جرب احكيلي الطلب مرة ثانية بشكل أقصر."
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
            reply = handle_user_text(text, chat_id=message.chat.id, speak_reply=False)
            bot.send_message(message.chat.id, reply)
            speak(reply, chat_id=message.chat.id, send_voice=True)
        except Exception as e:
            bot.send_message(message.chat.id, f"ما قدرت أفهم الفويس: {e}")

    @bot.message_handler(func=lambda m: True, content_types=["text"])
    def tg_text(message):
        if not should_handle_chat(message.chat.id):
            return
        reply = handle_user_text(message.text, chat_id=message.chat.id, speak_reply=False)
        bot.send_message(message.chat.id, reply)
        if any(k in message.text.lower() for k in ["احكي", "صوت", "تكلمي", "ردي بصوت"]):
            speak(reply, chat_id=message.chat.id, send_voice=True)

# =========================
# Main interaction
# =========================
def handle_user_text(text: str, chat_id: Optional[int] = None, speak_reply: bool = True) -> str:
    text = (text or "").strip()
    if not text:
        return ""

    low = text.lower()
    if low in ["/tasks", "المهام", "مهامي"]:
        reply = list_tasks_impl()
    elif re.match(r"^(تم|أنجزت|خلصت)\s+\d+$", low):
        idx = int(re.findall(r"\d+", low)[0])
        reply = complete_task_impl(idx)
    elif sandy_camera and hasattr(sandy_camera, "SECRET_PASSPHRASE") and text.strip() == getattr(sandy_camera, "SECRET_PASSPHRASE", ""):
        result = sandy_camera.handle_secret_phrase(text.strip(), speak_func=None)
        if result.get("ok"):
            if _arduino_enabled():
                _arduino_update_properties(SANDY_DEVICE_ID, {"autonomousMode": True})
            behavior_context["last_seen_name"] = result.get("name", "نبيل")
            reply = f"تم التحقق. أهلًا {result.get('name', '')}، فعلت الوضع الكامل."
            set_expression("happy", hold_seconds=3.0, source="auth")
        else:
            reply = "ما زبط التحقق من المالك."
            set_expression("confused", hold_seconds=2.5, source="auth")
    else:
        begin_activity("think", source="dialog")
        reply = run_agent(text)
        end_activity("think", source="dialog")
        apply_behavior_plan(text, reply)

    if speak_reply and not is_speaking:
        speak(reply, chat_id=chat_id, send_voice=False)
    else:
        restore_expression_face(force=True)
    return reply

def microphone_loop():
    print("Microphone active...")
    while True:
        heard = listen_once()
        if not heard:
            continue
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
    send_esp_cmd("MELODY_BOOT")
    show_text_on_screen("ساندي جاهزة")
    set_expression("idle", source="boot")
    restore_expression_face(force=True)


def ensure_files():
    for path, default in [
        (SESSION_FILE, []),
        (PLAN_FILE, []),
        (REMINDERS_FILE, []),
        (CAM_CONFIG_FILE, {}),
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

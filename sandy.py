# Built by Nabeel Alsultan
from dotenv import load_dotenv
load_dotenv()
import requests
import speech_recognition as sr
import time
import subprocess
import edge_tts
import sandy_camera as cam
import asyncio
import threading
import random
import os
import shutil
import telebot
from queue import Queue
from dotenv import load_dotenv, set_key
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import json
import re
from sandy_config import NABEEL_INFO, SANDY_PERSONALITY


load_dotenv()

# Base device settings I touch once and forget about
SANDY_IP          = os.getenv('SANDY_IP', '192.168.8.100').strip()
CAM_IP            = os.getenv('CAM_IP', '192.168.8.150').strip()
OPENAI_API_KEY    = os.getenv('OPENAI_API_KEY')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
OPENAI_MODEL      = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
OPENAI_MAX_TOKENS = 100
DOTENV_PATH       = os.path.join(os.path.dirname(__file__), '.env')
MEMORY_FILE       = "sandy_memory.json"

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is missing from .env")
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is missing from .env")

TTS_RATE          = '+25%'
EMOJI_FONT        = '/System/Library/Fonts/Apple Color Emoji.ttc'
IMG_W, IMG_H, EMOJI_SIZE = 240, 240, 200

client    = OpenAI(api_key=OPENAI_API_KEY)
bot       = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
scheduler = BackgroundScheduler()
scheduler.start()

# Load cached chat ID if we already have one
_raw_chat_id = os.getenv('SANDY_USER_CHAT_ID', '').strip()
USER_CHAT_ID = int(_raw_chat_id) if _raw_chat_id.lstrip('-').isdigit() else None

# Tiny memory buffer so Sandy keeps context
def load_memory():
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except: return []
    return []

def save_memory(user_msg, ai_msg):
    memory = load_memory()
    memory.append({"user": user_msg, "ai": ai_msg, "time": str(datetime.now())})
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(memory[-10:], f, ensure_ascii=False, indent=4) # keep last 10 turns

# Room-scan helper: move the neck and send a few photos
def perform_scan(chat_id):
    if not chat_id: return
    angles = {"SCAN_POS_1": "يمين (40°)", "SCAN_POS_2": "وسط (90°)", "SCAN_POS_3": "شمال (145°)"}
    speak("بدأت مسح الغرفة الصور رح توصلك عالتليجرام.")
    
    for cmd, label in angles.items():
        try:
            requests.get(f'http://{SANDY_IP}/cmd?cmd={cmd}', timeout=2)
            time.sleep(2) # give servo time to move
            img_resp = requests.get(f'http://{CAM_IP}/snapshot', timeout=7)
            if img_resp.status_code == 200:
                bot.send_photo(chat_id, img_resp.content, caption=f"📸 لقطة ساندي: {label}")
        except Exception as e:
            print(f"⚠️ Failed to capture {label}: {e}")
            
    requests.get(f'http://{SANDY_IP}/cmd?cmd=SCAN_POS_2') # reset to neutral pose
    speak("خلصت مسح الغرفة، كل شي تمام.")

# Audio + display utilities live here to keep the rest tidy
is_speaking   = False
device_online = False
http          = requests.Session()
recognizer    = sr.Recognizer()
_tts_loop     = None
_tts_thread   = None
_tts_lock     = threading.Lock()

def _ensure_tts_loop():
    global _tts_loop, _tts_thread
    with _tts_lock:
        if _tts_loop:
            return
        loop = asyncio.new_event_loop()
        _tts_loop = loop
        def _runner():
            asyncio.set_event_loop(loop)
            loop.run_forever()
        _tts_thread = threading.Thread(target=_runner, daemon=True)
        _tts_thread.start()

async def _speak_async(text):
    communicate = edge_tts.Communicate(text, voice="ar-LB-LaylaNeural", rate=TTS_RATE)
    await communicate.save("sandy_reply.mp3")

def speak(text):
    global is_speaking
    if not text: return
    is_speaking = True
    print(f"🤖 ساندي: {text}")
    _ensure_tts_loop()
    future = asyncio.run_coroutine_threadsafe(_speak_async(text), _tts_loop)
    future.result()
    subprocess.run(["afplay", "sandy_reply.mp3"], check=False)
    is_speaking = False

def show_on_screen(emoji=None, text=''):
    if not device_online: return
    try:
        canvas = Image.new('RGBA', (IMG_W, IMG_H), (0, 0, 0, 255))
        font   = ImageFont.truetype(EMOJI_FONT, 200)
        e_img  = Image.new('RGBA', (200, 200), (0, 0, 0, 0))
        ImageDraw.Draw(e_img).text((0, 0), emoji or '😊', font=font, embedded_color=True)
        e_img  = e_img.resize((EMOJI_SIZE, EMOJI_SIZE), Image.LANCZOS)
        canvas.paste(e_img, ((IMG_W - EMOJI_SIZE) // 2, (IMG_H - EMOJI_SIZE) // 2), e_img)
        rgb    = canvas.convert('RGB')
        result = bytearray()
        for r, g, b in rgb.getdata():
            color = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            result.append(color & 0xFF)
            result.append((color >> 8) & 0xFF)
        http.post(f'http://{SANDY_IP}/show_text', data=bytes(result), timeout=5)
    except: pass

def send_command(cmd):
    try: http.get(f'http://{SANDY_IP}/cmd?cmd={cmd}', timeout=3)
    except: pass

# Central brain that handles user text plus scan logic
def respond_to_user_text(user_text, source="mic", chat_id=None):
    global USER_CHAT_ID
    if chat_id and chat_id != USER_CHAT_ID:
                # Persist the latest chat ID in .env
        set_key(DOTENV_PATH, 'SANDY_USER_CHAT_ID', str(chat_id))
        USER_CHAT_ID = chat_id

    # Scan triggers
    if "فشي الغرفة" in user_text or "مسح" in user_text or "/scan" in user_text:
        threading.Thread(target=perform_scan, args=(chat_id or USER_CHAT_ID,)).start()
        return

    # Camera start/stop triggers
    if "عيونك" in user_text or "كاميرا" in user_text:
        if "افتحي" in user_text:
            speak("فتحت عيوني!")
            cam.start_camera(speak, show_on_screen, send_command)
            return
        if "سكري" in user_text:
            cam.stop_camera(); speak("سكرت عيوني."); return

    show_on_screen('🤔')

    # Build memory context for the prompt
    past_mem = load_memory()
    mem_context = "\n".join([f"مستخدم: {m['user']}\nساندي: {m['ai']}" for m in past_mem])

    try:
        current_time = datetime.now().strftime("%I:%M %p")
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            max_tokens=OPENAI_MAX_TOKENS,
            messages=[
                {
   "role": "system",
"content": (
    f"أنتِ المساعدة الذكية الخاصة في البيت. الوقت الآن {current_time}.\n"
    f"ذاكرتك:\n{mem_context}\n\n"
    f"— عن المستخدم:\n{NABEEL_INFO}\n\n"
    f"— شخصيتك:\n{SANDY_PERSONALITY}"
)

},
                {"role": "user", "content": user_text}
            ]
        )
        ai_reply = response.choices[0].message.content.strip()

        save_memory(user_text, ai_reply) # log the latest exchange
        send_command("FACE_SPEAK")
        show_on_screen(text=ai_reply)
        speak(ai_reply)
        send_command("FACE_IDLE")

        if source == "telegram" and chat_id:
            bot.send_message(chat_id, ai_reply)

    except Exception as e:
        print(f"⚠️ AI failure: {e}")

requests_queue = Queue()

def queue_user_text(user_text, source="mic", chat_id=None):
    requests_queue.put((user_text, source, chat_id))

def _requests_worker():
    while True:
        user_text, source, chat_id = requests_queue.get()
        try:
            respond_to_user_text(user_text, source, chat_id)
        except Exception as worker_err:
            print(f"⚠️ Failed to handle request: {worker_err}")
        finally:
            requests_queue.task_done()

threading.Thread(target=_requests_worker, daemon=True).start()

# Misc glue: Telegram handler + mic loop
@bot.message_handler(func=lambda message: True)
def handle_telegram(message):
    queue_user_text(message.text, "telegram", message.chat.id)

def listen_loop():
    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.7)
        while True:
            if not is_speaking:
                try:
                    show_on_screen('🤗')
                    audio = recognizer.listen(source, timeout=4, phrase_time_limit=6)
                    text  = recognizer.recognize_google(audio, language='ar-SA')
                    queue_user_text(text, source="mic")
                except: pass
            time.sleep(0.5)

if __name__ == "__main__":
    try:
        device_online = (requests.get(f'http://{SANDY_IP}/', timeout=2).status_code == 200)
    except: pass
    
    send_command("MELODY_BOOT")
    show_on_screen('💛')
    speak("أهلاً يا برو! ساندي شريكتك تذكرك الآن وجاهزة لكل أوامرك.")
    
    def safe_polling():
        while True:
            try:
                bot.polling(none_stop=False, timeout=30)
            except Exception as e:
                print(f"⚠️ Telegram polling died, retrying: {e}")
                time.sleep(5)

    threading.Thread(target=safe_polling, daemon=True).start()
    listen_loop()
    
   

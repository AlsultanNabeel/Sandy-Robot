1) انسخ .env.example إلى .env
2) عبّي OPENAI_API_KEY
3) غيّر SANDY_IP إلى IP الخاص بالـ ESP32 الرئيسي
4) اختياري: ضع TELEGRAM_BOT_TOKEN إذا بدك تلغرام
5) إذا لا تريد الميكروفون الآن ضع USE_MIC=0
6) ثبت المكتبات:
   pip install -r requirements.txt
7) شغّل:
   python3 sandy.py

الأوامر التي يتوافق معها هذا الملف مع السكيتش:
- /cmd?cmd=FACE_IDLE
- /cmd?cmd=FACE_LISTEN
- /cmd?cmd=FACE_THINK
- /cmd?cmd=FACE_SPEAK
- /cmd?cmd=FACE_ALERT
- /cmd?cmd=MELODY_BOOT
- /cmd?cmd=MELODY_CONFIRM
- /cmd?cmd=CENTER
- /cmd?cmd=LOOK_LEFT
- /cmd?cmd=LOOK_RIGHT
- /cmd?cmd=ANGLE_100
- /distance
- /show_text  (POST body raw text)

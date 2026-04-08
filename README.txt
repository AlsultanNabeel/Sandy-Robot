1) انسخ .env.example إلى .env
2) عبّي:
   OPENAI_API_KEY
   TELEGRAM_BOT_TOKEN
   SANDY_IP
   CAM_IP
   SANDY_USER_CHAT_ID

3) اجعل وضع التحكم الرئيسي:
   SANDY_COMMAND_MODE=cloud

4) تأكد أن:
   SANDY_ENABLE_SCREEN_HTTP=0
   SANDY_ENABLE_BASE_MOTION=0

5) إذا لا تريد الميكروفون الآن:
   USE_MIC=0

6) ثبت المكتبات:
   pip install -r requirements.txt

7) شغّل:
   python3 sandy.py
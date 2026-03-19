## Sandy — Your At-Home Robot Partner

Sandy is a DIY assistant built with an ESP32 board, an ESP32-CAM, and a Python control app that connects to OpenAI and Telegram. The robot listens, talks back in Arabic, can scan the room with its neck servo, and forwards snapshots from the camera straight to your phone.

### Project Layout
- `sandy.py`: main controller (voice I/O, OpenAI calls, Telegram bot, camera toggling, servo commands).
- `sandy/`: ESP32 firmware that drives the TFT display, neck servo, distance sensor, buzzer, and exposes HTTP endpoints.
- `esp32cam_stream/`: ESP32-CAM sketch that serves a `/snapshot` JPEG over Wi-Fi.
- `sandy_camera.py`: face-recognition helper that watches the camera stream and greets known faces.
- `faces/`: local face database (ignored in git; rebuild it on your own machine).
- `.env`, `config.h`, `sandy_config.py`: hold secrets or personal info. Keep them out of git and create local copies only.

### Quick Setup
1. Copy `.env.example` to `.env` and fill `OPENAI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `SANDY_IP`, `CAM_IP`, `SANDY_USER_CHAT_ID`.
2. Put Wi-Fi credentials and device keys in `config.h` (never push it).
3. If you need custom personality or bio info, duplicate `sandy_config.py` locally and edit it; the real file stays ignored.
4. Install Python deps (adjust as needed):
   ```bash
   pip install requests edge-tts telebot python-dotenv apscheduler pillow face-recognition opencv-python
   ```
5. Run Sandy:
   ```bash
   python sandy.py
   ```
   The script boots the TTS worker, starts Telegram polling, and opens the mic loop.
6. Flash `sandy/sandy.ino` to the main ESP32 board and `esp32cam_stream/esp32cam_stream.ino` to the ESP32-CAM after updating `config.h`.

### Notes
- Always check `git status` before committing so secrets stay unstaged.
- The face DB (`faces_db.pkl`) lives under `faces/`; add your own photos with `sandy_camera.py`.
- Runtime data such as `sandy_memory.json` and generated MP3 replies are ignored automatically.
- If `afplay` is unavailable (non-macOS), swap it for a player that works on your OS.

Feel free to expand this README with wiring diagrams, hardware photos, or setup tips that fit your build. Enjoy hacking on Sandy! :)

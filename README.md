# Sandy — Smart Robot Assistant

Sandy is a DIY assistant built from:
- Main ESP32 board
- ESP32-CAM
- Python controller app

## Current architecture
- `sandy.py` = main brain  
  Handles Telegram, voice I/O, OpenAI, memory, reminders, and camera requests.

- `sandy/` = main ESP32 firmware  
  Handles TFT face display, neck servo, distance sensor, and Arduino Cloud properties.

- `esp32cam_Camera/` = ESP32-CAM firmware  
  Handles camera snapshot, authentication, face recognition helpers, and private mode support.

## Important control rule
- Main ESP32 board uses **Arduino Cloud**
- ESP32-CAM uses **HTTP**
- Old HTTP assumptions for the main ESP32 are considered legacy and should not be relied on

## Main files
- `sandy.py`
- `sandy/sandy.ino`
- `sandy/sandy_faces.h`
- `esp32cam_Camera/esp32cam_Camera.ino`
- `sandy_camera_iot_ready.py`
- `sandy_memory_v2.py`

## Setup
1. Copy `.env.example` to `.env`
2. Fill in:
   - `OPENAI_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `SANDY_IP`
   - `CAM_IP`
   - `SANDY_USER_CHAT_ID`
   - Arduino Cloud credentials if needed
3. Flash:
   - `sandy/sandy.ino` to the main ESP32
   - `esp32cam_Camera/esp32cam_Camera.ino` to the ESP32-CAM
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   
5. python3 sandy.py
import cv2
import face_recognition
import numpy as np
import os
import pickle
import threading
import requests

# ESP32-CAM settings I locked in earlier
CAM_IP = "192.168.8.150" # static IP in the Arduino sketch
CAM_STREAM_URL  = f"http://{CAM_IP}/snapshot"
FACES_DB        = "faces/faces_db.pkl"

camera_active   = False
_stop_event     = threading.Event()
_last_name_seen = "unknown"

# Load the saved face encodings (if any)
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

known_encodings = []
known_names     = []

def load_faces():
    global known_encodings, known_names
    if os.path.exists(FACES_DB):
        with open(FACES_DB, "rb") as f:
            data = pickle.load(f)
            known_encodings = data.get("encodings", [])
            known_names     = data.get("names", [])
        print(f"✅ Loaded {len(known_names)} faces.")

def get_last_detected_name():
    global _last_name_seen
    return _last_name_seen

def _camera_loop(speak_func=None):
    global camera_active, _last_name_seen
    _last_name_seen = "unknown"
    bytes_buffer = b""

    try:
        # Try connecting to the camera stream; failure usually means the board is down
        stream = requests.get(CAM_STREAM_URL, stream=True, timeout=10)
    except Exception as e:
        print(f"❌ Camera connection failed: {e}")
        camera_active = False
        return

    for chunk in stream.iter_content(chunk_size=4096):
        if _stop_event.is_set(): break
        bytes_buffer += chunk
        a, b = bytes_buffer.find(b'\xff\xd8'), bytes_buffer.find(b'\xff\xd9')

        if a != -1 and b != -1:
            jpg = bytes_buffer[a:b+2]
            bytes_buffer = bytes_buffer[b+2:]
            frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
            
            if frame is not None:
                # Face recognition pipeline
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                encs = face_recognition.face_encodings(rgb)
                for enc in encs:
                    distances = face_recognition.face_distance(known_encodings, enc)
                    if len(distances) > 0 and np.min(distances) < 0.5:
                        name = known_names[np.argmin(distances)]
                        if name != _last_name_seen:
                            _last_name_seen = name
                            if speak_func and name == "Nabeel":
                                speak_func("أهلاً حبيبي، نورت مكانك!")
                    else:
                        _last_name_seen = "unknown"

    camera_active = False

def start_camera(speak_func=None):
    global camera_active, _stop_event
    if camera_active: return
    load_faces()
    _stop_event.clear()
    camera_active = True
    threading.Thread(target=_camera_loop, args=(speak_func,), daemon=True).start()

def stop_camera():
    _stop_event.set()

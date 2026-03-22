import cv2
import face_recognition
import json
import numpy as np
import os
import pickle
import time
from collections import deque
import requests

# تنظیمات الكاميرا والـ AI
CONFIG_PATH = "sandy_camera_config.json"
_DEFAULT_CONFIG = {
    "cam_ip": "192.168.8.150",
    "faces_db": "faces/faces_db.pkl",
    "snapshot_token": "",
    "face_match_threshold": 0.5,
    "face_cache_ttl_sec": 1.5,
    "reconnect_delay_sec": 2,
    "capture_retry_count": 2,
    "recent_faces_limit": 10,
    "stream_timeout_sec": 10,
    "frame_scale": 0.5,
    "min_frame_bytes": 2048,
    "liveness_frames": 3,
    "liveness_min_delta": 3.0,
    "liveness_interval_sec": 0.4,
    "cascade_scale_factor": 1.1,
    "cascade_min_neighbors": 5,
    "cascade_min_size": 60,
    "hog_upsample": 0,
    "clahe_clip_limit": 2.0,
    "clahe_tile_grid": 8
}


def _load_camera_config():
    config = dict(_DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    config.update({k: data[k] for k in config.keys() if k in data})
        except Exception as exc:
            print(f"⚠️  Failed to read {CONFIG_PATH}: {exc}")
    return config


_CAMERA_CONFIG = _load_camera_config()
CAM_IP = _CAMERA_CONFIG["cam_ip"]
CAM_STREAM_URL  = f"http://{CAM_IP}/snapshot"
SNAPSHOT_TOKEN  = _CAMERA_CONFIG["snapshot_token"]
FACES_DB        = _CAMERA_CONFIG["faces_db"]
FACE_MATCH_THRESHOLD = float(_CAMERA_CONFIG["face_match_threshold"])
FACE_CACHE_TTL_SEC   = float(_CAMERA_CONFIG["face_cache_ttl_sec"])
RECONNECT_DELAY_SEC  = float(_CAMERA_CONFIG["reconnect_delay_sec"])
CAPTURE_RETRY_COUNT  = int(_CAMERA_CONFIG["capture_retry_count"])
RECENT_FACES_LIMIT   = int(_CAMERA_CONFIG["recent_faces_limit"])
STREAM_TIMEOUT_SEC   = int(_CAMERA_CONFIG["stream_timeout_sec"])
FRAME_SCALE          = float(_CAMERA_CONFIG["frame_scale"])
MIN_FRAME_BYTES      = int(_CAMERA_CONFIG["min_frame_bytes"])
LIVENESS_FRAMES      = int(_CAMERA_CONFIG["liveness_frames"])
LIVENESS_MIN_DELTA   = float(_CAMERA_CONFIG["liveness_min_delta"])
LIVENESS_INTERVAL_SEC = float(_CAMERA_CONFIG["liveness_interval_sec"])
CASCADE_SCALE        = float(_CAMERA_CONFIG["cascade_scale_factor"])
CASCADE_NEIGHBORS    = int(_CAMERA_CONFIG["cascade_min_neighbors"])
CASCADE_MIN_SIZE     = int(_CAMERA_CONFIG["cascade_min_size"])
HOG_UPSAMPLE         = int(_CAMERA_CONFIG["hog_upsample"])
CLAHE_CLIP_LIMIT     = float(_CAMERA_CONFIG["clahe_clip_limit"])
CLAHE_TILE_GRID      = int(_CAMERA_CONFIG["clahe_tile_grid"])

FRAME_SCALE = min(1.0, max(0.1, FRAME_SCALE))
MIN_FRAME_BYTES = max(512, MIN_FRAME_BYTES)
CLAHE_TILE_GRID = max(2, CLAHE_TILE_GRID)
LIVENESS_FRAMES = max(1, LIVENESS_FRAMES)
LIVENESS_MIN_DELTA = max(0.5, LIVENESS_MIN_DELTA)
LIVENESS_INTERVAL_SEC = max(0.0, LIVENESS_INTERVAL_SEC)

camera_status   = "idle"
_last_name_seen = "unknown"
_recent_faces   = deque(maxlen=RECENT_FACES_LIMIT)
_faces_loaded   = False
_last_match_time = 0.0
_session = None
_clahe = cv2.createCLAHE(clipLimit=CLAHE_CLIP_LIMIT, tileGridSize=(CLAHE_TILE_GRID, CLAHE_TILE_GRID))

# here we load the saved face encodings (if any)
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

known_encodings = []
known_names     = []

def load_faces():
    global known_encodings, known_names, _faces_loaded
    if os.path.exists(FACES_DB):
        with open(FACES_DB, "rb") as f:
            data = pickle.load(f)
            known_encodings = data.get("encodings", [])
            known_names     = data.get("names", [])
        print(f"faces Loaded {len(known_names)} faces.")
    _faces_loaded = True

def _ensure_faces_loaded():
    if not _faces_loaded:
        load_faces()

def get_last_detected_name():
    global _last_name_seen
    return _last_name_seen

def get_camera_status():
    return camera_status

def get_recent_faces():
    return list(_recent_faces)

def _set_status(value):
    global camera_status
    if camera_status != value:
        camera_status = value

def _log_face_event(name, timestamp):
    _recent_faces.append({"name": name, "timestamp": timestamp})

def _http_session():
    global _session
    if _session is None:
        _session = requests.Session()
    return _session

def _enhance_frame(frame):
    if FRAME_SCALE < 1.0:
        frame = cv2.resize(
            frame,
            None,
            fx=FRAME_SCALE,
            fy=FRAME_SCALE,
            interpolation=cv2.INTER_AREA,
        )
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = _clahe.apply(l)
    lab = cv2.merge((l, a, b))
    enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    return enhanced

def _fetch_frame():
    session = _http_session()
    response = None
    try:
        url = CAM_STREAM_URL
        if SNAPSHOT_TOKEN:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}token={SNAPSHOT_TOKEN}"
        response = session.get(url, timeout=STREAM_TIMEOUT_SEC)
        if response.status_code != 200:
            raise ValueError(f"HTTP {response.status_code}")
        payload = response.content
        if not payload or len(payload) < MIN_FRAME_BYTES:
            raise ValueError("Frame payload too small")
        frame = cv2.imdecode(
            np.frombuffer(payload, dtype=np.uint8),
            cv2.IMREAD_COLOR,
        )
        if frame is None:
            raise ValueError("Empty frame received")
        return frame
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                pass

def _motion_delta(prev_frame, next_frame):
    prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
    next_gray = cv2.cvtColor(next_frame, cv2.COLOR_BGR2GRAY)
    if FRAME_SCALE < 1.0:
        prev_gray = cv2.resize(prev_gray, None, fx=FRAME_SCALE, fy=FRAME_SCALE, interpolation=cv2.INTER_AREA)
        next_gray = cv2.resize(next_gray, None, fx=FRAME_SCALE, fy=FRAME_SCALE, interpolation=cv2.INTER_AREA)
    diff = cv2.absdiff(prev_gray, next_gray)
    return float(np.mean(diff))

def _should_update_name(name, timestamp):
    if FACE_CACHE_TTL_SEC > 0 and name == _last_name_seen:
        return (timestamp - _last_match_time) >= FACE_CACHE_TTL_SEC
    return True

def _process_frame(frame, speak_func=None):
    global _last_name_seen, _last_match_time
    now = time.time()
    prepped = _enhance_frame(frame)
    rgb = cv2.cvtColor(prepped, cv2.COLOR_BGR2RGB)

    face_locations = face_recognition.face_locations(
        rgb,
        number_of_times_to_upsample=HOG_UPSAMPLE,
        model="hog",
    )

    if not face_locations and not face_cascade.empty():
        gray = cv2.cvtColor(prepped, cv2.COLOR_BGR2GRAY)
        boxes = face_cascade.detectMultiScale(
            gray,
            scaleFactor=CASCADE_SCALE,
            minNeighbors=CASCADE_NEIGHBORS,
            minSize=(CASCADE_MIN_SIZE, CASCADE_MIN_SIZE),
        )
        face_locations = [(y, x + w, y + h, x) for (x, y, w, h) in boxes]

    encs = face_recognition.face_encodings(
        rgb,
        known_face_locations=face_locations if face_locations else None,
    )

    name = "unknown"
    if known_encodings:
        for enc in encs:
            distances = face_recognition.face_distance(known_encodings, enc)
            if len(distances) == 0:
                continue
            best_idx = int(np.argmin(distances))
            if distances[best_idx] < FACE_MATCH_THRESHOLD:
                name = known_names[best_idx]
                break

    if _should_update_name(name, now):
        _last_name_seen = name
        _last_match_time = now
        _log_face_event(name, now)
        if speak_func and name == "Nabeel":
            speak_func("أهلاً حبيبي، نورت مكانك!")

    return name

def capture_snapshot(speak_func=None):
    _ensure_faces_loaded()
    frames = []
    required_frames = max(1, LIVENESS_FRAMES)
    for frame_idx in range(required_frames):
        captured = None
        for attempt in range(max(1, CAPTURE_RETRY_COUNT)):
            _set_status("capturing")
            try:
                captured = _fetch_frame()
                break
            except Exception as exc:
                print(f"❌ Camera snapshot failed (frame {frame_idx + 1}, attempt {attempt + 1}): {exc}")
                _set_status("error")
                if attempt < CAPTURE_RETRY_COUNT - 1:
                    time.sleep(RECONNECT_DELAY_SEC)
        if captured is None:
            return None
        frames.append(captured)
        if frame_idx < required_frames - 1 and LIVENESS_INTERVAL_SEC > 0:
            time.sleep(LIVENESS_INTERVAL_SEC)

    if required_frames > 1:
        movement_detected = any(
            _motion_delta(prev, curr) >= LIVENESS_MIN_DELTA
            for prev, curr in zip(frames, frames[1:])
        )
        if not movement_detected:
            print("⚠️ Liveness check failed: no motion detected between frames.")
            _set_status("error")
            return None

    name = _process_frame(frames[-1], speak_func)
    _set_status("ready")
    return name
 
def start_camera(speak_func=None, *_, **__):
    return capture_snapshot(speak_func=speak_func)

def stop_camera(*_, **__):
    global _last_name_seen, _last_match_time
    _last_name_seen = "unknown"
    _last_match_time = 0.0
    _set_status("idle")

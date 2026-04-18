import cv2
import face_recognition
import numpy as np
import os
import pickle
import time
import threading
from collections import deque
import requests
from requests.auth import HTTPBasicAuth

_DEFAULT_CONFIG = {
    "cam_ip": "192.168.1.150",
    "faces_db": "faces/faces_db.pkl",
    "snapshot_token": "",
    "control_token": "",
    "http_user": "Owner",
    "http_pass": "change-me-camera-pass",
    "secret_passphrase": "ساندي الوضع الكامل",
    "face_match_threshold": 0.5,
    "face_cache_ttl_sec": 1.5,
    "reconnect_delay_sec": 2,
    "capture_retry_count": 2,
    "eye_auto_close_sec": 20,
    "recent_faces_limit": 10,
    "stream_timeout_sec": 10,
    "control_timeout_sec": 5,
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
    "clahe_tile_grid": 8,
    "owner_names": ["Owner"]
}

_eye_close_timer = None
_camera_state_lock = threading.Lock()
_camera_power_on = False
_full_mode_enabled = False


def _load_camera_config():
    return dict(_DEFAULT_CONFIG)


def _parse_owner_names(value: str | None) -> list[str]:
    if not value:
        return ["Owner"]
    names = [name.strip() for name in value.split(",") if name.strip()]
    return names or ["Owner"]


def reload_camera_config():
    global _CAMERA_CONFIG, CAM_IP, CAM_SNAPSHOT_URL, CAM_STREAM_URL, CAM_CONTROL_URL, CAM_STATUS_URL
    global SNAPSHOT_TOKEN, CONTROL_TOKEN, HTTP_USER, HTTP_PASS, SECRET_PASSPHRASE
    global FACES_DB, FACE_MATCH_THRESHOLD, FACE_CACHE_TTL_SEC, RECONNECT_DELAY_SEC, CAPTURE_RETRY_COUNT
    global RECENT_FACES_LIMIT, STREAM_TIMEOUT_SEC, CONTROL_TIMEOUT_SEC, FRAME_SCALE, MIN_FRAME_BYTES
    global LIVENESS_FRAMES, LIVENESS_MIN_DELTA, LIVENESS_INTERVAL_SEC, CASCADE_SCALE, CASCADE_NEIGHBORS
    global CASCADE_MIN_SIZE, HOG_UPSAMPLE, CLAHE_CLIP_LIMIT, CLAHE_TILE_GRID, OWNER_NAMES, _clahe, _recent_faces
    global EYE_AUTO_CLOSE_SEC

    _CAMERA_CONFIG = _load_camera_config()
    CAM_IP = os.getenv("CAM_IP", "").strip() or _CAMERA_CONFIG.get("cam_ip", _DEFAULT_CONFIG["cam_ip"])
    CAM_SNAPSHOT_URL = f"http://{CAM_IP}/snapshot"
    CAM_STREAM_URL = f"http://{CAM_IP}/stream"
    CAM_CONTROL_URL = f"http://{CAM_IP}/control"
    CAM_STATUS_URL = f"http://{CAM_IP}/status"
    SNAPSHOT_TOKEN = os.getenv("CAM_SNAPSHOT_TOKEN", "").strip() or _CAMERA_CONFIG.get("snapshot_token", "")
    CONTROL_TOKEN = os.getenv("CAM_CONTROL_TOKEN", "").strip() or _CAMERA_CONFIG.get("control_token", "")
    HTTP_USER = os.getenv("CAM_HTTP_USER", "").strip() or _CAMERA_CONFIG.get("http_user", _DEFAULT_CONFIG["http_user"])
    HTTP_PASS = os.getenv("CAM_HTTP_PASS", "").strip() or _CAMERA_CONFIG.get("http_pass", _DEFAULT_CONFIG["http_pass"])
    SECRET_PASSPHRASE = os.getenv("CAM_SECRET_PASSPHRASE", "").strip() or _CAMERA_CONFIG.get("secret_passphrase", _DEFAULT_CONFIG["secret_passphrase"])
    FACES_DB = os.getenv("CAM_FACES_DB", "").strip() or _CAMERA_CONFIG.get("faces_db", _DEFAULT_CONFIG["faces_db"])
    FACE_MATCH_THRESHOLD = float(_CAMERA_CONFIG.get("face_match_threshold", 0.5))
    FACE_CACHE_TTL_SEC = float(_CAMERA_CONFIG.get("face_cache_ttl_sec", 1.5))
    RECONNECT_DELAY_SEC = float(_CAMERA_CONFIG.get("reconnect_delay_sec", 2))
    CAPTURE_RETRY_COUNT = int(_CAMERA_CONFIG.get("capture_retry_count", 2))
    EYE_AUTO_CLOSE_SEC = max(5, int(_CAMERA_CONFIG.get("eye_auto_close_sec", 20)))
    RECENT_FACES_LIMIT = int(_CAMERA_CONFIG.get("recent_faces_limit", 10))
    STREAM_TIMEOUT_SEC = int(_CAMERA_CONFIG.get("stream_timeout_sec", 10))
    CONTROL_TIMEOUT_SEC = int(_CAMERA_CONFIG.get("control_timeout_sec", 5))
    FRAME_SCALE = min(1.0, max(0.1, float(_CAMERA_CONFIG.get("frame_scale", 0.5))))
    MIN_FRAME_BYTES = max(512, int(_CAMERA_CONFIG.get("min_frame_bytes", 2048)))
    LIVENESS_FRAMES = max(1, int(_CAMERA_CONFIG.get("liveness_frames", 3)))
    LIVENESS_MIN_DELTA = max(0.5, float(_CAMERA_CONFIG.get("liveness_min_delta", 3.0)))
    LIVENESS_INTERVAL_SEC = max(0.0, float(_CAMERA_CONFIG.get("liveness_interval_sec", 0.4)))
    CASCADE_SCALE = float(_CAMERA_CONFIG.get("cascade_scale_factor", 1.1))
    CASCADE_NEIGHBORS = int(_CAMERA_CONFIG.get("cascade_min_neighbors", 5))
    CASCADE_MIN_SIZE = int(_CAMERA_CONFIG.get("cascade_min_size", 60))
    HOG_UPSAMPLE = int(_CAMERA_CONFIG.get("hog_upsample", 0))
    CLAHE_CLIP_LIMIT = float(_CAMERA_CONFIG.get("clahe_clip_limit", 2.0))
    CLAHE_TILE_GRID = max(2, int(_CAMERA_CONFIG.get("clahe_tile_grid", 8)))
    OWNER_NAMES = set(_parse_owner_names(os.getenv("CAM_OWNER_NAMES")) or _CAMERA_CONFIG.get("owner_names", ["Owner"]))
    _clahe = cv2.createCLAHE(clipLimit=CLAHE_CLIP_LIMIT, tileGridSize=(CLAHE_TILE_GRID, CLAHE_TILE_GRID))
    _recent_faces = deque(maxlen=RECENT_FACES_LIMIT)


def _cancel_eye_close_timer():
    global _eye_close_timer
    with _camera_state_lock:
        if _eye_close_timer is not None:
            _eye_close_timer.cancel()
            _eye_close_timer = None


def _schedule_eye_close_timer(delay_sec: int | None = None):
    global _eye_close_timer
    _cancel_eye_close_timer()
    delay = int(delay_sec or EYE_AUTO_CLOSE_SEC)
    if delay <= 0:
        return

    def _close_if_idle():
        try:
            if not _full_mode_enabled:
                camera_off()
        finally:
            _cancel_eye_close_timer()

    with _camera_state_lock:
        _eye_close_timer = threading.Timer(delay, _close_if_idle)
        _eye_close_timer.daemon = True
        _eye_close_timer.start()


reload_camera_config()
camera_status = "idle"
_last_name_seen = "unknown"
_faces_loaded = False
_last_match_time = 0.0
_session = None
_recent_faces = deque(maxlen=10)
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
known_encodings = []
known_names = []


def load_faces():
    global known_encodings, known_names, _faces_loaded
    if os.path.exists(FACES_DB):
        with open(FACES_DB, "rb") as f:
            data = pickle.load(f)
            known_encodings = data.get("encodings", [])
            known_names = data.get("names", [])
        print(f"faces loaded: {len(known_names)}")
    _faces_loaded = True


def _ensure_faces_loaded():
    if not _faces_loaded:
        load_faces()


def get_last_detected_name():
    return _last_name_seen


def get_camera_status():
    return camera_status


def get_recent_faces():
    return list(_recent_faces)


def _set_status(value):
    global camera_status
    camera_status = value


def _log_face_event(name, timestamp):
    _recent_faces.append({"name": name, "timestamp": timestamp})


def _http_session():
    global _session
    if _session is None:
        _session = requests.Session()
    return _session


def _auth():
    return HTTPBasicAuth(HTTP_USER, HTTP_PASS)


def _with_token(url, token):
    if not token:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}token={token}"


def _control(action):
    session = _http_session()
    url = _with_token(CAM_CONTROL_URL, CONTROL_TOKEN)
    resp = session.get(url, params={"action": action}, timeout=CONTROL_TIMEOUT_SEC, auth=_auth())
    resp.raise_for_status()
    return resp.json()


def get_remote_status():
    session = _http_session()
    resp = session.get(_with_token(CAM_STATUS_URL, CONTROL_TOKEN), timeout=CONTROL_TIMEOUT_SEC, auth=_auth())
    resp.raise_for_status()
    return resp.json()


def camera_on():
    global _camera_power_on
    _set_status("waking")
    try:
        _control("wake")
        _set_status("ready")
        _camera_power_on = True
        if not _full_mode_enabled:
            _schedule_eye_close_timer()
        return True
    except Exception as exc:
        _set_status("error")
        print(f"camera_on failed: {exc}")
        return False


def camera_off():
    global _camera_power_on
    try:
        _control("sleep")
    finally:
        _cancel_eye_close_timer()
        _camera_power_on = False
        _set_status("idle")


def arm_secret_mode():
    return _control("arm_secret")


def disarm_secret_mode():
    return _control("disarm_secret")


def reboot_camera():
    return _control("reboot")


def enable_full_mode():
    global _full_mode_enabled
    result = _control("full_mode_on")
    _full_mode_enabled = True
    _cancel_eye_close_timer()
    return result


def disable_full_mode():
    global _full_mode_enabled
    result = _control("full_mode_off")
    _full_mode_enabled = False
    if _camera_power_on:
        _schedule_eye_close_timer()
    return result


def report_auth_ok():
    return _control("auth_ok")


def report_auth_fail():
    return _control("auth_fail")


def _enhance_frame(frame):
    if FRAME_SCALE < 1.0:
        frame = cv2.resize(frame, None, fx=FRAME_SCALE, fy=FRAME_SCALE, interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = _clahe.apply(l)
    lab = cv2.merge((l, a, b))
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def _fetch_frame():
    session = _http_session()
    response = None
    try:
        response = session.get(_with_token(CAM_SNAPSHOT_URL, SNAPSHOT_TOKEN), timeout=STREAM_TIMEOUT_SEC, auth=_auth())
        if response.status_code != 200:
            raise ValueError(f"HTTP {response.status_code}")
        payload = response.content
        if not payload or len(payload) < MIN_FRAME_BYTES:
            raise ValueError("Frame payload too small")
        frame = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("Empty frame received")
        return frame
    finally:
        if response is not None:
            response.close()


def stream_url():
    return _with_token(CAM_STREAM_URL, SNAPSHOT_TOKEN)


def stream_auth():
    return (HTTP_USER, HTTP_PASS)


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
    face_locations = face_recognition.face_locations(rgb, number_of_times_to_upsample=HOG_UPSAMPLE, model="hog")

    if not face_locations and not face_cascade.empty():
        gray = cv2.cvtColor(prepped, cv2.COLOR_BGR2GRAY)
        boxes = face_cascade.detectMultiScale(
            gray,
            scaleFactor=CASCADE_SCALE,
            minNeighbors=CASCADE_NEIGHBORS,
            minSize=(CASCADE_MIN_SIZE, CASCADE_MIN_SIZE),
        )
        face_locations = [(y, x + w, y + h, x) for (x, y, w, h) in boxes]

    encs = face_recognition.face_encodings(rgb, known_face_locations=face_locations if face_locations else None)
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
        if speak_func and name in OWNER_NAMES:
            speak_func("أهلاً حبيبي، نورت المكان!")

    return name


def capture_snapshot(speak_func=None, auto_wake=True, auto_sleep=False):
    _ensure_faces_loaded()
    if auto_wake and not camera_on():
        return None

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
                print(f"camera snapshot failed (frame {frame_idx + 1}, attempt {attempt + 1}): {exc}")
                _set_status("error")
                if attempt < CAPTURE_RETRY_COUNT - 1:
                    time.sleep(RECONNECT_DELAY_SEC)
        if captured is None:
            if auto_sleep or not _full_mode_enabled:
                camera_off()
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
            print("liveness failed: no movement")
            _set_status("error")
            if auto_sleep:
                camera_off()
            return None

    name = _process_frame(frames[-1], speak_func)
    _set_status("ready")
    if auto_sleep:
        camera_off()
    elif not _full_mode_enabled:
        _schedule_eye_close_timer()
    return name


def verify_owner(speak_func=None):
    name = capture_snapshot(speak_func=speak_func, auto_wake=True, auto_sleep=False)
    if name and name in OWNER_NAMES:
        try:
            report_auth_ok()
        except Exception:
            pass
        return True, name
    try:
        report_auth_fail()
    except Exception:
        pass
    return False, name or "unknown"

def learn_new_face(new_name: str):
    _ensure_faces_loaded()
    if not camera_on():
        return False, "لم أتمكن من الاتصال بالكاميرا."

    _set_status("capturing")
    frames = []
    for _ in range(4): # نحاول التقاط 4 صور متتالية لضمان إيجاد الوجه
        try:
            f = _fetch_frame()
            if f is not None:
                frames.append(f)
        except Exception:
            pass
        time.sleep(0.3)
    
    camera_off()

    for frame in frames:
        prepped = _enhance_frame(frame)
        rgb = cv2.cvtColor(prepped, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb, model="hog")
        if face_locations:
            encs = face_recognition.face_encodings(rgb, known_face_locations=face_locations)
            if encs:
                global known_encodings, known_names
                known_encodings.append(encs[0])
                known_names.append(new_name)
                
                os.makedirs(os.path.dirname(FACES_DB), exist_ok=True)
                with open(FACES_DB, "wb") as f:
                    pickle.dump({"encodings": known_encodings, "names": known_names}, f)
                
                return True, f"تم حفظ الوجه بنجاح باسم {new_name}."

    return False, "لم أتمكن من رؤية وجه واضح، حاول الوقوف أمام الكاميرا في إضاءة جيدة."



def open_eyes():
    ok = camera_on()
    if ok and not _full_mode_enabled:
        _schedule_eye_close_timer()
    return ok


def close_eyes():
    camera_off()
    return True


def look_ahead(speak_func=None):
    return capture_snapshot(speak_func=speak_func, auto_wake=True, auto_sleep=False)


def handle_secret_phrase(spoken_text, speak_func=None):
    phrase = (spoken_text or "").strip()
    if phrase != SECRET_PASSPHRASE:
        return {"ok": False, "reason": "wrong_phrase"}

    arm_secret_mode()
    ok, name = verify_owner(speak_func=speak_func)
    if ok:
        enable_full_mode()
        return {"ok": True, "name": name, "mode": "full_enabled"}

    disarm_secret_mode()
    camera_off()
    return {"ok": False, "name": name, "mode": "secret_denied"}

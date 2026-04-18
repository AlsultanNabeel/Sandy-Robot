import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from app.utils.files import read_json_file, write_json_file








def _default_memory() -> Dict[str, Any]:
    now = datetime.now().isoformat()
    return {
        "conversations": [],
        "facts": [],
        "reminders": [],
        "tasks": [],
        "sandy_state": {
            "mood": "happy",
            "last_user_message_time": now,
            "repeat_count": 0,
            "last_message": "",
            "snapped": False,
            "last_mood_change": now,
            "custom_facts": [],
        },
    }


def _default_session() -> Dict[str, Any]:
    return {"messages": []}


def load_memory(memory_file: Optional[Path] = None, mongo_db=None) -> Dict[str, Any]:
    """Load persistent memory from MongoDB or disk."""
    default_memory = _default_memory()

    if mongo_db is not None:
        try:
            memory_doc = mongo_db["memory"].find_one({"_id": "sandy_memory"})
            if memory_doc:
                memory_doc.pop("_id", None)
                print("[Memory] ✅ Loaded from MongoDB")
                return memory_doc

            json_memory =read_json_file(memory_file, None)
            if isinstance(json_memory, dict):
                mongo_db["memory"].replace_one(
                    {"_id": "sandy_memory"},
                    {**json_memory, "_id": "sandy_memory"},
                    upsert=True,
                )
                print("[Memory] 🔁 Migrated JSON -> MongoDB")
                return json_memory

            print("[Memory] ✅ MongoDB is source of truth (new memory)")
            return default_memory

        except Exception as e:
            print(f"[Memory] ⚠️ MongoDB error: {e}, falling back to JSON")

    memory_json = read_json_file(memory_file, None)
    if isinstance(memory_json, dict):
        print("[Memory] 📄 Loaded from JSON file")
        return memory_json

    return default_memory


def save_memory(memory: Dict[str, Any], memory_file: Optional[Path] = None, mongo_db=None) -> None:
    """Save memory to MongoDB or disk."""
    if mongo_db is not None:
        try:
            memory_with_id = {**memory, "_id": "sandy_memory"}
            mongo_db["memory"].replace_one(
                {"_id": "sandy_memory"},
                memory_with_id,
                upsert=True,
            )
            print("[Memory] ✅ Saved to MongoDB")
            return
        except Exception as e:
            print(f"[Memory] ⚠️ MongoDB save error: {e}, falling back to JSON")

    if write_json_file(memory_file, memory):
        print("[Memory] 📄 Saved to JSON file")


def load_session(session_file: Optional[Path] = None, mongo_db=None) -> Dict[str, Any]:
    """Load current session memory from MongoDB or disk."""
    default_session = _default_session()

    if mongo_db is not None:
        try:
            session_doc = mongo_db["sessions"].find_one({"_id": "current_session"})
            if session_doc:
                session_doc.pop("_id", None)
                print("[Session] ✅ Loaded from MongoDB")
                return session_doc

            json_session = read_json_file(session_file, None)
            if isinstance(json_session, dict):
                mongo_db["sessions"].replace_one(
                    {"_id": "current_session"},
                    {**json_session, "_id": "current_session"},
                    upsert=True,
                )
                print("[Session] 🔁 Migrated JSON -> MongoDB")
                return json_session

            print("[Session] ✅ MongoDB is source of truth (new session)")
            return default_session

        except Exception as e:
            print(f"[Session] ⚠️ MongoDB error: {e}, falling back to JSON")

    session_json = read_json_file(session_file, None)
    if isinstance(session_json, dict):
        print("[Session] 📄 Loaded from JSON file")
        return session_json

    return default_session


def save_session(session: Dict[str, Any], session_file: Optional[Path] = None, mongo_db=None) -> None:
    """Save session memory to MongoDB or disk."""
    if mongo_db is not None:
        try:
            session_with_id = {**session, "_id": "current_session"}
            mongo_db["sessions"].replace_one(
                {"_id": "current_session"},
                session_with_id,
                upsert=True,
            )
            print("[Session] ✅ Saved to MongoDB")
            return
        except Exception as e:
            print(f"[Session] ⚠️ MongoDB save error: {e}, falling back to JSON")

    if write_json_file(session_file, session):
        print("[Session] 📄 Saved to JSON file")
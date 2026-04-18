import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from app.utils.files import read_json_file, write_json_file



def load_tasks(mongo_db=None, tasks_file: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load tasks from MongoDB or disk."""
    if mongo_db is not None:
        try:
            tasks = list(mongo_db["tasks"].find({"type": "task"}))
            for task in tasks:
                task.pop("_id", None)
                task.pop("type", None)

            if tasks:
                print("[Tasks] ✅ Loaded from MongoDB")
                return tasks

            if tasks_file:
                json_tasks = read_json_file(tasks_file, [])
                if isinstance(json_tasks, list) and json_tasks:
                    mongo_db["tasks"].delete_many({"type": "task"})
                    for task in json_tasks:
                        doc = {**task, "type": "task"}
                        mongo_db["tasks"].insert_one(doc)
                    print("[Tasks] 🔁 Migrated JSON -> MongoDB")
                    return json_tasks

            print("[Tasks] ✅ MongoDB is source of truth (0 tasks)")
            return []

        except Exception as e:
            print(f"[Tasks] ⚠️ MongoDB error: {e}")

    if tasks_file:
        tasks_json = read_json_file(tasks_file, [])
        if isinstance(tasks_json, list):
            if tasks_json:
                print("[Tasks] 📄 Loaded from JSON file")
            return tasks_json

    return []


def save_tasks(tasks: List[Dict[str, Any]], mongo_db=None, tasks_file: Optional[Path] = None):
    """Save tasks to MongoDB or disk."""
    if mongo_db is not None:
        try:
            mongo_db["tasks"].delete_many({"type": "task"})
            for task in tasks:
                doc = {**task, "type": "task"}
                mongo_db["tasks"].insert_one(doc)
            print("[Tasks] ✅ Saved to MongoDB")
            return
        except Exception as e:
            print(f"[Tasks] ⚠️ MongoDB save error: {e}")

    if tasks_file:
        try:
            if write_json_file(tasks_file, tasks):
                print("[Tasks] 📄 Saved to JSON file")
        except Exception as e:
            print(f"[Tasks] Error saving tasks: {e}")


def add_task(task_text: str, mongo_db=None, tasks_file: Optional[Path] = None) -> str:
    """Add a new task."""
    tasks = load_tasks(mongo_db=mongo_db, tasks_file=tasks_file)

    task = {
        "id": str(datetime.now().timestamp()),
        "text": task_text,
        "done": False,
        "created_at": datetime.now().isoformat(),
        "completed_at": None,
    }

    tasks.append(task)
    save_tasks(tasks, mongo_db=mongo_db, tasks_file=tasks_file)
    print(f"[Tasks] ✅ مهمة جديدة: {task_text}")
    return task["id"]


def complete_task(task_id: str, mongo_db=None, tasks_file: Optional[Path] = None) -> bool:
    """Mark task as complete."""
    tasks = load_tasks(mongo_db=mongo_db, tasks_file=tasks_file)

    for task in tasks:
        if task.get("id") == task_id:
            task["done"] = True
            task["completed_at"] = datetime.now().isoformat()
            save_tasks(tasks, mongo_db=mongo_db, tasks_file=tasks_file)
            print(f"[Tasks] ✅ تم إكمال: {task.get('text', '')}")
            return True

    return False


def list_tasks(mongo_db=None, tasks_file: Optional[Path] = None) -> str:
    """Get list of all pending tasks."""
    tasks = load_tasks(mongo_db=mongo_db, tasks_file=tasks_file)
    active_tasks = [t for t in tasks if not t.get("done", False)]

    if not active_tasks:
        return "✅ ما في مهام معلقة! أنت متفرغ! 🎉"

    lines = ["📋 المهام المعلقة:"]
    for i, task in enumerate(active_tasks, 1):
        lines.append(f"{i}. {task.get('text', '')}")

    return "\n".join(lines)
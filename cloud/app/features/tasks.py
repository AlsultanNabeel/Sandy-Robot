import json
import os
from datetime import datetime
from typing import Any, Dict, List



# بترجع كل المهام (من MongoDB أو ملف)
def load_tasks() -> List[Dict[str, Any]]:
    """Load tasks from MongoDB or disk"""
    
    # Try MongoDB first
    if mongo_db is not None:
        try:
            tasks = list(mongo_db['tasks'].find({"type": "task"}))
            for task in tasks:
                task.pop("_id", None)
            if tasks:
                print("[Tasks] ✅ Loaded from MongoDB")
                return tasks

            json_tasks = _read_json_file(TASKS_FILE, [])
            if isinstance(json_tasks, list) and json_tasks:
                mongo_db['tasks'].delete_many({"type": "task"})
                for task in json_tasks:
                    task["type"] = "task"
                    mongo_db['tasks'].insert_one(task)
                    task.pop("type", None)
                print("[Tasks] 🔁 Migrated JSON -> MongoDB")
                return json_tasks

            print("[Tasks] ✅ MongoDB is source of truth (0 tasks)")
            return []
        except Exception as e:
            print(f"[Tasks] ⚠️ MongoDB error: {e}")
    
    # Fallback to JSON file
    tasks_json = _read_json_file(TASKS_FILE, [])
    if isinstance(tasks_json, list) and tasks_json:
        print("[Tasks] 📄 Loaded from JSON file")
        return tasks_json
    return []

# بتخزن كل المهام (في MongoDB أو ملف)

def save_tasks(tasks: List[Dict[str, Any]]):
    """Save tasks to MongoDB or disk"""
    
    # Try MongoDB first
    if mongo_db is not None:
        try:
            mongo_db['tasks'].delete_many({"type": "task"})
            if tasks:
                for task in tasks:
                    task["type"] = "task"
                    mongo_db['tasks'].insert_one(task)
            print("[Tasks] ✅ Saved to MongoDB")
            return
        except Exception as e:
            print(f"[Tasks] ⚠️ MongoDB save error: {e}")
    
    # Fallback to JSON file
    try:
        with open(TASKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(tasks, f, ensure_ascii=False, indent=2)
            print("[Tasks] 📄 Saved to JSON file")
    except Exception as e:
        print(f"[Tasks] Error saving tasks: {e}")




# بتضيف مهمة جديدة وترجع رقمها
def add_task(task_text: str) -> str:
    """Add a new task"""
    tasks = load_tasks()
    task = {
        "id": str(datetime.now().timestamp()),
        "text": task_text,
        "done": False,
        "created_at": datetime.now().isoformat(),
        "completed_at": None
    }
    tasks.append(task)
    save_tasks(tasks)
    print(f"[Tasks] ✅ مهمة جديدة: {task_text}")
    return task["id"]

# بتعلم على المهمة إنها اكتملت
def complete_task(task_id: str) -> bool:
    """Mark task as complete"""
    tasks = load_tasks()
    for task in tasks:
        if task["id"] == task_id:
            task["done"] = True
            task["completed_at"] = datetime.now().isoformat()
            save_tasks(tasks)
            print(f"[Tasks] ✅ تم إكمال: {task['text']}")
            return True
    return False

# بترجع قائمة بكل المهام المعلقة
def list_tasks() -> str:
    """Get list of all tasks"""
    tasks = load_tasks()
    active_tasks = [t for t in tasks if not t["done"]]
    
    if not active_tasks:
        return "✅ ما في مهام معلقة! أنت متفرغ! 🎉"
    
    task_list = "📋 المهام المعلقة:\n"
    for i, task in enumerate(active_tasks, 1):
        task_list += f"{i}. {task['text']}\n"
    return task_list

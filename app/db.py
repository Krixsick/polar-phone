"""
Simple local task storage for the Telegram coach bot.

This stores today's tasks in a tasks.json file in the project root:

polar-phone/
├── app/
│   ├── coach.py
│   └── db.py
└── tasks.json
"""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


TIMEZONE = ZoneInfo("America/Toronto")

# Saves tasks.json in the project root, one folder above /app
TASKS_FILE = Path(__file__).resolve().parent.parent / "tasks.json"


def _today() -> str:
    """Return today's date like '2026-06-07'."""
    return datetime.now(TIMEZONE).strftime("%Y-%m-%d")


def _now() -> str:
    """Return current timestamp as a string."""
    return datetime.now(TIMEZONE).isoformat()


def _default_data() -> dict:
    """Default empty database shape."""
    return {
        "date": _today(),
        "tasks": []
    }


def _load() -> dict:
    """Load tasks.json. If missing or broken, return empty data."""
    if not TASKS_FILE.exists():
        return _default_data()

    try:
        data = json.loads(TASKS_FILE.read_text())

        if "date" not in data:
            data["date"] = _today()

        if "tasks" not in data:
            data["tasks"] = []

        return data

    except json.JSONDecodeError:
        return _default_data()


def _save(data: dict) -> None:
    """Save data to tasks.json."""
    TASKS_FILE.write_text(json.dumps(data, indent=2))


def get_today() -> list[dict]:
    """
    Return today's tasks.

    If the saved tasks are from a previous day, return an empty list.
    """
    data = _load()

    if data["date"] != _today():
        return []

    return data["tasks"]


def has_today_tasks() -> bool:
    """Return True if there are tasks for today."""
    return len(get_today()) > 0


def set_today_tasks(task_texts: list[str]) -> list[dict]:
    """
    Replace today's tasks with a fresh list.

    Example input:
    ["30 min leetcode", "gym - upper body", "read 20 pages"]
    """
    tasks = []

    for text in task_texts:
        tasks.append({
            "text": text,
            "done": False,
            "created_at": _now(),
            "completed_at": None
        })

    data = {
        "date": _today(),
        "tasks": tasks
    }

    _save(data)
    return tasks


def add_task(text: str) -> dict:
    """Add one task to today's list."""
    data = _load()

    if data["date"] != _today():
        data = _default_data()

    task = {
        "text": text,
        "done": False,
        "created_at": _now(),
        "completed_at": None
    }

    data["tasks"].append(task)
    _save(data)

    return task


def mark_done(index: int) -> bool:
    """
    Mark one task as done by its index.

    Returns True if it worked, False if the index was invalid.
    """
    data = _load()

    if data["date"] != _today():
        return False

    tasks = data["tasks"]

    if index < 0 or index >= len(tasks):
        return False

    tasks[index]["done"] = True
    tasks[index]["completed_at"] = _now()

    _save(data)
    return True


def mark_undone(index: int) -> bool:
    """Mark one task as not done."""
    data = _load()

    if data["date"] != _today():
        return False

    tasks = data["tasks"]

    if index < 0 or index >= len(tasks):
        return False

    tasks[index]["done"] = False
    tasks[index]["completed_at"] = None

    _save(data)
    return True


def tasks_as_text() -> str:
    """
    Return today's tasks as readable text for Claude.

    Example:
    0. [ ] 30 min leetcode
    1. [x] gym - upper body
    """
    tasks = get_today()

    lines = []

    for index, task in enumerate(tasks):
        box = "x" if task["done"] else " "
        lines.append(f"{index}. [{box}] {task['text']}")

    return "\n".join(lines)


def get_progress_summary() -> str:
    """Return a simple progress summary like '2/5 tasks done'."""
    tasks = get_today()

    if not tasks:
        return "no tasks for today yet"

    done_count = sum(1 for task in tasks if task["done"])
    total_count = len(tasks)

    return f"{done_count}/{total_count} tasks done"


def clear_today() -> None:
    """Delete today's task list."""
    _save(_default_data())
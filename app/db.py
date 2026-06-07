"""
Simple task memory — saved to a plain tasks.json file in your project folder.

Each day gets its own fresh list. Every task is just text plus a done flag:
    {"text": "30 min leetcode", "done": false}

You can open tasks.json yourself any time to see exactly what's stored.
"""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# tasks.json lives in the project root (one folder up from this file)
TASKS_FILE = Path(__file__).resolve().parent.parent / "tasks.json"
TIMEZONE = ZoneInfo("America/Toronto")


def _today() -> str:
    """Today's date as text, e.g. '2026-06-07'."""
    return datetime.now(TIMEZONE).strftime("%Y-%m-%d")


def _load() -> dict:
    """Read the whole file. If it doesn't exist yet, start empty."""
    if TASKS_FILE.exists():
        return json.loads(TASKS_FILE.read_text())
    return {"date": "", "tasks": []}


def _save(data: dict) -> None:
    """Write the whole file (indented so it's easy to read by eye)."""
    TASKS_FILE.write_text(json.dumps(data, indent=2))


def get_today() -> list[dict]:
    """Return today's tasks. If it's a new day, the old list doesn't count."""
    data = _load()
    if data["date"] != _today():
        return []
    return data["tasks"]


def set_today_tasks(task_texts: list[str]) -> list[dict]:
    """Replace today's list with a fresh set of tasks (all start not-done)."""
    tasks = [{"text": text, "done": False} for text in task_texts]
    _save({"date": _today(), "tasks": tasks})
    return tasks


def mark_done(index: int) -> None:
    """Check off one task by its position in today's list."""
    data = _load()
    if data["date"] == _today() and 0 <= index < len(data["tasks"]):
        data["tasks"][index]["done"] = True
        _save(data)


def tasks_as_text() -> str:
    """Today's list as readable text like '0. [x] gym'. Empty string if no list."""
    lines = []
    for i, task in enumerate(get_today()):
        box = "x" if task["done"] else " "
        lines.append(f"{i}. [{box}] {task['text']}")
    return "\n".join(lines)

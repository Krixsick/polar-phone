import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


class JsonTaskStore:
    def __init__(
        self,
        file_path: Path | None = None,
        timezone: str = "America/Toronto",
    ):
        self.timezone = ZoneInfo(timezone)

        if file_path is None:
            self.file_path = Path(__file__).resolve().parent.parent / "tasks.json"
        else:
            self.file_path = file_path

    def _today(self) -> str:
        return datetime.now(self.timezone).strftime("%Y-%m-%d")

    def _now(self) -> str:
        return datetime.now(self.timezone).isoformat()

    def _default_data(self) -> dict:
        return {
            "date": self._today(),
            "tasks": [],
        }

    def _load(self) -> dict:
        if not self.file_path.exists():
            return self._default_data()

        try:
            data = json.loads(self.file_path.read_text())

            if "date" not in data:
                data["date"] = self._today()

            if "tasks" not in data:
                data["tasks"] = []

            return data

        except json.JSONDecodeError:
            return self._default_data()

    def _save(self, data: dict) -> None:
        self.file_path.write_text(json.dumps(data, indent=2))

    def get_today(self) -> list[dict]:
        data = self._load()

        if data["date"] != self._today():
            return []

        return data["tasks"]

    def has_today_tasks(self) -> bool:
        return len(self.get_today()) > 0

    def set_today_tasks(self, task_texts: list[str]) -> list[dict]:
        tasks = []

        for text in task_texts:
            tasks.append({
                "text": text,
                "done": False,
                "created_at": self._now(),
                "completed_at": None,
            })

        data = {
            "date": self._today(),
            "tasks": tasks,
        }

        self._save(data)
        return tasks

    def add_task(self, text: str) -> dict:
        data = self._load()

        if data["date"] != self._today():
            data = self._default_data()

        task = {
            "text": text,
            "done": False,
            "created_at": self._now(),
            "completed_at": None,
        }

        data["tasks"].append(task)
        self._save(data)

        return task

    def mark_done(self, index: int) -> bool:
        data = self._load()

        if data["date"] != self._today():
            return False

        tasks = data["tasks"]

        if index < 0 or index >= len(tasks):
            return False

        tasks[index]["done"] = True
        tasks[index]["completed_at"] = self._now()

        self._save(data)
        return True

    def mark_undone(self, index: int) -> bool:
        data = self._load()

        if data["date"] != self._today():
            return False

        tasks = data["tasks"]

        if index < 0 or index >= len(tasks):
            return False

        tasks[index]["done"] = False
        tasks[index]["completed_at"] = None

        self._save(data)
        return True

    def tasks_as_text(self) -> str:
        tasks = self.get_today()

        lines = []

        for index, task in enumerate(tasks):
            box = "x" if task["done"] else " "
            lines.append(f"{index}. [{box}] {task['text']}")

        return "\n".join(lines)

    def get_progress_summary(self) -> str:
        tasks = self.get_today()

        if not tasks:
            return "no tasks for today yet"

        done_count = sum(1 for task in tasks if task["done"])
        total_count = len(tasks)

        return f"{done_count}/{total_count} tasks done"

    def clear_today(self) -> None:
        self._save(self._default_data())


task_store = JsonTaskStore()
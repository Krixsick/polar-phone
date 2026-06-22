from collections.abc import Iterator
from contextlib import contextmanager
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class SQLiteTaskStore:
    def __init__(
        self,
        db_path: Path | str | None = None,
        timezone: str = "America/Toronto",
        migrate_json_path: Path | str | None = PROJECT_ROOT / "tasks.json",
    ):
        self.timezone = ZoneInfo(timezone)

        if db_path is None:
            env_path = os.environ.get("POLAR_PHONE_DB_PATH")
            self.db_path = Path(env_path) if env_path else PROJECT_ROOT / "polar_phone.sqlite3"
        else:
            self.db_path = Path(db_path)

        self.migrate_json_path = (
            Path(migrate_json_path) if migrate_json_path is not None else None
        )

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._migrate_json_tasks()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL,
                    task_date TEXT,
                    recurrence TEXT NOT NULL DEFAULT 'none'
                        CHECK (recurrence IN ('none', 'daily')),
                    position INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    archived_at TEXT
                );

                CREATE TABLE IF NOT EXISTS task_completions (
                    task_id INTEGER NOT NULL,
                    completion_date TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    PRIMARY KEY (task_id, completion_date),
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS store_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_tasks_date
                    ON tasks(task_date, archived_at, position);

                CREATE INDEX IF NOT EXISTS idx_tasks_recurrence
                    ON tasks(recurrence, archived_at, position);

                CREATE INDEX IF NOT EXISTS idx_completions_date
                    ON task_completions(completion_date);
                """
            )

    def _migrate_json_tasks(self) -> None:
        if self.migrate_json_path is None or not self.migrate_json_path.exists():
            return

        with self._connect() as connection:
            migrated = connection.execute(
                "SELECT value FROM store_metadata WHERE key = ?",
                ("json_tasks_migrated",),
            ).fetchone()

            if migrated:
                return

            try:
                data = json.loads(self.migrate_json_path.read_text())
            except json.JSONDecodeError:
                data = {}

            task_date = data.get("date")
            tasks = data.get("tasks", [])

            if task_date and isinstance(tasks, list):
                for position, task in enumerate(tasks):
                    if not isinstance(task, dict) or not task.get("text"):
                        continue

                    cursor = connection.execute(
                        """
                        INSERT INTO tasks (
                            text,
                            task_date,
                            recurrence,
                            position,
                            created_at
                        )
                        VALUES (?, ?, 'none', ?, ?)
                        """,
                        (
                            task["text"],
                            task_date,
                            position,
                            task.get("created_at") or self._now(),
                        ),
                    )

                    if task.get("done"):
                        connection.execute(
                            """
                            INSERT OR REPLACE INTO task_completions (
                                task_id,
                                completion_date,
                                completed_at
                            )
                            VALUES (?, ?, ?)
                            """,
                            (
                                cursor.lastrowid,
                                task_date,
                                task.get("completed_at") or self._now(),
                            ),
                        )

            connection.execute(
                """
                INSERT OR REPLACE INTO store_metadata (key, value)
                VALUES (?, ?)
                """,
                ("json_tasks_migrated", self._now()),
            )

    def _today(self) -> str:
        return datetime.now(self.timezone).strftime("%Y-%m-%d")

    def _now(self) -> str:
        return datetime.now(self.timezone).isoformat()

    def _next_position(
        self,
        connection: sqlite3.Connection,
        task_date: str | None,
        recurrence: str,
    ) -> int:
        row = connection.execute(
            """
            SELECT COALESCE(MAX(position), -1) + 1 AS next_position
            FROM tasks
            WHERE archived_at IS NULL
                AND recurrence = ?
                AND (
                    (? IS NULL AND task_date IS NULL)
                    OR task_date = ?
                )
            """,
            (recurrence, task_date, task_date),
        ).fetchone()

        return int(row["next_position"])

    def _task_from_row(self, row: sqlite3.Row) -> dict:
        completed_at = row["completed_at"]

        return {
            "id": row["id"],
            "text": row["text"],
            "done": completed_at is not None,
            "created_at": row["created_at"],
            "completed_at": completed_at,
            "recurrence": row["recurrence"],
        }

    def _task_at_index(self, index: int, day: str) -> dict | None:
        tasks = self.get_tasks_for_date(day)

        if index < 0 or index >= len(tasks):
            return None

        return tasks[index]

    def get_tasks_for_date(self, day: str) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    tasks.id,
                    tasks.text,
                    tasks.recurrence,
                    tasks.position,
                    tasks.created_at,
                    task_completions.completed_at
                FROM tasks
                LEFT JOIN task_completions
                    ON task_completions.task_id = tasks.id
                    AND task_completions.completion_date = ?
                WHERE tasks.archived_at IS NULL
                    AND (
                        tasks.task_date = ?
                        OR tasks.recurrence = 'daily'
                    )
                ORDER BY
                    CASE WHEN tasks.task_date = ? THEN 0 ELSE 1 END,
                    tasks.position ASC,
                    tasks.created_at ASC,
                    tasks.id ASC
                """,
                (day, day, day),
            ).fetchall()

        return [self._task_from_row(row) for row in rows]

    def get_today(self) -> list[dict]:
        return self.get_tasks_for_date(self._today())

    def has_today_tasks(self) -> bool:
        return len(self.get_today()) > 0

    def set_today_tasks(self, task_texts: list[str]) -> list[dict]:
        today = self._today()
        now = self._now()
        clean_task_texts = [text.strip() for text in task_texts if text.strip()]

        with self._connect() as connection:
            connection.execute(
                """
                UPDATE tasks
                SET archived_at = ?
                WHERE task_date = ?
                    AND recurrence = 'none'
                    AND archived_at IS NULL
                """,
                (now, today),
            )

            for position, text in enumerate(clean_task_texts):
                connection.execute(
                    """
                    INSERT INTO tasks (
                        text,
                        task_date,
                        recurrence,
                        position,
                        created_at
                    )
                    VALUES (?, ?, 'none', ?, ?)
                    """,
                    (text, today, position, now),
                )

        return self.get_today()

    def add_task(self, text: str, recurrence: str = "none") -> dict:
        if recurrence not in {"none", "daily"}:
            raise ValueError("recurrence must be 'none' or 'daily'")

        clean_text = text.strip()
        if not clean_text:
            raise ValueError("task text cannot be empty")

        today = self._today()
        task_date = None if recurrence == "daily" else today
        now = self._now()

        with self._connect() as connection:
            position = self._next_position(connection, task_date, recurrence)
            cursor = connection.execute(
                """
                INSERT INTO tasks (
                    text,
                    task_date,
                    recurrence,
                    position,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (clean_text, task_date, recurrence, position, now),
            )
            task_id = cursor.lastrowid

        for task in self.get_today():
            if task["id"] == task_id:
                return task

        raise RuntimeError("created task was not found")

    def add_daily_task(self, text: str) -> dict:
        return self.add_task(text, recurrence="daily")

    def mark_done(self, index: int) -> bool:
        today = self._today()
        task = self._task_at_index(index, today)

        if task is None:
            return False

        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO task_completions (
                    task_id,
                    completion_date,
                    completed_at
                )
                VALUES (?, ?, ?)
                """,
                (task["id"], today, self._now()),
            )

        return True

    def mark_undone(self, index: int) -> bool:
        today = self._today()
        task = self._task_at_index(index, today)

        if task is None:
            return False

        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM task_completions
                WHERE task_id = ?
                    AND completion_date = ?
                """,
                (task["id"], today),
            )

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
        today = self._today()
        now = self._now()

        with self._connect() as connection:
            connection.execute(
                """
                UPDATE tasks
                SET archived_at = ?
                WHERE task_date = ?
                    AND recurrence = 'none'
                    AND archived_at IS NULL
                """,
                (now, today),
            )
            connection.execute(
                """
                DELETE FROM task_completions
                WHERE completion_date = ?
                    AND task_id IN (
                        SELECT id
                        FROM tasks
                        WHERE recurrence = 'daily'
                            AND archived_at IS NULL
                    )
                """,
                (today,),
            )


task_store = SQLiteTaskStore()

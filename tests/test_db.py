from datetime import datetime, timedelta
import os
from pathlib import Path
import tempfile
from tempfile import TemporaryDirectory
import unittest

os.environ["POLAR_PHONE_DB_PATH"] = str(
    Path(tempfile.gettempdir()) / "polar_phone_unittest_import.sqlite3"
)

from app.db import SQLiteTaskStore


class SQLiteTaskStoreTests(unittest.TestCase):
    def make_store(self, tmpdir: str) -> SQLiteTaskStore:
        return SQLiteTaskStore(
            db_path=Path(tmpdir) / "tasks.sqlite3",
            migrate_json_path=None,
        )

    def test_today_tasks_can_be_completed_and_uncompleted(self):
        with TemporaryDirectory() as tmpdir:
            store = self.make_store(tmpdir)
            store.set_today_tasks(["leetcode", "gym"])

            self.assertEqual(
                store.tasks_as_text(),
                "0. [ ] leetcode\n1. [ ] gym",
            )

            self.assertTrue(store.mark_done(1))
            self.assertEqual(store.get_progress_summary(), "1/2 tasks done")
            self.assertEqual(
                store.tasks_as_text(),
                "0. [ ] leetcode\n1. [x] gym",
            )

            self.assertTrue(store.mark_undone(1))
            self.assertEqual(store.get_progress_summary(), "0/2 tasks done")

    def test_daily_task_completion_is_per_day(self):
        with TemporaryDirectory() as tmpdir:
            store = self.make_store(tmpdir)
            store.add_daily_task("drink water")

            today = store._today()
            tomorrow = (
                datetime.strptime(today, "%Y-%m-%d") + timedelta(days=1)
            ).strftime("%Y-%m-%d")

            self.assertTrue(store.mark_done(0))

            self.assertTrue(store.get_tasks_for_date(today)[0]["done"])
            self.assertFalse(store.get_tasks_for_date(tomorrow)[0]["done"])

    def test_oauth_state_can_only_be_consumed_once(self):
        with TemporaryDirectory() as tmpdir:
            store = self.make_store(tmpdir)
            store.save_oauth_state("google", "state-value")

            self.assertTrue(store.consume_oauth_state("google", "state-value"))
            self.assertFalse(store.consume_oauth_state("google", "state-value"))

    def test_google_tokens_are_saved(self):
        with TemporaryDirectory() as tmpdir:
            store = self.make_store(tmpdir)
            store.save_google_tokens(
                {
                    "access_token": "access-token",
                    "refresh_token": "refresh-token",
                    "scope": "calendar-scope",
                    "token_type": "Bearer",
                },
                expires_at="2026-06-24T12:00:00+00:00",
            )

            self.assertEqual(
                store.get_google_tokens(),
                {
                    "access_token": "access-token",
                    "refresh_token": "refresh-token",
                    "expires_at": "2026-06-24T12:00:00+00:00",
                    "scope": "calendar-scope",
                    "token_type": "Bearer",
                    "updated_at": store.get_google_tokens()["updated_at"],
                },
            )


if __name__ == "__main__":
    unittest.main()

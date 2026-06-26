from datetime import datetime
from zoneinfo import ZoneInfo
import unittest

from app.task_summary import (
    format_task_summary,
    looks_like_task_summary_request,
    resolve_task_summary_day,
)


class TaskSummaryTests(unittest.TestCase):
    def test_looks_like_task_summary_request(self):
        self.assertTrue(looks_like_task_summary_request("what are my tasks tomorrow?"))
        self.assertTrue(looks_like_task_summary_request("what do i have to do friday?"))
        self.assertFalse(looks_like_task_summary_request("what's on my calendar tomorrow?"))
        self.assertFalse(
            looks_like_task_summary_request(
                "what tasks and events do i have tomorrow?"
            )
        )

    def test_resolve_task_summary_day_today_and_tomorrow(self):
        now = datetime(2026, 6, 25, 10, 0, tzinfo=ZoneInfo("America/Toronto"))

        self.assertEqual(resolve_task_summary_day("tasks today", now), "2026-06-25")
        self.assertEqual(resolve_task_summary_day("tasks tomorrow", now), "2026-06-26")

    def test_resolve_task_summary_day_weekday(self):
        now = datetime(2026, 6, 25, 10, 0, tzinfo=ZoneInfo("America/Toronto"))

        self.assertEqual(resolve_task_summary_day("tasks friday", now), "2026-06-26")
        self.assertEqual(resolve_task_summary_day("tasks thursday", now), "2026-07-02")

    def test_format_task_summary(self):
        self.assertEqual(
            format_task_summary(
                [
                    {"text": "LeetCode", "done": False},
                    {"text": "Gym", "done": True},
                ],
                "2026-06-25",
            ),
            "Thursday Jun 25 tasks:\n0. [ ] LeetCode\n1. [x] Gym",
        )

    def test_format_task_summary_empty(self):
        self.assertEqual(
            format_task_summary([], "2026-06-25"),
            "no saved tasks for Thursday Jun 25 yet.",
        )


if __name__ == "__main__":
    unittest.main()

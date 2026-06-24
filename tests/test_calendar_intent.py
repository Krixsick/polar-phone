from datetime import datetime
from zoneinfo import ZoneInfo
import unittest

from app.calendar_intent import (
    build_calendar_extraction_message,
    format_calendar_event_confirmation,
    looks_like_calendar_request,
    parse_calendar_event_intent,
)


class CalendarIntentTests(unittest.TestCase):
    def test_looks_like_calendar_request(self):
        self.assertTrue(looks_like_calendar_request("add gym tomorrow at 6pm"))
        self.assertTrue(looks_like_calendar_request("book dentist friday"))
        self.assertTrue(looks_like_calendar_request("put this on my calendar"))
        self.assertFalse(looks_like_calendar_request("finished gym"))
        self.assertFalse(looks_like_calendar_request("what should i do today"))

    def test_build_calendar_extraction_message(self):
        current_time = datetime(
            2026,
            6,
            24,
            10,
            0,
            tzinfo=ZoneInfo("America/Toronto"),
        )

        self.assertEqual(
            build_calendar_extraction_message("add gym tomorrow at 6pm", current_time),
            (
                "current local time: Wednesday 2026-06-24 10:00 AM -0400\n"
                "message: add gym tomorrow at 6pm"
            ),
        )

    def test_parse_calendar_event_intent_accepts_create_event(self):
        self.assertEqual(
            parse_calendar_event_intent(
                """
                {
                  "action": "create_event",
                  "summary": "Gym",
                  "start_iso": "2026-06-25T18:00:00-04:00",
                  "end_iso": "2026-06-25T19:00:00-04:00",
                  "timezone": "America/Toronto",
                  "description": null
                }
                """
            ),
            {
                "action": "create_event",
                "summary": "Gym",
                "start_iso": "2026-06-25T18:00:00-04:00",
                "end_iso": "2026-06-25T19:00:00-04:00",
                "timezone": "America/Toronto",
                "description": None,
            },
        )

    def test_parse_calendar_event_intent_handles_markdown_json(self):
        self.assertEqual(
            parse_calendar_event_intent('```json\n{"action": "none"}\n```'),
            {"action": "none"},
        )

    def test_parse_calendar_event_intent_accepts_needs_more_info(self):
        self.assertEqual(
            parse_calendar_event_intent(
                '{"action": "needs_more_info", "missing": ["time"], "message": "what time?"}'
            ),
            {
                "action": "needs_more_info",
                "missing": ["time"],
                "message": "what time?",
            },
        )

    def test_parse_calendar_event_intent_rejects_invalid_dates(self):
        self.assertEqual(
            parse_calendar_event_intent(
                """
                {
                  "action": "create_event",
                  "summary": "Gym",
                  "start_iso": "2026-06-25T19:00:00-04:00",
                  "end_iso": "2026-06-25T18:00:00-04:00"
                }
                """
            ),
            {"action": "none"},
        )

    def test_format_calendar_event_confirmation(self):
        self.assertEqual(
            format_calendar_event_confirmation(
                {
                    "summary": "Gym",
                    "start": {"dateTime": "2026-06-25T18:00:00-04:00"},
                    "htmlLink": "https://calendar.google.com/event?id=123",
                }
            ),
            (
                "added Gym to your calendar for 2026-06-25T18:00:00-04:00\n"
                "https://calendar.google.com/event?id=123"
            ),
        )


if __name__ == "__main__":
    unittest.main()

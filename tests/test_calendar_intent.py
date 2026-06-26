from datetime import datetime
from zoneinfo import ZoneInfo
import unittest

from app.calendar_intent import (
    build_calendar_extraction_message,
    calendar_day_range,
    format_calendar_event_confirmation,
    format_calendar_events_summary,
    looks_like_calendar_request,
    looks_like_calendar_summary_request,
    parse_calendar_event_intent,
    parse_calendar_summary_intent,
)


class CalendarIntentTests(unittest.TestCase):
    def test_looks_like_calendar_request(self):
        self.assertTrue(looks_like_calendar_request("add gym tomorrow at 6pm"))
        self.assertTrue(
            looks_like_calendar_request(
                "Can you add a Google Calendar event at 3pm today named test that goes until 4:30pm"
            )
        )
        self.assertTrue(looks_like_calendar_request("book dentist friday"))
        self.assertTrue(looks_like_calendar_request("put this on my calendar"))
        self.assertFalse(looks_like_calendar_request("finished gym"))
        self.assertFalse(looks_like_calendar_request("what should i do today"))

    def test_looks_like_calendar_summary_request(self):
        self.assertTrue(looks_like_calendar_summary_request("what's on my calendar today?"))
        self.assertTrue(looks_like_calendar_summary_request("summarize my calendar tomorrow"))
        self.assertTrue(looks_like_calendar_summary_request("am i free monday?"))
        self.assertTrue(looks_like_calendar_summary_request("what event do i have tomorrow?"))
        self.assertTrue(
            looks_like_calendar_summary_request(
                "what tasks and events do i have tomorrow?"
            )
        )
        self.assertTrue(looks_like_calendar_summary_request("what do i have friday?"))
        self.assertFalse(looks_like_calendar_summary_request("add gym tomorrow at 6pm"))
        self.assertFalse(
            looks_like_calendar_summary_request(
                "add a Google Calendar event at 3pm today named test"
            )
        )

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

    def test_parse_calendar_summary_intent_accepts_summary(self):
        self.assertEqual(
            parse_calendar_summary_intent(
                '{"action": "summarize_events", "date": "2026-06-25", "timezone": "America/Toronto"}'
            ),
            {
                "action": "summarize_events",
                "date": "2026-06-25",
                "timezone": "America/Toronto",
            },
        )

    def test_parse_calendar_summary_intent_accepts_needs_more_info(self):
        self.assertEqual(
            parse_calendar_summary_intent(
                '{"action": "needs_more_info", "message": "which day should i check?"}'
            ),
            {
                "action": "needs_more_info",
                "message": "which day should i check?",
            },
        )

    def test_calendar_day_range(self):
        self.assertEqual(
            calendar_day_range("2026-06-25", "America/Toronto"),
            (
                "2026-06-25T00:00:00-04:00",
                "2026-06-26T00:00:00-04:00",
            ),
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

    def test_format_calendar_events_summary(self):
        self.assertEqual(
            format_calendar_events_summary(
                [
                    {
                        "summary": "Gym",
                        "start": {"dateTime": "2026-06-25T15:00:00-04:00"},
                        "end": {"dateTime": "2026-06-25T16:30:00-04:00"},
                    },
                    {
                        "summary": "Holiday",
                        "start": {"date": "2026-06-25"},
                        "end": {"date": "2026-06-26"},
                    },
                ],
                "2026-06-25",
            ),
            "Thursday Jun 25:\n- 3:00 pm-4:30 pm: Gym\n- all day: Holiday",
        )

    def test_format_calendar_events_summary_empty(self):
        self.assertEqual(
            format_calendar_events_summary([], "2026-06-25"),
            "nothing on your calendar for Thursday Jun 25.",
        )


if __name__ == "__main__":
    unittest.main()

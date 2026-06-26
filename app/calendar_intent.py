import json
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


CALENDAR_ACTION_WORDS = (
    "add",
    "book",
    "calendar",
    "create",
    "put",
    "schedule",
)
CALENDAR_TIME_WORDS = (
    "today",
    "tomorrow",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "am",
    "pm",
)
CALENDAR_SUMMARY_WORDS = (
    "agenda",
    "events",
    "free",
    "have",
    "on my calendar",
    "schedule",
    "summarize",
    "summary",
    "what's on",
)
CALENDAR_CONTEXT_WORDS = (
    "agenda",
    "calendar",
    "calender",
    "event",
    "events",
    "schedule",
)
CALENDAR_CREATION_WORDS = (
    "add",
    "book",
    "create",
    "put",
)


def looks_like_calendar_request(user_text: str) -> bool:
    text = user_text.lower()

    if "calendar" in text or "schedule" in text or "book" in text:
        return True

    has_action = any(word in text.split() for word in CALENDAR_ACTION_WORDS)
    has_time_hint = any(word in text for word in CALENDAR_TIME_WORDS) or ":" in text

    return has_action and has_time_hint


def looks_like_calendar_summary_request(user_text: str) -> bool:
    text = user_text.lower()
    words = text.split()

    if any(word in words for word in CALENDAR_CREATION_WORDS):
        return False

    has_calendar_context = any(word in text for word in CALENDAR_CONTEXT_WORDS)
    has_summary_word = any(word in text for word in CALENDAR_SUMMARY_WORDS)
    has_day_hint = any(word in text for word in CALENDAR_TIME_WORDS)
    asks_what_have = "what do i have" in text or "what have i got" in text
    asks_tasks_and_events = "tasks" in text and (
        "event" in text or "calendar" in text or "calender" in text
    )

    return (
        (has_calendar_context and has_summary_word)
        or ("free" in text and has_day_hint)
        or (asks_what_have and has_day_hint)
        or (asks_tasks_and_events and has_day_hint)
    )


def build_calendar_extraction_message(
    user_text: str,
    current_local_time: datetime,
) -> str:
    return (
        "current local time: "
        f"{current_local_time.strftime('%A %Y-%m-%d %I:%M %p %z')}\n"
        f"message: {user_text}"
    )


def _strip_json_markdown(raw_text: str) -> str:
    text = raw_text.strip()

    if not text.startswith("```"):
        return text

    lines = text.splitlines()[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]

    return "\n".join(lines).strip()


def _parse_iso_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def parse_calendar_event_intent(raw_text: str) -> dict:
    try:
        data = json.loads(_strip_json_markdown(raw_text))
    except json.JSONDecodeError:
        return {"action": "none"}

    if not isinstance(data, dict):
        return {"action": "none"}

    action = data.get("action")
    if action == "none":
        return {"action": "none"}

    if action == "needs_more_info":
        message = data.get("message")
        if not isinstance(message, str) or not message.strip():
            message = "what day and time should i put it for?"

        missing = data.get("missing")
        if not isinstance(missing, list):
            missing = []

        return {
            "action": "needs_more_info",
            "missing": [item for item in missing if isinstance(item, str)],
            "message": message.strip(),
        }

    if action != "create_event":
        return {"action": "none"}

    summary = data.get("summary")
    start_iso = data.get("start_iso")
    end_iso = data.get("end_iso")
    timezone = data.get("timezone") or "America/Toronto"
    description = data.get("description")

    if not isinstance(summary, str) or not summary.strip():
        return {"action": "none"}

    if not isinstance(start_iso, str) or not isinstance(end_iso, str):
        return {"action": "none"}

    start_at = _parse_iso_datetime(start_iso)
    end_at = _parse_iso_datetime(end_iso)
    if start_at is None or end_at is None or end_at <= start_at:
        return {"action": "none"}

    if not isinstance(timezone, str) or not timezone.strip():
        timezone = "America/Toronto"

    if description is not None and not isinstance(description, str):
        description = None

    return {
        "action": "create_event",
        "summary": summary.strip(),
        "start_iso": start_iso,
        "end_iso": end_iso,
        "timezone": timezone.strip(),
        "description": description.strip() if isinstance(description, str) else None,
    }


def parse_calendar_summary_intent(raw_text: str) -> dict:
    try:
        data = json.loads(_strip_json_markdown(raw_text))
    except json.JSONDecodeError:
        return {"action": "none"}

    if not isinstance(data, dict):
        return {"action": "none"}

    action = data.get("action")
    if action == "none":
        return {"action": "none"}

    if action == "needs_more_info":
        message = data.get("message")
        if not isinstance(message, str) or not message.strip():
            message = "which day should i check?"

        return {
            "action": "needs_more_info",
            "message": message.strip(),
        }

    if action != "summarize_events":
        return {"action": "none"}

    day = data.get("date")
    timezone = data.get("timezone") or "America/Toronto"

    if not isinstance(day, str) or not isinstance(timezone, str):
        return {"action": "none"}

    try:
        date.fromisoformat(day)
    except ValueError:
        return {"action": "none"}

    return {
        "action": "summarize_events",
        "date": day,
        "timezone": timezone,
    }


def calendar_day_range(day: str, timezone: str) -> tuple[str, str]:
    tzinfo = ZoneInfo(timezone)
    start = datetime.combine(date.fromisoformat(day), time.min, tzinfo=tzinfo)
    end = start + timedelta(days=1)

    return start.isoformat(), end.isoformat()


def format_calendar_event_confirmation(event: dict) -> str:
    summary = event.get("summary") or "Event"
    start = event.get("start", {})
    start_time = start.get("dateTime")
    html_link = event.get("htmlLink")

    if html_link and start_time:
        return f"added {summary} to your calendar for {start_time}\n{html_link}"

    if start_time:
        return f"added {summary} to your calendar for {start_time}"

    return f"added {summary} to your calendar"


def _format_event_time(value: str, timezone: str) -> str:
    parsed = datetime.fromisoformat(value)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone))
    else:
        parsed = parsed.astimezone(ZoneInfo(timezone))

    return parsed.strftime("%-I:%M %p").lower()


def format_calendar_events_summary(
    events: list[dict],
    day: str,
    timezone: str = "America/Toronto",
) -> str:
    display_day = date.fromisoformat(day).strftime("%A %b %-d")

    if not events:
        return f"nothing on your calendar for {display_day}."

    lines = [f"{display_day}:"]

    for event in events:
        title = event.get("summary") or "Untitled event"
        start = event.get("start", {})
        end = event.get("end", {})

        if "dateTime" in start:
            start_time = _format_event_time(start["dateTime"], timezone)
            end_time = _format_event_time(end["dateTime"], timezone)
            lines.append(f"- {start_time}-{end_time}: {title}")
        else:
            lines.append(f"- all day: {title}")

    return "\n".join(lines)

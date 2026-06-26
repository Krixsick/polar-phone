from datetime import date, datetime, timedelta


WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

TASK_CONTEXT_WORDS = (
    "task",
    "tasks",
    "to do",
    "todo",
    "list",
)

GOOGLE_CALENDAR_CONTEXT_WORDS = (
    "agenda",
    "calendar",
    "calender",
    "event",
    "events",
    "schedule",
)


def looks_like_task_summary_request(user_text: str) -> bool:
    text = user_text.lower()
    if any(word in text for word in GOOGLE_CALENDAR_CONTEXT_WORDS):
        return False

    has_task_context = any(word in text for word in TASK_CONTEXT_WORDS)
    has_day_context = (
        "today" in text
        or "tomorrow" in text
        or any(day in text for day in WEEKDAYS)
    )

    return has_task_context and has_day_context


def resolve_task_summary_day(user_text: str, current_local_time: datetime) -> str | None:
    text = user_text.lower()
    current_day = current_local_time.date()

    if "today" in text:
        return current_day.isoformat()

    if "tomorrow" in text:
        return (current_day + timedelta(days=1)).isoformat()

    for weekday_name, weekday_number in WEEKDAYS.items():
        if weekday_name not in text:
            continue

        days_until = (weekday_number - current_day.weekday()) % 7
        if days_until == 0:
            days_until = 7

        return (current_day + timedelta(days=days_until)).isoformat()

    return None


def format_task_summary(tasks: list[dict], day: str) -> str:
    display_day = date.fromisoformat(day).strftime("%A %b %-d")

    if not tasks:
        return f"no saved tasks for {display_day} yet."

    lines = [f"{display_day} tasks:"]

    for index, task in enumerate(tasks):
        box = "x" if task["done"] else " "
        lines.append(f"{index}. [{box}] {task['text']}")

    return "\n".join(lines)

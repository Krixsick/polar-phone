def build_completion_extraction_message(task_text: str, user_text: str) -> str:
    return f"list:\n{task_text}\n\nmessage:\n{user_text}"


def parse_completed_task_index(raw_text: str, task_count: int) -> int | None:
    result = raw_text.strip().lower()

    if result == "none":
        return None

    if not result.isdigit():
        return None

    index = int(result)
    if index < 0 or index >= task_count:
        return None

    return index

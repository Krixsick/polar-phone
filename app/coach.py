import os
import asyncio
import json
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from anthropic import Anthropic
from dotenv import load_dotenv
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
from app.configs import (
    CALENDAR_MODEL,
    CLAUDE_API,
    COACH_MODEL,
    EXTRACTOR_MODEL,
    MAX_TOKENS,
)
from app.google_calendar import (
    GoogleCalendarAuthError,
    GoogleCalendarConfigError,
    build_google_auth_route_url,
    build_google_authorization_url,
    create_google_calendar_event,
    exchange_google_code_for_tokens,
    get_google_debug_config,
    list_google_calendar_events_for_visible_calendars,
    make_google_oauth_state,
    token_expires_at,
)
from app.prompts import (
    CALENDAR_EVENT_PROMPT,
    CALENDAR_SUMMARY_PROMPT,
    COACH_PROMPT,
    EXTRACTOR_PROMPT,
    USER_PROFILE,
    MORNING_PROMPT,
)
from app.task_completion import (
    build_completion_extraction_message,
    parse_completed_task_index,
)
from app.task_summary import (
    format_task_summary,
    looks_like_task_summary_request,
    resolve_task_summary_day,
)

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from contextlib import asynccontextmanager
from zoneinfo import ZoneInfo
from app.db import task_store

load_dotenv()


scheduler = AsyncIOScheduler(timezone=ZoneInfo("America/Toronto"))

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
MY_TELEGRAM_ID = os.environ.get("MY_TELEGRAM_ID")  # for proactive messages


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(
        send_morning_message,
        CronTrigger(
            hour=7,
            minute=0,
            timezone=ZoneInfo("America/Toronto"),
        ),
        id="morning_message",
        replace_existing=True,
    )

    scheduler.start()

    yield

    scheduler.shutdown()
    

claude = Anthropic()
app = FastAPI(lifespan=lifespan)

"""
Helper functions
"""

def generate_reply(user_text: str) -> str:
    task_text = task_store.tasks_as_text()
    now = datetime.now(task_store.timezone)
    
    system = f"""{COACH_PROMPT}

    current time: {now.strftime("%A %Y-%m-%d %I:%M %p")}

    today's tasks:
    {task_text if task_text else "no saved tasks for today"}
    """

    reply = claude.messages.create(
        model=COACH_MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[
            {"role": "user", "content": user_text},
        ],
    )
    return reply.content[0].text

def extract_completed_task_index(user_text: str) -> int | None:
    tasks = task_store.get_today()
    if not tasks:
        return None

    task_text = task_store.tasks_as_text()
    reply = claude.messages.create(
        model=EXTRACTOR_MODEL,
        max_tokens=10,
        system=EXTRACTOR_PROMPT,
        messages=[
            {
                "role": "user",
                "content": build_completion_extraction_message(task_text, user_text),
            },
        ],
    )

    raw_result = reply.content[0].text
    return parse_completed_task_index(raw_result, len(tasks))

def mark_completed_task_from_message(user_text: str) -> int | None:
    completed_index = extract_completed_task_index(user_text)

    if completed_index is None:
        return None

    if not task_store.mark_done(completed_index):
        return None

    return completed_index

def extract_calendar_event_intent(user_text: str) -> dict:
    if not looks_like_calendar_request(user_text):
        return {"action": "none"}

    now = datetime.now(task_store.timezone)
    reply = claude.messages.create(
        model=CALENDAR_MODEL,
        max_tokens=MAX_TOKENS,
        system=CALENDAR_EVENT_PROMPT,
        messages=[
            {
                "role": "user",
                "content": build_calendar_extraction_message(user_text, now),
            },
        ],
    )

    raw_result = reply.content[0].text
    print("Calendar intent raw result:", raw_result, flush=True)
    return parse_calendar_event_intent(raw_result)

def extract_calendar_summary_intent(user_text: str) -> dict:
    if not looks_like_calendar_summary_request(user_text):
        return {"action": "none"}

    now = datetime.now(task_store.timezone)
    reply = claude.messages.create(
        model=CALENDAR_MODEL,
        max_tokens=MAX_TOKENS,
        system=CALENDAR_SUMMARY_PROMPT,
        messages=[
            {
                "role": "user",
                "content": build_calendar_extraction_message(user_text, now),
            },
        ],
    )

    raw_result = reply.content[0].text
    print("Calendar summary raw result:", raw_result, flush=True)
    return parse_calendar_summary_intent(raw_result)

async def summarize_calendar_from_message(user_text: str) -> str | None:
    is_summary_request = looks_like_calendar_summary_request(user_text)

    try:
        intent = extract_calendar_summary_intent(user_text)
    except Exception as exc:
        print("Calendar summary extraction failed:", exc, flush=True)
        return "i couldn't read that calendar summary request. try: what's on my calendar today?"

    action = intent["action"]

    if action == "none" and is_summary_request:
        return "i saw this as a calendar summary request, but couldn't parse the day. try: what's on my calendar today?"

    if action == "none":
        return None

    if action == "needs_more_info":
        return intent["message"]

    try:
        start_iso, end_iso = calendar_day_range(intent["date"], intent["timezone"])
        events = await list_google_calendar_events_for_visible_calendars(
            task_store,
            start_iso=start_iso,
            end_iso=end_iso,
            timezone=intent["timezone"],
        )
    except GoogleCalendarAuthError:
        try:
            auth_url = build_google_auth_route_url()
        except GoogleCalendarConfigError as exc:
            return f"Google Calendar is not connected, and config is missing: {exc}"

        return f"connect Google Calendar first: {auth_url}"
    except GoogleCalendarConfigError as exc:
        return f"calendar config is missing: {exc}"
    except httpx.HTTPStatusError as exc:
        return f"Google Calendar rejected that request: {exc.response.text}"
    except httpx.RequestError as exc:
        return f"couldn't reach Google Calendar: {exc}"
    except Exception as exc:
        print("Google Calendar event summary failed:", exc, flush=True)
        return "i couldn't summarize your calendar. check Railway logs for the exact error."

    return format_calendar_events_summary(
        events,
        day=intent["date"],
        timezone=intent["timezone"],
    )

async def create_calendar_event_from_message(user_text: str) -> str | None:
    is_calendar_request = looks_like_calendar_request(user_text)

    try:
        intent = extract_calendar_event_intent(user_text)
    except Exception as exc:
        print("Calendar intent extraction failed:", exc, flush=True)
        return "i couldn't read that calendar request. try: add test today at 3pm until 4:30pm"

    action = intent["action"]

    if action == "none" and is_calendar_request:
        return "i saw this as a calendar request, but couldn't parse it. try: add test today at 3pm until 4:30pm"

    if action == "none":
        return None

    if action == "needs_more_info":
        return intent["message"]

    try:
        event = await create_google_calendar_event(
            task_store,
            summary=intent["summary"],
            start_iso=intent["start_iso"],
            end_iso=intent["end_iso"],
            timezone=intent["timezone"],
            description=intent["description"],
        )
    except GoogleCalendarAuthError:
        try:
            auth_url = build_google_auth_route_url()
        except GoogleCalendarConfigError as exc:
            return f"Google Calendar is not connected, and config is missing: {exc}"

        return f"connect Google Calendar first: {auth_url}"
    except GoogleCalendarConfigError as exc:
        return f"calendar config is missing: {exc}"
    except httpx.HTTPStatusError as exc:
        return f"Google Calendar rejected that event: {exc.response.text}"
    except httpx.RequestError as exc:
        return f"couldn't reach Google Calendar: {exc}"
    except Exception as exc:
        print("Google Calendar event creation failed:", exc, flush=True)
        return "i couldn't add that calendar event. check the server logs for the exact error."

    return format_calendar_event_confirmation(event)

def summarize_tasks_from_message(user_text: str) -> str | None:
    if not looks_like_task_summary_request(user_text):
        return None

    now = datetime.now(task_store.timezone)
    day = resolve_task_summary_day(user_text, now)
    if day is None:
        return "which day should i check tasks for?"

    tasks = task_store.get_tasks_for_date(day)
    return format_task_summary(tasks, day)

def send_telegram(chat_id: int | str, text: str) -> dict:
    """POST to Telegram's /sendMessage endpoint."""
    response = httpx.post(
        f"{TELEGRAM_API}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=5.0,
    )
    response.raise_for_status()
    return response.json()

def morning_message() -> str:
    """Generate today's task list and return a short morning text to send."""
    now = datetime.now(task_store.timezone)
    today = now.strftime("%A %Y-%m-%d")
    day_of_week = now.strftime("%A")

    user_context = f"""
        today is {today}
        day of week: {day_of_week}

        linus's default cadence:
        - weekdays: leetcode, review coding notes, reading/writing, exercise, do hobbies (coding, blender, writing, sports)
        - tuesday/thursday: add system design
        - weekends: learning new stuff, exercise, reading/writing, do hobbies (coding, blender, writing, sports)

        no special context was provided today, so make a reasonable default plan.
        
        """

    reply = claude.messages.create(
        model=COACH_MODEL,
        max_tokens=MAX_TOKENS,
        system=MORNING_PROMPT,
        messages=[
            {"role": "user", "content": user_context}
        ],
    )
    
    raw_text = reply.content[0].text.strip()
    json_text = raw_text
    if json_text.startswith("```"):
        lines = json_text.splitlines()

        # remove opening line, like ```json
        lines = lines[1:]
        print(lines)

        # remove closing line, like ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        print(lines)
        json_text = "\n".join(lines).strip()

    try:
        data = json.loads(json_text)
        print("PARSED MORNING DATA:", data, flush=True)

        task_store.set_today_tasks(data["tasks"])
        return data["message"]

    except (json.JSONDecodeError, KeyError) as e:
        print("Failed to parse morning JSON:", e, flush=True)
        return raw_text
def send_morning_message():
    morning_text = morning_message()
    send_telegram(MY_TELEGRAM_ID, morning_text)

@app.post("/telegram")
async def send_message(request: Request):
    chat_id = None

    try:
        user_message = await request.json()

        message = user_message.get("message")
        if not message or "text" not in message:
            return {"ok": True}

        chat_id = message["chat"]["id"]
        incoming_text = message["text"]

        task_summary_reply = summarize_tasks_from_message(incoming_text)
        if task_summary_reply is not None:
            send_telegram(chat_id, task_summary_reply)
            return {"ok": True}

        calendar_summary_reply = await summarize_calendar_from_message(incoming_text)
        if calendar_summary_reply is not None:
            send_telegram(chat_id, calendar_summary_reply)
            return {"ok": True}

        calendar_reply = await create_calendar_event_from_message(incoming_text)
        if calendar_reply is not None:
            send_telegram(chat_id, calendar_reply)
            return {"ok": True}

        mark_completed_task_from_message(incoming_text)
        reply_text = generate_reply(incoming_text)
        send_telegram(chat_id, reply_text)

        return {"ok": True}

    except Exception as exc:
        print("Telegram webhook failed:", exc, flush=True)
        traceback.print_exc()

        if chat_id is not None:
            try:
                send_telegram(chat_id, "something broke on the server. check Railway logs.")
            except Exception as send_exc:
                print("Failed to send Telegram error message:", send_exc, flush=True)

        return {"ok": False, "error": str(exc)}

@app.get("/google/auth")
async def google_auth():
    state = make_google_oauth_state()
    task_store.save_oauth_state("google", state)

    try:
        authorization_url = build_google_authorization_url(state)
    except GoogleCalendarConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RedirectResponse(authorization_url)

@app.get("/google/oauth2callback")
async def google_oauth2callback(request: Request):
    error = request.query_params.get("error")
    if error:
        raise HTTPException(status_code=400, detail=f"Google OAuth error: {error}")

    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing OAuth code or state")

    if not task_store.consume_oauth_state("google", state):
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    try:
        token_data = await exchange_google_code_for_tokens(code)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Google token exchange failed: {exc.response.text}",
        ) from exc

    task_store.save_google_tokens(
        token_data,
        expires_at=token_expires_at(token_data["expires_in"]),
    )

    return {
        "ok": True,
        "message": "Google Calendar connected. You can close this tab.",
        "scope": token_data.get("scope"),
    }

@app.get("/google/status")
async def google_status():
    tokens = task_store.get_google_tokens()

    if tokens is None:
        return {"connected": False}

    return {
        "connected": True,
        "expires_at": tokens["expires_at"],
        "scope": tokens["scope"],
        "token_type": tokens["token_type"],
        "updated_at": tokens["updated_at"],
    }

@app.get("/google/debug-config")
async def google_debug_config():
    try:
        return get_google_debug_config()
    except GoogleCalendarConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

#used to test out our morning function
@app.post("/test-morning")
async def test_morning():
    morning_text = morning_message()
    send_telegram(MY_TELEGRAM_ID, morning_text)

    return {
        "ok": True,
        "message": morning_text,
        "tasks": task_store.get_today()
    }

    
    
@app.get("/")
async def health():
    """Railway health check."""
    return {"status": "ok"}

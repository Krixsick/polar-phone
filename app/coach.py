import os
import asyncio
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, Request
from anthropic import Anthropic
from dotenv import load_dotenv
from app.configs import CLAUDE_API, COACH_MODEL, MAX_TOKENS
from app.prompts import COACH_PROMPT, EXTRACTOR_PROMPT, USER_PROFILE, MORNING_PROMPT

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from contextlib import asynccontextmanager
from zoneinfo import ZoneInfo


load_dotenv()


scheduler = AsyncIOScheduler(timezone=ZoneInfo("America/Toronto"))

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
MY_TELEGRAM_ID = os.environ.get("MY_TELEGRAM_ID")  # for proactive messages


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(
        morning_message,
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
    """Ask Claude for a reply to the user's message."""
    reply = claude.messages.create(
        model=COACH_MODEL,
        max_tokens=MAX_TOKENS,
        system=COACH_PROMPT,                             
        messages=[                                        
            {"role": "user", "content": user_text},
        ],
    )
    return reply.content[0].text

def send_telegram(chat_id: int | str, text: str) -> dict:
    """POST to Telegram's /sendMessage endpoint."""
    response = httpx.post(
        f"{TELEGRAM_API}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()

def morning_message():
    morning_reply = claude.messages.create(
        model=COACH_MODEL,
        max_tokens=MAX_TOKENS,
        system=COACH_PROMPT,
        messages=[
            {"role": "user", "content": MORNING_PROMPT}
        ],
    )

    morning_text = morning_reply.content[0].text

    send_telegram(MY_TELEGRAM_ID, morning_text)

@app.post("/telegram")
async def send_message(request: Request):
    #Reading user's input
    user_message = await request.json()
    if not user_message["message"] or "text" not in user_message["message"]:
        return {"ok": True}
    
    chat_id = user_message["message"]["chat"]["id"]
    
    incoming_text = user_message["message"]["text"]
    reply_text = generate_reply(incoming_text)
    
    send_telegram(chat_id, reply_text)
    return {"ok": True}

@app.post("/test-morning")
async def test_morning():
    morning_message()
    return {"ok": True}

    
    
@app.get("/")
async def health():
    """Railway health check."""
    return {"status": "ok"}


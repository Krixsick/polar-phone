import os
import asyncio
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, Request
from anthropic import Anthropic
from dotenv import load_dotenv
from configs import CLAUDE_API, COACH_MODEL, MAX_TOKENS
from prompts import COACH_PROMPT, EXTRACTOR_PROMPT, USER_PROFILE, MORNING_PROMPT

load_dotenv()

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
MY_TELEGRAM_ID = os.environ.get("MY_TELEGRAM_ID")  # for proactive messages

claude = Anthropic()
app = FastAPI()

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
    
@app.get("/")
async def health():
    """Railway health check."""
    return {"status": "ok"}


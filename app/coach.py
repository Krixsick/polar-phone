import os
from collections import defaultdict

from fastapi import FastAPI, Request
import telnyx   
from anthropic import Anthropic
from dotenv import load_dotenv

# ─────────────────────────────────────────────────────────────
# SETUP
# ─────────────────────────────────────────────────────────────

load_dotenv()

telnyx.api_key = os.environ["TELNYX_API_KEY"]

claude = Anthropic()
app = FastAPI()
counters: dict[str, int] = defaultdict(int)


# ─────────────────────────────────────────────────────────────
# THE WEBHOOK
# ─────────────────────────────────────────────────────────────

@app.post("/sms")
async def sms_webhook(request: Request):
    payload = await request.json()
    event_type = payload.get("data", {}).get("event_type")
    if event_type != "message.received":
        return {"ok": True}
    data = payload["data"]["payload"]
    from_number = data["from"]["phone_number"]
    incoming = data.get("text", "").strip()

    if not from_number or not incoming:
        return {"ok": True}

    counters[from_number] += 1
    count = counters[from_number]

    reply = generate_reply(incoming, count)
    telnyx.Message.create(
        from_=os.environ["TELNYX_NUMBER"],
        to=from_number,
        text=reply,
    )

    return {"ok": True}


def generate_reply(user_message: str, count: int) -> str:
    response = claude.messages.create(
        model="claude-haiku-4-5",
        max_tokens=200,
        system=(
            "You are a friendly accountability bot. Reply in 1-2 short "
            "sentences, lowercase, casual. Mention the count naturally in "
            "your reply (e.g. 'that's 5 messages now' or 'on text 5 today')."
        ),
        messages=[
            {
                "role": "user",
                "content": f"(this is message #{count} from me) {user_message}",
            }
        ],
    )
    return response.content[0].text

@app.post("/ping")
async def ping_me(request: Request):
    """Make the bot send you a message. Call this manually."""
    body = await request.json()
    message_text = body.get("text", "yo, what's up")
    to_number = body.get("to", os.environ.get("PHONE_NUMBER"))

    if not to_number:
        return {"error": "no phone number"}

    telnyx.Message.create(
        from_=os.environ["TELNYX_NUMBER"],
        to=to_number,
        text=message_text,
    )

    return {"ok": True, "sent_to": to_number}


@app.get("/counts")
async def show_counts():
    return dict(counters)
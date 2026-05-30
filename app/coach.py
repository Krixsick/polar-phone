import os
import asyncio
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, Request
from anthropic import Anthropic
from dotenv import load_dotenv

# ─────────────────────────────────────────────────────────────
# SETUP
# ─────────────────────────────────────────────────────────────

load_dotenv()

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
MY_TELEGRAM_ID = os.environ.get("MY_TELEGRAM_ID")  # for proactive messages

claude = Anthropic()
app = FastAPI()

# In-memory state per user. Resets every restart/redeploy — that's
# the pain point that motivates adding Neon next session.
#
# Each user has:
#   - tasks: list of strings, things they should do today
#   - history: list of {role, content} for Claude conversation context
state: dict[str, dict] = {}


def get_user_state(chat_id: str) -> dict:
    """Get or create state for a user. defaultdict-ish but more explicit."""
    if chat_id not in state:
        state[chat_id] = {
            "tasks": [],
            "history": [],
        }
    return state[chat_id]


# ─────────────────────────────────────────────────────────────
# PROMPTS
# ─────────────────────────────────────────────────────────────

# The friend-vibe coach. Note this prompt does TWO things:
# 1. Defines personality (chill friend, not assistant)
# 2. Instructs Claude on how to handle specific scenarios
COACH_PROMPT = """
You are Linus's chill friend who helps him stay on top of his life.
You text like a real friend — lowercase, casual, short. No "Assistant" energy.

How you behave:

WHEN HE ASKS "what should I do" OR similar:
- Look at the task list in context
- Pick ONE specific thing and tell him to do it
- Be concrete: "do 30 min of sql practice" not "study"
- If the list is empty, suggest something based on his goals

WHEN HE SAYS HE FINISHED SOMETHING:
- React naturally ("nice", "lets go", "okay grinding")
- Suggest the next thing from his list
- Don't be over the top

WHEN HE SAYS HE'S TIRED or doesn't want to do something:
- Ask why briefly first
- If reason is weak (tired, lazy, not feeling it): push back. remind him of his goals
- If reason is legit (sick, slept badly, already worked out): scale it DOWN
  - "tired at the gym" → suggest light workout, mobility, or just cardio
  - "tired studying" → "okay just do 15 min instead of an hour"
  - "had a long day" → maybe just review notes instead of full grind
- Never just say "ok no worries" and let him off — always counter-offer something smaller

WHEN HE CHATS ABOUT RANDOM STUFF (nba, valorant, life):
- Just be a friend. Talk back like one.
- Don't redirect to "but did you do your tasks tho" unless it's been a while

His goals: gym 4x/week, coding, reading, reviewing notes, catching up with friends.
Reward stuff (not procrastination): valorant, nba.

Keep replies SHORT. 1-2 sentences usually. He's reading on his phone.
""".strip()


# Separate prompt for the morning task-list generation.
# Different job, different prompt — the two-call pattern.
MORNING_PROMPT = """
You are texting Linus first thing in the morning. He's a 3rd year CS student
at Western on co-op, starts a government dev job May 2026.

Generate a short morning text (1-2 sentences) + a list of 4-6 things he should
do today across his goals (gym, coding, reading/reviewing notes, friends/social).
Mix categories. Be specific (e.g. "30 min SQL practice" not "study").

Output ONLY valid JSON in this exact shape:
{"message": "morning text", "tasks": ["task 1", "task 2", ...]}

No prose outside the JSON. No markdown fences.
""".strip()


# Prompt for the "did the user just finish something?" extractor.
# Returns the task index or "none" — small, focused job.
COMPLETION_PROMPT_TEMPLATE = """
Linus's current task list:
{numbered_tasks}

He just said: "{user_message}"

Did he finish or complete one of these tasks?
Respond with ONLY the number (0-indexed) of the completed task, or "none".
Be conservative — only mark complete if he clearly says he DID it.
"i'll do it" or "going to do it" = "none". Only past tense / just now counts.
""".strip()


# ─────────────────────────────────────────────────────────────
# TELEGRAM HELPERS
# ─────────────────────────────────────────────────────────────

def send_telegram(chat_id: int | str, text: str) -> dict:
    """POST to Telegram's /sendMessage endpoint."""
    response = httpx.post(
        f"{TELEGRAM_API}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()


# ─────────────────────────────────────────────────────────────
# CLAUDE CALLS
# ─────────────────────────────────────────────────────────────

def generate_reply(user_state: dict, user_message: str) -> str:
    """
    Main coach reply. Injects the task list as context and uses
    conversation history for memory within the session.
    """
    tasks = user_state["tasks"]
    history = user_state["history"]

    # Build a fresh context block for THIS turn. The task list might
    # have changed since the last message, so we always recompute.
    if tasks:
        task_context = "his current tasks:\n" + "\n".join(f"- {t}" for t in tasks)
    else:
        task_context = "no tasks on his list right now. ask what he wants to add or suggest something."

    # The "fake first turn" technique: prepend a context message and
    # a one-word "got it" so the model sees the state without it being
    # part of the system prompt (system prompt should stay static for
    # prompt caching later).
    messages = [
        {"role": "user", "content": f"[context — don't respond to this directly]\n{task_context}"},
        {"role": "assistant", "content": "got it."},
        # Then the last 10 turns of real conversation history
        *history[-10:],
    ]

    response = claude.messages.create(
        model="claude-haiku-4-5",
        max_tokens=300,
        system=COACH_PROMPT,
        messages=messages,
    )
    return response.content[0].text.strip()


def extract_completed_task(user_state: dict, user_message: str) -> int | None:
    """
    Second Claude call: parse whether the user just finished a task.
    Returns the task index to remove, or None if no completion.

    Why a separate call? Mixing 'generate a reply' with 'parse
    structured info' in one prompt is unreliable. Two specialized
    calls beat one mixed one almost every time.
    """
    tasks = user_state["tasks"]
    if not tasks:
        return None

    numbered = "\n".join(f"{i}. {t}" for i, t in enumerate(tasks))
    prompt = COMPLETION_PROMPT_TEMPLATE.format(
        numbered_tasks=numbered,
        user_message=user_message,
    )

    response = claude.messages.create(
        model="claude-haiku-4-5",
        max_tokens=10,
        messages=[{"role": "user", "content": prompt}],
    )
    answer = response.content[0].text.strip().lower()

    # Parse defensively — model might say "1", "task 1", "1.", "none", etc.
    digits = "".join(c for c in answer if c.isdigit())
    if not digits:
        return None

    idx = int(digits)
    if 0 <= idx < len(tasks):
        return idx
    return None


def generate_morning_briefing() -> tuple[str, list[str]]:
    """
    Generate the morning check-in: a casual message plus a task list.
    Returns (message_text, tasks_list).
    """
    response = claude.messages.create(
        model="claude-haiku-4-5",
        max_tokens=400,
        system=MORNING_PROMPT,
        messages=[{
            "role": "user",
            "content": "Generate today's morning text and task list now.",
        }],
    )
    raw = response.content[0].text.strip()

    # Strip any markdown code fences the model might add despite instructions
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        parsed = json.loads(raw)
        return parsed["message"], parsed["tasks"]
    except (json.JSONDecodeError, KeyError) as e:
        # Fallback if the model returns malformed JSON
        print(f"morning briefing parse failed: {e}, raw: {raw}", flush=True)
        return (
            "yo good morning. let's get it today.",
            ["gym - 45 min", "1 hour coding", "review notes for 20 min", "text someone you haven't talked to"],
        )


# ─────────────────────────────────────────────────────────────
# WEBHOOK
# ─────────────────────────────────────────────────────────────

@app.post("/telegram")
async def telegram_webhook(request: Request):
    payload = await request.json()

    message = payload.get("message")
    if not message or "text" not in message:
        return {"ok": True}

    chat_id = str(message["chat"]["id"])
    incoming = message["text"].strip()
    if not incoming:
        return {"ok": True}

    user_state = get_user_state(chat_id)

    # Append the user's message to history BEFORE generating reply
    # so the model sees it
    user_state["history"].append({"role": "user", "content": incoming})

    # First Claude call: the coach reply
    reply = generate_reply(user_state, incoming)

    # Save the assistant's reply to history too
    user_state["history"].append({"role": "assistant", "content": reply})

    # Second Claude call: did the user just finish a task?
    # We do this AFTER generating the reply so the reply is sent
    # quickly. The task removal happens in the background.
    completed_idx = extract_completed_task(user_state, incoming)
    if completed_idx is not None:
        finished = user_state["tasks"].pop(completed_idx)
        print(f"[{chat_id}] completed: {finished}", flush=True)

    send_telegram(chat_id, reply)
    return {"ok": True}


# ─────────────────────────────────────────────────────────────
# MORNING SCHEDULER
# ─────────────────────────────────────────────────────────────

@app.on_event("startup")
async def start_scheduler():
    """Kick off the background scheduler when uvicorn boots."""
    asyncio.create_task(morning_scheduler())


async def morning_scheduler():
    """
    Wake up every minute. At 8am Toronto time, send a morning briefing
    that sets the day's tasks.
    """
    sent_today = set()  # dates we've already sent for; resets on restart

    while True:
        await asyncio.sleep(60)

        try:
            now = datetime.now(ZoneInfo("America/Toronto"))
            date_key = now.strftime("%Y-%m-%d")

            # 8am exactly, once per day
            if now.hour == 8 and now.minute == 0 and date_key not in sent_today:
                sent_today.add(date_key)
                await send_morning_briefing()
        except Exception as e:
            # Never crash the loop — print and continue
            print(f"scheduler error: {e}", flush=True)


async def send_morning_briefing():
    """Generate the morning task list and text Linus."""
    if not MY_TELEGRAM_ID:
        print("no MY_TELEGRAM_ID set, skipping morning briefing", flush=True)
        return

    message, tasks = generate_morning_briefing()

    # Replace Linus's task list with the fresh morning list.
    user_state = get_user_state(MY_TELEGRAM_ID)
    user_state["tasks"] = tasks

    # Send the message AND the task list as two separate texts so
    # the list is easy to see and reference.
    send_telegram(MY_TELEGRAM_ID, message)
    task_text = "today's lineup:\n" + "\n".join(f"• {t}" for t in tasks)
    send_telegram(MY_TELEGRAM_ID, task_text)
    print(f"morning briefing sent: {len(tasks)} tasks", flush=True)


# ─────────────────────────────────────────────────────────────
# DEBUG ENDPOINTS
# ─────────────────────────────────────────────────────────────

@app.get("/")
async def health_check():
    return {"status": "ok"}


@app.get("/state/{chat_id}")
async def show_state(chat_id: str):
    """View someone's current state."""
    return state.get(chat_id, {"tasks": [], "history": []})


@app.post("/trigger-morning")
async def trigger_morning_now():
    """Manually fire the morning briefing without waiting for 8am."""
    await send_morning_briefing()
    return {"ok": True}


@app.post("/reset/{chat_id}")
async def reset_user(chat_id: str):
    """Wipe a user's tasks and history."""
    state.pop(chat_id, None)
    return {"ok": True}
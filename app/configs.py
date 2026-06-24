from dotenv import load_dotenv
import os
load_dotenv()
MY_TELEGRAM_ID = os.environ["MY_TELEGRAM_ID"]

MY_PHONE_NUMBER = os.environ["PHONE_NUMBER"]

CLAUDE_API = os.environ["ANTHROPIC_API_KEY"]

NEON_API = os.environ.get("NEON_API") 

COACH_MODEL = "claude-haiku-4-5"
EXTRACTOR_MODEL = "claude-haiku-4-5"
CALENDAR_MODEL = "claude-haiku-4-5"
MAX_TOKENS = 500
MAX_HISTORY_TURNS = 20
ACTIVITY_LOOKBACK_HOURS = 48

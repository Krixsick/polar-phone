from dotenv import load_dotenv
import os
load_dotenv()

TELNYX_API_KEY = os.environ["TELNYX_API_KEY"]
TELNYX_NUMBER = os.environ["TELNYX_NUMBER"]
MY_PHONE_NUMBER = os.environ["PHONE_NUMBER"]

CLAUDE_API = os.environ["ANTHROPIC_API_KEY"]

NEON_API = os.environ["NEON_API"]

COACH_MODEL = "claude-haiku-4-5"
EXTRACTOR_MODEL = "claude-haiku-4-5"
MAX_TOKENS = 500
MAX_HISTORY_TURNS = 20
ACTIVITY_LOOKBACK_HOURS = 48


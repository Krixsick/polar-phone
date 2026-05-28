from dotenv import load_dotenv
import os
load_dotenv()

TWILIO_ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_PHONE_NUMBER = os.environ["TWILIO_NUMBER"]
MY_PHONE_NUMBER = os.environ["PHONE_NUMBER"]

CLAUDE_API = os.environ["ANTHROPIC_API_KEY"]

NEON_API = os.environ["NEON_API"]

COACH_MODEL = "claude-haiku-4-5"
EXTRACTOR_MODEL = "claude-haiku-4-5"
MAX_TOKENS = 500
MAX_HISTORY_TURNS = 20
ACTIVITY_LOOKBACK_HOURS = 48

def twilio_credentials():
    return (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
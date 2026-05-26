import os
from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()

account_sid = os.environ["TWILIO_ACCOUNT_SID"]
auth_token = os.environ["TWILIO_AUTH_TOKEN"]
twilio_phone_number = os.environ["TWILIO_NUMBER"]
phone_number = os.environ["PHONE_NUMBER"]
client = Client(account_sid, auth_token)

message = client.messages.create(
    body="Join Earth's mightiest heroes. Like Kevin Bacon.",
    from_=twilio_phone_number,
    to=phone_number,
)

print(message.sid)  # print the SID, not the body
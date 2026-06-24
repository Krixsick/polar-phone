import os
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from urllib.parse import urlencode, urlsplit, urlunsplit

from app.db import SQLiteTaskStore


GOOGLE_AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_EVENTS_URL = (
    "https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
)
GOOGLE_CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events"


class GoogleCalendarConfigError(RuntimeError):
    pass


class GoogleCalendarAuthError(RuntimeError):
    pass


def _required_env(
    name: str,
    aliases: tuple[str, ...] = (),
    default: str | None = None,
) -> str:
    value = os.environ.get(name)
    if value:
        return value

    for alias in aliases:
        value = os.environ.get(alias)
        if value:
            return value

    if default is not None:
        return default

    raise GoogleCalendarConfigError(f"{name} is not set")


def get_google_oauth_config() -> dict:
    return {
        "client_id": _required_env("GOOGLE_CLIENT_ID", aliases=("CLIENT_ID",)),
        "client_secret": _required_env(
            "GOOGLE_CLIENT_SECRET",
            aliases=("CLIENT_SECRET",),
        ),
        "redirect_uri": _required_env(
            "GOOGLE_REDIRECT_URI",
            default="http://localhost:8000/google/oauth2callback",
        ),
    }


def make_google_oauth_state() -> str:
    return token_urlsafe(32)


def build_google_authorization_url(state: str) -> str:
    config = get_google_oauth_config()
    query = urlencode(
        {
            "client_id": config["client_id"],
            "redirect_uri": config["redirect_uri"],
            "response_type": "code",
            "scope": GOOGLE_CALENDAR_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
    )

    return f"{GOOGLE_AUTHORIZATION_URL}?{query}"


def build_google_auth_route_url() -> str:
    redirect_uri = get_google_oauth_config()["redirect_uri"]
    parts = urlsplit(redirect_uri)

    return urlunsplit((parts.scheme, parts.netloc, "/google/auth", "", ""))


def token_expires_at(expires_in: int) -> str:
    return (datetime.now(UTC) + timedelta(seconds=expires_in)).isoformat()


def token_is_expired(expires_at: str, buffer_seconds: int = 60) -> bool:
    return datetime.fromisoformat(expires_at) <= (
        datetime.now(UTC) + timedelta(seconds=buffer_seconds)
    )


async def exchange_google_code_for_tokens(code: str) -> dict:
    import httpx

    config = get_google_oauth_config()

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
                "redirect_uri": config["redirect_uri"],
                "grant_type": "authorization_code",
            },
        )

    response.raise_for_status()
    return response.json()


async def refresh_google_access_token(refresh_token: str) -> dict:
    import httpx

    config = get_google_oauth_config()

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )

    response.raise_for_status()
    return response.json()


async def get_google_access_token(store: SQLiteTaskStore) -> str:
    tokens = store.get_google_tokens()
    if tokens is None:
        raise GoogleCalendarAuthError("Google Calendar is not connected")

    if not token_is_expired(tokens["expires_at"]):
        return tokens["access_token"]

    refreshed_tokens = await refresh_google_access_token(tokens["refresh_token"])
    store.save_google_tokens(
        refreshed_tokens,
        expires_at=token_expires_at(refreshed_tokens["expires_in"]),
    )
    updated_tokens = store.get_google_tokens()

    if updated_tokens is None:
        raise GoogleCalendarAuthError("Google Calendar token refresh failed")

    return updated_tokens["access_token"]


async def create_google_calendar_event(
    store: SQLiteTaskStore,
    summary: str,
    start_iso: str,
    end_iso: str,
    timezone: str = "America/Toronto",
    description: str | None = None,
    calendar_id: str = "primary",
) -> dict:
    import httpx

    access_token = await get_google_access_token(store)
    event_body = {
        "summary": summary,
        "start": {
            "dateTime": start_iso,
            "timeZone": timezone,
        },
        "end": {
            "dateTime": end_iso,
            "timeZone": timezone,
        },
    }

    if description:
        event_body["description"] = description

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            GOOGLE_CALENDAR_EVENTS_URL.format(calendar_id=calendar_id),
            headers={"Authorization": f"Bearer {access_token}"},
            json=event_body,
        )

    response.raise_for_status()
    return response.json()

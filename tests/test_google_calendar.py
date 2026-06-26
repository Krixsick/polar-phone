import os
import sys
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse
import unittest

from app.google_calendar import (
    GOOGLE_CALENDAR_LIST_URL,
    GOOGLE_CALENDAR_SCOPE,
    GoogleCalendarConfigError,
    build_google_auth_route_url,
    build_google_authorization_url,
    get_google_debug_config,
    get_google_oauth_config,
    list_google_calendar_events_for_visible_calendars,
    token_expires_at,
    token_is_expired,
)


class FakeGoogleResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        return None


class FakeGoogleAsyncClient:
    requests: list[dict] = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def get(self, url: str, headers: dict | None = None, params: dict | None = None):
        self.requests.append({"url": url, "headers": headers, "params": params})

        if url == GOOGLE_CALENDAR_LIST_URL:
            return FakeGoogleResponse(
                {
                    "items": [
                        {
                            "id": "primary",
                            "summary": "Personal",
                            "primary": True,
                            "selected": True,
                        },
                        {
                            "id": "team@example.com",
                            "summary": "Team",
                            "selected": True,
                        },
                        {
                            "id": "hidden@example.com",
                            "summary": "Hidden",
                            "selected": False,
                        },
                    ]
                }
            )

        if url.endswith("/calendars/primary/events"):
            return FakeGoogleResponse(
                {
                    "items": [
                        {
                            "summary": "Dinner",
                            "start": {"dateTime": "2026-06-26T21:00:00-04:00"},
                            "end": {"dateTime": "2026-06-26T22:00:00-04:00"},
                        }
                    ]
                }
            )

        if url.endswith("/calendars/team%40example.com/events"):
            return FakeGoogleResponse(
                {
                    "items": [
                        {
                            "summary": "Soccer",
                            "start": {"dateTime": "2026-06-26T20:00:00-04:00"},
                            "end": {"dateTime": "2026-06-26T22:00:00-04:00"},
                        }
                    ]
                }
            )

        return FakeGoogleResponse({"items": []})


class GoogleCalendarTests(unittest.TestCase):
    def test_build_google_authorization_url(self):
        with patch.dict(
            os.environ,
            {
                "GOOGLE_CLIENT_ID": "client-id",
                "GOOGLE_CLIENT_SECRET": "client-secret",
                "GOOGLE_REDIRECT_URI": "http://localhost:8000/google/oauth2callback",
            },
        ):
            parsed_url = urlparse(build_google_authorization_url("state-value"))
            params = parse_qs(parsed_url.query)

        self.assertEqual(parsed_url.scheme, "https")
        self.assertEqual(parsed_url.netloc, "accounts.google.com")
        self.assertEqual(params["client_id"], ["client-id"])
        self.assertEqual(
            params["redirect_uri"],
            ["http://localhost:8000/google/oauth2callback"],
        )
        self.assertEqual(params["response_type"], ["code"])
        self.assertEqual(params["scope"], [GOOGLE_CALENDAR_SCOPE])
        self.assertIn("https://www.googleapis.com/auth/calendar.events", params["scope"][0])
        self.assertIn(
            "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
            params["scope"][0],
        )
        self.assertEqual(params["access_type"], ["offline"])
        self.assertEqual(params["prompt"], ["consent"])
        self.assertEqual(params["state"], ["state-value"])

    def test_build_google_auth_route_url(self):
        with patch.dict(
            os.environ,
            {
                "GOOGLE_CLIENT_ID": "client-id",
                "GOOGLE_CLIENT_SECRET": "client-secret",
                "GOOGLE_REDIRECT_URI": "http://localhost:8000/google/oauth2callback",
            },
        ):
            self.assertEqual(
                build_google_auth_route_url(),
                "http://localhost:8000/google/auth",
            )

    def test_google_config_accepts_local_aliases(self):
        with patch.dict(
            os.environ,
            {
                "CLIENT_ID": "client-id",
                "CLIENT_SECRET": "client-secret",
            },
            clear=True,
        ):
            self.assertEqual(
                get_google_oauth_config(),
                {
                    "client_id": "client-id",
                    "client_secret": "client-secret",
                    "redirect_uri": "http://localhost:8000/google/oauth2callback",
                },
            )

    def test_google_config_uses_public_base_url(self):
        with patch.dict(
            os.environ,
            {
                "GOOGLE_CLIENT_ID": "client-id",
                "GOOGLE_CLIENT_SECRET": "client-secret",
                "PUBLIC_BASE_URL": "https://polar-phone.up.railway.app/",
            },
            clear=True,
        ):
            self.assertEqual(
                get_google_oauth_config()["redirect_uri"],
                "https://polar-phone.up.railway.app/google/oauth2callback",
            )
            self.assertEqual(
                build_google_auth_route_url(),
                "https://polar-phone.up.railway.app/google/auth",
            )
            self.assertEqual(
                get_google_debug_config()["redirect_uri"],
                "https://polar-phone.up.railway.app/google/oauth2callback",
            )

    def test_google_config_ignores_localhost_redirect_on_railway_with_public_base_url(self):
        with patch.dict(
            os.environ,
            {
                "GOOGLE_CLIENT_ID": "client-id",
                "GOOGLE_CLIENT_SECRET": "client-secret",
                "GOOGLE_REDIRECT_URI": "http://localhost:8000/google/oauth2callback",
                "PUBLIC_BASE_URL": "https://polar-phone-production.up.railway.app",
                "RAILWAY_ENVIRONMENT": "production",
            },
            clear=True,
        ):
            self.assertEqual(
                get_google_oauth_config()["redirect_uri"],
                "https://polar-phone-production.up.railway.app/google/oauth2callback",
            )

    def test_google_config_rejects_localhost_redirect_on_railway_without_public_base_url(self):
        with patch.dict(
            os.environ,
            {
                "GOOGLE_CLIENT_ID": "client-id",
                "GOOGLE_CLIENT_SECRET": "client-secret",
                "GOOGLE_REDIRECT_URI": "http://localhost:8000/google/oauth2callback",
                "RAILWAY_ENVIRONMENT": "production",
            },
            clear=True,
        ):
            with self.assertRaises(GoogleCalendarConfigError):
                get_google_oauth_config()

    def test_google_config_requires_public_url_on_railway(self):
        with patch.dict(
            os.environ,
            {
                "GOOGLE_CLIENT_ID": "client-id",
                "GOOGLE_CLIENT_SECRET": "client-secret",
                "RAILWAY_ENVIRONMENT": "production",
            },
            clear=True,
        ):
            with self.assertRaises(GoogleCalendarConfigError):
                get_google_oauth_config()

    def test_token_expiration_helpers(self):
        expires_at = token_expires_at(3600)
        expired_at = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()

        self.assertFalse(token_is_expired(expires_at))
        self.assertTrue(token_is_expired(expired_at))


class GoogleCalendarAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_visible_calendar_events_reads_selected_calendars(self):
        FakeGoogleAsyncClient.requests = []
        fake_httpx = SimpleNamespace(
            AsyncClient=FakeGoogleAsyncClient,
            HTTPStatusError=Exception,
        )

        with (
            patch("app.google_calendar.get_google_access_token", AsyncMock(return_value="token")),
            patch.dict(sys.modules, {"httpx": fake_httpx}),
        ):
            events = await list_google_calendar_events_for_visible_calendars(
                store=object(),
                start_iso="2026-06-26T00:00:00-04:00",
                end_iso="2026-06-27T00:00:00-04:00",
                timezone="America/Toronto",
            )

        self.assertEqual([event["summary"] for event in events], ["Soccer", "Dinner"])
        self.assertEqual(events[0]["_calendar_summary"], "Team")

        requested_urls = [request["url"] for request in FakeGoogleAsyncClient.requests]
        self.assertIn(GOOGLE_CALENDAR_LIST_URL, requested_urls)
        self.assertTrue(
            any(url.endswith("/calendars/team%40example.com/events") for url in requested_urls)
        )
        self.assertFalse(
            any("hidden%40example.com" in url for url in requested_urls)
        )


if __name__ == "__main__":
    unittest.main()

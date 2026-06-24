import os
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
import unittest

from app.google_calendar import (
    GOOGLE_CALENDAR_SCOPE,
    build_google_auth_route_url,
    build_google_authorization_url,
    get_google_oauth_config,
    token_expires_at,
    token_is_expired,
)


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

    def test_token_expiration_helpers(self):
        expires_at = token_expires_at(3600)
        expired_at = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()

        self.assertFalse(token_is_expired(expires_at))
        self.assertTrue(token_is_expired(expired_at))


if __name__ == "__main__":
    unittest.main()

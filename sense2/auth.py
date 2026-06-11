"""OAuth 2.0 Authorization Code + PKCE flow for the Fitbit Web API.

Works with a "Personal" application registered at https://dev.fitbit.com/apps.
Personal apps get intraday access to the owner's own data without any
special approval. Tokens are persisted to disk and refreshed automatically.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import secrets
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

import requests

AUTHORIZE_URL = "https://www.fitbit.com/oauth2/authorize"
TOKEN_URL = "https://api.fitbit.com/oauth2/token"

# Every scope the Sense 2 can populate.
DEFAULT_SCOPES = [
    "activity",
    "cardio_fitness",
    "electrocardiogram",
    "heartrate",
    "oxygen_saturation",
    "profile",
    "respiratory_rate",
    "settings",
    "sleep",
    "temperature",
    "weight",
]

DEFAULT_TOKEN_PATH = Path.home() / ".sense2" / "tokens.json"
CALLBACK_PORT = 8765
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}/auth/callback"


class AuthError(Exception):
    pass


def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return verifier, challenge


class TokenStore:
    """Loads, saves and refreshes the OAuth token set."""

    def __init__(self, client_id: str, client_secret: str = "", path: Path | None = None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.path = Path(path or DEFAULT_TOKEN_PATH)
        self._tokens: dict = {}
        if self.path.exists():
            self._tokens = json.loads(self.path.read_text())

    @property
    def has_tokens(self) -> bool:
        return bool(self._tokens.get("refresh_token"))

    def save(self, tokens: dict) -> None:
        tokens["obtained_at"] = int(time.time())
        self._tokens = tokens
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(tokens, indent=2))
        self.path.chmod(0o600)

    def _token_request(self, data: dict) -> dict:
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if self.client_secret:
            basic = base64.b64encode(
                f"{self.client_id}:{self.client_secret}".encode()
            ).decode()
            headers["Authorization"] = f"Basic {basic}"
        else:
            data["client_id"] = self.client_id
        resp = requests.post(TOKEN_URL, data=data, headers=headers, timeout=30)
        if resp.status_code != 200:
            raise AuthError(f"Token request failed ({resp.status_code}): {resp.text}")
        return resp.json()

    def access_token(self) -> str:
        """Return a valid access token, refreshing if it is near expiry."""
        if not self.has_tokens:
            raise AuthError("Not authorized yet — run `python -m sense2 auth` first.")
        expires_at = self._tokens.get("obtained_at", 0) + self._tokens.get("expires_in", 0)
        if time.time() > expires_at - 120:
            self.save(
                self._token_request(
                    {
                        "grant_type": "refresh_token",
                        "refresh_token": self._tokens["refresh_token"],
                    }
                )
            )
        return self._tokens["access_token"]


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    code: str | None = None
    expected_state: str = ""

    def do_GET(self):  # noqa: N802
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if query.get("state", [""])[0] != self.expected_state:
            self.send_error(400, "State mismatch")
            return
        type(self).code = query.get("code", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<h2>Authorized — you can close this tab.</h2>")

    def log_message(self, *args):  # silence request logging
        pass


def authorize(client_id: str, client_secret: str = "", scopes: list[str] | None = None,
              token_path: Path | None = None, open_browser: bool = True) -> TokenStore:
    """Run the interactive PKCE flow and persist the resulting tokens."""
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(scopes or DEFAULT_SCOPES),
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    url = f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    _CallbackHandler.code = None
    _CallbackHandler.expected_state = state
    server = http.server.HTTPServer(("localhost", CALLBACK_PORT), _CallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    print(f"Open this URL to authorize:\n\n  {url}\n")
    if open_browser:
        webbrowser.open(url)

    try:
        deadline = time.time() + 300
        while _CallbackHandler.code is None and time.time() < deadline:
            time.sleep(0.2)
    finally:
        server.shutdown()

    if _CallbackHandler.code is None:
        raise AuthError("Timed out waiting for the authorization callback (5 min).")

    store = TokenStore(client_id, client_secret, token_path)
    store.save(
        store._token_request(
            {
                "grant_type": "authorization_code",
                "code": _CallbackHandler.code,
                "redirect_uri": REDIRECT_URI,
                "code_verifier": verifier,
            }
        )
    )
    print("Authorized — tokens saved to", store.path)
    return store


def store_from_env(token_path: Path | None = None) -> TokenStore:
    client_id = os.environ.get("FITBIT_CLIENT_ID", "")
    if not client_id:
        raise AuthError(
            "Set FITBIT_CLIENT_ID (and optionally FITBIT_CLIENT_SECRET) from your "
            "Personal app at https://dev.fitbit.com/apps, or use --demo mode."
        )
    return TokenStore(client_id, os.environ.get("FITBIT_CLIENT_SECRET", ""), token_path)

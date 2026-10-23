"""One-time Google login (OAuth installed-app loopback flow). Saves the refresh token in .env.

Usage: python scripts/google_login.py [client_secret.json]
With the client JSON downloaded from the Console it reads the id and secret from it; otherwise
from BYTE_GOOGLE_CLIENT_ID / BYTE_GOOGLE_CLIENT_SECRET (environment or `.env`). Writes the id,
secret and refresh token into `.env`, so no secret is printed to the terminal.

Google Cloud Console setup, once:
- Enable the Google Calendar API.
- Create an OAuth client of type "Desktop app" (loopback redirects need no registration).
- Set the OAuth consent screen to "In production": in "Testing", refresh tokens expire
  after 7 days.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import ClassVar

SCOPE = "https://www.googleapis.com/auth/calendar.events"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105


class _Handler(BaseHTTPRequestHandler):
    params: ClassVar[dict[str, list[str]]] = {}

    def do_GET(self) -> None:
        _Handler.params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Byte: login ok, pode fechar esta aba.")

    # The request log contains the auth code, so it stays silent.
    def log_message(self, format: str, *args: object) -> None:
        pass


def _setting(name: str) -> str:
    if value := os.environ.get(name):
        return value
    env = Path(".env")
    lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
    for line in lines:
        key, _, value = line.partition("=")
        if key.strip() == name and value.strip():
            return value.strip().strip("\"'")
    sys.exit(f"missing {name} (environment or .env)")


def _from_json(path: str) -> tuple[str, str]:
    client = json.loads(Path(path).read_text(encoding="utf-8"))["installed"]
    return client["client_id"], client["client_secret"]


def _save(values: dict[str, str]) -> None:
    """Set each key in `.env`, replacing an existing line or appending one."""
    env = Path(".env")
    lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
    kept = [line for line in lines if line.partition("=")[0].strip() not in values]
    env.write_text("\n".join([*kept, *(f"{k}={v}" for k, v in values.items())]) + "\n", "utf-8")


def main() -> None:
    if len(sys.argv) > 1:
        client_id, client_secret = _from_json(sys.argv[1])
    else:
        client_id = _setting("BYTE_GOOGLE_CLIENT_ID")
        client_secret = _setting("BYTE_GOOGLE_CLIENT_SECRET")
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    redirect = f"http://127.0.0.1:{server.server_port}"
    state = secrets.token_urlsafe(16)
    url = (
        AUTH_URL
        + "?"
        + urllib.parse.urlencode(
            {
                "client_id": client_id,
                "response_type": "code",
                "redirect_uri": redirect,
                "scope": SCOPE,
                "state": state,
                "access_type": "offline",
                "prompt": "consent",
            }
        )
    )
    webbrowser.open(url)
    print("Abra se não abriu sozinho:", url)
    server.handle_request()
    if _Handler.params.get("state") != [state] or "code" not in _Handler.params:
        sys.exit("login failed: bad state or no code")
    data = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": _Handler.params["code"][0],
            "redirect_uri": redirect,
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode()
    req = urllib.request.Request(TOKEN_URL, data=data)
    with urllib.request.urlopen(req) as res:  # noqa: S310
        token = json.load(res)["refresh_token"]
    _save(
        {
            "BYTE_GOOGLE_CLIENT_ID": client_id,
            "BYTE_GOOGLE_CLIENT_SECRET": client_secret,
            "BYTE_GOOGLE_REFRESH_TOKEN": token,
        }
    )
    print("\nok: BYTE_GOOGLE_CLIENT_ID, _SECRET e _REFRESH_TOKEN gravados no .env")


if __name__ == "__main__":
    main()

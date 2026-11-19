"""One-time Spotify login (OAuth PKCE). Prints the refresh token for .env.

Usage: python scripts/spotify_login.py <client_id>
Redirect URI http://127.0.0.1:8888/callback must be registered in the Spotify app.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import sys
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar

REDIRECT = "http://127.0.0.1:8888/callback"
SCOPES = (
    "user-read-playback-state user-modify-playback-state user-read-currently-playing "
    "playlist-read-private"
)


class _Handler(BaseHTTPRequestHandler):
    params: ClassVar[dict[str, list[str]]] = {}

    def do_GET(self) -> None:
        _Handler.params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Byte: login ok, pode fechar esta aba.")

    def log_message(self, *_: object) -> None:  # silence request log (contains the code)
        pass


def main(client_id: str) -> None:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    state = secrets.token_urlsafe(16)
    url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": REDIRECT,
            "scope": SCOPES,
            "state": state,
            "code_challenge_method": "S256",
            "code_challenge": challenge.decode(),
        }
    )
    webbrowser.open(url)
    print("Abra se não abriu sozinho:", url)
    HTTPServer(("127.0.0.1", 8888), _Handler).handle_request()
    if _Handler.params.get("state") != [state] or "code" not in _Handler.params:
        sys.exit("login failed: bad state or no code")
    data = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": _Handler.params["code"][0],
            "redirect_uri": REDIRECT,
            "client_id": client_id,
            "code_verifier": verifier,
        }
    ).encode()
    req = urllib.request.Request("https://accounts.spotify.com/api/token", data=data)
    with urllib.request.urlopen(req) as res:  # noqa: S310
        token = json.load(res)["refresh_token"]
    print(f"\nBYTE_SPOTIFY_REFRESH_TOKEN={token}")


if __name__ == "__main__":
    main(sys.argv[1])

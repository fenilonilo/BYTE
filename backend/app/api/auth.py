from __future__ import annotations

import hmac
from typing import TYPE_CHECKING

from fastapi import Depends, Header, HTTPException, WebSocket, status

from app.api.deps import get_device_auth, get_settings

if TYPE_CHECKING:
    from pydantic import SecretStr

    from app.config import Settings

BEARER = "Bearer "
BEARER_SUBPROTOCOL = "bearer"


def token_matches(header: str | None, token: SecretStr) -> bool:
    if header is None or not header.startswith(BEARER):
        return False
    return hmac.compare_digest(header[len(BEARER) :].encode(), token.get_secret_value().encode())


def _allowed(header: str | None, master: SecretStr) -> bool:
    """The master token (devices, scripts) or a live access token from a signed-in panel."""
    if token_matches(header, master):
        return True
    return (
        header is not None
        and header.startswith(BEARER)
        and (get_device_auth().access_valid(header[len(BEARER) :]))
    )


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing token",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_token(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if not _allowed(authorization, settings.api_token):
        raise _unauthorized()


async def require_master(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """Only the master token signs a device in: an access token must not mint more of itself."""
    if not token_matches(authorization, settings.api_token):
        raise _unauthorized()


def _subprotocol_token(websocket: WebSocket) -> str | None:
    """Browsers cannot set headers on a WebSocket, so they offer `["bearer", <token>]`."""
    match websocket.scope.get("subprotocols", []):
        case [str(name), str(token)] if name == BEARER_SUBPROTOCOL:
            return token
        case _:
            return None


async def accept_authorized(websocket: WebSocket, token: SecretStr) -> bool:
    """Accept the socket if it carries the token (header or subprotocol); close it otherwise."""
    offered = _subprotocol_token(websocket)
    header = websocket.headers.get("authorization") if offered is None else f"{BEARER}{offered}"
    if not _allowed(header, token):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return False
    # echo only the fixed name: the token itself must never travel back
    await websocket.accept(subprotocol=None if offered is None else BEARER_SUBPROTOCOL)
    return True

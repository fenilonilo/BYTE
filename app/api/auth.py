from __future__ import annotations

import hmac
from typing import TYPE_CHECKING

from fastapi import Depends, Header, HTTPException, status

from app.api.deps import get_settings

if TYPE_CHECKING:
    from pydantic import SecretStr

    from app.config import Settings

BEARER = "Bearer "


def token_matches(header: str | None, token: SecretStr) -> bool:
    if header is None or not header.startswith(BEARER):
        return False
    return hmac.compare_digest(header[len(BEARER) :].encode(), token.get_secret_value().encode())


async def require_token(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if not token_matches(authorization, settings.api_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing token",
            headers={"WWW-Authenticate": "Bearer"},
        )

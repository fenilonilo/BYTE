from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from app.domain.device_grant import DeviceGrant

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from app.ports.device_grants import DeviceGrantStorePort

ACCESS_TTL = timedelta(hours=1)
REFRESH_IDLE = timedelta(days=180)


@dataclass(frozen=True, slots=True)
class TokenPair:
    access: str
    refresh: str
    expires_in: int


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class DeviceAuth:
    """Sign a device in once; afterwards it trades its refresh token for short access tokens."""

    def __init__(self, grants: DeviceGrantStorePort, clock: Callable[[], datetime]) -> None:
        self._grants = grants
        self._clock = clock
        # ponytail: access tokens live in memory; a restart makes each device refresh once
        self._access: dict[str, datetime] = {}

    async def login(self) -> TokenPair:
        """Call only after the master token was verified."""
        refresh = secrets.token_urlsafe(32)
        now = self._clock()
        await self._grants.put(DeviceGrant(_digest(refresh), now, now))
        return self._issue(refresh)

    async def refresh(self, refresh_token: str) -> TokenPair | None:
        grant = await self._grants.get(_digest(refresh_token))
        now = self._clock()
        if grant is None or now - grant.last_used_at > REFRESH_IDLE:
            return None
        await self._grants.put(DeviceGrant(grant.token_hash, grant.created_at, now))
        return self._issue(refresh_token)

    async def logout(self, refresh_token: str) -> None:
        await self._grants.remove(_digest(refresh_token))

    def access_valid(self, token: str) -> bool:
        # a dict lookup by hash, not a string compare: no timing leak on the token itself
        expires = self._access.get(_digest(token))
        return expires is not None and self._clock() < expires

    def _issue(self, refresh: str) -> TokenPair:
        now = self._clock()
        self._access = {h: exp for h, exp in self._access.items() if exp > now}
        access = secrets.token_urlsafe(32)
        self._access[_digest(access)] = now + ACCESS_TTL
        return TokenPair(access, refresh, int(ACCESS_TTL.total_seconds()))

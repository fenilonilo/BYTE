from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from app.adapters.files.json_device_grants import JsonDeviceGrantStore
from app.application.device_auth import ACCESS_TTL, REFRESH_IDLE, DeviceAuth

if TYPE_CHECKING:
    from pathlib import Path

T0 = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


def make(tmp_path: Path) -> tuple[DeviceAuth, Clock]:
    clock = Clock()
    return DeviceAuth(JsonDeviceGrantStore(tmp_path / "devices.json"), clock), clock


@pytest.mark.unit
async def test_login_hands_out_a_live_access_token(tmp_path: Path) -> None:
    auth, _ = make(tmp_path)
    pair = await auth.login()
    assert auth.access_valid(pair.access)
    assert pair.expires_in == int(ACCESS_TTL.total_seconds())
    assert pair.access != pair.refresh
    assert not auth.access_valid(pair.refresh)
    assert not auth.access_valid("x" * 43)


@pytest.mark.unit
async def test_access_expires_and_refresh_issues_a_new_one(tmp_path: Path) -> None:
    auth, clock = make(tmp_path)
    pair = await auth.login()
    clock.now += ACCESS_TTL + timedelta(seconds=1)
    assert not auth.access_valid(pair.access)
    renewed = await auth.refresh(pair.refresh)
    assert renewed is not None
    assert renewed.refresh == pair.refresh  # no rotation: two tabs must not sign each other out
    assert auth.access_valid(renewed.access)


@pytest.mark.unit
async def test_refresh_survives_a_restart_but_access_does_not(tmp_path: Path) -> None:
    auth, _ = make(tmp_path)
    pair = await auth.login()
    reborn, _ = make(tmp_path)
    assert not reborn.access_valid(pair.access)
    assert await reborn.refresh(pair.refresh) is not None


@pytest.mark.unit
async def test_unknown_idle_or_revoked_refresh_is_refused(tmp_path: Path) -> None:
    auth, clock = make(tmp_path)
    assert await auth.refresh("nope") is None
    idle = await auth.login()
    used = await auth.login()
    clock.now += REFRESH_IDLE - timedelta(days=1)
    assert await auth.refresh(used.refresh) is not None  # use slides the window
    clock.now += timedelta(days=2)
    assert await auth.refresh(idle.refresh) is None
    assert await auth.refresh(used.refresh) is not None
    await auth.logout(used.refresh)
    assert await auth.refresh(used.refresh) is None


@pytest.mark.unit
async def test_the_file_holds_hashes_never_tokens(tmp_path: Path) -> None:
    auth, _ = make(tmp_path)
    pair = await auth.login()
    raw = (tmp_path / "devices.json").read_text(encoding="utf-8")
    assert pair.refresh not in raw
    assert pair.access not in raw


@pytest.mark.unit
async def test_logout_of_an_unknown_token_is_quiet(tmp_path: Path) -> None:
    auth, _ = make(tmp_path)
    await auth.logout("nope")

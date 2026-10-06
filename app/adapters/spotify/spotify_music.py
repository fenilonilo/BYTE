from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from typing import Any

import aiohttp

from app.domain.exceptions import MusicError, UnknownMusicDeviceError
from app.domain.music import (
    MediaKind,
    MusicItem,
    PlaybackChange,
    PlaybackState,
    Repeat,
    Skip,
)
from app.ports.music import MusicPort

API = "https://api.spotify.com/v1"
TOKEN_URL = "https://accounts.spotify.com/api/token"  # noqa: S105
SEARCH_LIMIT = 5  # dev-mode apps cap search results at 10
NO_CONTENT = 204
SETTLE_SECONDS = 0.7  # ponytail: Spotify state lags commands; poll if this proves flaky


def parse_item(raw: dict[str, Any]) -> MusicItem:
    artists = raw.get("artists") or ([raw["owner"]] if "owner" in raw else [])
    name = ", ".join(a.get("name") or a.get("display_name", "") for a in artists)
    return MusicItem(raw["uri"], raw["name"], MediaKind(raw["type"]), name)


def parse_state(raw: dict[str, Any] | None) -> PlaybackState:
    if not raw:
        return PlaybackState(False, None, 0, 0, 0, False, Repeat.OFF, "")
    item = raw.get("item")
    device = raw.get("device") or {}
    return PlaybackState(
        playing=bool(raw.get("is_playing")),
        item=parse_item(item) if item and item.get("type") == "track" else None,
        progress_ms=raw.get("progress_ms") or 0,
        duration_ms=(item or {}).get("duration_ms", 0),
        volume=device.get("volume_percent") or 0,
        shuffle=bool(raw.get("shuffle_state")),
        repeat=Repeat(raw.get("repeat_state", "off")),
        device=device.get("name", ""),
    )


class SpotifyMusic(MusicPort):
    """Spotify Web API. Needs Premium; audio plays on a Connect device (e.g. a Nest Mini)."""

    def __init__(self, client_id: str, refresh_token: str, default_device: str = "") -> None:
        self._client_id = client_id
        self._refresh_token = refresh_token
        self._default_device = default_device
        self._token = ""
        self._expires = 0.0
        self._session: aiohttp.ClientSession | None = None

    async def _access_token(self) -> str:
        if time.monotonic() < self._expires:
            return self._token
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "client_id": self._client_id,
        }
        async with self._http().post(TOKEN_URL, data=data) as res:
            if res.status != 200:  # noqa: PLR2004
                raise MusicError(f"spotify token refresh failed: {res.status}")
            body = await res.json()
        self._token = body["access_token"]
        self._refresh_token = body.get("refresh_token", self._refresh_token)
        self._expires = time.monotonic() + body["expires_in"] - 30
        return self._token

    def _http(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        return self._session

    async def _call(
        self, method: str, path: str, params: dict[str, Any] | None = None, body: object = None
    ) -> dict[str, Any] | None:
        headers = {"Authorization": f"Bearer {await self._access_token()}"}
        try:
            async with self._http().request(
                method, API + path, params=params, json=body, headers=headers
            ) as res:
                if res.status == NO_CONTENT:
                    return None
                if res.status >= 400:  # noqa: PLR2004
                    reason = "no active device" if res.status == 404 else f"http {res.status}"  # noqa: PLR2004
                    raise MusicError(f"spotify {method} {path}: {reason}")
                return await res.json() if res.content_type == "application/json" else None
        except aiohttp.ClientError as exc:
            raise MusicError("spotify unreachable") from exc

    async def _data(
        self, method: str, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return await self._call(method, path, params) or {}

    async def _device_id(self, name: str) -> str:
        raw = await self._data("GET", "/me/player/devices")
        for d in raw["devices"]:
            if d["name"].lower() == name.lower():
                return str(d["id"])
        raise UnknownMusicDeviceError(f"unknown device: {name!r}")

    async def devices(self) -> tuple[str, ...]:
        raw = await self._data("GET", "/me/player/devices")
        return tuple(d["name"] for d in raw["devices"])

    async def state(self) -> PlaybackState:
        return parse_state(await self._call("GET", "/me/player"))

    async def _settled_state(self) -> PlaybackState:
        await asyncio.sleep(SETTLE_SECONDS)
        return await self.state()

    async def search(self, query: str, kind: MediaKind) -> tuple[MusicItem, ...]:
        params = {"q": query, "type": kind.value, "limit": SEARCH_LIMIT}
        raw = await self._data("GET", "/search", params)
        return tuple(parse_item(i) for i in raw[f"{kind.value}s"]["items"] if i)

    async def play(self, uri: str | None = None, device: str | None = None) -> PlaybackState:
        name = device or self._default_device
        params = {"device_id": await self._device_id(name)} if name else None
        if uri is None:
            body = None
        elif ":track:" in uri:
            body = {"uris": [uri]}
        else:
            body = {"context_uri": uri}
        await self._call("PUT", "/me/player/play", params, body)
        return await self._settled_state()

    async def queue(self, uri: str) -> None:
        await self._call("POST", "/me/player/queue", {"uri": uri})

    async def playlists(self) -> tuple[MusicItem, ...]:
        raw = await self._data("GET", "/me/playlists", {"limit": 50})
        return tuple(parse_item(i) for i in raw["items"] if i)

    async def apply(self, change: PlaybackChange) -> PlaybackState:
        player = "/me/player"
        if change.paused is not None:
            await self._call("PUT", f"{player}/{'pause' if change.paused else 'play'}")
        if change.skip is Skip.NEXT:
            await self._call("POST", f"{player}/next")
        elif change.skip is Skip.PREVIOUS:
            await self._call("POST", f"{player}/previous")
        if change.seek_ms is not None:
            await self._call("PUT", f"{player}/seek", {"position_ms": change.seek_ms})
        if change.volume is not None:
            await self._call("PUT", f"{player}/volume", {"volume_percent": change.volume})
        if change.shuffle is not None:
            await self._call("PUT", f"{player}/shuffle", {"state": str(change.shuffle).lower()})
        if change.repeat is not None:
            await self._call("PUT", f"{player}/repeat", {"state": change.repeat.value})
        state = await self._settled_state()
        if change.volume is None:
            return state
        return replace(state, volume=change.volume)  # Cast devices report volume late

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()

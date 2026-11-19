from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from app.domain.exceptions import MusicError, UnknownMusicDeviceError
from app.domain.music import MediaKind, MusicDevice, MusicItem, PlaybackState, Repeat
from app.ports.music import MusicPort

if TYPE_CHECKING:
    from app.domain.music import PlaybackChange

CATALOG = (
    MusicItem("spotify:track:1", "Bohemian Rhapsody", MediaKind.TRACK, "Queen"),
    MusicItem("spotify:track:2", "Aquarela", MediaKind.TRACK, "Toquinho"),
    MusicItem("spotify:playlist:1", "Treino", MediaKind.PLAYLIST),
)


class InMemoryMusic(MusicPort):
    def __init__(self, devices: tuple[str, ...] = ("nest mini",)) -> None:
        self._devices = devices
        self.queued: list[str] = []
        self._state = PlaybackState(False, None, 0, 0, 50, False, Repeat.OFF, devices[0])

    @property
    def volume(self) -> int:
        return self._state.volume

    async def devices(self) -> tuple[str, ...]:
        return self._devices

    async def list_devices(self) -> tuple[MusicDevice, ...]:
        return tuple(
            MusicDevice(
                d, d == self._state.device, self._state.volume if d == self._state.device else None
            )
            for d in self._devices
        )

    async def select_device(self, name: str) -> None:
        if name.lower() not in self._devices:
            raise UnknownMusicDeviceError(f"unknown device: {name!r}")
        self._state = replace(self._state, device=name.lower())

    async def state(self) -> PlaybackState:
        return self._state

    async def search(self, query: str, kind: MediaKind) -> tuple[MusicItem, ...]:
        q = query.lower()
        return tuple(i for i in CATALOG if i.kind is kind and q in f"{i.name} {i.artist}".lower())

    async def play(self, uri: str | None = None, device: str | None = None) -> PlaybackState:
        if device is not None:
            if device.lower() not in self._devices:
                raise UnknownMusicDeviceError(f"unknown device: {device!r}")
            self._state = replace(self._state, device=device.lower())
        if uri is None:
            self._state = replace(self._state, playing=True)
            return self._state
        item = next((i for i in CATALOG if i.uri == uri), None)
        if item is None:
            raise MusicError(f"unknown uri: {uri!r}")
        self._state = replace(self._state, playing=True, item=item, progress_ms=0, duration_ms=1)
        return self._state

    async def queue(self, uri: str) -> None:
        self.queued.append(uri)

    async def playlists(self) -> tuple[MusicItem, ...]:
        return tuple(i for i in CATALOG if i.kind is MediaKind.PLAYLIST)

    async def apply(self, change: PlaybackChange) -> PlaybackState:
        self._state = change.apply_to(self._state)
        return self._state

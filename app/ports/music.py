from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.music import MediaKind, MusicItem, PlaybackChange, PlaybackState


class MusicPort(ABC):
    """Music playback by device name. Unknown device -> UnknownMusicDeviceError."""

    @abstractmethod
    async def devices(self) -> tuple[str, ...]: ...

    @abstractmethod
    async def state(self) -> PlaybackState: ...

    @abstractmethod
    async def search(self, query: str, kind: MediaKind) -> tuple[MusicItem, ...]: ...

    @abstractmethod
    async def play(self, uri: str | None = None, device: str | None = None) -> PlaybackState:
        """Play `uri` (a search/playlist result), or resume when None; `device` moves playback."""

    @abstractmethod
    async def queue(self, uri: str) -> None: ...

    @abstractmethod
    async def playlists(self) -> tuple[MusicItem, ...]: ...

    @abstractmethod
    async def apply(self, change: PlaybackChange) -> PlaybackState:
        """Apply a partial change and return the resulting state."""

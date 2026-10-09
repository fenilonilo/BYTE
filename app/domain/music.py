from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from app.domain.exceptions import MusicError

MAX_VOLUME = 100


class Repeat(StrEnum):
    OFF = "off"
    TRACK = "track"
    CONTEXT = "context"


class MediaKind(StrEnum):
    TRACK = "track"
    ALBUM = "album"
    PLAYLIST = "playlist"
    ARTIST = "artist"


class Skip(StrEnum):
    NEXT = "next"
    PREVIOUS = "previous"


@dataclass(frozen=True, slots=True)
class MusicItem:
    uri: str
    name: str
    kind: MediaKind
    artist: str = ""


@dataclass(frozen=True, slots=True)
class MusicDevice:
    name: str
    active: bool
    volume: int | None


@dataclass(frozen=True, slots=True)
class PlaybackState:
    playing: bool
    item: MusicItem | None
    progress_ms: int
    duration_ms: int
    volume: int
    shuffle: bool
    repeat: Repeat
    device: str


@dataclass(frozen=True, slots=True)
class PlaybackChange:
    """Partial update. `None` leaves a field alone."""

    paused: bool | None = None
    volume: int | None = None
    shuffle: bool | None = None
    repeat: Repeat | None = None
    seek_ms: int | None = None
    skip: Skip | None = None

    def __post_init__(self) -> None:
        if all(getattr(self, f) is None for f in self.__slots__):
            raise MusicError("empty playback change")
        if self.volume is not None and not 0 <= self.volume <= MAX_VOLUME:
            raise MusicError(f"volume must be 0-{MAX_VOLUME}")
        if self.seek_ms is not None and self.seek_ms < 0:
            raise MusicError("seek must be >= 0")

    def apply_to(self, state: PlaybackState) -> PlaybackState:
        new = state
        if self.paused is not None:
            new = replace(new, playing=not self.paused)
        if self.volume is not None:
            new = replace(new, volume=self.volume)
        if self.shuffle is not None:
            new = replace(new, shuffle=self.shuffle)
        if self.repeat is not None:
            new = replace(new, repeat=self.repeat)
        if self.seek_ms is not None:
            new = replace(new, progress_ms=min(self.seek_ms, state.duration_ms))
        if self.skip is not None:
            new = replace(new, progress_ms=0, playing=True)
        return new

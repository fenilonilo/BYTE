from __future__ import annotations

import pytest

from app.domain.exceptions import MusicError
from app.domain.music import PlaybackChange, PlaybackState, Repeat, Skip

STATE = PlaybackState(True, None, 5000, 10000, 50, False, Repeat.OFF, "nest")


def test_empty_change_rejected() -> None:
    with pytest.raises(MusicError):
        PlaybackChange()


@pytest.mark.parametrize("kw", [{"volume": 101}, {"volume": -1}, {"seek_ms": -1}])
def test_bounds_rejected(kw: dict[str, int]) -> None:
    with pytest.raises(MusicError):
        PlaybackChange(**kw)


def test_apply_fields() -> None:
    new = PlaybackChange(paused=True, volume=20, shuffle=True, repeat=Repeat.TRACK).apply_to(STATE)
    assert (new.playing, new.volume, new.shuffle, new.repeat) == (False, 20, True, Repeat.TRACK)


def test_seek_clamped_and_skip_restarts() -> None:
    assert PlaybackChange(seek_ms=99999).apply_to(STATE).progress_ms == 10000
    assert PlaybackChange(skip=Skip.NEXT).apply_to(STATE).progress_ms == 0

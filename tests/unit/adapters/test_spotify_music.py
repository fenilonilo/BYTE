from __future__ import annotations

from typing import TYPE_CHECKING

from app.adapters.spotify import spotify_music
from app.adapters.spotify.spotify_music import parse_item, parse_state
from app.domain.music import MediaKind, PlaybackChange, Repeat

if TYPE_CHECKING:
    import pytest

TRACK = {
    "uri": "spotify:track:1",
    "name": "Aquarela",
    "type": "track",
    "artists": [{"name": "Toquinho"}, {"name": "Vinicius"}],
    "duration_ms": 200000,
}


def test_parse_item_track_and_playlist() -> None:
    assert parse_item(TRACK).artist == "Toquinho, Vinicius"
    pl = {"uri": "spotify:playlist:9", "name": "Treino", "type": "playlist"}
    assert parse_item(pl).kind is MediaKind.PLAYLIST


def test_parse_state_playing() -> None:
    st = parse_state(
        {
            "is_playing": True,
            "item": TRACK,
            "progress_ms": 1000,
            "shuffle_state": True,
            "repeat_state": "track",
            "device": {"name": "Nest Mini", "volume_percent": 30},
        }
    )
    assert (st.playing, st.volume, st.repeat, st.device) == (True, 30, Repeat.TRACK, "Nest Mini")
    assert st.item is not None and st.duration_ms == 200000


def test_parse_state_idle() -> None:
    assert parse_state(None).playing is False


async def test_apply_volume_returns_requested_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(spotify_music, "SETTLE_SECONDS", 0)
    music = spotify_music.SpotifyMusic("cid", "tok")
    calls: list[tuple[str, str]] = []

    async def fake_call(method: str, path: str, *_: object, **__: object) -> dict[str, object]:
        calls.append((method, path))
        return {"device": {"name": "Nest", "volume_percent": 99}}

    monkeypatch.setattr(music, "_call", fake_call)
    state = await music.apply(PlaybackChange(volume=20))
    assert state.volume == 20
    assert ("PUT", "/me/player/volume") in calls

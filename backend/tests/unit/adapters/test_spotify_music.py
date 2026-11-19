from __future__ import annotations

import pytest

from app.adapters.spotify import spotify_music
from app.adapters.spotify.spotify_music import parse_item, parse_state
from app.domain.exceptions import MusicOfflineError, UnknownMusicDeviceError
from app.domain.music import MediaKind, PlaybackChange, Repeat

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


DEVICES: dict[str, object] = {
    "devices": [
        {"id": "a1", "name": "BatCaverna", "is_active": True, "volume_percent": 40},
        {"id": "b2", "name": "Quarto", "is_active": False, "volume_percent": None},
    ]
}


def _fake(music: spotify_music.SpotifyMusic, monkeypatch: pytest.MonkeyPatch, playing: bool):
    calls: list[tuple[str, str, object]] = []

    async def fake_call(
        method: str, path: str, params: object = None, body: object = None
    ) -> dict[str, object] | None:
        calls.append((method, path, body))
        if path == "/me/player/devices":
            return DEVICES
        if path == "/me/player" and method == "GET":
            return {"is_playing": playing, "device": {"name": "BatCaverna"}}
        return None

    monkeypatch.setattr(music, "_call", fake_call)
    return calls


async def test_list_devices_maps_spotify_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    music = spotify_music.SpotifyMusic("cid", "tok")
    _fake(music, monkeypatch, playing=False)
    devices = await music.list_devices()
    assert [(d.name, d.active, d.volume) for d in devices] == [
        ("BatCaverna", True, 40),
        ("Quarto", False, None),
    ]


@pytest.mark.parametrize("playing", [True, False])
async def test_select_device_transfers_by_id_and_keeps_play_state(
    monkeypatch: pytest.MonkeyPatch, playing: bool
) -> None:
    music = spotify_music.SpotifyMusic("cid", "tok")
    calls = _fake(music, monkeypatch, playing)
    await music.select_device("quarto")
    assert ("PUT", "/me/player", {"device_ids": ["b2"], "play": playing}) in calls


async def test_select_unknown_device(monkeypatch: pytest.MonkeyPatch) -> None:
    music = spotify_music.SpotifyMusic("cid", "tok", "Sala")
    _fake(music, monkeypatch, playing=False)
    with pytest.raises(UnknownMusicDeviceError):
        await music.select_device("garagem")


async def test_default_device_missing_reads_as_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    music = spotify_music.SpotifyMusic("cid", "tok", "Sala")
    _fake(music, monkeypatch, playing=False)
    with pytest.raises(MusicOfflineError, match=r"Sala está offline no Spotify\. Abra o Spotify"):
        await music.play("spotify:track:1")


async def test_no_devices_is_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    music = spotify_music.SpotifyMusic("cid", "tok")

    async def empty(*_: object, **__: object) -> None:
        return None

    monkeypatch.setattr(music, "_call", empty)
    assert await music.list_devices() == ()

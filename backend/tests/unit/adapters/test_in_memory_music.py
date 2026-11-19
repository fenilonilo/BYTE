from __future__ import annotations

import pytest

from app.adapters.memory.in_memory_music import InMemoryMusic
from app.domain.exceptions import MusicError, UnknownMusicDeviceError
from app.domain.music import MediaKind, PlaybackChange


async def test_search_filters_by_kind_and_text() -> None:
    items = await InMemoryMusic().search("queen", MediaKind.TRACK)
    assert [i.name for i in items] == ["Bohemian Rhapsody"]


async def test_play_uri_then_apply() -> None:
    m = InMemoryMusic()
    st = await m.play("spotify:track:2")
    assert st.playing and st.item is not None and st.item.name == "Aquarela"
    assert (await m.apply(PlaybackChange(volume=10))).volume == 10


async def test_unknown_device_and_uri() -> None:
    m = InMemoryMusic()
    with pytest.raises(UnknownMusicDeviceError):
        await m.play(device="cozinha")
    with pytest.raises(MusicError):
        await m.play("spotify:track:x")


async def test_list_and_select_device() -> None:
    m = InMemoryMusic(("nest mini", "cozinha"))
    devices = await m.list_devices()
    assert [(d.name, d.active) for d in devices] == [("nest mini", True), ("cozinha", False)]
    assert devices[1].volume is None
    await m.select_device("Cozinha")
    assert (await m.state()).device == "cozinha"
    with pytest.raises(UnknownMusicDeviceError):
        await m.select_device("garagem")

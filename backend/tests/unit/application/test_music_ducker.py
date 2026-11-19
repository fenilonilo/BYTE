from __future__ import annotations

import asyncio

import pytest

from app.adapters.memory.in_memory_music import InMemoryMusic
from app.application.music_ducker import MusicDucker
from app.domain.exceptions import MusicError
from app.domain.music import PlaybackChange, PlaybackState
from tests.fakes.logger import RecordingLogger


class BrokenMusic(InMemoryMusic):
    async def state(self) -> PlaybackState:
        raise MusicError("fora do ar")


class RestoreFails(InMemoryMusic):
    def __init__(self) -> None:
        super().__init__()
        self.fail = False

    async def apply(self, change: PlaybackChange) -> PlaybackState:
        if self.fail:
            raise MusicError("fora do ar")
        return await super().apply(change)


async def playing_music(volume: int = 70, music: InMemoryMusic | None = None) -> InMemoryMusic:
    music = music or InMemoryMusic()
    await music.play("spotify:track:1")
    await music.apply(PlaybackChange(volume=volume))
    return music


async def settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


def make(music: InMemoryMusic, percent: int = 20) -> tuple[MusicDucker, RecordingLogger]:
    log = RecordingLogger()
    return MusicDucker(music, log, percent), log


async def volume(music: InMemoryMusic) -> int:
    return (await music.state()).volume


async def test_ducks_then_restores() -> None:
    music = await playing_music(70)
    ducker, _ = make(music)
    async with ducker.session():
        await settle()
        assert await volume(music) == 20
    assert await volume(music) == 70


async def test_volume_the_agent_chose_wins() -> None:
    music = await playing_music(70)
    ducker, _ = make(music)
    async with ducker.session():
        await settle()
        await music.apply(PlaybackChange(volume=60))
        ducker.note_volume(60)
    assert await volume(music) == 60


async def test_nothing_playing_is_left_alone() -> None:
    music = InMemoryMusic()
    ducker, log = make(music)
    async with ducker.session():
        await settle()
    assert await volume(music) == 50
    assert ("info", "music.duck_skipped", {"reason": "idle"}) in log.events


async def test_already_quieter_than_the_duck_is_left_alone() -> None:
    music = await playing_music(10)
    ducker, _ = make(music)
    async with ducker.session():
        await settle()
        assert await volume(music) == 10
    assert await volume(music) == 10


async def test_100_disables_ducking() -> None:
    music = await playing_music(70)
    ducker, _ = make(music, 100)
    async with ducker.session():
        await settle()
        assert await volume(music) == 70


async def test_music_error_is_swallowed() -> None:
    ducker, log = make(BrokenMusic())
    async with ducker.session():
        await settle()
    assert ("info", "music.duck_skipped", {"reason": "MusicError"}) in log.events


async def test_restore_error_is_swallowed() -> None:
    music = RestoreFails()
    await playing_music(70, music)
    ducker, log = make(music)
    async with ducker.session():
        await settle()
        music.fail = True
    assert ("info", "music.duck_skipped", {"reason": "MusicError"}) in log.events


async def test_restores_when_the_session_raises() -> None:
    music = await playing_music(70)
    ducker, _ = make(music)
    with pytest.raises(RuntimeError):
        async with ducker.session():
            await settle()
            raise RuntimeError("socket caiu")
    assert await volume(music) == 70


async def test_restores_when_the_session_is_cancelled() -> None:
    music = await playing_music(70)
    ducker, _ = make(music)

    async def session() -> None:
        async with ducker.session():
            await asyncio.sleep(10)

    task = asyncio.create_task(session())
    await settle()
    assert await volume(music) == 20
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await settle()
    assert await volume(music) == 70


async def test_replacement_keeps_the_original_volume() -> None:
    music = await playing_music(70)
    ducker, _ = make(music)
    old, new = ducker.session(), ducker.session()
    await old.__aenter__()
    await settle()
    await new.__aenter__()
    await settle()
    await old.__aexit__(None, None, None)
    assert await volume(music) == 20  # the new session is still running
    await new.__aexit__(None, None, None)
    assert await volume(music) == 70


async def test_a_session_shorter_than_the_duck_still_restores() -> None:
    music = await playing_music(70)
    ducker, _ = make(music)
    async with ducker.session():
        pass
    assert await volume(music) == 70

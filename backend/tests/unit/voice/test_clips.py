from __future__ import annotations

import wave
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from tests.fakes.logger import RecordingLogger
from voice.clips import ClipStore

if TYPE_CHECKING:
    from pathlib import Path

PCM = b"\x01\x00" * 16_000  # one second at 16 kHz


def at(second: int) -> datetime:
    return datetime(2026, 11, 19, 18, 0, second, tzinfo=UTC)


def test_a_clip_is_a_16k_mono_wav_named_by_time_and_score(tmp_path: Path) -> None:
    store = ClipStore(tmp_path / "clips", keep=10, log=RecordingLogger(), now=lambda: at(5))
    name = store.save(PCM, 0.734)
    assert name == "20261119T180005Z_0.73.wav"
    with wave.open(str(tmp_path / "clips" / name), "rb") as clip:
        assert (clip.getnchannels(), clip.getsampwidth(), clip.getframerate()) == (1, 2, 16_000)
        assert clip.readframes(clip.getnframes()) == PCM


def test_only_the_newest_clips_are_kept(tmp_path: Path) -> None:
    seconds = iter(range(5))
    store = ClipStore(tmp_path, keep=2, log=RecordingLogger(), now=lambda: at(next(seconds)))
    for _ in range(5):
        store.save(PCM, 0.9)
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "20261119T180003Z_0.90.wav",
        "20261119T180004Z_0.90.wav",
    ]


def test_an_unwritable_directory_disables_clips_without_raising(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    log = RecordingLogger()
    store = ClipStore(blocker / "clips", keep=10, log=log, now=lambda: at(0))
    assert store.save(PCM, 0.9) is None
    assert "voice.clips_disabled" in log.names()

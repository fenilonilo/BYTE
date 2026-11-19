from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from tests.fakes.clock import FakeClock
from tests.fakes.logger import RecordingLogger
from tests.fakes.voice import FakeSocket, FakeSpeaker
from voice.notifications import BEEPS, CHIME, RING_PAUSE_SECONDS, Notifier

if TYPE_CHECKING:
    from collections.abc import Callable

SPEECH = b"\x01\x00" * 10


class StopError(Exception):
    pass


class Rig:
    def __init__(self, ring_seconds: float = 300.0) -> None:
        self.socket = FakeSocket()
        self.speaker = FakeSpeaker()
        self.clock = FakeClock()
        self.log = RecordingLogger()
        self.idle = True
        self.slept: list[float] = []
        self.hook: Callable[[], None] | None = None
        self.notifier = Notifier(
            connect=self._connect,
            speaker=self.speaker,
            log=self.log,
            idle=lambda: self.idle,
            clock=self.clock,
            sleep=self._sleep,
            ring_seconds=ring_seconds,
        )
        self.connects = 0
        self.fail_first = False

    async def _connect(self) -> FakeSocket:
        self.connects += 1
        if self.fail_first and self.connects == 1:
            raise ConnectionRefusedError
        return self.socket

    async def _sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.clock.advance(seconds)
        if self.hook is not None:
            self.hook()
        await asyncio.sleep(0)

    def send(self, rid: str, kind: str) -> None:
        self.socket.push({"type": "reminder", "id": rid, "kind": kind})
        self.socket.push(SPEECH)

    async def serve(self) -> None:
        self.socket.end()
        await self.notifier._serve(self.socket)  # pyright: ignore[reportPrivateUsage]


def acks(rig: Rig) -> list[object]:
    return [e["id"] for e in rig.socket.events() if e["type"] == "ack"]


@pytest.mark.unit
async def test_reminder_chimes_speaks_once_and_acks() -> None:
    rig = Rig()
    rig.send("r1", "lembrete")
    await rig.serve()
    assert rig.speaker.played == [CHIME + SPEECH]
    assert acks(rig) == ["r1"]


@pytest.mark.unit
async def test_reminder_waits_for_the_live_conversation_to_end() -> None:
    rig = Rig()
    rig.idle = False

    def end_conversation() -> None:
        rig.idle = True

    rig.hook = end_conversation
    rig.send("r1", "lembrete")
    await rig.serve()
    assert rig.slept[0] < 1  # polled while busy
    assert rig.speaker.played == [CHIME + SPEECH]


@pytest.mark.unit
async def test_alarm_rings_until_the_wake_word_stops_it() -> None:
    rig = Rig()

    def wake_on_third_ring() -> None:
        if rig.speaker.played.count(BEEPS + SPEECH) == 3:
            assert rig.notifier.stop()

    rig.hook = wake_on_third_ring
    rig.send("a1", "alarme")
    await rig.serve()
    assert rig.speaker.played.count(BEEPS + SPEECH) == 3
    assert rig.speaker.cleared == 1
    assert acks(rig) == ["a1"]
    assert not rig.notifier.stop()  # nothing playing any more


@pytest.mark.unit
async def test_alarm_nobody_stops_gives_up_after_the_cap() -> None:
    rig = Rig(ring_seconds=RING_PAUSE_SECONDS * 4)
    rig.send("a1", "alarme")
    await rig.serve()
    assert rig.speaker.played.count(BEEPS + SPEECH) == 4
    assert acks(rig) == ["a1"]


@pytest.mark.unit
async def test_wake_word_while_speaking_a_reminder_silences_it() -> None:
    rig = Rig()
    rig.speaker.is_busy = True

    def wake() -> None:
        assert rig.notifier.stop()

    rig.hook = wake
    rig.send("r1", "lembrete")
    await rig.serve()
    assert acks(rig) == ["r1"]


@pytest.mark.unit
async def test_audio_without_a_header_and_other_events_are_ignored() -> None:
    rig = Rig()
    rig.socket.push(SPEECH)
    rig.socket.push({"type": "hello"})
    rig.socket.push(SPEECH)
    await rig.serve()
    assert rig.speaker.played == []
    assert rig.socket.sent == []


@pytest.mark.unit
async def test_run_reconnects_after_a_failure() -> None:
    rig = Rig()
    rig.fail_first = True

    def stop_after_second_connect() -> None:
        if rig.connects >= 2:
            raise StopError

    rig.hook = stop_after_second_connect
    rig.socket.end()
    with pytest.raises(StopError):
        await rig.notifier.run()
    assert rig.connects == 2
    assert "voice.notify_link_failed" in rig.log.names()
    assert "voice.notify_linked" in rig.log.names()

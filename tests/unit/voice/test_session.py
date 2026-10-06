from __future__ import annotations

import asyncio

import numpy as np
import pytest

from tests.fakes.clock import FakeClock
from tests.fakes.logger import RecordingLogger
from tests.fakes.voice import FakeDetector, FakeSocket, FakeSpeaker
from voice.session import SessionConfig, VoiceSession, upsample_16k_to_24k

FRAME = np.zeros(1280, dtype=np.int16).tobytes()  # 80 ms at 16 kHz


def tone(value: int) -> bytes:
    return np.full(1280, value, dtype=np.int16).tobytes()


def middle(chunk: bytes) -> int:
    return int(np.frombuffer(chunk, dtype=np.int16)[len(chunk) // 4])


async def settle() -> None:
    for _ in range(10):
        await asyncio.sleep(0)


class Rig:
    def __init__(
        self, config: SessionConfig | None = None, connect_error: Exception | None = None
    ) -> None:
        self.sockets: list[FakeSocket] = []
        self.connect_error = connect_error
        self.detector = FakeDetector()
        self.speaker = FakeSpeaker()
        self.clock = FakeClock()
        self.log = RecordingLogger()
        self.session = VoiceSession(
            detector=self.detector,
            connect=self._connect,
            speaker=self.speaker,
            clock=self.clock,
            log=self.log,
            config=config or SessionConfig(),
        )

    async def _connect(self) -> FakeSocket:
        if self.connect_error is not None:
            raise self.connect_error
        self.sockets.append(FakeSocket())
        return self.sockets[-1]

    @property
    def socket(self) -> FakeSocket:
        return self.sockets[-1]

    async def wake(self) -> None:
        self.detector.wake_next = True
        await self.session.on_frame(FRAME)
        await settle()

    async def go_live(self) -> None:
        await self.wake()
        self.socket.push({"type": "ready"})
        await settle()


def test_upsample_ratio_is_three_to_two() -> None:
    assert len(upsample_16k_to_24k(FRAME)) == 3840


async def test_idle_frames_only_reach_the_detector() -> None:
    rig = Rig()
    await rig.session.on_frame(FRAME)
    assert rig.detector.calls == 1
    assert rig.sockets == []
    assert rig.session.state == "idle"


async def test_wake_opens_the_socket_and_sends_start() -> None:
    rig = Rig(SessionConfig(segment="home"))
    await rig.wake()
    assert rig.session.state == "connecting"
    assert rig.socket.events() == [{"type": "start", "segment": "home"}]


async def test_audio_before_ready_is_buffered_then_flushed_in_order() -> None:
    rig = Rig()
    await rig.wake()
    for value in (100, 200, 300):
        await rig.session.on_frame(tone(value))
    assert rig.socket.audio() == []
    rig.socket.push({"type": "ready"})
    await settle()
    assert rig.session.state == "live"
    assert [middle(c) for c in rig.socket.audio()] == pytest.approx([100, 200, 300], rel=0.05)


async def test_buffer_keeps_only_the_latest_frames() -> None:
    rig = Rig(SessionConfig(buffer_seconds=0.16))  # two frames
    await rig.wake()
    for value in (100, 200, 300, 400):
        await rig.session.on_frame(tone(value))
    rig.socket.push({"type": "ready"})
    await settle()
    assert [middle(c) for c in rig.socket.audio()] == pytest.approx([300, 400], rel=0.05)


async def test_second_wake_while_connecting_is_ignored() -> None:
    rig = Rig()
    await rig.wake()
    rig.detector.wake_next = True
    await rig.session.on_frame(FRAME)
    await settle()
    assert len(rig.sockets) == 1
    assert rig.detector.calls == 1


async def test_binary_before_ready_is_not_played() -> None:
    rig = Rig()
    await rig.wake()
    rig.socket.push(b"\x01\x02")
    await settle()
    assert rig.speaker.played == []


async def test_live_frames_are_upsampled_and_sent() -> None:
    rig = Rig()
    await rig.go_live()
    await rig.session.on_frame(FRAME)
    assert [len(c) for c in rig.socket.audio()] == [3840]


async def test_odd_length_frame_is_dropped_without_crashing() -> None:
    rig = Rig()
    await rig.go_live()
    await rig.session.on_frame(b"\x00\x00\x00")
    assert rig.socket.audio() == []
    assert rig.session.state == "live"


async def test_server_audio_is_played() -> None:
    rig = Rig()
    await rig.go_live()
    rig.socket.push(b"\x01\x00" * 10)
    await settle()
    assert rig.speaker.played == [b"\x01\x00" * 10]


async def test_mic_is_muted_while_speaking_and_for_the_echo_tail() -> None:
    rig = Rig()
    await rig.go_live()
    rig.speaker.is_busy = True
    await rig.session.on_frame(FRAME)
    assert rig.socket.audio() == []
    rig.speaker.is_busy = False
    rig.clock.advance(0.1)
    await rig.session.on_frame(FRAME)  # inside the 0.3 s tail
    assert rig.socket.audio() == []
    rig.clock.advance(0.3)
    await rig.session.on_frame(FRAME)
    assert len(rig.socket.audio()) == 1


async def test_interrupt_flushes_playback_and_reports_played_ms() -> None:
    rig = Rig()
    await rig.go_live()
    rig.speaker.played_ms = 1234
    rig.socket.push({"type": "interrupt"})
    await settle()
    assert rig.speaker.cleared == 1
    assert {"type": "played", "audio_end_ms": 1234} in rig.socket.events()

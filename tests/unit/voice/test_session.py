from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import TYPE_CHECKING

import numpy as np
import pytest

from tests.fakes.clock import FakeClock
from tests.fakes.logger import RecordingLogger
from tests.fakes.voice import FakeDetector, FakeSocket, FakeSpeaker
from voice.session import SessionConfig, VoiceSession, upsample_16k_to_24k

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

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
    await arm(rig)
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


async def arm(rig: Rig) -> None:
    rig.socket.push({"type": "turn_done"})
    await settle()


async def test_idle_timeout_closes_the_link() -> None:
    rig = Rig()
    await rig.go_live()
    await arm(rig)
    rig.clock.advance(9)
    await rig.session.on_frame(FRAME)
    await settle()
    assert rig.socket.closed
    assert rig.session.state == "idle"
    assert "voice.idle_close" in rig.log.names()
    assert rig.detector.resets == 1
    assert rig.speaker.cleared >= 1


async def test_no_idle_close_before_the_first_turn_done() -> None:
    rig = Rig()
    await rig.go_live()
    rig.clock.advance(20)
    await rig.session.on_frame(FRAME)
    await settle()
    assert not rig.socket.closed


async def test_server_events_count_as_activity() -> None:
    rig = Rig()
    await rig.go_live()
    await arm(rig)
    rig.clock.advance(7)
    rig.socket.push({"type": "transcript", "role": "assistant", "text": "ignored", "final": True})
    await settle()
    rig.clock.advance(7)
    await rig.session.on_frame(FRAME)
    await settle()
    assert not rig.socket.closed


async def test_agent_audio_disarms_idle() -> None:
    rig = Rig()
    await rig.go_live()
    await arm(rig)
    rig.socket.push(b"")
    await settle()
    rig.clock.advance(20)
    await rig.session.on_frame(FRAME)
    await settle()
    assert not rig.socket.closed


async def test_user_transcript_disarms_idle() -> None:
    rig = Rig()
    await rig.go_live()
    await arm(rig)
    rig.socket.push({"type": "transcript", "role": "user", "text": "x", "final": False})
    await settle()
    rig.clock.advance(20)
    await rig.session.on_frame(FRAME)
    await settle()
    assert not rig.socket.closed


async def test_idle_close_fires_once() -> None:
    rig = Rig()
    await rig.go_live()
    await arm(rig)
    rig.clock.advance(9)
    await rig.session.on_frame(FRAME)
    await rig.session.on_frame(FRAME)
    assert rig.log.names().count("voice.idle_close") == 1


async def test_long_agent_speech_is_not_idle_closed() -> None:
    rig = Rig()
    await rig.go_live()
    rig.speaker.is_busy = True
    for _ in range(300):  # 24 s of agent audio, longer than idle_seconds
        rig.clock.advance(0.08)
        await rig.session.on_frame(FRAME)
    rig.speaker.is_busy = False
    rig.clock.advance(0.31)
    await rig.session.on_frame(FRAME)
    await settle()
    assert not rig.socket.closed
    assert len(rig.socket.audio()) == 1


async def test_server_close_returns_to_idle_and_resets_the_detector() -> None:
    rig = Rig()
    await rig.go_live()
    rig.socket.end()
    await settle()
    assert rig.session.state == "idle"
    assert rig.detector.resets == 1
    assert rig.speaker.cleared >= 1
    await rig.wake()  # a new wake word opens a fresh session
    assert len(rig.sockets) == 2


async def test_error_event_ends_the_session_and_logs_only_the_code() -> None:
    rig = Rig()
    await rig.go_live()
    rig.socket.push({"type": "error", "code": "session_limit"})
    await settle()
    assert rig.socket.closed
    assert rig.session.state == "idle"
    assert ("warning", "voice.server_error", {"code": "session_limit"}) in rig.log.events


async def test_closed_event_ends_the_session() -> None:
    rig = Rig()
    await rig.go_live()
    rig.socket.push({"type": "closed", "reason": "idle"})
    await settle()
    assert rig.session.state == "idle"


async def test_malformed_server_message_ends_the_session() -> None:
    rig = Rig()
    await rig.wake()
    rig.socket.push("not json")
    await settle()
    assert rig.session.state == "idle"
    assert rig.socket.closed


async def test_connect_failure_returns_to_idle_and_can_retry() -> None:
    rig = Rig(connect_error=OSError("refused"))
    await rig.wake()
    assert rig.session.state == "idle"
    assert ("warning", "voice.link_failed", {"error": "OSError"}) in rig.log.events
    rig.connect_error = None
    await rig.wake()
    assert len(rig.sockets) == 1


class _StatusError(Exception):
    def __init__(self) -> None:
        super().__init__("rejected")
        self.response = SimpleNamespace(status_code=403)


async def test_connect_failure_logs_the_http_status() -> None:
    rig = Rig(connect_error=_StatusError())
    await rig.wake()
    assert ("warning", "voice.link_failed", {"error": "_StatusError", "status": 403}) in (
        rig.log.events
    )


async def test_send_failure_on_a_dead_socket_does_not_crash_the_mic_loop() -> None:
    rig = Rig()
    await rig.go_live()
    rig.socket.closed = True  # peer vanished, receive loop has not noticed yet
    await rig.session.on_frame(FRAME)  # must not raise
    assert rig.socket.audio() == []


async def test_detector_is_not_called_while_live() -> None:
    rig = Rig()
    await rig.go_live()
    calls = rig.detector.calls
    await rig.session.on_frame(FRAME)
    assert rig.detector.calls == calls


async def test_run_closes_the_link_when_the_mic_ends() -> None:
    rig = Rig()
    rig.detector.wake_next = True

    async def mic() -> AsyncIterator[bytes]:
        yield FRAME
        await settle()

    await rig.session.run(mic())
    assert rig.socket.closed
    assert rig.session.state == "idle"

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

import pytest

from app.application.tool import Tool
from app.application.tools.args import object_schema
from app.application.use_cases.run_live_session import LiveLimits
from app.domain.exceptions import LiveSessionError
from app.domain.live import (
    AssistantAudio,
    AssistantTranscript,
    LiveError,
    ResponseDone,
    ResponseStarted,
    UserSpeechStarted,
    UserTranscript,
)
from app.domain.tools import ToolCall, ToolSpec
from tests.fakes.events import events_on_day, seed_event
from tests.fakes.live import LiveWorld, eventually

if TYPE_CHECKING:
    from collections.abc import Mapping


class GateTool(Tool):
    """Blocks until the test opens the gate."""

    def __init__(self) -> None:
        self.spec = ToolSpec("gate", "d", object_schema({}), "home")
        self.gate = asyncio.Event()
        self.started = False

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        self.started = True
        await self.gate.wait()
        return "aberto"


class BrokenTool(Tool):
    def __init__(self) -> None:
        self.spec = ToolSpec("broken", "d", object_schema({}), "home")

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        raise RuntimeError("detalhe interno")


def call(name: str, arguments: str = "{}", call_id: str = "call-1") -> ToolCall:
    return ToolCall(id=call_id, name=name, arguments=arguments)


def user_says(world: LiveWorld, text: str, item: str = "u1") -> None:
    world.session.push(UserSpeechStarted(item), UserTranscript(item, text))


async def finish(world: LiveWorld, task: asyncio.Task[None]) -> None:
    world.transport.disconnect()
    await asyncio.wait_for(task, timeout=1)


async def start_and_wait_ready(world: LiveWorld, segment: str | None = None) -> asyncio.Task[None]:
    task = world.start(segment)
    await eventually(lambda: bool(world.transport.sent("ready")))
    return task


async def ask_to_delete_the_event(world: LiveWorld) -> None:
    """The user asks; the model calls the sensitive tool; the pending action is created."""
    await seed_event(world.calendar)
    user_says(world, "apaga o dentista")
    world.session.push(
        ResponseStarted(),
        ResponseDone(calls=(call("delete_event", '{"event_id": "evt-1"}'),)),
    )
    await eventually(lambda: len(world.session.tool_results) == 1)
    assert "needs_confirmation" in world.session.tool_results[0][0].output
    world.session.push(
        ResponseStarted(), AssistantTranscript("Apagar o evento evt-1?"), ResponseDone()
    )
    await eventually(lambda: bool(world.transport.sent("turn_done")))


@pytest.mark.unit
async def test_opens_the_provider_with_instructions_and_the_segment_tools_then_says_ready() -> None:
    world = LiveWorld()
    task = await start_and_wait_ready(world, "home")

    assert world.adapter.opened_with is not None
    instructions, tools = world.adapter.opened_with
    assert "Byte" in instructions
    assert "Agora: 2026-10-21T12:00+00:00" in instructions
    assert {t.segment for t in tools} == {"home", "*"}
    ready = world.transport.sent("ready")[0]
    assert ready["conversation_id"] == "c1"
    assert ready["audio"] == {"format": "pcm16", "rate": 24000, "channels": 1}
    await finish(world, task)
    assert world.session.closed is True


@pytest.mark.unit
async def test_audio_is_relayed_in_both_directions_untouched() -> None:
    world = LiveWorld()
    task = await start_and_wait_ready(world)

    world.transport.feed(b"\x01\x02\x03")
    world.session.push(AssistantAudio(data=b"\x09\x08", item_id="a1"))
    await eventually(lambda: world.session.audio_in == [b"\x01\x02\x03"])
    await eventually(lambda: world.transport.audio_out == [b"\x09\x08"])
    await finish(world, task)


@pytest.mark.unit
async def test_transcripts_are_forwarded_and_saved_under_the_conversation() -> None:
    world = LiveWorld()
    task = await start_and_wait_ready(world)

    user_says(world, "oi")
    world.session.push(AssistantTranscript("olá"), ResponseDone())
    await eventually(lambda: bool(world.transport.sent("turn_done")))

    roles = [(e["role"], e["text"]) for e in world.transport.sent("transcript")]
    assert roles == [("user", "oi"), ("assistant", "olá")]
    stored = await world.store.recent("c1", 20)
    assert [(m.role, m.content) for m in stored] == [("user", "oi"), ("assistant", "olá")]
    await finish(world, task)


@pytest.mark.unit
async def test_a_multi_call_response_sends_every_result_then_exactly_one_response_create() -> None:
    world = LiveWorld()
    task = await start_and_wait_ready(world)

    world.session.push(
        ResponseStarted(),
        ResponseDone(calls=(call("list_lights", call_id="a"), call("list_lights", call_id="b"))),
    )
    await eventually(lambda: len(world.session.tool_results) == 1)

    assert [r.call_id for r in world.session.tool_results[0]] == ["a", "b"]
    assert world.session.response_requests == 1
    await finish(world, task)


@pytest.mark.unit
async def test_response_create_waits_while_another_response_is_active() -> None:
    gate = GateTool()
    world = LiveWorld(extra_tools=[gate])
    task = await start_and_wait_ready(world)

    world.session.push(ResponseDone(calls=(call("gate"),)))
    await eventually(lambda: gate.started)
    world.session.push(ResponseStarted())  # the user barged in and the provider answered on its own
    await asyncio.sleep(0.05)
    gate.gate.set()
    await eventually(lambda: len(world.session.tool_results) == 1)

    assert world.session.response_requests == 0
    world.session.push(ResponseDone())
    await eventually(lambda: world.session.response_requests == 1)
    await finish(world, task)


@pytest.mark.unit
async def test_confirmation_waits_for_the_transcript_then_runs_the_tool() -> None:
    world = LiveWorld()
    task = await start_and_wait_ready(world)
    await ask_to_delete_the_event(world)

    world.session.push(
        UserSpeechStarted("u2"),
        ResponseStarted(),
        ResponseDone(calls=(call("confirm_action", call_id="c2"),)),
    )
    await asyncio.sleep(0.05)
    assert len(await events_on_day(world.calendar)) == 1  # still waiting for the transcript

    world.session.push(UserTranscript("u2", "sim"))
    await eventually(lambda: len(world.session.tool_results) == 2)

    assert world.session.tool_results[1][0].output == "Evento evt-1 apagado"
    assert await events_on_day(world.calendar) == ()
    await finish(world, task)


@pytest.mark.unit
async def test_speech_over_the_assistant_voice_cannot_confirm() -> None:
    world = LiveWorld()
    task = await start_and_wait_ready(world)
    await ask_to_delete_the_event(world)

    world.session.push(
        ResponseStarted(),
        AssistantAudio(data=b"\x01", item_id="a1"),
        UserSpeechStarted("echo"),
        UserTranscript("echo", "sim"),
        ResponseDone(calls=(call("confirm_action", call_id="c2"),)),
    )
    await eventually(lambda: len(world.session.tool_results) == 2)

    assert world.transport.sent("interrupt")
    assert world.session.tool_results[1][0].output.startswith("erro: aguarde")
    assert len(await events_on_day(world.calendar)) == 1
    await finish(world, task)


@pytest.mark.unit
async def test_confirm_without_any_transcript_is_refused_after_the_wait() -> None:
    world = LiveWorld(limits=LiveLimits(transcript_wait_seconds=0.03))
    task = await start_and_wait_ready(world)

    world.session.push(ResponseDone(calls=(call("confirm_action"),)))
    await eventually(lambda: len(world.session.tool_results) == 1)

    assert world.session.tool_results[0][0].output == "erro: não ouvi a confirmação do usuário"
    await finish(world, task)


@pytest.mark.unit
async def test_barge_in_interrupts_the_client_and_truncates_what_was_heard() -> None:
    world = LiveWorld()
    task = await start_and_wait_ready(world)

    world.session.push(AssistantAudio(data=b"\x01", item_id="a1"), UserSpeechStarted("u1"))
    await eventually(lambda: bool(world.transport.sent("interrupt")))
    world.transport.feed({"type": "played", "audio_end_ms": 1234})
    world.transport.feed({"type": "played", "audio_end_ms": "soon"})
    world.transport.feed({"type": "played", "audio_end_ms": True})
    world.transport.feed({"type": "hello"})
    await eventually(lambda: world.session.truncations == [("a1", 1234)])
    await finish(world, task)
    assert world.session.truncations == [("a1", 1234)]


@pytest.mark.unit
async def test_a_failing_tool_does_not_end_the_session() -> None:
    world = LiveWorld(extra_tools=[BrokenTool()])
    task = await start_and_wait_ready(world)

    world.session.push(ResponseDone(calls=(call("broken"),)))
    await eventually(lambda: len(world.session.tool_results) == 1)

    assert world.session.tool_results[0][0].output == "erro: falha interna na ferramenta"
    assert world.session.response_requests == 1
    assert not task.done()
    await finish(world, task)


@pytest.mark.unit
async def test_provider_errors_are_reported_to_the_client_and_raised() -> None:
    world = LiveWorld()
    task = await start_and_wait_ready(world)

    world.session.push(LiveError("rate_limit"))
    with pytest.raises(LiveSessionError, match="rate_limit"):
        await asyncio.wait_for(task, timeout=1)

    assert world.transport.sent("error")[0]["code"] == "rate_limit"
    assert world.session.closed is True


@pytest.mark.unit
async def test_open_failure_tells_the_client_and_never_says_ready() -> None:
    world = LiveWorld(open_error=LiveSessionError("provider down"))
    with pytest.raises(LiveSessionError, match="provider down"):
        await world.start()
    assert world.transport.events == [{"type": "error", "code": "model_unavailable"}]


@pytest.mark.unit
async def test_idle_sessions_are_closed() -> None:
    world = LiveWorld(limits=LiveLimits(idle_seconds=0.05))
    task = world.start()
    await asyncio.wait_for(task, timeout=1)

    assert world.transport.sent("closed")[0]["reason"] == "idle"
    assert world.session.closed is True


@pytest.mark.unit
async def test_the_hard_cap_ends_the_session_with_an_error_event() -> None:
    world = LiveWorld(limits=LiveLimits(max_seconds=0.05))
    task = world.start()
    await asyncio.wait_for(task, timeout=1)

    assert world.transport.sent("error")[0]["code"] == "session_limit"
    assert world.session.closed is True


@pytest.mark.unit
async def test_the_session_ends_when_the_provider_ends() -> None:
    world = LiveWorld()
    task = await start_and_wait_ready(world)
    world.session.end()
    await asyncio.wait_for(task, timeout=1)
    assert world.session.closed is True


@pytest.mark.unit
async def test_cancelling_the_session_still_closes_the_provider() -> None:
    world = LiveWorld()
    task = await start_and_wait_ready(world)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    assert world.session.closed is True


async def test_music_is_ducked_during_the_session_and_restored_after() -> None:
    world = LiveWorld()
    await world.music.play("spotify:track:1")
    task = await start_and_wait_ready(world)
    await eventually(lambda: world.music.volume == 20)
    await finish(world, task)
    await eventually(lambda: world.music.volume == 50)


async def test_volume_the_agent_sets_by_voice_survives_the_restore() -> None:
    world = LiveWorld()
    await world.music.play("spotify:track:1")
    task = await start_and_wait_ready(world)
    await eventually(lambda: world.music.volume == 20)
    world.session.push(
        ResponseStarted(),
        ResponseDone(calls=(call("control_music", '{"volume": 60}'),)),
    )
    await eventually(lambda: len(world.session.tool_results) == 1)
    await finish(world, task)
    await eventually(lambda: world.music.volume == 60)

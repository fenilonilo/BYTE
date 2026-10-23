from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

import pytest

from app.adapters.memory.in_memory_calendar import InMemoryCalendar
from app.adapters.memory.in_memory_climate import InMemoryClimate
from app.adapters.memory.in_memory_expenses import InMemoryExpenses
from app.adapters.memory.in_memory_light import InMemoryLight
from app.adapters.memory.in_memory_music import InMemoryMusic
from app.application.pending_actions import PendingActionStore
from app.application.registry import Registry
from app.application.tool import Tool
from app.application.tool_runner import CONFIRM_ACTION, UNKNOWN_STATE, ToolRunner
from app.application.tools.args import object_schema
from app.application.tools.catalog import build_tool_registry
from app.domain.climate import ClimateChange
from app.domain.exceptions import (
    DomainError,
    MusicError,
    MusicOfflineError,
    ToolArgumentError,
    UnknownMusicDeviceError,
    UnknownUriError,
)
from app.domain.tools import ToolCall, ToolSpec
from tests.fakes.clock import FakeClock
from tests.fakes.events import events_on_day, seed_event
from tests.fakes.logger import RecordingLogger

if TYPE_CHECKING:
    from collections.abc import Mapping

CID = "c1"


class RecordingTool(Tool):
    def __init__(
        self,
        name: str,
        *,
        segment: str = "home",
        confirm: bool = False,
        output: str = "ok",
        gate: asyncio.Event | None = None,
        error: Exception | None = None,
    ) -> None:
        self.spec = ToolSpec(name, "d", object_schema({}), segment, confirm)
        self.calls: list[tuple[Mapping[str, object], str]] = []
        self.finished = False
        self._output = output
        self._gate = gate
        self._error = error

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        self.calls.append((args, key))
        if self._gate is not None:
            await self._gate.wait()
        if self._error is not None:
            raise self._error
        self.finished = True
        return self._output

    def summarize(self, args: Mapping[str, object]) -> str:
        return f"Resumo de {self.spec.name}"


def build(
    *tools: Tool, timeout: float = 5.0, max_chars: int = 2000
) -> tuple[ToolRunner, PendingActionStore, RecordingLogger]:
    registry: Registry[Tool] = Registry()
    for tool in tools:
        registry.register(tool.spec.name, tool)
    pending = PendingActionStore(FakeClock(), ttl_seconds=60)
    log = RecordingLogger()
    runner = ToolRunner(registry, pending, log, tool_timeout=timeout, max_output_chars=max_chars)
    return runner, pending, log


def call(name: str, arguments: str = "{}", call_id: str = "call-1") -> ToolCall:
    return ToolCall(id=call_id, name=name, arguments=arguments)


@pytest.mark.unit
async def test_unknown_tool() -> None:
    runner, _, _ = build()
    result = await runner.run(call("nope"), CID, None)
    assert result.output == "erro: ferramenta desconhecida"
    assert result.call_id == "call-1"


@pytest.mark.unit
async def test_tool_outside_the_segment_filter() -> None:
    runner, _, _ = build(RecordingTool("t", segment="home"))
    result = await runner.run(call("t"), CID, "finance")
    assert result.output == "erro: ferramenta fora do segmento"


@pytest.mark.unit
@pytest.mark.parametrize("arguments", ["{not json", "[1, 2]", '"text"'])
async def test_bad_arguments_become_an_error_text(arguments: str) -> None:
    tool = RecordingTool("t")
    runner, _, _ = build(tool)
    result = await runner.run(call("t", arguments), CID, None)
    assert result.output.startswith("erro:")
    assert tool.calls == []


@pytest.mark.unit
async def test_runs_a_safe_tool_with_the_call_id_as_idempotency_key() -> None:
    tool = RecordingTool("t", output="feito")
    runner, _, _ = build(tool)
    result = await runner.run(call("t", call_id="call-9"), CID, None)
    assert result.output == "feito"
    assert tool.calls == [({}, "call-9")]


@pytest.mark.unit
async def test_output_is_truncated() -> None:
    runner, _, _ = build(RecordingTool("t", output="x" * 50), max_chars=10)
    assert (await runner.run(call("t"), CID, None)).output == "x" * 10


@pytest.mark.unit
async def test_domain_error_is_reported_to_the_model() -> None:
    runner, _, _ = build(RecordingTool("t", error=DomainError("dispositivo sumiu")))
    assert (await runner.run(call("t"), CID, None)).output == "erro: dispositivo sumiu"


@pytest.mark.unit
async def test_unexpected_error_does_not_leak_details() -> None:
    runner, _, log = build(RecordingTool("t", error=RuntimeError("senha=123")))
    result = await runner.run(call("t"), CID, None)
    assert result.output == "erro: falha interna na ferramenta"
    await runner.drain()
    assert "tool.failed" in log.names()
    assert "senha" not in repr(log.events)


@pytest.mark.unit
async def test_timeout_reports_unknown_state_and_the_tool_still_finishes() -> None:
    gate = asyncio.Event()
    tool = RecordingTool("t", gate=gate)
    runner, _, log = build(tool, timeout=0.01)
    result = await runner.run(call("t"), CID, None)
    assert result.output == UNKNOWN_STATE
    gate.set()
    await runner.drain()
    assert tool.finished is True
    assert "tool.done" in log.names()


@pytest.mark.unit
async def test_cancelling_the_caller_does_not_abort_the_tool() -> None:
    gate = asyncio.Event()
    tool = RecordingTool("t", gate=gate)
    runner, _, _ = build(tool)
    caller = asyncio.create_task(runner.run(call("t"), CID, None))
    await asyncio.sleep(0.01)
    caller.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await caller
    gate.set()
    await runner.drain()
    assert tool.finished is True


@pytest.mark.unit
async def test_sensitive_tool_is_not_executed_when_called() -> None:
    tool = RecordingTool("danger", confirm=True)
    runner, pending, _ = build(tool)
    result = await runner.run(call("danger"), CID, None)
    assert result.output.startswith("needs_confirmation:")
    assert "Resumo de danger" in result.output
    assert tool.calls == []
    assert pending.peek(CID) is not None


@pytest.mark.unit
async def test_confirmation_flow_executes_once_with_the_pending_key() -> None:
    tool = RecordingTool("danger", confirm=True, output="feito")
    runner, pending, _ = build(tool)
    await runner.run(call("danger", '{"a": 1}'), CID, None)
    action = pending.peek(CID)
    assert action is not None
    pending.on_user_utterance(CID, "sim")

    first = await runner.run(call(CONFIRM_ACTION), CID, None)
    second = await runner.run(call(CONFIRM_ACTION), CID, None)

    assert first.output == "feito"
    assert tool.calls == [({"a": 1}, action.key)]
    assert second.output == "erro: nada para confirmar"


@pytest.mark.unit
async def test_confirm_in_the_same_turn_is_refused() -> None:
    tool = RecordingTool("danger", confirm=True)
    runner, _, _ = build(tool)
    await runner.run(call("danger"), CID, None)
    result = await runner.run(call(CONFIRM_ACTION), CID, None)
    assert result.output.startswith("erro: aguarde")
    assert tool.calls == []


@pytest.mark.unit
async def test_a_negative_answer_never_executes() -> None:
    tool = RecordingTool("danger", confirm=True)
    runner, pending, _ = build(tool)
    await runner.run(call("danger"), CID, None)
    pending.on_user_utterance(CID, "não, deixa pra lá")
    result = await runner.run(call(CONFIRM_ACTION), CID, None)
    assert result.output == "erro: o usuário não confirmou"
    assert tool.calls == []


@pytest.mark.unit
async def test_confirm_with_nothing_pending() -> None:
    runner, _, _ = build()
    assert (await runner.run(call(CONFIRM_ACTION), CID, None)).output == "erro: nada para confirmar"


@pytest.mark.unit
async def test_parallel_confirm_calls_execute_once() -> None:
    tool = RecordingTool("danger", confirm=True)
    runner, pending, _ = build(tool)
    await runner.run(call("danger"), CID, None)
    pending.on_user_utterance(CID, "sim")
    results = await asyncio.gather(
        runner.run(call(CONFIRM_ACTION, call_id="a"), CID, None),
        runner.run(call(CONFIRM_ACTION, call_id="b"), CID, None),
    )
    assert len(tool.calls) == 1
    assert sorted(r.output for r in results) == ["erro: nada para confirmar", "ok"]


@pytest.mark.unit
async def test_pending_action_of_another_conversation_cannot_be_confirmed() -> None:
    tool = RecordingTool("danger", confirm=True)
    runner, pending, _ = build(tool)
    await runner.run(call("danger"), "mine", None)
    pending.on_user_utterance("other", "sim")
    result = await runner.run(call(CONFIRM_ACTION), "other", None)
    assert result.output == "erro: nada para confirmar"
    assert tool.calls == []


@pytest.mark.unit
async def test_specs_always_include_confirm_action_and_respect_the_segment() -> None:
    runner, _, _ = build(RecordingTool("a", segment="home"), RecordingTool("b", segment="agenda"))
    assert [s.name for s in runner.specs(None)] == ["a", "b", CONFIRM_ACTION]
    assert [s.name for s in runner.specs("agenda")] == ["b", CONFIRM_ACTION]
    assert runner.segments() == frozenset({"home", "agenda"})


def real_tools_runner() -> tuple[ToolRunner, PendingActionStore, InMemoryCalendar, InMemoryClimate]:
    calendar = InMemoryCalendar()
    climate = InMemoryClimate()
    registry = build_tool_registry(
        InMemoryLight(("lampada", "quarto")), climate, InMemoryMusic(), calendar, InMemoryExpenses()
    )
    pending = PendingActionStore(FakeClock())
    return ToolRunner(registry, pending, RecordingLogger()), pending, calendar, climate


@pytest.mark.unit
async def test_switching_the_air_conditioner_on_runs_at_once() -> None:
    runner, _, _, climate = real_tools_runner()
    args = '{"name": "ar-condicionado", "power": true, "target_temperature": 22}'

    done = await runner.run(call("set_climate", args), CID, None)

    state = await climate.get_state("ar-condicionado")
    assert (state.power, state.target_temperature) == (True, 22.0)
    assert done.output.startswith("ar-condicionado: ligado")


@pytest.mark.unit
async def test_adjusting_the_air_conditioner_without_switching_it_does_not_ask() -> None:
    runner, _, _, climate = real_tools_runner()
    await climate.apply("ar-condicionado", ClimateChange(power=True))

    result = await runner.run(
        call("set_climate", '{"name": "ar-condicionado", "target_temperature": 21}'), CID, None
    )

    assert not result.output.startswith("needs_confirmation:")
    assert (await climate.get_state("ar-condicionado")).target_temperature == 21.0


@pytest.mark.unit
async def test_end_to_end_with_the_real_agenda_tools() -> None:
    runner, pending, calendar, _ = real_tools_runner()
    event = await seed_event(calendar)

    asked = await runner.run(call("delete_event", f'{{"event_id": "{event.id}"}}'), CID, None)
    assert "Apagar o evento evt-1" in asked.output
    assert len(await events_on_day(calendar)) == 1

    pending.on_user_utterance(CID, "pode sim")
    done = await runner.run(call(CONFIRM_ACTION), CID, None)

    assert done.output == "Evento evt-1 apagado"
    assert await events_on_day(calendar) == ()


@pytest.mark.unit
async def test_unknown_device_from_the_model_becomes_error_text_not_a_crash() -> None:
    runner, _, _, _ = real_tools_runner()

    result = await runner.run(call("set_light", '{"name": "cofre", "power": true}'), CID, None)

    assert result.output == "erro: unknown light: 'cofre'"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (UnknownUriError("uri"), "guard"),
        (MusicOfflineError("offline"), "offline"),
        (ToolArgumentError("x"), "validation"),
        (UnknownMusicDeviceError("x"), "validation"),
        (MusicError("spotify 500"), "upstream"),
        (RuntimeError("senha=123"), "upstream"),
    ],
)
async def test_tool_failed_log_carries_a_reason_category(error: Exception, reason: str) -> None:
    runner, _, log = build(RecordingTool("t", error=error))
    await runner.run(call("t"), CID, None)
    await runner.drain()
    failed = [f for _, name, f in log.events if name == "tool.failed"]
    assert [f["reason"] for f in failed] == [reason]
    assert "senha" not in str(failed)


def panel_tool() -> RecordingTool:
    tool = RecordingTool("open_thing", segment="projects")
    tool.spec = ToolSpec("open_thing", "d", object_schema({}), "projects", panel_only=True)
    return tool


@pytest.mark.unit
def test_panel_only_hidden_from_non_panel_specs() -> None:
    runner, _, _ = build(panel_tool(), RecordingTool("t"))
    assert {s.name for s in runner.specs(None)} == {"t", CONFIRM_ACTION}


@pytest.mark.unit
def test_panel_only_listed_for_panel() -> None:
    runner, _, _ = build(panel_tool())
    assert "open_thing" in {s.name for s in runner.specs(None, panel=True)}


@pytest.mark.unit
async def test_panel_only_refused_when_not_panel() -> None:
    tool = panel_tool()
    runner, _, _ = build(tool)
    result = await runner.run(call("open_thing"), CID, None)
    assert result.output == "erro: ferramenta disponível só no painel"
    assert tool.calls == []


@pytest.mark.unit
async def test_panel_only_runs_for_panel() -> None:
    tool = panel_tool()
    runner, _, _ = build(tool)
    assert (await runner.run(call("open_thing"), CID, None, panel=True)).output == "ok"

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from app.application.use_cases.process_chat_message import ProcessChatMessage
from app.domain.entities import Message
from app.domain.exceptions import AgentError
from app.domain.model import ModelMessage, ModelTurn
from app.ports.chat_model import ChatModelPort
from tests.fakes.clock import wall
from tests.fakes.events import events_on_day, seed_event
from tests.fakes.logger import RecordingLogger
from tests.fakes.world import World, text_turn, tool_turn

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.domain.tools import ToolSpec

CID = "c1"


@pytest.mark.unit
async def test_plain_reply_is_returned_and_persisted() -> None:
    world = World([text_turn("Oi!")])
    reply = await world.chat.execute(CID, "olá", None)

    assert reply.message.role == "assistant"
    assert reply.message.content == "Oi!"
    assert reply.pending_summary is None
    stored = await world.store.recent(CID, 20)
    assert [(m.role, m.content) for m in stored] == [("user", "olá"), ("assistant", "Oi!")]
    messages, tools = world.model.calls[0]
    assert [m.role for m in messages] == ["system", "user"]
    assert "confirm_action" in [t.name for t in tools]


@pytest.mark.unit
async def test_tool_loop_feeds_results_back_but_never_persists_them() -> None:
    world = World([tool_turn("list_lights"), text_turn("A lâmpada está desligada.")])
    reply = await world.chat.execute(CID, "o que está ligado?", None)

    assert reply.message.content == "A lâmpada está desligada."
    second_call_messages, _ = world.model.calls[1]
    assert [m.role for m in second_call_messages] == ["system", "user", "assistant", "tool"]
    assert second_call_messages[-1].content == (
        "lampada: desligada, modo white, brilho 100%, temperatura de cor 50%"
    )
    assert second_call_messages[-1].tool_call_id == "call-1"
    stored = await world.store.recent(CID, 20)
    assert [m.role for m in stored] == ["user", "assistant"]


@pytest.mark.unit
async def test_only_the_last_n_messages_reach_the_model() -> None:
    world = World([text_turn("ok")], history_limit=20)
    now = datetime.now(tz=UTC)
    old = [Message(id=f"m{i}", role="user", content=f"old {i}", timestamp=now) for i in range(30)]
    await world.store.append(CID, old)

    await world.chat.execute(CID, "novo", None)

    messages, _ = world.model.calls[0]
    assert len(messages) == 1 + 20 + 1
    assert messages[1].content == "old 10"
    assert messages[-1].content == "novo"


@pytest.mark.unit
async def test_segment_filter_limits_the_tools_offered() -> None:
    world = World([text_turn("ok")])
    await world.chat.execute(CID, "oi", "finance")
    _, tools = world.model.calls[0]
    assert {t.segment for t in tools} == {"finance", "*"}


@pytest.mark.unit
async def test_step_limit_raises_agent_error() -> None:
    world = World([tool_turn("list_lights") for _ in range(3)], max_steps=3)
    with pytest.raises(AgentError, match="step limit"):
        await world.chat.execute(CID, "oi", None)
    assert await world.store.recent(CID, 20) == ()


@pytest.mark.unit
async def test_empty_model_text_raises_agent_error() -> None:
    world = World([text_turn("   ")])
    with pytest.raises(AgentError, match="no text"):
        await world.chat.execute(CID, "oi", None)


@pytest.mark.unit
async def test_timeout_raises_agent_error() -> None:
    class Hanging(ChatModelPort):
        async def complete(
            self, messages: Sequence[ModelMessage], tools: Sequence[ToolSpec]
        ) -> ModelTurn:
            await asyncio.sleep(10)
            return ModelTurn(text="never")

    world = World([], timeout_seconds=0.01)
    chat = ProcessChatMessage(
        Hanging(),
        world.store,
        world.runner,
        world.pending,
        RecordingLogger(),
        clock=wall,
        timeout_seconds=0.01,
    )
    with pytest.raises(AgentError, match="timed out"):
        await chat.execute(CID, "oi", None)


DELETE = '{"event_id": "evt-1"}'


@pytest.mark.unit
async def test_confirmation_round_trip_across_two_requests() -> None:
    world = World(
        [
            tool_turn("delete_event", DELETE),
            text_turn("Apagar o evento evt-1. Posso?"),
            tool_turn("confirm_action", call_id="call-2"),
            text_turn("Pronto, apaguei."),
        ]
    )
    await seed_event(world.calendar)

    first = await world.chat.execute(CID, "apaga o dentista", None)
    assert first.pending_summary == "Apagar o evento evt-1"
    assert len(await events_on_day(world.calendar)) == 1

    second = await world.chat.execute(CID, "sim", None)
    assert second.pending_summary is None
    assert await events_on_day(world.calendar) == ()
    system_prompt = world.model.calls[2][0][0].content
    assert "Apagar o evento evt-1" in system_prompt


@pytest.mark.unit
async def test_an_unrelated_message_in_between_cancels_the_pending_action() -> None:
    world = World(
        [
            tool_turn("delete_event", DELETE),
            text_turn("Apagar o evento evt-1. Posso?"),
            text_turn("São três horas."),
            tool_turn("confirm_action", call_id="call-2"),
            text_turn("Não há nada para confirmar."),
        ]
    )
    await seed_event(world.calendar)
    await world.chat.execute(CID, "apaga o dentista", None)
    await world.chat.execute(CID, "que horas são", None)
    await world.chat.execute(CID, "sim", None)

    assert len(await events_on_day(world.calendar)) == 1
    tool_message = world.model.calls[4][0][-1]
    assert tool_message.role == "tool"
    assert tool_message.content == "erro: nada para confirmar"


@pytest.mark.unit
async def test_the_model_cannot_confirm_in_the_same_request() -> None:
    world = World(
        [
            tool_turn("delete_event", DELETE),
            tool_turn("confirm_action", call_id="call-2"),
            text_turn("Apagar o evento evt-1. Posso?"),
        ]
    )
    await seed_event(world.calendar)
    reply = await world.chat.execute(CID, "apaga o dentista", None)

    assert len(await events_on_day(world.calendar)) == 1
    assert reply.pending_summary == "Apagar o evento evt-1"
    refused: ModelMessage = world.model.calls[2][0][-1]
    assert refused.content.startswith("erro: aguarde")


@pytest.mark.unit
async def test_system_prompt_tells_the_model_the_current_time() -> None:
    world = World([text_turn("oi")])
    await world.chat.execute(CID, "que horas são?", None)
    assert "Agora: 2026-10-21T12:00+00:00, quarta-feira." in world.model.calls[0][0][0].content


@pytest.mark.unit
async def test_system_prompt_names_the_projects() -> None:
    world = World([text_turn("oi")], projects=("FinFlow",))
    await world.chat.execute(CID, "oi", None)
    assert "Projetos: FinFlow." in world.model.calls[0][0][0].content

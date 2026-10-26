from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from app.application.claude_bridge import ClaudeBridge
from app.application.lynus import COMPACT_AT, Lynus, LynusLimits, LynusListener
from app.application.project_session import ProjectSession
from app.domain.exceptions import (
    AgentError,
    LynusBusyError,
    ProjectNotTrustedError,
    UnknownProjectError,
)
from app.domain.lynus import LynusPhase
from app.domain.model import ModelMessage, ModelTurn
from app.domain.projects import Project
from app.domain.tools import ToolCall
from app.ports.chat_model import ChatModelPort
from app.ports.documents import DocumentSourcePort
from tests.fakes.chat_model import ScriptedChatModel
from tests.fakes.clock import wall
from tests.fakes.logger import RecordingLogger
from tests.fakes.terminal import FakeTerminal

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from app.domain.tools import ToolSpec

ROOT = "D:/P/Byte"
PROJECT = Project("Byte", ROOT, ("CLAUDE.md",))
PASTE_START, PASTE_END = b"\x1b[200~", b"\x1b[201~"


class Docs(DocumentSourcePort):
    def __init__(self) -> None:
        self.files = {
            str(Path(ROOT) / "CLAUDE.md"): "# Byte\nhexagonal",
            str(Path(ROOT) / "docs/spec.md"): "spec body",
        }

    async def reachable(self, root: str) -> bool:
        return True

    async def read(self, path: str) -> str | None:
        return self.files.get(path)


class Recorder(LynusListener):
    def __init__(self) -> None:
        self.count = 0

    async def changed(self) -> None:
        self.count += 1


class FailingModel(ChatModelPort):
    async def complete(
        self, messages: Sequence[ModelMessage], tools: Sequence[ToolSpec]
    ) -> ModelTurn:
        raise AgentError("down")


def call(name: str, **args: object) -> ToolCall:
    return ToolCall(id=f"c-{name}", name=name, arguments=json.dumps(args))


def text(content: str) -> ModelTurn:
    return ModelTurn(text=content)


def tool(name: str, **args: object) -> ModelTurn:
    return ModelTurn(text="", tool_calls=(call(name, **args),))


class World:
    def __init__(self, turns: Sequence[ModelTurn], limits: LynusLimits | None = None) -> None:
        self.model = ScriptedChatModel(turns)
        self.terminal = FakeTerminal()
        self.log = RecordingLogger()
        self.bridge = ClaudeBridge("http://x/hooks", self.log)
        self.session = ProjectSession(
            self.terminal, [PROJECT], ["claude"], {}, self.log, bridge=(self.bridge, "h.json")
        )
        self.listener = Recorder()
        self.lynus = Lynus(
            self.model,
            self.session,
            self.bridge,
            Docs(),
            [PROJECT],
            log=self.log,
            clock=wall,
            limits=limits or LynusLimits(paste_delay=0),
        )
        self.lynus.attach(self.listener)

    def prompts(self) -> list[str]:
        out: list[str] = []
        for chunk in self.terminal.written:
            if chunk.startswith(PASTE_START):
                out.append(chunk.removeprefix(PASTE_START).removesuffix(PASTE_END).decode())
        return out

    def notes(self, role: str) -> list[str]:
        return [n.text for n in self.lynus.view().notes if n.role == role]

    async def stop_hook(self, message: str) -> None:
        await self.bridge.hook({"hook_event_name": "Stop", "last_assistant_message": message})

    async def close(self) -> None:
        await self.lynus.aclose()
        await self.session.aclose()


async def until(condition: Callable[[], bool]) -> None:
    for _ in range(500):
        if condition():
            return
        await asyncio.sleep(0)
    raise AssertionError("condition never held")


def tool_names(world: World, index: int) -> set[str]:
    return {spec.name for spec in world.model.calls[index][1]}


@pytest.mark.unit
async def test_start_opens_a_strict_session_and_lynus_asks_the_owner() -> None:
    w = World([text("Qual o critério de pronto?")])
    await w.lynus.start("Byte", "adicionar logs")
    await until(lambda: bool(w.notes("lynus")))
    _, argv, _ = w.terminal.started[0]
    assert argv[-2:] == ("--permission-mode", "default")
    assert w.lynus.view().phase is LynusPhase.BRIEFING
    assert w.notes("lynus") == ["Qual o critério de pronto?"]
    assert tool_names(w, 0) == {"read_file", "begin_work"}
    first = w.model.calls[0][0][1].content
    assert "adicionar logs" in first
    assert "hexagonal" in first
    assert w.listener.count > 0
    await w.close()


@pytest.mark.unit
async def test_start_refuses_an_unknown_project() -> None:
    w = World([])
    with pytest.raises(UnknownProjectError):
        await w.lynus.start("Nope", "x")
    assert w.lynus.view().phase is LynusPhase.OFF
    await w.close()


@pytest.mark.unit
async def test_owner_talks_during_briefing() -> None:
    w = World([text("Pergunta 1?"), text("Entendi.")])
    await w.lynus.start("Byte", "t")
    await until(lambda: len(w.notes("lynus")) == 1)
    await w.lynus.say("só o backend")
    await until(lambda: len(w.notes("lynus")) == 2)
    assert w.notes("owner")[-1] == "só o backend"
    assert w.model.calls[1][0][-1] == ModelMessage(role="user", content="só o backend")
    await w.close()


@pytest.mark.unit
async def test_say_is_refused_when_lynus_is_not_active() -> None:
    w = World([])
    with pytest.raises(LynusBusyError):
        await w.lynus.say("oi")
    await w.close()


@pytest.mark.unit
async def test_begin_work_types_the_brief_and_takes_over_permissions() -> None:
    w = World([text("Ok?"), tool("begin_work", brief="Faça X.\nCom testes.")])
    await w.lynus.start("Byte", "t")
    await until(lambda: bool(w.notes("lynus")))
    await w.lynus.say("pode começar")
    await until(lambda: w.terminal.written[-1:] == [b"\r"])
    assert w.lynus.view().phase is LynusPhase.WORKING
    assert w.prompts() == ["Faça X.\nCom testes."]
    assert w.terminal.written[-1] == b"\r"
    assert w.bridge.pilot is not None
    assert w.notes("claude") == ["Faça X.\nCom testes."]
    await w.close()


async def working(w: World) -> None:
    await w.lynus.start("Byte", "t")
    await until(lambda: len(w.prompts()) == 1)


@pytest.mark.unit
async def test_turn_end_reviewed_then_next_prompt_then_finish() -> None:
    w = World(
        [
            tool("begin_work", brief="brief"),
            tool("send_to_claude", text="rode os testes"),
            tool("finish", summary="Feito, testes verdes."),
        ]
    )
    await working(w)
    await w.stop_hook("implementei")
    await until(lambda: len(w.prompts()) == 2)
    review = w.model.calls[1][0][-1].content
    assert "implementei" in review
    assert tool_names(w, 1) == {"read_file", "send_to_claude", "finish"}
    await w.stop_hook("12 passed")
    await until(lambda: w.lynus.view().phase is LynusPhase.DONE)
    assert w.prompts() == ["brief", "rode os testes"]
    assert w.notes("lynus")[-1] == "Feito, testes verdes."
    assert w.bridge.pilot is None
    await w.close()


@pytest.mark.unit
async def test_no_decision_after_a_nudge_fails() -> None:
    w = World([tool("begin_work", brief="b"), text("hmm"), text("ainda pensando")])
    await working(w)
    await w.stop_hook("feito")
    await until(lambda: w.lynus.view().phase is LynusPhase.FAILED)
    assert w.bridge.pilot is None
    await w.close()


@pytest.mark.unit
async def test_turn_budget_stops_lynus() -> None:
    w = World(
        [tool("begin_work", brief="b"), tool("send_to_claude", text="mais")],
        LynusLimits(max_turns=1, paste_delay=0),
    )
    await working(w)
    await w.stop_hook("feito")
    await until(lambda: w.lynus.view().phase is LynusPhase.STOPPED)
    assert w.prompts() == ["b"]
    assert "limite" in w.notes("system")[-1]
    await w.close()


@pytest.mark.unit
async def test_a_turn_that_never_ends_fails() -> None:
    w = World([tool("begin_work", brief="b")], LynusLimits(turn_seconds=0.01, paste_delay=0))
    await working(w)
    for _ in range(200):
        if w.lynus.view().phase is LynusPhase.FAILED:
            break
        await asyncio.sleep(0.005)
    assert w.lynus.view().phase is LynusPhase.FAILED
    await w.close()


@pytest.mark.unit
async def test_closing_the_session_fails_the_task() -> None:
    w = World([tool("begin_work", brief="b")])
    await working(w)
    await w.session.close()
    await until(lambda: w.lynus.view().phase is LynusPhase.FAILED)
    await w.close()


@pytest.mark.unit
async def test_stop_interrupts_claude_and_drops_the_pilot() -> None:
    w = World([tool("begin_work", brief="b")])
    await working(w)
    phase = await w.lynus.stop()
    assert phase is LynusPhase.STOPPED
    assert w.terminal.written[-1] == b"\x1b"
    assert w.bridge.pilot is None
    await w.stop_hook("tarde demais")
    await asyncio.sleep(0)
    assert w.lynus.view().phase is LynusPhase.STOPPED
    await w.close()


@pytest.mark.unit
async def test_owner_message_while_working_can_steer_claude_at_once() -> None:
    w = World([tool("begin_work", brief="b"), tool("send_to_claude", text="use Postgres")])
    await working(w)
    await w.lynus.say("troque para Postgres")
    await until(lambda: len(w.prompts()) == 2)
    assert w.model.calls[1][0][-1].content == "Mensagem do dono: troque para Postgres"
    await w.close()


@pytest.mark.unit
async def test_read_file_stays_inside_the_project() -> None:
    w = World(
        [
            tool("read_file", path="docs/spec.md"),
            tool("read_file", path="../secret.txt"),
            tool("read_file", path="nada.md"),
            text("li"),
        ]
    )
    await w.lynus.start("Byte", "t")
    await until(lambda: bool(w.notes("lynus")))
    outputs = [m.content for m in w.model.calls[3][0] if m.role == "tool"]
    assert outputs == [
        "spec body",
        "erro: caminho fora do projeto",
        "arquivo não encontrado",
    ]
    await w.close()


@pytest.mark.unit
async def test_pilot_answers_claude_questions_with_the_model() -> None:
    w = World([tool("begin_work", brief="b"), text("Use a opção A.")])
    await working(w)
    pilot = w.bridge.pilot
    assert pilot is not None
    assert await pilot('{"questions": []}') == "Use a opção A."
    await w.close()


@pytest.mark.unit
async def test_model_failure_is_reported_without_changing_phase() -> None:
    w = World([])
    w.lynus = Lynus(FailingModel(), w.session, w.bridge, Docs(), [PROJECT], log=w.log, clock=wall)
    await w.lynus.start("Byte", "t")
    await until(lambda: bool(w.notes("system")[1:]))
    assert w.lynus.view().phase is LynusPhase.BRIEFING
    await w.close()


@pytest.mark.unit
async def test_long_transcripts_are_compacted_keeping_the_brief() -> None:
    turns = [text(f"r{i}") for i in range(30)]
    w = World(turns)
    await w.lynus.start("Byte", "tarefa-original")
    await until(lambda: len(w.notes("lynus")) == 1)
    for i in range(29):
        await w.lynus.say(f"m{i}")
        await until(lambda i=i: len(w.notes("lynus")) == i + 2)
    sent = w.model.calls[-1][0]
    assert len(sent) <= COMPACT_AT + 2  # system + brief + at most COMPACT_AT messages
    assert "tarefa-original" in sent[1].content
    assert sent[2].role == "user"
    assert sent[2].tool_call_id is None
    await w.close()


@pytest.mark.unit
async def test_logs_hold_no_content() -> None:
    w = World([tool("begin_work", brief="segredo-do-brief")])
    await working(w)
    assert "segredo" not in repr(w.log.events)
    assert "lynus.started" in w.log.names()
    await w.close()


TRUST_FILE = "C:/Users/o/.claude.json"


def with_trust(state: str | None) -> World:
    w = World([text("Oi?")])
    docs = Docs()
    if state is not None:
        docs.files[TRUST_FILE] = state
    w.lynus = Lynus(
        w.model,
        w.session,
        w.bridge,
        docs,
        [PROJECT],
        log=w.log,
        clock=wall,
        limits=LynusLimits(paste_delay=0),
        trust_file=TRUST_FILE,
    )
    return w


@pytest.mark.unit
async def test_an_untrusted_folder_is_refused_before_claude_starts() -> None:
    w = with_trust(json.dumps({"projects": {"D:/P/Other": {"hasTrustDialogAccepted": True}}}))
    with pytest.raises(ProjectNotTrustedError, match="Yes, I trust this folder"):
        await w.lynus.start("Byte", "t")
    assert w.terminal.started == []
    assert w.lynus.view().phase is LynusPhase.OFF
    await w.close()


@pytest.mark.unit
@pytest.mark.parametrize(
    "state",
    [
        json.dumps({"projects": {r"d:\p\byte" + "\\": {"hasTrustDialogAccepted": True}}}),
        None,  # no Claude state file: do not guess, go on
        "not json",
        json.dumps({"other": 1}),
    ],
)
async def test_trusted_or_unknown_trust_starts(state: str | None) -> None:
    w = with_trust(state)
    await w.lynus.start("Byte", "t")
    assert w.lynus.view().phase is LynusPhase.BRIEFING
    await w.close()

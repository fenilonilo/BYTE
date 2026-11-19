from __future__ import annotations

import asyncio
import contextlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from app.application.prompts import LYNUS_PROMPT, now_line
from app.application.tools.args import object_schema, str_arg
from app.domain.exceptions import (
    DomainError,
    LynusBusyError,
    ProjectNotTrustedError,
    UnknownProjectError,
)
from app.domain.lynus import LynusNote, LynusPhase
from app.domain.model import ModelMessage
from app.domain.projects import is_inside
from app.domain.tools import ToolSpec

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Mapping, Sequence
    from datetime import datetime

    from app.application.claude_bridge import ClaudeBridge
    from app.application.project_session import ProjectSession
    from app.domain.projects import Project
    from app.domain.tools import ToolCall
    from app.ports.chat_model import ChatModelPort
    from app.ports.documents import DocumentSourcePort
    from app.ports.logger import LoggerPort

STRICT_PERMISSIONS = ("--permission-mode", "default")  # every request reaches the hook
INTERRUPT = b"\x1b"
PASTE_START, PASTE_END = b"\x1b[200~", b"\x1b[201~"
CLAUDE_MD_CHARS = 6000
FILE_CHARS = 20000
CLAUDE_REPLY_CHARS = 8000
MAX_STEPS = 8  # model calls per decision, so a chain of read_file cannot run away
COMPACT_AT, COMPACT_TO = 40, 30
QUESTION_SECONDS = 90.0  # under the hook's 120 s
NUDGE = "Decida agora: chame send_to_claude com o próximo prompt ou finish se acabou."
FALLBACK_ANSWER = "Siga a opção recomendada e registre a escolha."

_TOOL = "lynus"
READ_FILE = ToolSpec(
    "read_file",
    "Lê um arquivo do projeto (caminho relativo à pasta do projeto).",
    object_schema({"path": ("string", "Caminho relativo, ex.: docs/superpowers/plans/x.md")}),
    _TOOL,
)
BEGIN_WORK = ToolSpec(
    "begin_work",
    "Encerra a conversa com o dono e começa o trabalho: envia o brief ao Claude.",
    object_schema({"brief": ("string", "O brief completo para o Claude.")}),
    _TOOL,
)
SEND = ToolSpec(
    "send_to_claude",
    "Envia o próximo prompt ao Claude Code.",
    object_schema({"text": ("string", "O prompt.")}),
    _TOOL,
)
FINISH = ToolSpec(
    "finish",
    "Encerra a tarefa, que está pronta e verificada.",
    object_schema({"summary": ("string", "Resumo para o dono: o que foi feito e verificado.")}),
    _TOOL,
)
BRIEF_TOOLS = (READ_FILE, BEGIN_WORK)
WORK_TOOLS = (READ_FILE, SEND, FINISH)


class LynusListener(ABC):
    """The panel's push socket (a WebSocket in production)."""

    @abstractmethod
    async def changed(self) -> None:
        """Lynus's phase or notes changed. Must not raise."""


@dataclass(frozen=True, slots=True)
class LynusLimits:
    max_turns: int = 40
    turn_seconds: float = 1800.0
    paste_delay: float = 0.3  # the TUI takes a paste and its Enter as one prompt only apart
    max_notes: int = 200


@dataclass(frozen=True, slots=True)
class LynusView:
    phase: LynusPhase
    project: str | None
    task: str
    turns: int
    notes: tuple[LynusNote, ...]


def _args(call: ToolCall) -> Mapping[str, object]:
    try:
        parsed: object = json.loads(call.arguments or "{}")
    except json.JSONDecodeError:
        return {}
    return cast("dict[str, object]", parsed) if isinstance(parsed, dict) else {}


def _folder(path: str) -> str:
    return path.replace("\\", "/").rstrip("/").casefold()


class Lynus:
    """The agent that drives Claude Code on its own once the owner hands it a task.

    It is not one of Byte's tools: it has its own model, prompt, tools and transcript.
    Eight public members on purpose: Byte's tools start it, the panel talks to it, stops it,
    reads it and listens to it, and the lifespan closes it."""

    def __init__(
        self,
        model: ChatModelPort,
        session: ProjectSession,
        bridge: ClaudeBridge,
        documents: DocumentSourcePort,
        projects: Sequence[Project],
        *,
        log: LoggerPort,
        clock: Callable[[], datetime],
        limits: LynusLimits | None = None,
        trust_file: str | None = None,
    ) -> None:
        """`trust_file`: Claude Code's own state file, read only, to see the folders it trusts."""
        self._model = model
        self._session = session
        self._bridge = bridge
        self._documents = documents
        self._projects = {p.name: p for p in projects}
        self._log = log
        self._clock = clock
        self._limits = limits or LynusLimits()
        self._trust_file = trust_file
        self._phase = LynusPhase.OFF
        self._project: Project | None = None
        self._task = ""
        self._turns = 0
        self._notes: list[LynusNote] = []
        self._history: list[ModelMessage] = []
        self._listener: LynusListener | None = None
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task[None]] = set()

    def view(self) -> LynusView:
        name = self._project.name if self._project else None
        return LynusView(self._phase, name, self._task, self._turns, tuple(self._notes))

    def status(self) -> str:
        if self._project is None:
            return "o Lynus não está com nenhuma tarefa"
        said = next((n.text for n in reversed(self._notes) if n.role != "owner"), "")
        return f"{self._phase.value} em {self._project.name}: {said[:400]}"

    def attach(self, listener: LynusListener) -> None:
        self._listener = listener

    def detach(self, listener: LynusListener) -> None:
        if self._listener is listener:
            self._listener = None

    async def start(self, project: str, task: str) -> None:
        chosen = self._projects.get(project)
        if chosen is None:
            raise UnknownProjectError(f"projeto desconhecido; válidos: {', '.join(self._projects)}")
        if not await self._trusted(chosen):
            raise ProjectNotTrustedError(
                f"o Claude Code ainda não confia na pasta de {chosen.name}: abra o projeto no "
                "painel, escolha 'Yes, I trust this folder' e chame o Lynus de novo"
            )
        await self._halt()
        await self._session.open(chosen.name, STRICT_PERMISSIONS)
        guide = await self._read(chosen, "CLAUDE.md") or "(sem CLAUDE.md)"
        self._project, self._task, self._turns = chosen, task, 0
        self._notes = []
        self._history = [
            ModelMessage(
                role="user",
                content=(
                    f"Projeto: {chosen.name}. Tarefa do dono: {task}\n\n"
                    f"CLAUDE.md do projeto (trecho):\n{guide[:CLAUDE_MD_CHARS]}"
                ),
            )
        ]
        self._log.info("lynus.started", project=chosen.name)
        await self._set_phase(LynusPhase.BRIEFING)
        await self._note("system", f"Lynus assumiu {chosen.name}.")
        await self._note("owner", task)
        self._spawn(self._turn(None, BRIEF_TOOLS))

    async def say(self, text: str) -> None:
        if not self._phase.active:
            raise LynusBusyError("o Lynus não está com uma tarefa ativa")
        await self._note("owner", text)
        if self._phase is LynusPhase.WORKING:
            self._spawn(self._turn(f"Mensagem do dono: {text}", WORK_TOOLS))
        else:
            self._spawn(self._turn(text, BRIEF_TOOLS))

    async def stop(self) -> LynusPhase:
        if not self._phase.active:
            return self._phase
        await self._halt()
        if self._session.current is not None:
            await self._session.write(INTERRUPT)
        await self._finish(LynusPhase.STOPPED, "Parado pelo dono.")
        return self._phase

    async def aclose(self) -> None:
        await self._halt()

    async def _trusted(self, project: Project) -> bool:
        """An untrusted folder opens on Claude's trust dialog, whose default answer exits, and
        Lynus never types into dialogs. Unknown state (no file, other format) is not a no."""
        if self._trust_file is None:
            return True
        try:
            state: object = json.loads(await self._documents.read(self._trust_file) or "null")
        except (DomainError, ValueError):
            return True
        folders = (
            cast("dict[str, object]", state).get("projects") if isinstance(state, dict) else None
        )
        if not isinstance(folders, dict):
            return True
        wanted = _folder(project.path)
        return any(
            _folder(path) == wanted
            and isinstance(entry, dict)
            and cast("dict[str, object]", entry).get("hasTrustDialogAccepted") is True
            for path, entry in cast("dict[str, object]", folders).items()
        )

    async def _halt(self) -> None:
        self._bridge.pilot = None
        tasks = [t for t in self._tasks if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    def _spawn(self, coro: Coroutine[object, object, None]) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _turn(self, text: str | None, tools: Sequence[ToolSpec]) -> None:
        async with self._lock:
            if not self._phase.active:
                return
            if text is not None:
                self._history.append(ModelMessage(role="user", content=text))
            await self._decide(tools)

    async def _work(self) -> None:
        while self._phase is LynusPhase.WORKING:
            last = await self._bridge.next_turn(self._limits.turn_seconds)
            if self._phase is not LynusPhase.WORKING:
                return
            if last is None:
                ended = self._session.current is None
                reason = "a sessão do Claude terminou" if ended else "o Claude não terminou o turno"
                await self._finish(LynusPhase.FAILED, f"Parei: {reason}.")
                return
            async with self._lock:
                reply = last[:CLAUDE_REPLY_CHARS]
                content = f"Claude terminou o turno. Última mensagem:\n{reply}"
                self._history.append(ModelMessage(role="user", content=content))
                if await self._decide(WORK_TOOLS) or self._phase is not LynusPhase.WORKING:
                    continue
                self._history.append(ModelMessage(role="user", content=NUDGE))
                if not await self._decide(WORK_TOOLS) and self._phase is LynusPhase.WORKING:
                    await self._finish(LynusPhase.FAILED, "Parei: não decidi o próximo passo.")

    async def _decide(self, tools: Sequence[ToolSpec]) -> bool:
        """Model calls until a text reply or an action. True when Lynus acted on Claude."""
        try:
            for _ in range(MAX_STEPS):
                self._compact()
                turn = await self._model.complete(self._messages(), tools)
                self._history.append(
                    ModelMessage(role="assistant", content=turn.text, tool_calls=turn.tool_calls)
                )
                if turn.text.strip():
                    await self._note("lynus", turn.text.strip())
                if not turn.tool_calls:
                    return False
                acted = False
                for call in turn.tool_calls:
                    output, did = await self._run(call, tools)
                    acted = acted or did
                    self._history.append(
                        ModelMessage(role="tool", content=output, tool_call_id=call.id)
                    )
                if acted:
                    return True
        except DomainError as exc:
            self._log.warning("lynus.model_failed", error=type(exc).__name__)
            await self._note("system", "O modelo do Lynus não respondeu; tente de novo.")
        return False

    async def _run(self, call: ToolCall, tools: Sequence[ToolSpec]) -> tuple[str, bool]:
        if call.name not in {t.name for t in tools}:
            return "erro: ferramenta indisponível agora", False
        args = _args(call)
        try:
            if call.name == READ_FILE.name:
                return await self._read_file(str_arg(args, "path")), False
            if call.name == BEGIN_WORK.name:
                await self._begin(str_arg(args, "brief"))
                return "trabalho iniciado: o Claude recebeu o brief", True
            if call.name == SEND.name:
                await self._send(str_arg(args, "text"))
                return "enviado ao Claude", True
            await self._finish(LynusPhase.DONE, str_arg(args, "summary"), role="lynus")
            return "tarefa encerrada", True
        except DomainError as exc:
            return f"erro: {exc}", False

    async def _read_file(self, path: str) -> str:
        assert self._project is not None  # only reachable while a task is active
        if not is_inside(path):
            return "erro: caminho fora do projeto"
        content = await self._read(self._project, path)
        return "arquivo não encontrado" if content is None else content[:FILE_CHARS]

    async def _read(self, project: Project, path: str) -> str | None:
        return await self._documents.read(str(Path(project.path) / path))

    async def _begin(self, brief: str) -> None:
        await self._set_phase(LynusPhase.WORKING)
        self._bridge.pilot = self._answer
        await self._send(brief)
        self._spawn(self._work())

    async def _send(self, text: str) -> None:
        if self._turns >= self._limits.max_turns:
            await self._finish(LynusPhase.STOPPED, "Parei: limite de turnos atingido.")
            return
        self._turns += 1
        self._bridge.clear()
        clean = text.replace("\x1b", "")
        await self._session.write(PASTE_START + clean.encode() + PASTE_END)
        await asyncio.sleep(self._limits.paste_delay)
        await self._session.write(b"\r")
        self._log.info("lynus.prompt_sent", turn=self._turns)
        await self._note("claude", clean)

    async def _answer(self, question: str) -> str:
        """The pilot: Lynus answers Claude's multiple-choice question as the owner would."""
        ask = ModelMessage(
            role="user",
            content=(
                f"O Claude fez esta pergunta (AskUserQuestion): {question}\n"
                "Responda como o dono, em uma frase curta, escolhendo entre as opções."
            ),
        )
        try:
            turn = await asyncio.wait_for(
                self._model.complete([*self._messages(), ask], ()), QUESTION_SECONDS
            )
        except (TimeoutError, DomainError):
            return FALLBACK_ANSWER
        answer = turn.text.strip() or FALLBACK_ANSWER
        await self._note("lynus", f"Respondi ao Claude: {answer}")
        return answer

    async def _finish(
        self, phase: LynusPhase, text: str, role: Literal["lynus", "system"] = "system"
    ) -> None:
        self._bridge.pilot = None
        await self._set_phase(phase)
        await self._note(role, text)

    def _messages(self) -> list[ModelMessage]:
        system = f"{LYNUS_PROMPT} {now_line(self._clock())}"
        return [ModelMessage(role="system", content=system), *self._history]

    def _compact(self) -> None:
        """Keep the brief and a recent tail that starts at a plain owner/Claude message."""
        if len(self._history) <= COMPACT_AT:
            return
        tail = self._history[-COMPACT_TO:]
        while tail and (tail[0].role != "user" or tail[0].tool_call_id is not None):
            tail.pop(0)
        self._history = [self._history[0], *tail]

    async def _set_phase(self, phase: LynusPhase) -> None:
        self._phase = phase
        self._log.info("lynus.phase", phase=phase.value, turns=self._turns)
        await self._changed()

    async def _note(self, role: Literal["owner", "lynus", "claude", "system"], text: str) -> None:
        self._notes.append(LynusNote(role, text, self._clock()))
        del self._notes[: max(0, len(self._notes) - self._limits.max_notes)]
        await self._changed()

    async def _changed(self) -> None:
        if self._listener is not None:
            with contextlib.suppress(Exception):  # a dead panel link must not stop the work
                await self._listener.changed()

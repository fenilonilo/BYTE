from __future__ import annotations

import asyncio
import contextlib
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from app.domain.exceptions import UnknownProjectError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from app.domain.projects import Project
    from app.ports.logger import LoggerPort
    from app.ports.terminal import ProjectTerminalPort

DEFAULT_SIZE = (120, 30)
PROVIDER_KEYS = frozenset({"OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"})
# Markers of a parent `claude` session (Byte started from inside Claude Code). Inherited, they
# make the new session think it is a child and hand it the parent's messaging token.
CLAUDE_SESSION_KEYS = frozenset(
    {
        "CLAUDECODE",
        "CLAUDE_PID",
        "CLAUDE_EFFORT",
        "CLAUDE_CODE_CHILD_SESSION",
        "CLAUDE_CODE_ENTRYPOINT",
        "CLAUDE_CODE_EXECPATH",
    }
)
CLAUDE_SESSION_PREFIXES = ("CLAUDE_CODE_SESSION_", "CLAUDE_CODE_MESSAGING_")


def _secret_or_inherited(name: str) -> bool:
    key = name.upper()
    return (
        key.startswith(("BYTE_", *CLAUDE_SESSION_PREFIXES))
        or key in PROVIDER_KEYS
        or key in CLAUDE_SESSION_KEYS
    )


def child_env(environ: Mapping[str, str]) -> dict[str, str]:
    """The server's environment minus Byte's secrets and any parent Claude session's markers."""
    return {k: v for k, v in environ.items() if not _secret_or_inherited(k)}


class TerminalListener(ABC):
    """The panel's terminal socket (a WebSocket in production)."""

    @abstractmethod
    async def state(self, project: str | None) -> None:
        """Which project is open now. Must not raise."""

    @abstractmethod
    async def output(self, data: bytes) -> None:
        """Raw terminal output. Must not raise."""


class ProjectSession:
    """The one `claude` process of the open project, owned by the server, not by a browser tab.

    Seven public members on purpose: it is the single seam the tools, the socket and the
    lifespan share (open/close for tools, attach/write/resize for the socket, aclose)."""

    def __init__(
        self,
        terminal: ProjectTerminalPort,
        projects: Sequence[Project],
        command: Sequence[str],
        environ: Mapping[str, str],
        log: LoggerPort,
        *,
        scrollback: int = 262144,
    ) -> None:
        self._terminal = terminal
        self._projects = {p.name: p for p in projects}
        self._command = tuple(command)
        self._env = child_env(environ)
        self._log = log
        self._limit = scrollback
        self._buffer = bytearray()
        self._listeners: list[TerminalListener] = []
        self._current: str | None = None
        self._reader: asyncio.Task[None] | None = None
        self._size = DEFAULT_SIZE
        self._lock = asyncio.Lock()

    @property
    def current(self) -> str | None:
        return self._current

    async def open(self, name: str) -> None:
        """Always a fresh `claude`: whatever was open is stopped first."""
        project = self._projects.get(name)
        if project is None:
            raise UnknownProjectError(f"projeto desconhecido; válidos: {', '.join(self._projects)}")
        async with self._lock:
            await self._stop()
            await self._terminal.start(project.path, self._command, self._env, *self._size)
            self._current = name
            self._reader = asyncio.create_task(self._pump(name))
        self._log.info("project.opened", project=name)
        await self._broadcast_state()

    async def close(self) -> bool:
        async with self._lock:
            name = self._current
            if name is None:
                return False
            await self._stop()
        self._log.info("project.closed", project=name)
        await self._broadcast_state()
        return True

    async def attach(self, listener: TerminalListener) -> None:
        self._listeners.append(listener)
        await listener.state(self._current)
        if self._current is not None and self._buffer:
            await listener.output(bytes(self._buffer))

    def detach(self, listener: TerminalListener) -> None:
        with contextlib.suppress(ValueError):
            self._listeners.remove(listener)

    async def write(self, data: bytes) -> None:
        if self._current is not None:
            await self._terminal.write(data)

    async def resize(self, cols: int, rows: int) -> None:
        self._size = (cols, rows)
        if self._current is not None:
            await self._terminal.resize(cols, rows)

    async def aclose(self) -> None:
        async with self._lock:
            await self._stop()

    async def _stop(self) -> None:
        """Stop the process without telling anyone; callers broadcast the new state."""
        reader, self._reader = self._reader, None
        if reader is not None:
            reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reader
        if self._current is not None:
            await self._terminal.stop()
        self._current = None
        self._buffer.clear()

    async def _pump(self, name: str) -> None:
        # read even with nobody attached: a full pipe would block the process
        while data := await self._terminal.read():
            self._buffer += data
            del self._buffer[: max(0, len(self._buffer) - self._limit)]
            for listener in list(self._listeners):
                await listener.output(data)
        # the process ended by itself (/exit or a crash): only this reader's session is over
        self._reader = None
        self._current = None
        self._buffer.clear()
        self._log.info("project.exited", project=name)
        await self._broadcast_state()

    async def _broadcast_state(self) -> None:
        for listener in list(self._listeners):
            await listener.state(self._current)

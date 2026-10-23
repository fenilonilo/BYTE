from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from winpty import PtyProcess

from app.domain.exceptions import ProjectError
from app.ports.terminal import ProjectTerminalPort

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

READ_CHARS = 4096


class WinPtyTerminal(ProjectTerminalPort):
    """Windows ConPTY through pywinpty. Blocking pty calls run in worker threads."""

    def __init__(self) -> None:
        self._proc: PtyProcess | None = None

    @property
    def alive(self) -> bool:
        return self._proc is not None and bool(self._proc.isalive())

    async def start(
        self, cwd: str, argv: Sequence[str], env: Mapping[str, str], cols: int, rows: int
    ) -> None:
        try:
            self._proc = await asyncio.to_thread(
                PtyProcess.spawn, list(argv), cwd=cwd, env=dict(env), dimensions=(rows, cols)
            )
        except Exception as exc:
            raise ProjectError("could not start the project terminal") from exc

    async def write(self, data: bytes) -> None:
        proc = self._proc
        if proc is None:
            return
        try:
            await asyncio.to_thread(proc.write, data.decode("utf-8", errors="replace"))
        except Exception as exc:
            raise ProjectError("terminal write failed") from exc

    async def resize(self, cols: int, rows: int) -> None:
        proc = self._proc
        if proc is not None:
            try:
                await asyncio.to_thread(proc.setwinsize, rows, cols)
            except Exception as exc:
                raise ProjectError("terminal resize failed") from exc

    async def read(self) -> bytes:
        proc = self._proc
        if proc is None:
            return b""
        return await asyncio.to_thread(_read, proc)

    async def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        if proc.isalive():
            # claude spawns node and tool processes: kill the whole tree, not just the shell
            killer = await asyncio.create_subprocess_exec(
                "taskkill",
                "/PID",
                str(proc.pid),
                "/T",
                "/F",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await killer.wait()
        await asyncio.to_thread(proc.close, True)


def _read(proc: PtyProcess) -> bytes:
    try:
        while True:
            text = proc.read(READ_CHARS)
            if text:  # pywinpty returns "" for its own control frames: not the end
                return text.encode()
    except (EOFError, OSError):
        return b""

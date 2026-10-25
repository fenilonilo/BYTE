from __future__ import annotations

import asyncio
import os
import sys

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(sys.platform != "win32", reason="ConPTY is Windows only"),
]


async def read_all(terminal: object) -> bytes:
    out = b""
    while chunk := await terminal.read():  # type: ignore[attr-defined]
        out += chunk
    return out


async def test_runs_a_command_and_reports_the_end() -> None:
    from app.adapters.pty.winpty_terminal import WinPtyTerminal  # noqa: PLC0415 - win32 only

    terminal = WinPtyTerminal()
    await terminal.start(os.getcwd(), ["cmd", "/c", "echo byte-ok"], dict(os.environ), 80, 24)
    assert b"byte-ok" in await read_all(terminal)
    await terminal.stop()


async def test_stop_kills_a_running_process() -> None:
    from app.adapters.pty.winpty_terminal import WinPtyTerminal  # noqa: PLC0415 - win32 only

    terminal = WinPtyTerminal()
    await terminal.start(os.getcwd(), ["cmd"], dict(os.environ), 80, 24)
    assert terminal.alive
    await terminal.write(b"echo hi\r")
    await terminal.resize(100, 30)
    await terminal.stop()
    assert not terminal.alive
    assert await read_all(terminal) is not None
    await terminal.stop()  # idempotent


def test_stop_works_on_a_selector_loop() -> None:
    """uvicorn --reload runs a SelectorEventLoop, which cannot spawn asyncio subprocesses."""
    from app.adapters.pty.winpty_terminal import WinPtyTerminal  # noqa: PLC0415 - win32 only

    async def main() -> bool:
        terminal = WinPtyTerminal()
        await terminal.start(os.getcwd(), ["cmd"], dict(os.environ), 80, 24)
        await terminal.stop()
        return terminal.alive

    assert asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop) is False


def test_kill_tolerates_a_process_still_dying_after_taskkill() -> None:
    """pywinpty's close() signals a process taskkill already doomed; Windows says access denied."""
    from app.adapters.pty.winpty_terminal import (  # noqa: PLC0415 - win32 only
        _kill_tree,  # pyright: ignore[reportPrivateUsage]
    )

    class Dying:
        pid = 0

        def isalive(self) -> bool:
            return False

        def close(self, force: bool = False) -> None:
            raise PermissionError(13, "Acesso negado")

    _kill_tree(Dying())  # type: ignore[arg-type]

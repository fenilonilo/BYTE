from __future__ import annotations

import contextlib
import json
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, WebSocket, status

from app.api.auth import accept_authorized
from app.api.deps import get_logger, get_project_session, get_settings, get_terminal_slot
from app.application.project_session import TerminalListener
from app.domain.exceptions import DomainError

if TYPE_CHECKING:
    from app.api.live_slot import LiveSlot
    from app.application.project_session import ProjectSession
    from app.config import Settings
    from app.ports.logger import LoggerPort

MIN_SIZE, MAX_SIZE = 2, 500

router = APIRouter()


class WebSocketTerminal(TerminalListener):
    def __init__(self, websocket: WebSocket) -> None:
        self._ws = websocket

    async def state(self, project: str | None) -> None:
        with contextlib.suppress(Exception):  # a dead socket is cleaned up by its own handler
            await self._ws.send_json({"type": "state", "project": project})

    async def output(self, data: bytes) -> None:
        with contextlib.suppress(Exception):
            await self._ws.send_bytes(data)


def _resize(text: str) -> tuple[int, int] | None:
    try:
        message = json.loads(text)
    except ValueError:
        return None
    if not isinstance(message, dict) or message.get("type") != "resize":  # pyright: ignore[reportUnknownMemberType]
        return None
    cols, rows = message.get("cols"), message.get("rows")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    if not isinstance(cols, int) or not isinstance(rows, int):
        return None
    return (min(max(cols, MIN_SIZE), MAX_SIZE), min(max(rows, MIN_SIZE), MAX_SIZE))


@router.websocket("/ws/terminal")
async def terminal(
    websocket: WebSocket,
    settings: Settings = Depends(get_settings),
    session: ProjectSession | None = Depends(get_project_session),
    slot: LiveSlot = Depends(get_terminal_slot),
    log: LoggerPort = Depends(get_logger),
) -> None:
    if not await accept_authorized(websocket, settings.api_token):
        return
    if session is None:  # no claude, no pty or no projects on this machine
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await slot.claim(websocket)
    listener = WebSocketTerminal(websocket)
    await session.attach(listener)
    try:
        while (message := await websocket.receive())["type"] != "websocket.disconnect":
            try:
                if (data := message.get("bytes")) is not None:
                    await session.write(data)
                elif (size := _resize(message.get("text") or "")) is not None:
                    await session.resize(*size)
            except DomainError as exc:  # a broken pty must not take the socket down with it
                log.warning("terminal.input_failed", error=type(exc).__name__)
    except RuntimeError:  # receive() after a replacement closed this socket
        pass
    finally:
        session.detach(listener)
        slot.release(websocket)

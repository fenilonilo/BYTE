from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING
from uuid import uuid4

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError

from app.api.auth import accept_authorized
from app.api.deps import (
    get_live_slot,
    get_logger,
    get_run_live_session,
    get_runner,
    get_settings,
)
from app.api.live_transport import WebSocketTransport
from app.api.schemas import LiveStartSchema
from app.domain.exceptions import LiveSessionError

if TYPE_CHECKING:
    from app.api.live_slot import LiveSlot
    from app.application.tool_runner import ToolRunner
    from app.application.use_cases.run_live_session import RunLiveSession
    from app.config import Settings
    from app.ports.logger import LoggerPort

AUTO = "auto"
START_TIMEOUT_SECONDS = 5.0

router = APIRouter()


async def _reject(websocket: WebSocket, code: str) -> None:
    await websocket.send_json({"type": "error", "code": code})
    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)


async def _read_start(websocket: WebSocket, runner: ToolRunner) -> LiveStartSchema | None:
    """The first frame must be a valid `start`; anything else closes the socket."""
    try:
        raw = await asyncio.wait_for(websocket.receive_json(), START_TIMEOUT_SECONDS)
    except (TimeoutError, WebSocketDisconnect, ValueError):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None
    try:
        start = LiveStartSchema.model_validate(raw)
    except ValidationError:
        await _reject(websocket, "bad_start")
        return None
    segment = start.segment.strip().lower()
    if segment != AUTO and segment not in runner.segments():
        await _reject(websocket, "bad_segment")
        return None
    return start


@router.websocket("/live")
async def live(
    websocket: WebSocket,
    settings: Settings = Depends(get_settings),
    runner: ToolRunner = Depends(get_runner),
    slot: LiveSlot = Depends(get_live_slot),
    run: RunLiveSession = Depends(get_run_live_session),
    log: LoggerPort = Depends(get_logger),
) -> None:
    if not await accept_authorized(websocket, settings.api_token):
        return
    start = await _read_start(websocket, runner)
    if start is None:
        return
    segment = start.segment.strip().lower()
    await slot.claim(websocket)
    transport = WebSocketTransport(
        websocket,
        pace_factor=settings.live_pace_factor,
        max_frame_bytes=settings.live_max_frame_bytes,
    )
    try:
        await run.execute(
            transport,
            start.conversation_id or uuid4().hex,
            None if segment == AUTO else segment,
            panel=start.client == "panel",
        )
    except LiveSessionError as exc:
        cause = type(exc.__cause__).__name__ if exc.__cause__ is not None else None
        log.error("live.failed", error=type(exc).__name__, cause=cause)
    finally:
        await transport.aclose()
        # a replaced or vanished client is already gone: closing it again raises
        with contextlib.suppress(RuntimeError, WebSocketDisconnect):
            await websocket.close()
        slot.release(websocket)  # last: "released" means this connection is fully cleaned up

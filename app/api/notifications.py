from __future__ import annotations

import asyncio
import contextlib
import json
import re
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.api.auth import accept_authorized
from app.api.deps import get_notify_slot, get_reminder_hub, get_settings, get_wall_clock
from app.application.reminder_hub import ReminderListener

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from datetime import datetime

    from app.api.live_slot import LiveSlot
    from app.application.reminder_hub import ReminderHub
    from app.config import Settings
    from app.domain.reminders import Reminder
    from app.ports.logger import LoggerPort

TICK_SECONDS = 5.0
SYNC_EVERY_TICKS = 60  # five minutes
REMINDER_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

router = APIRouter()


class WebSocketListener(ReminderListener):
    def __init__(self, websocket: WebSocket) -> None:
        self._ws = websocket

    async def push(self, reminder: Reminder, audio: bytes) -> None:
        # a dead link never acks, so the reminder goes out again on the next connection
        with contextlib.suppress(Exception):
            await self._ws.send_json({"type": "reminder", "id": reminder.id, "kind": reminder.kind})
            await self._ws.send_bytes(audio)


def _acked_id(text: str) -> str | None:
    try:
        message = json.loads(text)
    except ValueError:
        return None
    if not isinstance(message, dict) or message.get("type") != "ack":  # pyright: ignore[reportUnknownMemberType]
        return None
    rid = message.get("id")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    return rid if isinstance(rid, str) and REMINDER_ID.match(rid) else None


@router.websocket("/ws/notifications")
async def notifications(
    websocket: WebSocket,
    settings: Settings = Depends(get_settings),
    hub: ReminderHub = Depends(get_reminder_hub),
    slot: LiveSlot = Depends(get_notify_slot),
    clock: Callable[[], datetime] = Depends(get_wall_clock),
) -> None:
    if not await accept_authorized(websocket, settings.api_token):
        return
    await slot.claim(websocket)
    listener = WebSocketListener(websocket)
    hub.attach(listener)
    try:
        await hub.tick(clock())  # the backlog goes out on connect, not 5 s later
        async for text in websocket.iter_text():
            rid = _acked_id(text)
            if rid is not None:
                await hub.ack(rid)
    except WebSocketDisconnect:
        pass
    finally:
        hub.detach(listener)
        slot.release(websocket)


async def _guarded(log: LoggerPort, step: str, work: Awaitable[None]) -> None:
    try:
        await work
    except Exception as exc:  # the loop must outlive Google outages and bad data
        log.error("reminders.failed", step=step, error=type(exc).__name__)


async def run_reminders(
    hub: ReminderHub,
    clock: Callable[[], datetime],
    log: LoggerPort,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Background loop of the lifespan: fire due reminders, refresh calendar warnings."""
    # ponytail: polling every 5 s; sleep until the next due time if that ever matters
    ticks = 0
    while True:
        if ticks % SYNC_EVERY_TICKS == 0:
            await _guarded(log, "sync", hub.sync_calendar(clock()))
        await _guarded(log, "tick", hub.tick(clock()))
        ticks += 1
        await sleep(TICK_SECONDS)

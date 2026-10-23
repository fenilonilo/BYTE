from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.api.auth import accept_authorized
from app.api.deps import get_panel_slot, get_settings, get_weather_display
from app.application.weather_display import WeatherListener

if TYPE_CHECKING:
    from app.api.live_slot import LiveSlot
    from app.application.weather_display import WeatherDisplay
    from app.config import Settings

router = APIRouter()


class PanelListener(WeatherListener):
    def __init__(self, websocket: WebSocket) -> None:
        self._ws = websocket

    async def changed(self) -> None:
        # no data on purpose: the panel reads the truth from GET /weather
        with contextlib.suppress(Exception):
            await self._ws.send_json({"type": "weather"})


@router.websocket("/ws/panel")
async def panel(
    websocket: WebSocket,
    settings: Settings = Depends(get_settings),
    slot: LiveSlot = Depends(get_panel_slot),
    display: WeatherDisplay = Depends(get_weather_display),
) -> None:
    """Server -> panel pushes. One panel at a time; a new one replaces the old (4000)."""
    if not await accept_authorized(websocket, settings.api_token):
        return
    await slot.claim(websocket)
    listener = PanelListener(websocket)
    display.attach(listener)
    try:
        async for _ in websocket.iter_text():
            pass
    except WebSocketDisconnect:
        pass
    finally:
        display.detach(listener)
        slot.release(websocket)

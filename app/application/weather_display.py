from __future__ import annotations

import contextlib
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.weather import Place
    from app.ports.weather import WeatherPort


class WeatherListener(ABC):
    """The panel's push socket (a WebSocket in production)."""

    @abstractmethod
    async def changed(self) -> None:
        """What the panel shows changed. Must not raise."""


class WeatherDisplay:
    """Which place the panel's weather section shows: home unless the owner asked for another."""

    def __init__(self, weather: WeatherPort, home_query: str) -> None:
        self._weather = weather
        self._home_query = home_query
        self._home: Place | None = None
        self._shown: Place | None = None
        self._listener: WeatherListener | None = None

    async def home(self) -> Place:
        if self._home is None:
            self._home = await self._weather.find_place(self._home_query)
        return self._home

    async def shown(self) -> Place:
        return self._shown or await self.home()

    async def show(self, place: Place | None) -> None:
        self._shown = None if place is None or place == await self.home() else place
        if self._listener is not None:
            # a broken panel link must never fail the tool that changed the display
            with contextlib.suppress(Exception):
                await self._listener.changed()

    def attach(self, listener: WeatherListener) -> None:
        self._listener = listener

    def detach(self, listener: WeatherListener) -> None:
        if self._listener is listener:
            self._listener = None

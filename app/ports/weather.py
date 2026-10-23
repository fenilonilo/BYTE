from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.weather import Forecast, Place


class WeatherPort(ABC):
    """Current weather and forecast for any city, found by name."""

    @abstractmethod
    async def find_place(self, query: str) -> Place:
        """`query` is "Cidade" or "Cidade, UF/estado/país". Raises UnknownPlaceError."""

    @abstractmethod
    async def forecast(self, place: Place) -> Forecast:
        """Now, the next 24 hours and 7 days. Raises WeatherUnavailableError."""

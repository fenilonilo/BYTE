"""WeatherPortContract against the real Open-Meteo (no key needed, only the network)."""

from __future__ import annotations

import pytest

from app.adapters.openmeteo.open_meteo_weather import OpenMeteoWeather
from tests.contracts.weather_contract import WeatherPortContract

pytestmark = [pytest.mark.integration, pytest.mark.slow]


class TestOpenMeteoContract(WeatherPortContract):
    def make(self) -> OpenMeteoWeather:
        return OpenMeteoWeather()

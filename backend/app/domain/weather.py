from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date, datetime


class Condition(StrEnum):
    CLEAR = "clear"
    PARTLY_CLOUDY = "partly_cloudy"
    CLOUDY = "cloudy"
    FOG = "fog"
    DRIZZLE = "drizzle"
    RAIN = "rain"
    STORM = "storm"


WET = frozenset({Condition.DRIZZLE, Condition.RAIN, Condition.STORM})

BRAZIL_STATES = {
    "AC": "Acre",
    "AL": "Alagoas",
    "AP": "Amapá",
    "AM": "Amazonas",
    "BA": "Bahia",
    "CE": "Ceará",
    "DF": "Distrito Federal",
    "ES": "Espírito Santo",
    "GO": "Goiás",
    "MA": "Maranhão",
    "MT": "Mato Grosso",
    "MS": "Mato Grosso do Sul",
    "MG": "Minas Gerais",
    "PA": "Pará",
    "PB": "Paraíba",
    "PR": "Paraná",
    "PE": "Pernambuco",
    "PI": "Piauí",
    "RJ": "Rio de Janeiro",
    "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul",
    "RO": "Rondônia",
    "RR": "Roraima",
    "SC": "Santa Catarina",
    "SP": "São Paulo",
    "SE": "Sergipe",
    "TO": "Tocantins",
}


def fold(text: str) -> str:
    """Casefolded and accent-free, so "GOIÂNIA" and "goiania" compare equal."""
    decomposed = unicodedata.normalize("NFKD", text.strip())
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


@dataclass(frozen=True, slots=True)
class Place:
    name: str
    region: str
    country: str
    latitude: float
    longitude: float

    @property
    def label(self) -> str:
        return f"{self.name}, {self.region}" if self.region else self.name

    def matches(self, qualifier: str) -> bool:
        """Whether "Cidade, <qualifier>" can mean this place: region, country or a UF."""
        q = fold(qualifier)
        region = fold(self.region)
        state = BRAZIL_STATES.get(qualifier.strip().upper())
        return q in (region, fold(self.country)) or (state is not None and fold(state) == region)


@dataclass(frozen=True, slots=True)
class CurrentWeather:
    temperature: float
    feels_like: float
    humidity: int
    wind_kmh: float
    condition: Condition
    raining: bool
    is_day: bool


@dataclass(frozen=True, slots=True)
class HourlyPoint:
    time: datetime
    temperature: float
    rain_chance: int
    condition: Condition
    is_day: bool


@dataclass(frozen=True, slots=True)
class DailyForecast:
    day: date
    condition: Condition
    low: float
    high: float
    rain_chance: int


@dataclass(frozen=True, slots=True)
class Forecast:
    place: Place
    current: CurrentWeather
    hours: tuple[HourlyPoint, ...]
    days: tuple[DailyForecast, ...]

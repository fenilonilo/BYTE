from __future__ import annotations

from typing import TYPE_CHECKING

from app.application.tool import Tool
from app.application.tools.args import object_schema, opt_int, opt_str
from app.domain.exceptions import ToolArgumentError, UnknownPlaceError, WeatherUnavailableError
from app.domain.tools import ToolSpec
from app.domain.weather import Condition

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.application.weather_display import WeatherDisplay
    from app.domain.weather import Forecast, Place
    from app.ports.weather import WeatherPort

SEGMENT = "weather"
MAX_DAYS = 7
DEFAULT_DAYS = 3
WEEKDAYS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
CONDITION_WORD = {
    Condition.CLEAR: "céu limpo",
    Condition.PARTLY_CLOUDY: "parcialmente nublado",
    Condition.CLOUDY: "nublado",
    Condition.FOG: "neblina",
    Condition.DRIZZLE: "garoa",
    Condition.RAIN: "chuva",
    Condition.STORM: "tempestade",
}
UNAVAILABLE = "Previsão indisponível agora."
CITY = ("string", 'Cidade, opcionalmente com UF ou país ("Santa Maria, RS"). Omita para casa.')


def describe(forecast: Forecast, days: int) -> str:
    """Compact on purpose: every character reaches the model as tokens."""
    c = forecast.current
    lines = [
        f"{forecast.place.label} — agora {round(c.temperature)}°C "
        f"(sensação {round(c.feels_like)}°), {'chovendo' if c.raining else 'sem chuva'}, "
        f"umidade {c.humidity}%, vento {round(c.wind_kmh)} km/h."
    ]
    for i, day in enumerate(forecast.days[:days]):
        label = "hoje" if i == 0 else WEEKDAYS[day.day.weekday()]
        lines.append(
            f"{label}: {round(day.low)}-{round(day.high)}°, chuva {day.rain_chance}%, "
            f"{CONDITION_WORD[day.condition]}"
        )
    return "\n".join(lines)


async def _place(weather: WeatherPort, display: WeatherDisplay, city: str | None) -> Place:
    return await display.home() if city is None else await weather.find_place(city)


class GetWeather(Tool):
    spec = ToolSpec(
        name="get_weather",
        description=(
            "Tempo lá fora (não é o ar-condicionado): temperatura agora, se está chovendo e a "
            "previsão dos próximos dias. Sem city, usa a cidade de casa. Use para perguntas; "
            "não muda o painel."
        ),
        parameters=object_schema(
            {"city": CITY, "days": ("integer", "Quantos dias de previsão, de 1 a 7 (padrão 3).")},
            required=[],
        ),
        segment=SEGMENT,
    )

    def __init__(self, weather: WeatherPort, display: WeatherDisplay) -> None:
        self._weather = weather
        self._display = display

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        city = opt_str(args, "city")
        days = opt_int(args, "days")
        days = DEFAULT_DAYS if days is None else days
        if not 1 <= days <= MAX_DAYS:
            raise ToolArgumentError("argumento 'days' deve ser de 1 a 7")
        try:
            place = await _place(self._weather, self._display, city)
            return describe(await self._weather.forecast(place), days)
        except UnknownPlaceError:
            return f"Não encontrei a cidade {city}."
        except WeatherUnavailableError:
            return UNAVAILABLE


class ShowWeather(Tool):
    spec = ToolSpec(
        name="show_weather",
        description=(
            "Coloca a previsão de uma cidade no painel. Use SOMENTE quando o dono pedir para "
            "mostrar, exibir ou colocar no painel; para só perguntar, use get_weather. Sem city, "
            "volta para a cidade de casa."
        ),
        parameters=object_schema({"city": CITY}, required=[]),
        segment=SEGMENT,
    )

    def __init__(self, weather: WeatherPort, display: WeatherDisplay) -> None:
        self._weather = weather
        self._display = display

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        city = opt_str(args, "city")
        try:
            place = await _place(self._weather, self._display, city)
            await self._display.show(place)
            home = await self._display.home()
        except UnknownPlaceError:
            return f"Não encontrei a cidade {city}."
        except WeatherUnavailableError:
            return UNAVAILABLE
        if place == home:
            return f"Painel de volta para {home.label}."
        return f"Painel mostrando {place.label}."

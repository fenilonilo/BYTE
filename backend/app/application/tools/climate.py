from __future__ import annotations

from typing import TYPE_CHECKING

from app.application.tool import Tool
from app.application.tools.args import (
    object_schema,
    opt_bool,
    opt_enum,
    opt_float,
    opt_int,
    opt_str,
)
from app.domain.climate import ClimateChange, ClimateMode, FanSpeed
from app.domain.exceptions import UnknownClimateDeviceError
from app.domain.tools import ToolSpec

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.domain.climate import ClimateState
    from app.ports.climate import ClimatePort


def describe_climate(name: str, state: ClimateState) -> str:
    text = (
        f"{name}: {'ligado' if state.power else 'desligado'}, modo {state.mode.value}, "
        f"alvo {state.target_temperature:g}°C, ambiente {state.current_temperature:g}°C, "
        f"ventilador {state.fan_speed.value}"
    )
    return f"{text}, ATENÇÃO: o aparelho reporta erro" if state.has_error else text


class ListClimates(Tool):
    spec = ToolSpec(
        name="list_climates",
        description="Lista os ar-condicionados da casa com o estado atual de cada um.",
        parameters=object_schema({}),
        segment="home",
    )

    def __init__(self, climate: ClimatePort) -> None:
        self._climate = climate

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        names = await self._climate.devices()
        lines = [describe_climate(n, await self._climate.get_state(n)) for n in names]
        return "; ".join(lines) or "nenhum ar-condicionado configurado"


class SetClimate(Tool):
    spec = ToolSpec(
        name="set_climate",
        description=(
            "Muda um ar-condicionado. Só informe o que mudar. Ajustar modo, temperatura ou "
            "ventilador liga o aparelho. Se a casa tem um aparelho só, omita name."
        ),
        parameters=object_schema(
            {
                "name": (
                    "string",
                    "Nome do aparelho, como em list_climates; opcional se houver um só.",
                ),
                "power": ("boolean", "true liga, false desliga."),
                "mode": ("string", "cool, dry, fan ou auto."),
                "target_temperature": ("number", "Temperatura alvo de 18 a 30, em graus inteiros."),
                "fan_speed": ("string", "auto, low, mid, high ou nature."),
                "swing": ("boolean", "Oscilação das aletas."),
                "power_save": ("boolean", "Modo economia."),
                "display_light": ("boolean", "Luz do display do aparelho."),
                "stop_in_minutes": ("integer", "Desliga em N minutos; 0 cancela."),
                "start_in_minutes": ("integer", "Liga em N minutos; 0 cancela."),
                "sleep_in_minutes": ("integer", "Modo dormir por N minutos; 0 cancela."),
            },
            required=[],
        ),
        segment="home",
    )

    def __init__(self, climate: ClimatePort) -> None:
        self._climate = climate

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        name = await self._resolve(opt_str(args, "name"))
        mode = opt_enum(args, "mode", ClimateMode)
        target = opt_float(args, "target_temperature")
        fan = opt_enum(args, "fan_speed", FanSpeed)
        power = opt_bool(args, "power")
        if power is None and (mode, target, fan) != (None, None, None):
            # "põe em 22" on a stopped unit means turn it on, not ask first
            power = True if not (await self._climate.get_state(name)).power else None
        change = ClimateChange(
            power=power,
            mode=mode,
            target_temperature=target,
            fan_speed=fan,
            swing=opt_bool(args, "swing"),
            power_save=opt_bool(args, "power_save"),
            display_light=opt_bool(args, "display_light"),
            stop_in_minutes=opt_int(args, "stop_in_minutes"),
            start_in_minutes=opt_int(args, "start_in_minutes"),
            sleep_in_minutes=opt_int(args, "sleep_in_minutes"),
        )
        return describe_climate(name, await self._climate.apply(name, change))

    async def _resolve(self, name: str | None) -> str:
        """With a single unit, any name the model says ("o ar", "ar do quarto") means it."""
        names = await self._climate.devices()
        if len(names) == 1:
            return names[0]
        if name is None:
            raise UnknownClimateDeviceError("informe qual aparelho: " + ", ".join(names))
        return name

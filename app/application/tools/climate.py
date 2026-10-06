from __future__ import annotations

from typing import TYPE_CHECKING

from app.application.tool import Tool
from app.application.tools.args import (
    object_schema,
    opt_bool,
    opt_enum,
    opt_float,
    opt_int,
    str_arg,
)
from app.domain.climate import ClimateChange, ClimateMode, FanSpeed
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
    """Turning the unit on or off is physical, so that (and only that) asks for confirmation."""

    spec = ToolSpec(
        name="set_climate",
        description=(
            "Muda um ar-condicionado. Só informe o que mudar. Ligar ou desligar (power) exige "
            "confirmação do usuário. Um aparelho desligado recusa ajustes: ligue-o antes."
        ),
        parameters=object_schema(
            {
                "name": ("string", "Nome do aparelho, como em list_climates."),
                "power": ("boolean", "true liga, false desliga."),
                "mode": ("string", "cool, dry, fan ou auto."),
                "target_temperature": ("number", "Temperatura alvo de 18 a 30, de 0,5 em 0,5."),
                "fan_speed": ("string", "auto, low, mid, high ou nature."),
                "swing": ("boolean", "Oscilação das aletas."),
                "power_save": ("boolean", "Modo economia."),
                "display_light": ("boolean", "Luz do display do aparelho."),
                "stop_in_minutes": ("integer", "Desliga em N minutos; 0 cancela."),
                "start_in_minutes": ("integer", "Liga em N minutos; 0 cancela."),
                "sleep_in_minutes": ("integer", "Modo dormir por N minutos; 0 cancela."),
            },
            required=["name"],
        ),
        segment="home",
    )

    def __init__(self, climate: ClimatePort) -> None:
        self._climate = climate

    def needs_confirmation(self, args: Mapping[str, object]) -> bool:
        return opt_bool(args, "power") is not None

    def summarize(self, args: Mapping[str, object]) -> str:
        verb = "Ligar" if opt_bool(args, "power") else "Desligar"
        others = [k for k, v in args.items() if k not in ("name", "power") and v is not None]
        extra = " e aplicar os outros ajustes pedidos" if others else ""
        return f"{verb} {str_arg(args, 'name')}{extra}"

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        name = str_arg(args, "name")
        change = ClimateChange(
            power=opt_bool(args, "power"),
            mode=opt_enum(args, "mode", ClimateMode),
            target_temperature=opt_float(args, "target_temperature"),
            fan_speed=opt_enum(args, "fan_speed", FanSpeed),
            swing=opt_bool(args, "swing"),
            power_save=opt_bool(args, "power_save"),
            display_light=opt_bool(args, "display_light"),
            stop_in_minutes=opt_int(args, "stop_in_minutes"),
            start_in_minutes=opt_int(args, "start_in_minutes"),
            sleep_in_minutes=opt_int(args, "sleep_in_minutes"),
        )
        return describe_climate(name, await self._climate.apply(name, change))

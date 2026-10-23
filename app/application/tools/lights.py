from __future__ import annotations

from typing import TYPE_CHECKING

from app.application.tool import Tool
from app.application.tools.args import (
    object_schema,
    opt_bool,
    opt_int,
    opt_str,
)
from app.domain.exceptions import UnknownLightDeviceError
from app.domain.light import Color, LightChange, LightMode
from app.domain.tools import ToolSpec

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.domain.light import LightState
    from app.ports.light import LightPort


def describe_light(name: str, state: LightState) -> str:
    if state.mode is LightMode.COLOUR:
        c = state.color
        look = f"cor (matiz {c.hue}, saturação {c.saturation}%, brilho {c.brightness}%)"
    else:
        look = (
            f"modo {state.mode.value}, brilho {state.brightness}%, "
            f"temperatura de cor {state.color_temperature}%"
        )
    return f"{name}: {'ligada' if state.power else 'desligada'}, {look}"


class ListLights(Tool):
    spec = ToolSpec(
        name="list_lights",
        description="Lista as luzes da casa com o estado atual de cada uma.",
        parameters=object_schema({}),
        segment="home",
    )

    def __init__(self, light: LightPort) -> None:
        self._light = light

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        names = await self._light.devices()
        lines = [describe_light(n, await self._light.get_state(n)) for n in names]
        return "; ".join(lines) or "nenhuma luz configurada"


class SetLight(Tool):
    spec = ToolSpec(
        name="set_light",
        description=(
            "Muda uma luz. Só informe o que mudar. Escolha um visual: branco (brightness "
            "e/ou color_temperature) ou cor (hue, com saturation e brightness). "
            "Escolher um visual liga a luz. Se a casa tem uma luz só, omita name."
        ),
        parameters=object_schema(
            {
                "name": ("string", "Nome da luz, como em list_lights; opcional se houver uma só."),
                "power": ("boolean", "true liga, false desliga."),
                "brightness": ("integer", "Brilho de 1 a 100."),
                "color_temperature": ("integer", "Temperatura de cor de 0 (quente) a 100 (fria)."),
                "hue": ("integer", "Matiz de 0 a 360; ativa o modo cor."),
                "saturation": ("integer", "Saturação de 0 a 100 (com hue; padrão 100)."),
                "timer_minutes": ("integer", "Desliga/liga em N minutos; 0 cancela o timer."),
                "do_not_disturb": ("boolean", "Modo não perturbe."),
            },
            required=[],
        ),
        segment="home",
    )

    def __init__(self, light: LightPort) -> None:
        self._light = light

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        name = await self._resolve(opt_str(args, "name"))
        power = opt_bool(args, "power")
        hue = opt_int(args, "hue")
        brightness = opt_int(args, "brightness")
        color = None
        if hue is not None:
            saturation = opt_int(args, "saturation")
            color = Color(
                hue,
                100 if saturation is None else saturation,
                100 if brightness is None else brightness,
            )
        change = LightChange(
            power=power,
            brightness=None if color is not None else brightness,
            color_temperature=opt_int(args, "color_temperature"),
            color=color,
            timer_minutes=opt_int(args, "timer_minutes"),
            do_not_disturb=opt_bool(args, "do_not_disturb"),
        )
        return describe_light(name, await self._light.apply(name, change))

    async def _resolve(self, name: str | None) -> str:
        """With a single lamp, any name the model says ("a luz", "luz do quarto") means it."""
        names = await self._light.devices()
        if len(names) == 1:
            return names[0]
        if name is None:
            raise UnknownLightDeviceError("informe qual luz: " + ", ".join(names))
        return name

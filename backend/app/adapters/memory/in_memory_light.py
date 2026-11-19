from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain.exceptions import UnknownLightDeviceError
from app.domain.light import Color, LightMode, LightState
from app.ports.light import LightPort

if TYPE_CHECKING:
    from app.domain.light import LightChange


def _initial() -> LightState:
    return LightState(
        power=False,
        mode=LightMode.WHITE,
        brightness=100,
        color_temperature=50,
        color=Color(hue=0, saturation=100, brightness=100),
        scene=(),
        timer_seconds=0,
        do_not_disturb=False,
    )


class InMemoryLight(LightPort):
    def __init__(self, names: tuple[str, ...] = ("lampada",)) -> None:
        self._states = {n.lower(): _initial() for n in names}

    async def devices(self) -> tuple[str, ...]:
        return tuple(self._states)

    async def get_state(self, device: str) -> LightState:
        try:
            return self._states[device.lower()]
        except KeyError:
            raise UnknownLightDeviceError(f"unknown light: {device!r}") from None

    async def apply(self, device: str, change: LightChange) -> LightState:
        new = change.apply_to(await self.get_state(device))
        self._states[device.lower()] = new
        return new

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.adapters.memory.in_memory_light import InMemoryLight
from app.domain.exceptions import UnknownLightDeviceError
from app.domain.light import Color, LightChange, LightMode

if TYPE_CHECKING:
    from app.ports.light import LightPort

DEVICE = "lampada"


@pytest.fixture
def light() -> LightPort:
    return InMemoryLight()


async def test_lists_devices(light: LightPort) -> None:
    assert await light.devices() == (DEVICE,)


async def test_starts_off(light: LightPort) -> None:
    assert (await light.get_state(DEVICE)).power is False


async def test_apply_returns_and_stores_new_state(light: LightPort) -> None:
    color = Color(hue=240, saturation=100, brightness=50)
    state = await light.apply(DEVICE, LightChange(color=color))
    assert (state.power, state.mode, state.color) == (True, LightMode.COLOUR, color)
    assert await light.get_state(DEVICE) == state


async def test_name_is_case_insensitive(light: LightPort) -> None:
    assert (await light.get_state("Lampada")).power is False


async def test_unknown_device(light: LightPort) -> None:
    with pytest.raises(UnknownLightDeviceError):
        await light.get_state("geladeira")
    with pytest.raises(UnknownLightDeviceError):
        await light.apply("geladeira", LightChange(power=True))

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.adapters.memory.in_memory_climate import InMemoryClimate
from app.domain.climate import ClimateChange, ClimateMode, FanSpeed
from app.domain.exceptions import UnknownClimateDeviceError

if TYPE_CHECKING:
    from app.ports.climate import ClimatePort

DEVICE = "ar-condicionado"


@pytest.fixture
def climate() -> ClimatePort:
    return InMemoryClimate()


async def test_lists_devices(climate: ClimatePort) -> None:
    assert await climate.devices() == (DEVICE,)


async def test_apply_all_fields(climate: ClimatePort) -> None:
    state = await climate.apply(
        DEVICE,
        ClimateChange(
            power=True,
            mode=ClimateMode.DRY,
            target_temperature=21.5,
            fan_speed=FanSpeed.NATURE,
            swing=True,
            power_save=True,
            display_light=False,
            stop_in_minutes=90,
            sleep_in_minutes=30,
        ),
    )
    assert (state.power, state.mode, state.target_temperature) == (True, ClimateMode.DRY, 21.5)
    assert (state.fan_speed, state.swing, state.power_save) == (FanSpeed.NATURE, True, True)
    assert (state.display_light, state.stop_timer_minutes) == (False, 90)
    assert state.sleep_timer_minutes == 30
    assert await climate.get_state(DEVICE) == state


async def test_zero_cancels_timer(climate: ClimatePort) -> None:
    await climate.apply(DEVICE, ClimateChange(stop_in_minutes=60))
    state = await climate.apply(DEVICE, ClimateChange(stop_in_minutes=0))
    assert state.stop_timer_minutes is None


async def test_name_is_case_insensitive(climate: ClimatePort) -> None:
    assert (await climate.get_state("AR-Condicionado")).power is False


async def test_unknown_device(climate: ClimatePort) -> None:
    with pytest.raises(UnknownClimateDeviceError):
        await climate.get_state("geladeira")
    with pytest.raises(UnknownClimateDeviceError):
        await climate.apply("geladeira", ClimateChange(power=True))

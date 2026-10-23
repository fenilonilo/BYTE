from __future__ import annotations

from dataclasses import fields, replace

from app.domain.climate import ClimateChange, ClimateMode, ClimateState, FanSpeed
from app.domain.exceptions import ClimateError, UnknownClimateDeviceError
from app.ports.climate import ClimatePort

_TIMER_FIELDS = {
    "stop_in_minutes": "stop_timer_minutes",
    "start_in_minutes": "start_timer_minutes",
    "sleep_in_minutes": "sleep_timer_minutes",
}


def _adjusts(change: ClimateChange) -> bool:
    """True when the change touches anything a stopped unit refuses (a start timer is fine)."""
    ignored = {"power", "start_in_minutes"}
    return any(getattr(change, f.name) is not None for f in fields(change) if f.name not in ignored)


def _initial() -> ClimateState:
    return ClimateState(
        power=False,
        mode=ClimateMode.COOL,
        target_temperature=24.0,
        current_temperature=25.0,
        fan_speed=FanSpeed.AUTO,
        swing=False,
        power_save=False,
        display_light=True,
        stop_timer_minutes=None,
        start_timer_minutes=None,
        sleep_timer_minutes=None,
        filter_used_hours=0,
        has_error=False,
    )


class InMemoryClimate(ClimatePort):
    def __init__(self, names: tuple[str, ...] = ("ar-condicionado",)) -> None:
        self._states = {n.lower(): _initial() for n in names}

    async def devices(self) -> tuple[str, ...]:
        return tuple(self._states)

    async def get_state(self, device: str) -> ClimateState:
        try:
            return self._states[device.lower()]
        except KeyError:
            raise UnknownClimateDeviceError(f"unknown climate device: {device!r}") from None

    async def apply(self, device: str, change: ClimateChange) -> ClimateState:
        state = await self.get_state(device)
        if not state.power and change.power is not True and _adjusts(change):
            raise ClimateError(f"{device} está desligado: ligue-o antes de ajustar")
        updates: dict[str, object] = {}
        for f in fields(change):
            value = getattr(change, f.name)
            if value is None:
                continue
            if f.name in _TIMER_FIELDS:
                updates[_TIMER_FIELDS[f.name]] = value or None
            else:
                updates[f.name] = value
        new = replace(state, **updates)  # pyright: ignore[reportArgumentType]
        self._states[device.lower()] = new
        return new

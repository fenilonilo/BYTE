from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.domain.exceptions import ClimateError

MIN_TARGET_C = 18.0
MAX_TARGET_C = 30.0
TARGET_STEP_C = 1.0
MAX_TIMER_MINUTES = 24 * 60


class ClimateMode(StrEnum):
    COOL = "cool"
    DRY = "dry"
    FAN = "fan"
    AUTO = "auto"


class FanSpeed(StrEnum):
    AUTO = "auto"
    LOW = "low"
    MID = "mid"
    HIGH = "high"
    NATURE = "nature"


@dataclass(frozen=True, slots=True)
class ClimateState:
    power: bool
    mode: ClimateMode
    target_temperature: float
    current_temperature: float
    fan_speed: FanSpeed
    swing: bool
    power_save: bool
    display_light: bool
    stop_timer_minutes: int | None
    start_timer_minutes: int | None
    sleep_timer_minutes: int | None
    filter_used_hours: int
    has_error: bool


@dataclass(frozen=True, slots=True)
class ClimateChange:
    """Partial update. `None` leaves a field alone; a timer of 0 cancels it."""

    power: bool | None = None
    mode: ClimateMode | None = None
    target_temperature: float | None = None
    fan_speed: FanSpeed | None = None
    swing: bool | None = None
    power_save: bool | None = None
    display_light: bool | None = None
    stop_in_minutes: int | None = None
    start_in_minutes: int | None = None
    sleep_in_minutes: int | None = None

    def __post_init__(self) -> None:
        if all(getattr(self, f) is None for f in self.__slots__):
            raise ClimateError("empty climate change")
        t = self.target_temperature
        if t is not None and not (
            MIN_TARGET_C <= t <= MAX_TARGET_C and (t - MIN_TARGET_C) % TARGET_STEP_C == 0
        ):
            raise ClimateError(
                f"target temperature must be {MIN_TARGET_C}-{MAX_TARGET_C} in {TARGET_STEP_C} steps"
            )
        for minutes in (self.stop_in_minutes, self.start_in_minutes, self.sleep_in_minutes):
            if minutes is not None and not 0 <= minutes <= MAX_TIMER_MINUTES:
                raise ClimateError(f"timer must be 0-{MAX_TIMER_MINUTES} minutes")

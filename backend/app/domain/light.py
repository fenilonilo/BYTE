from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from app.domain.exceptions import LightError

MAX_PERCENT = 100
MAX_HUE = 360
MAX_TIMER_MINUTES = 24 * 60
MAX_SCENE_UNITS = 8
MAX_SCENE_SECONDS = 100


class LightMode(StrEnum):
    WHITE = "white"
    COLOUR = "colour"
    SCENE = "scene"
    MUSIC = "music"


class SceneTransition(StrEnum):
    STATIC = "static"
    JUMP = "jump"
    GRADIENT = "gradient"


def _percent(name: str, value: int, low: int = 0) -> None:
    if not low <= value <= MAX_PERCENT:
        raise LightError(f"{name} must be {low}-{MAX_PERCENT}")


@dataclass(frozen=True, slots=True)
class Color:
    hue: int
    saturation: int
    brightness: int

    def __post_init__(self) -> None:
        if not 0 <= self.hue <= MAX_HUE:
            raise LightError(f"hue must be 0-{MAX_HUE}")
        _percent("saturation", self.saturation)
        _percent("brightness", self.brightness)


@dataclass(frozen=True, slots=True)
class SceneUnit:
    """One step of a scene: a colour, or white when `color` is None."""

    transition: SceneTransition
    switch_seconds: int = 0
    gradient_seconds: int = 0
    color: Color | None = None
    brightness: int = 0
    temperature: int = 0

    def __post_init__(self) -> None:
        for name in ("switch_seconds", "gradient_seconds"):
            if not 0 <= getattr(self, name) <= MAX_SCENE_SECONDS:
                raise LightError(f"{name} must be 0-{MAX_SCENE_SECONDS}")
        _percent("brightness", self.brightness)
        _percent("temperature", self.temperature)


@dataclass(frozen=True, slots=True)
class LightState:
    power: bool
    mode: LightMode
    brightness: int
    color_temperature: int
    color: Color
    scene: tuple[SceneUnit, ...]
    timer_seconds: int
    do_not_disturb: bool


@dataclass(frozen=True, slots=True)
class LightChange:
    """Partial update. `None` leaves a field alone; `timer_minutes=0` cancels the timer.

    Colour, scene and white (brightness / temperature) are mutually exclusive looks.
    Choosing a look turns the light on unless `power` says otherwise. A bare
    `brightness` while in colour mode dims the colour instead of leaving it.
    """

    power: bool | None = None
    brightness: int | None = None
    color_temperature: int | None = None
    color: Color | None = None
    scene: tuple[SceneUnit, ...] | None = None
    timer_minutes: int | None = None
    do_not_disturb: bool | None = None

    def __post_init__(self) -> None:
        if all(getattr(self, f) is None for f in self.__slots__):
            raise LightError("empty light change")
        if self.brightness is not None:
            _percent("brightness", self.brightness, low=1)
        if self.color_temperature is not None:
            _percent("color temperature", self.color_temperature)
        if self.scene is not None and not 1 <= len(self.scene) <= MAX_SCENE_UNITS:
            raise LightError(f"scene needs 1-{MAX_SCENE_UNITS} units")
        white = self.brightness is not None or self.color_temperature is not None
        if (white + (self.color is not None) + (self.scene is not None)) > 1:
            raise LightError("choose one look: white, color or scene")
        if self.timer_minutes is not None and not 0 <= self.timer_minutes <= MAX_TIMER_MINUTES:
            raise LightError(f"timer must be 0-{MAX_TIMER_MINUTES} minutes")

    def apply_to(self, state: LightState) -> LightState:
        new = state
        looks = True
        if self.color is not None:
            new = replace(new, mode=LightMode.COLOUR, color=self.color)
        elif self.scene is not None:
            new = replace(new, mode=LightMode.SCENE, scene=self.scene)
        elif (
            self.brightness is not None
            and self.color_temperature is None
            and (state.mode is LightMode.COLOUR)
        ):
            new = replace(new, color=replace(state.color, brightness=self.brightness))
        elif self.brightness is not None or self.color_temperature is not None:
            new = replace(
                new,
                mode=LightMode.WHITE,
                brightness=self.brightness or state.brightness,
                color_temperature=(
                    state.color_temperature
                    if self.color_temperature is None
                    else self.color_temperature
                ),
            )
        else:
            looks = False
        if self.power is not None:
            new = replace(new, power=self.power)
        elif looks:
            new = replace(new, power=True)
        if self.timer_minutes is not None:
            new = replace(new, timer_seconds=self.timer_minutes * 60)
        if self.do_not_disturb is not None:
            new = replace(new, do_not_disturb=self.do_not_disturb)
        return new

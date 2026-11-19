from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from app.domain.exceptions import LightError
from app.domain.light import (
    Color,
    LightChange,
    LightMode,
    LightState,
    SceneTransition,
    SceneUnit,
)

if TYPE_CHECKING:
    from collections.abc import Callable

OFF_WHITE = LightState(
    power=False,
    mode=LightMode.WHITE,
    brightness=100,
    color_temperature=50,
    color=Color(hue=18, saturation=100, brightness=100),
    scene=(),
    timer_seconds=0,
    do_not_disturb=True,
)
RED = Color(hue=0, saturation=100, brightness=80)


def test_empty_change_rejected() -> None:
    with pytest.raises(LightError):
        LightChange()


@pytest.mark.parametrize(
    "make",
    [
        lambda: LightChange(brightness=0),
        lambda: LightChange(brightness=101),
        lambda: LightChange(color_temperature=-1),
        lambda: LightChange(color_temperature=101),
        lambda: LightChange(timer_minutes=-1),
        lambda: LightChange(timer_minutes=24 * 60 + 1),
    ],
)
def test_out_of_range_rejected(make: Callable[[], LightChange]) -> None:
    with pytest.raises(LightError):
        make()


@pytest.mark.parametrize(
    "bad",
    [
        {"hue": 361, "saturation": 0, "brightness": 0},
        {"hue": 0, "saturation": 101, "brightness": 0},
        {"hue": 0, "saturation": 0, "brightness": 101},
        {"hue": -1, "saturation": 0, "brightness": 0},
    ],
)
def test_bad_color_rejected(bad: dict[str, int]) -> None:
    with pytest.raises(LightError):
        Color(**bad)


def test_bad_scene_unit_rejected() -> None:
    with pytest.raises(LightError):
        SceneUnit(SceneTransition.JUMP, switch_seconds=101)
    with pytest.raises(LightError):
        SceneUnit(SceneTransition.JUMP, brightness=101)


def test_scene_limits() -> None:
    unit = SceneUnit(SceneTransition.STATIC, brightness=20)
    with pytest.raises(LightError):
        LightChange(scene=())
    with pytest.raises(LightError):
        LightChange(scene=(unit,) * 9)
    assert LightChange(scene=(unit,) * 8).scene is not None


def test_only_one_look_at_a_time() -> None:
    unit = SceneUnit(SceneTransition.STATIC, brightness=20)
    with pytest.raises(LightError):
        LightChange(color=RED, brightness=50)
    with pytest.raises(LightError):
        LightChange(color=RED, scene=(unit,))
    with pytest.raises(LightError):
        LightChange(scene=(unit,), color_temperature=10)


def test_power_only() -> None:
    new = LightChange(power=True).apply_to(OFF_WHITE)
    assert new == replace(OFF_WHITE, power=True)


def test_color_switches_mode_and_turns_on() -> None:
    new = LightChange(color=RED).apply_to(OFF_WHITE)
    assert (new.power, new.mode, new.color) == (True, LightMode.COLOUR, RED)


def test_explicit_power_off_wins_over_look() -> None:
    new = LightChange(power=False, color=RED).apply_to(replace(OFF_WHITE, power=True))
    assert (new.power, new.mode) == (False, LightMode.COLOUR)


def test_brightness_in_white_mode() -> None:
    new = LightChange(brightness=30).apply_to(OFF_WHITE)
    assert (new.power, new.mode, new.brightness) == (True, LightMode.WHITE, 30)


def test_brightness_alone_in_colour_mode_dims_the_colour() -> None:
    lit = replace(OFF_WHITE, power=True, mode=LightMode.COLOUR, color=RED)
    new = LightChange(brightness=30).apply_to(lit)
    assert new.mode is LightMode.COLOUR
    assert new.color == replace(RED, brightness=30)
    assert new.brightness == lit.brightness


def test_temperature_in_colour_mode_goes_white() -> None:
    lit = replace(OFF_WHITE, power=True, mode=LightMode.COLOUR, color=RED)
    new = LightChange(color_temperature=0).apply_to(lit)
    assert (new.mode, new.color_temperature) == (LightMode.WHITE, 0)


def test_scene_in_scene_mode() -> None:
    unit = SceneUnit(SceneTransition.GRADIENT, switch_seconds=5, color=RED)
    new = LightChange(scene=(unit,)).apply_to(OFF_WHITE)
    assert (new.power, new.mode, new.scene) == (True, LightMode.SCENE, (unit,))


def test_timer_minutes_to_seconds_and_zero_cancels() -> None:
    timed = LightChange(timer_minutes=2).apply_to(OFF_WHITE)
    assert timed.timer_seconds == 120
    assert LightChange(timer_minutes=0).apply_to(timed).timer_seconds == 0


def test_timer_and_dnd_do_not_touch_power() -> None:
    new = LightChange(timer_minutes=5, do_not_disturb=False).apply_to(OFF_WHITE)
    assert (new.power, new.do_not_disturb) == (False, False)

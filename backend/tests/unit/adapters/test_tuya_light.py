from __future__ import annotations

from dataclasses import replace

import pytest

from app.adapters.tuya.tuya_light import encode_scene, parse_state, to_dps
from app.domain.exceptions import LightError
from app.domain.light import (
    Color,
    LightChange,
    LightMode,
    SceneTransition,
    SceneUnit,
)

# Captured from the real lamp (Smart Lampada Wi-Fi V4 EB, protocol 3.3).
CAPTURED = {
    "20": True,
    "21": "white",
    "22": 1000,
    "23": 500,
    "24": "001203e803e8",
    "25": "000e0d0000000000000000c80000",
    "26": 0,
    "34": True,
}
CURRENT = parse_state(CAPTURED)
BLUE = Color(hue=240, saturation=100, brightness=50)


def test_parse_captured_state() -> None:
    assert (CURRENT.power, CURRENT.mode) == (True, LightMode.WHITE)
    assert (CURRENT.brightness, CURRENT.color_temperature) == (100, 50)
    assert CURRENT.color == Color(hue=18, saturation=100, brightness=100)
    assert CURRENT.scene == (
        SceneUnit(SceneTransition.STATIC, switch_seconds=14, gradient_seconds=13, brightness=20),
    )
    assert (CURRENT.timer_seconds, CURRENT.do_not_disturb) == (0, True)


def test_parse_clamps_minimum_brightness_to_one_percent() -> None:
    assert parse_state({**CAPTURED, "22": 10}).brightness == 1


def test_parse_tolerates_missing_and_garbled_values() -> None:
    state = parse_state({"20": False, "25": "zz"})
    assert (state.power, state.mode, state.scene) == (False, LightMode.WHITE, ())


def test_power_only_writes_one_dps() -> None:
    new = LightChange(power=False).apply_to(CURRENT)
    assert to_dps(new, CURRENT) == {20: False}


def test_colour_from_white_writes_mode_and_hsv() -> None:
    new = LightChange(color=BLUE).apply_to(CURRENT)
    assert to_dps(new, CURRENT) == {21: "colour", 24: "00f003e801f4"}


def test_turning_on_with_a_look_writes_power_too() -> None:
    off = replace(CURRENT, power=False)
    dps = to_dps(LightChange(color=BLUE).apply_to(off), off)
    assert dps[20] is True


def test_white_brightness_and_temperature() -> None:
    new = LightChange(brightness=1).apply_to(CURRENT)
    assert to_dps(new, CURRENT) == {22: 10}
    new = LightChange(color_temperature=100).apply_to(CURRENT)
    assert to_dps(new, CURRENT) == {23: 1000}


def test_bare_brightness_in_colour_mode_rewrites_hsv_only() -> None:
    colour = replace(CURRENT, mode=LightMode.COLOUR, color=BLUE)
    new = LightChange(brightness=80).apply_to(colour)
    assert to_dps(new, colour) == {24: "00f003e80320"}


def test_unchanged_state_writes_nothing() -> None:
    assert to_dps(CURRENT, CURRENT) == {}


def test_timer_and_dnd() -> None:
    new = LightChange(timer_minutes=2, do_not_disturb=False).apply_to(CURRENT)
    assert to_dps(new, CURRENT) == {26: 120, 34: False}


def test_scene_round_trip_two_units() -> None:
    units = (
        SceneUnit(SceneTransition.GRADIENT, 5, 7, color=Color(0, 100, 100)),
        SceneUnit(SceneTransition.JUMP, 1, 2, brightness=40, temperature=60),
    )
    new = LightChange(scene=units).apply_to(CURRENT)
    dps = to_dps(new, CURRENT)
    assert dps[21] == "scene"
    assert parse_state({**CAPTURED, "25": dps[25]}).scene == units


def test_encode_scene_layout() -> None:
    unit = SceneUnit(SceneTransition.GRADIENT, 5, 5, color=Color(0, 100, 100), brightness=50)
    assert encode_scene((unit,)) == "01" + "050502" + "0000" + "03e8" + "03e8" + "01f4" + "0000"


def test_scene_over_limit_is_a_light_error() -> None:
    with pytest.raises(LightError):
        encode_scene(())

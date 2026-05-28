from __future__ import annotations

import pytest

from gesture_service.events import Vec3
from gesture_service.motion import Motion, classify_motion


def test_hold_when_nearly_still() -> None:
    sample = classify_motion(Vec3(0.5, 0.5, 0.0), Vec3(0.5, 0.5, 0.0), dt=0.033)
    assert sample.motion == Motion.HOLD
    assert sample.speed == pytest.approx(0.0)


def test_swipe_on_fast_horizontal() -> None:
    sample = classify_motion(Vec3(0.2, 0.5, 0.0), Vec3(0.6, 0.5, 0.0), dt=0.1)
    assert sample.motion == Motion.SWIPE
    assert sample.velocity.x == pytest.approx(4.0)


def test_swipe_sign_negative_when_moving_left() -> None:
    sample = classify_motion(Vec3(0.6, 0.5, 0.0), Vec3(0.2, 0.5, 0.0), dt=0.1)
    assert sample.motion == Motion.SWIPE
    assert sample.velocity.x < 0


def test_none_when_moderate_vertical() -> None:
    sample = classify_motion(Vec3(0.5, 0.2, 0.0), Vec3(0.5, 0.5, 0.0), dt=0.1)
    assert sample.motion == Motion.NONE


def test_zero_dt_does_not_divide_by_zero() -> None:
    sample = classify_motion(Vec3(0.5, 0.5, 0.0), Vec3(0.5, 0.5, 0.0), dt=0.0)
    assert sample.motion == Motion.HOLD

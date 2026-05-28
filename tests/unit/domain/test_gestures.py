from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.domain.gestures import GestureEvent, GestureParams, Vec3


def test_vec3_defaults() -> None:
    assert Vec3() == Vec3(0.0, 0.0, 0.0)


def test_gesture_event_fields() -> None:
    ev = GestureEvent(
        gesture="pinch",
        phase="start",
        hands=1,
        params=GestureParams(points=(Vec3(0.5, 0.5, 0.0),)),
        ts=1.0,
    )
    assert ev.gesture == "pinch"
    assert ev.params.points[0].x == 0.5


def test_gesture_event_frozen() -> None:
    ev = GestureEvent(gesture="none", phase="idle", hands=0, params=GestureParams(), ts=0.0)
    with pytest.raises(FrozenInstanceError):
        ev.gesture = "x"  # type: ignore[misc]

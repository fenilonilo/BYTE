from __future__ import annotations

import pytest

from gesture_service.events import GestureEvent, GestureParams, Vec3


def test_vec3_defaults_to_zero() -> None:
    v = Vec3()
    assert (v.x, v.y, v.z) == (0.0, 0.0, 0.0)


def test_gesture_params_defaults() -> None:
    p = GestureParams()
    assert p.points == ()
    assert p.vector == Vec3()
    assert p.center == Vec3()
    assert p.radius == 0.0
    assert p.magnitude == 0.0


def test_gesture_event_fields() -> None:
    ev = GestureEvent(
        gesture="pinch",
        phase="start",
        hands=1,
        params=GestureParams(points=(Vec3(0.5, 0.5, 0.0),)),
        ts=123.0,
    )
    assert ev.gesture == "pinch"
    assert ev.phase == "start"
    assert ev.hands == 1
    assert ev.params.points[0] == Vec3(0.5, 0.5, 0.0)
    assert ev.ts == 123.0


def test_gesture_event_is_frozen() -> None:
    ev = GestureEvent(gesture="none", phase="idle", hands=0, params=GestureParams(), ts=0.0)
    with pytest.raises(Exception):
        ev.gesture = "x"  # type: ignore[misc]

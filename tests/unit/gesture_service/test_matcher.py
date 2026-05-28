from __future__ import annotations

from gesture_service.events import Vec3
from gesture_service.matcher import GestureMatcher, HandFrame
from gesture_service.motion import Motion, MotionSample
from gesture_service.pose import Pose


def _still() -> MotionSample:
    return MotionSample(Motion.HOLD, Vec3(), 0.0)


def _swipe(vx: float) -> MotionSample:
    return MotionSample(Motion.SWIPE, Vec3(vx, 0.0, 0.0), abs(vx))


def _hand(
    pose: Pose, cx: float, cy: float, handed: str, motion: MotionSample | None = None
) -> HandFrame:
    return HandFrame(pose=pose, center=Vec3(cx, cy, 0.0), motion=motion or _still(), handedness=handed)


def test_no_hands_returns_none() -> None:
    m = GestureMatcher()
    assert m.update([], now=0.0) is None


def test_pinch_emits_start_then_hold() -> None:
    m = GestureMatcher()
    hand = _hand(Pose.PINCH, 0.5, 0.5, "right")
    first = m.update([hand], now=0.0)
    second = m.update([hand], now=0.1)
    assert first is not None and first.gesture == "pinch" and first.phase == "start"
    assert second is not None and second.gesture == "pinch" and second.phase == "hold"
    assert first.hands == 1


def test_sustained_emits_end_when_released() -> None:
    m = GestureMatcher()
    hand = _hand(Pose.PINCH, 0.5, 0.5, "right")
    m.update([hand], now=0.0)
    end = m.update([], now=0.2)
    assert end is not None and end.gesture == "pinch" and end.phase == "end"


def test_swipe_emits_instant_once() -> None:
    m = GestureMatcher()
    hand = _hand(Pose.OPEN, 0.5, 0.5, "right", motion=_swipe(3.0))
    first = m.update([hand], now=0.0)
    second = m.update([hand], now=0.05)
    assert first is not None and first.gesture == "swipe" and first.phase == "instant"
    assert first.params.vector.x > 0
    assert second is None


def test_freeze_both_fists_instant() -> None:
    m = GestureMatcher()
    left = _hand(Pose.FIST, 0.4, 0.5, "left")
    right = _hand(Pose.FIST, 0.6, 0.5, "right")
    ev = m.update([left, right], now=0.0)
    assert ev is not None and ev.gesture == "freeze" and ev.phase == "instant" and ev.hands == 2


def test_portal_both_open_in_range() -> None:
    m = GestureMatcher()
    left = _hand(Pose.OPEN, 0.3, 0.5, "left")
    right = _hand(Pose.OPEN, 0.7, 0.5, "right")
    ev = m.update([left, right], now=0.0)
    assert ev is not None and ev.gesture == "portal" and ev.phase == "start"
    assert ev.params.center.x == 0.5
    assert ev.params.radius > 0


def test_orbit_one_pinch_other_moving() -> None:
    m = GestureMatcher()
    anchor = _hand(Pose.PINCH, 0.4, 0.5, "left")
    free = _hand(
        Pose.OPEN, 0.6, 0.5, "right", motion=MotionSample(Motion.NONE, Vec3(0.0, 0.5, 0.0), 0.5)
    )
    ev = m.update([anchor, free], now=0.0)
    assert ev is not None and ev.gesture == "orbit" and ev.phase == "start"
    assert ev.params.center.x == 0.4

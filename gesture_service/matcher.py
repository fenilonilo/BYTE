from __future__ import annotations

from dataclasses import dataclass

from gesture_service.config import Thresholds
from gesture_service.events import GestureEvent, GestureParams, Vec3
from gesture_service.motion import Motion, MotionSample
from gesture_service.pose import Pose

INSTANT_GESTURES = frozenset({"swipe", "freeze"})

_ONE_HAND = 1
_TWO_HANDS = 2


@dataclass(frozen=True, slots=True)
class HandFrame:
    pose: Pose
    center: Vec3
    motion: MotionSample
    handedness: str


def _distance(a: Vec3, b: Vec3) -> float:
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2) ** 0.5


class GestureMatcher:
    def __init__(self, thresholds: Thresholds | None = None) -> None:
        self._t = thresholds or Thresholds()
        self._current: str | None = None
        self._last_instant: dict[str, float] = {}

    def update(self, hands: list[HandFrame], now: float) -> GestureEvent | None:
        raw = self._classify(hands)
        name = raw[0] if raw else None
        hand_count = len(hands)

        if name != self._current:
            ended = self._end_event(now) if self._is_sustained(self._current) else None
            self._current = name
            if name is None:
                return ended
            params = raw[1]  # type: ignore[index]
            if name in INSTANT_GESTURES:
                last = self._last_instant.get(name, 0.0)
                if now - last < self._t.instant_cooldown_s:
                    return None
                self._last_instant[name] = now
                return GestureEvent(gesture=name, phase="instant", hands=hand_count, params=params, ts=now)
            return GestureEvent(gesture=name, phase="start", hands=hand_count, params=params, ts=now)

        if name is None:
            return None
        if name in INSTANT_GESTURES:
            return None
        params = raw[1]  # type: ignore[index]
        return GestureEvent(gesture=name, phase="hold", hands=hand_count, params=params, ts=now)

    def _is_sustained(self, name: str | None) -> bool:
        return name is not None and name not in INSTANT_GESTURES

    def _end_event(self, now: float) -> GestureEvent:
        return GestureEvent(
            gesture=self._current or "none",
            phase="end",
            hands=0,
            params=GestureParams(),
            ts=now,
        )

    def _classify(self, hands: list[HandFrame]) -> tuple[str, GestureParams] | None:
        if len(hands) == _ONE_HAND:
            return self._classify_one(hands[0])
        if len(hands) == _TWO_HANDS:
            return self._classify_two(hands[0], hands[1])
        return None

    def _classify_one(self, h: HandFrame) -> tuple[str, GestureParams] | None:
        if h.pose == Pose.PINCH:
            return "pinch", GestureParams(points=(h.center,))
        if h.pose == Pose.OPEN and h.motion.motion == Motion.SWIPE:
            sign = 1.0 if h.motion.velocity.x >= 0 else -1.0
            return "swipe", GestureParams(vector=Vec3(sign, 0.0, 0.0), magnitude=h.motion.speed)
        return None

    def _classify_two(self, a: HandFrame, b: HandFrame) -> tuple[str, GestureParams] | None:
        if a.pose == Pose.FIST and b.pose == Pose.FIST:
            return "freeze", GestureParams(points=(a.center, b.center))

        pinching = [h for h in (a, b) if h.pose == Pose.PINCH]
        if len(pinching) == 1:
            anchor = pinching[0]
            free = b if anchor is a else a
            if free.motion.speed > self._t.orbit_move_speed:
                return "orbit", GestureParams(center=anchor.center, points=(free.center,))

        if a.pose == Pose.OPEN and b.pose == Pose.OPEN:
            dist = _distance(a.center, b.center)
            y_diff = abs(a.center.y - b.center.y)
            if self._t.portal_near <= dist <= self._t.portal_far and y_diff < self._t.portal_y_tol:
                center = Vec3((a.center.x + b.center.x) / 2, (a.center.y + b.center.y) / 2, 0.0)
                return "portal", GestureParams(center=center, radius=dist / 2)
        return None

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from gesture_service.config import Thresholds
from gesture_service.events import Vec3

_DEFAULTS = Thresholds()


class Motion(str, Enum):
    NONE = "none"
    HOLD = "hold"
    SWIPE = "swipe"


@dataclass(frozen=True, slots=True)
class MotionSample:
    motion: Motion
    velocity: Vec3
    speed: float


def classify_motion(
    prev: Vec3, curr: Vec3, dt: float, thresholds: Thresholds = _DEFAULTS
) -> MotionSample:
    dt = max(dt, 1e-3)
    vx = (curr.x - prev.x) / dt
    vy = (curr.y - prev.y) / dt
    vz = (curr.z - prev.z) / dt
    speed = (vx * vx + vy * vy + vz * vz) ** 0.5
    velocity = Vec3(vx, vy, vz)

    if abs(vx) > thresholds.swipe_speed and abs(vx) > abs(vy):
        return MotionSample(Motion.SWIPE, velocity, speed)
    if speed < thresholds.hold_speed:
        return MotionSample(Motion.HOLD, velocity, speed)
    return MotionSample(Motion.NONE, velocity, speed)

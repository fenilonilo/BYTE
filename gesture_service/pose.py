from __future__ import annotations

from enum import StrEnum

from gesture_service.config import Thresholds
from gesture_service.landmarks import HandLandmarks, distance

THUMB_TIP, INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP = 4, 8, 12, 16, 20
INDEX_PIP, MIDDLE_PIP, RING_PIP, PINKY_PIP = 6, 10, 14, 18

_DEFAULTS = Thresholds()


class Pose(StrEnum):
    NONE = "none"
    FIST = "fist"
    OPEN = "open"
    PINCH = "pinch"
    POINT = "point"


def _curled(tip_y: float, pip_y: float) -> bool:
    return tip_y > pip_y  # image coords: tip below pip => finger curled


def classify_pose(hand: HandLandmarks, thresholds: Thresholds = _DEFAULTS) -> Pose:
    p = hand.points
    if distance(p[THUMB_TIP], p[INDEX_TIP]) < thresholds.pinch_dist:
        return Pose.PINCH

    index_c = _curled(p[INDEX_TIP].y, p[INDEX_PIP].y)
    middle_c = _curled(p[MIDDLE_TIP].y, p[MIDDLE_PIP].y)
    ring_c = _curled(p[RING_TIP].y, p[RING_PIP].y)
    pinky_c = _curled(p[PINKY_TIP].y, p[PINKY_PIP].y)

    if index_c and middle_c and ring_c and pinky_c:
        return Pose.FIST
    if not (index_c or middle_c or ring_c or pinky_c):
        return Pose.OPEN
    if not index_c and middle_c and ring_c and pinky_c:
        return Pose.POINT
    return Pose.NONE

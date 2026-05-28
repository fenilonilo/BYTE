from __future__ import annotations

from gesture_service.landmarks import HandLandmarks, Landmark
from gesture_service.pose import Pose, classify_pose


def make_hand(
    *,
    index_curled: bool,
    middle_curled: bool,
    ring_curled: bool,
    pinky_curled: bool,
    pinch: bool = False,
    cx: float = 0.5,
    cy: float = 0.5,
    handedness: str = "right",
) -> HandLandmarks:
    """Build 21 landmarks. Extended finger: tip above pip (tip.y < pip.y).
    Curled finger: tip below pip (tip.y > pip.y). Image coords: y grows down.
    """
    pts = [Landmark(cx, cy, 0.0) for _ in range(21)]
    pts[9] = Landmark(cx, cy, 0.0)  # hand center
    pts[4] = Landmark(cx, cy, 0.0)  # thumb tip

    fingers = {
        "index": (8, 6),
        "middle": (12, 10),
        "ring": (16, 14),
        "pinky": (20, 18),
    }
    curl_flags = {
        "index": index_curled,
        "middle": middle_curled,
        "ring": ring_curled,
        "pinky": pinky_curled,
    }
    for name, (tip, pip) in fingers.items():
        pts[pip] = Landmark(cx, cy, 0.0)
        offset = 0.1 if curl_flags[name] else -0.1
        pts[tip] = Landmark(cx, cy + offset, 0.0)

    if pinch:
        pts[8] = Landmark(cx + 0.02, cy, 0.0)
        pts[4] = Landmark(cx, cy, 0.0)
    else:
        pts[4] = Landmark(cx + 0.3, cy, 0.0)

    return HandLandmarks(points=tuple(pts), handedness=handedness)


def test_open_hand() -> None:
    hand = make_hand(index_curled=False, middle_curled=False, ring_curled=False, pinky_curled=False)
    assert classify_pose(hand) == Pose.OPEN


def test_fist() -> None:
    hand = make_hand(index_curled=True, middle_curled=True, ring_curled=True, pinky_curled=True)
    assert classify_pose(hand) == Pose.FIST


def test_pinch_takes_priority() -> None:
    hand = make_hand(
        index_curled=False, middle_curled=False, ring_curled=False, pinky_curled=False, pinch=True
    )
    assert classify_pose(hand) == Pose.PINCH


def test_point_index_only_extended() -> None:
    hand = make_hand(index_curled=False, middle_curled=True, ring_curled=True, pinky_curled=True)
    assert classify_pose(hand) == Pose.POINT


def test_mixed_is_none() -> None:
    hand = make_hand(index_curled=False, middle_curled=False, ring_curled=True, pinky_curled=False)
    assert classify_pose(hand) == Pose.NONE

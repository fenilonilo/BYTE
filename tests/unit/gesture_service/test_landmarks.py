from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from gesture_service.landmarks import HandLandmarks, Landmark, distance, hand_center


def test_distance_euclidean() -> None:
    a = Landmark(0.0, 0.0, 0.0)
    b = Landmark(3.0, 4.0, 0.0)
    assert distance(a, b) == pytest.approx(5.0)


def test_hand_center_is_landmark_9() -> None:
    pts = tuple(Landmark(float(i), 0.0, 0.0) for i in range(21))
    hand = HandLandmarks(points=pts, handedness="right")
    assert hand_center(hand) == Landmark(9.0, 0.0, 0.0)


def test_landmark_is_frozen() -> None:
    lm = Landmark(1.0, 2.0, 3.0)
    with pytest.raises(FrozenInstanceError):
        lm.x = 9.0  # type: ignore[misc]

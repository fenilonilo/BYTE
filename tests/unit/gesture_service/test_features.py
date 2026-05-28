from __future__ import annotations

import pytest

from gesture_service.features import feature_vector
from gesture_service.landmarks import HandLandmarks, Landmark


def _hand(offset: float) -> HandLandmarks:
    pts = tuple(Landmark(0.1 * i + offset, 0.1 * i + offset, 0.0) for i in range(21))
    return HandLandmarks(points=pts, handedness="right")


def test_vector_length_is_63() -> None:
    assert len(feature_vector(_hand(0.0))) == 63


def test_translation_invariant() -> None:
    a = feature_vector(_hand(0.0))
    b = feature_vector(_hand(0.3))
    for x, y in zip(a, b, strict=True):
        assert x == pytest.approx(y, abs=1e-6)

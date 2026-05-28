from __future__ import annotations

from gesture_service.knn import KnnClassifier


def test_classifies_nearest_label() -> None:
    clf = KnnClassifier(threshold=0.5)
    clf.add("fist", (0.0, 0.0, 0.0))
    clf.add("open", (10.0, 10.0, 10.0))
    assert clf.classify((0.1, 0.1, 0.1)) == "fist"
    assert clf.classify((9.9, 9.9, 9.9)) == "open"


def test_returns_none_when_far() -> None:
    clf = KnnClassifier(threshold=0.5)
    clf.add("fist", (0.0, 0.0, 0.0))
    assert clf.classify((50.0, 50.0, 50.0)) is None


def test_empty_classifier_returns_none() -> None:
    assert KnnClassifier(threshold=0.5).classify((0.0,)) is None

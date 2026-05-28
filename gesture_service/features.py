from __future__ import annotations

from gesture_service.landmarks import HandLandmarks, distance

WRIST = 0
MIDDLE_MCP = 9


def feature_vector(hand: HandLandmarks) -> tuple[float, ...]:
    """Translation- and scale-invariant 63-d vector: each landmark relative to
    the wrist, divided by hand size (wrist->middle-MCP distance)."""
    p = hand.points
    origin = p[WRIST]
    scale = distance(p[WRIST], p[MIDDLE_MCP]) or 1.0
    out: list[float] = []
    for lm in p:
        out.append((lm.x - origin.x) / scale)
        out.append((lm.y - origin.y) / scale)
        out.append((lm.z - origin.z) / scale)
    return tuple(out)

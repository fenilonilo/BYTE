from __future__ import annotations

from dataclasses import dataclass

HAND_CENTER_INDEX = 9  # middle-finger MCP


@dataclass(frozen=True, slots=True)
class Landmark:
    x: float
    y: float
    z: float


@dataclass(frozen=True, slots=True)
class HandLandmarks:
    points: tuple[Landmark, ...]  # 21 landmarks
    handedness: str  # 'left' | 'right'


def distance(a: Landmark, b: Landmark) -> float:
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2) ** 0.5


def hand_center(hand: HandLandmarks) -> Landmark:
    return hand.points[HAND_CENTER_INDEX]

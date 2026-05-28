from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Vec3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass(frozen=True, slots=True)
class GestureParams:
    points: tuple[Vec3, ...] = ()
    vector: Vec3 = field(default_factory=Vec3)
    center: Vec3 = field(default_factory=Vec3)
    radius: float = 0.0
    magnitude: float = 0.0


@dataclass(frozen=True, slots=True)
class GestureEvent:
    gesture: str
    phase: str   # 'start' | 'hold' | 'end' | 'instant' | 'idle'
    hands: int   # 0 | 1 | 2
    params: GestureParams
    ts: float

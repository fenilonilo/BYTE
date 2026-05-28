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
    phase: str
    hands: int
    params: GestureParams
    ts: float


@dataclass(frozen=True, slots=True)
class Binding:
    effect: str
    action: str | None
    action_params: dict[str, object]

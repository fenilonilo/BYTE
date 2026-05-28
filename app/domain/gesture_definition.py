from __future__ import annotations

from dataclasses import dataclass

from app.domain.gestures import Binding


@dataclass(frozen=True, slots=True)
class PoseSpec:
    shape: str   # 'fist'|'open'|'pinch'|'point' or a custom template label
    hands: int


@dataclass(frozen=True, slots=True)
class MotionSpec:
    type: str    # 'hold'|'swipe'|'circle'|'approach'|'none'
    params: dict[str, object]


@dataclass(frozen=True, slots=True)
class GestureDefinition:
    id: str
    name: str
    pose: PoseSpec
    motion: MotionSpec
    binding: Binding

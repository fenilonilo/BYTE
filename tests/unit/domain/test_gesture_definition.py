from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.domain.gesture_definition import GestureDefinition, MotionSpec, PoseSpec
from app.domain.gestures import Binding


def _def() -> GestureDefinition:
    return GestureDefinition(
        id="punho_duplo",
        name="Punho duplo",
        pose=PoseSpec(shape="fist", hands=2),
        motion=MotionSpec(type="hold", params={}),
        binding=Binding(effect="freeze", action="swap_model", action_params={"model": "gemini"}),
    )


def test_fields() -> None:
    d = _def()
    assert d.id == "punho_duplo"
    assert d.pose.shape == "fist"
    assert d.pose.hands == 2
    assert d.motion.type == "hold"
    assert d.binding.effect == "freeze"


def test_frozen() -> None:
    d = _def()
    with pytest.raises(FrozenInstanceError):
        d.id = "x"  # type: ignore[misc]

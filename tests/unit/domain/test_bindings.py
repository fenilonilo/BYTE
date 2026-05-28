from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.domain.gestures import Binding


def test_binding_fields() -> None:
    b = Binding(effect="freeze", action="swap_model", action_params={"model": "gemini"})
    assert b.effect == "freeze"
    assert b.action == "swap_model"
    assert b.action_params == {"model": "gemini"}


def test_binding_action_optional() -> None:
    b = Binding(effect="attract", action=None, action_params={})
    assert b.action is None


def test_binding_frozen() -> None:
    b = Binding(effect="freeze", action=None, action_params={})
    with pytest.raises(FrozenInstanceError):
        b.effect = "x"  # type: ignore[misc]

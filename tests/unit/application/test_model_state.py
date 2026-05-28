from __future__ import annotations

from app.application.model_state import ModelState


def test_default_active_is_none() -> None:
    assert ModelState().active is None


def test_set_active() -> None:
    state = ModelState()
    state.active = "gemini"
    assert state.active == "gemini"

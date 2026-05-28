from __future__ import annotations

import pytest

from app.adapters.actions.swap_model import SwapModelAction
from app.application.model_state import ModelState


@pytest.mark.asyncio
async def test_swap_sets_active_model() -> None:
    state = ModelState()
    action = SwapModelAction(state)
    await action.execute({"model": "gemini"})
    assert state.active == "gemini"


@pytest.mark.asyncio
async def test_swap_ignores_missing_model() -> None:
    state = ModelState(active="groq")
    action = SwapModelAction(state)
    await action.execute({})
    assert state.active == "groq"

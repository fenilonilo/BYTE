from __future__ import annotations

from typing import TYPE_CHECKING

from app.ports.action import ActionPort

if TYPE_CHECKING:
    from app.application.model_state import ModelState


class SwapModelAction(ActionPort):
    def __init__(self, model_state: ModelState) -> None:
        self._state = model_state

    async def execute(self, params: dict[str, object]) -> None:
        model = params.get("model")
        if isinstance(model, str) and model:
            self._state.active = model

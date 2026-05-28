from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.ports.gesture_def_repo import GestureDefinitionRepositoryPort


class DeleteGestureDefinition:
    def __init__(self, repo: GestureDefinitionRepositoryPort) -> None:
        self._repo = repo

    async def execute(self, def_id: str) -> None:
        await self._repo.delete(def_id)

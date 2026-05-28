from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.gesture_definition import GestureDefinition
    from app.ports.gesture_def_repo import GestureDefinitionRepositoryPort


class ListGestureDefinitions:
    def __init__(self, repo: GestureDefinitionRepositoryPort) -> None:
        self._repo = repo

    async def execute(self) -> tuple[GestureDefinition, ...]:
        return await self._repo.list_all()

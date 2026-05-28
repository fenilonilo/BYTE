from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain.exceptions import DomainError

if TYPE_CHECKING:
    from app.domain.gesture_definition import GestureDefinition
    from app.ports.gesture_def_repo import GestureDefinitionRepositoryPort


class SaveGestureDefinition:
    def __init__(self, repo: GestureDefinitionRepositoryPort) -> None:
        self._repo = repo

    async def execute(self, definition: GestureDefinition) -> None:
        if not definition.id.strip():
            raise DomainError("GestureDefinition id must not be empty")
        await self._repo.save(definition)

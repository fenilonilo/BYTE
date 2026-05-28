from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.gesture_definition import GestureDefinition


class GestureDefinitionRepositoryPort(ABC):
    @abstractmethod
    async def list_all(self) -> tuple[GestureDefinition, ...]: ...

    @abstractmethod
    async def get(self, def_id: str) -> GestureDefinition | None: ...

    @abstractmethod
    async def save(self, definition: GestureDefinition) -> None: ...

    @abstractmethod
    async def delete(self, def_id: str) -> None: ...

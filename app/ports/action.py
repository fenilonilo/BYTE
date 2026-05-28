from __future__ import annotations

from abc import ABC, abstractmethod


class ActionPort(ABC):
    @abstractmethod
    async def execute(self, params: dict[str, object]) -> None: ...

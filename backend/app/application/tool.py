from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.domain.tools import ToolSpec


class Tool(ABC):
    """Application code the model can call. It talks to the world only through ports."""

    spec: ToolSpec

    @abstractmethod
    async def execute(self, args: Mapping[str, object], key: str) -> str:
        """`key` is an idempotency key: the same key must never apply the change twice."""

    def summarize(self, args: Mapping[str, object]) -> str:
        """Code-generated, human-readable description used to ask for confirmation."""
        return self.spec.name

    def needs_confirmation(self, args: Mapping[str, object]) -> bool:
        """Static by default. Override when only some calls of the tool are sensitive."""
        return self.spec.requires_confirmation

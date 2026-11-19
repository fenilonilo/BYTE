from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


class EmbedderPort(ABC):
    """Turns text into vectors. Vectors of different models are never compared."""

    @property
    @abstractmethod
    def model(self) -> str:
        """Name of the embedding model; stored next to every vector it produced."""

    @abstractmethod
    async def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        """One vector per text, in order. Raises KnowledgeError."""

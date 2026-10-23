from __future__ import annotations

import hashlib
import math
from typing import TYPE_CHECKING

from app.ports.embedder import EmbedderPort

if TYPE_CHECKING:
    from collections.abc import Sequence


def fake_vector(text: str, dims: int = 16) -> tuple[float, ...]:
    """Deterministic, normalised: the same text always gets the same vector."""
    digest = hashlib.sha256(text.encode()).digest()
    raw = [digest[i % len(digest)] - 127.5 for i in range(dims)]
    norm = math.sqrt(sum(v * v for v in raw))
    return tuple(v / norm for v in raw)


class FakeEmbedder(EmbedderPort):
    def __init__(self, model: str = "fake", dims: int = 16) -> None:
        self._model = model
        self._dims = dims
        self.calls = 0

    @property
    def model(self) -> str:
        return self._model

    async def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        self.calls += 1
        return tuple(fake_vector(t, self._dims) for t in texts)

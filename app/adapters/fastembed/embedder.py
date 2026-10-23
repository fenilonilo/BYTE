from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING

from fastembed import TextEmbedding

from app.domain.exceptions import KnowledgeError
from app.ports.embedder import EmbedderPort

if TYPE_CHECKING:
    from collections.abc import Sequence


class FastEmbedder(EmbedderPort):
    """Local ONNX embeddings on the CPU. The model downloads once into `cache_dir`."""

    def __init__(self, model: str, cache_dir: str) -> None:
        self._model = model
        self._cache_dir = cache_dir
        self._engine: TextEmbedding | None = None
        self._lock = threading.Lock()

    @property
    def model(self) -> str:
        return self._model

    async def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        return await asyncio.to_thread(self._embed, list(texts))

    def _embed(self, texts: list[str]) -> tuple[tuple[float, ...], ...]:
        try:
            with self._lock:  # loading is slow: never twice, and one ONNX session at a time
                if self._engine is None:
                    self._engine = TextEmbedding(self._model, cache_dir=self._cache_dir)
                return tuple(tuple(float(x) for x in v) for v in self._engine.embed(texts))
        except Exception as exc:
            raise KnowledgeError("embedding failed") from exc

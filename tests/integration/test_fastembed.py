from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pytest

from app.adapters.fastembed.embedder import FastEmbedder

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.slow]

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


async def test_portuguese_paraphrase_is_closer_than_an_unrelated_sentence(tmp_path: Path) -> None:
    embedder = FastEmbedder(MODEL, str(tmp_path))
    query, paraphrase, other = await embedder.embed(
        [
            "qual banco de dados o projeto usa?",
            "o sistema guarda os dados no PostgreSQL",
            "o gato dorme no sofá",
        ]
    )
    assert len(query) == 384
    assert cosine(query, paraphrase) > cosine(query, other)

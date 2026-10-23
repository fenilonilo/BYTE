from __future__ import annotations

import pytest

from app.adapters.fastembed import embedder as module
from app.domain.exceptions import KnowledgeError


class Exploding:
    def __init__(self, *args: object, **kwargs: object) -> None:
        raise RuntimeError("download failed")


@pytest.mark.unit
async def test_fastembed_wraps_vendor_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "TextEmbedding", Exploding)
    embedder = module.FastEmbedder("m", "cache")
    assert embedder.model == "m"
    with pytest.raises(KnowledgeError) as info:
        await embedder.embed(["oi"])
    assert isinstance(info.value.__cause__, RuntimeError)

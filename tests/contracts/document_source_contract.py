from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from app.ports.documents import DocumentSourcePort


class DocumentSourceContract(ABC):
    """Every DocumentSourcePort adapter must pass this, reading files under `self.root`."""

    root: Path

    @pytest.fixture(autouse=True)
    def _root(self, tmp_path: Path) -> None:
        self.root = tmp_path

    @abstractmethod
    def make(self) -> DocumentSourcePort: ...

    async def test_read_existing_utf8_with_bom(self) -> None:
        (self.root / "CLAUDE.md").write_bytes("﻿# Olá".encode())
        assert await self.make().read(str(self.root / "CLAUDE.md")) == "# Olá"

    async def test_read_missing_is_none(self) -> None:
        assert await self.make().read(str(self.root / "nope.md")) is None

    async def test_reachable_true_for_dir_false_for_missing(self) -> None:
        source = self.make()
        assert await source.reachable(str(self.root))
        assert not await source.reachable(str(self.root / "gone"))

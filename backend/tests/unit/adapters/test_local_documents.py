from __future__ import annotations

import pytest

from app.adapters.files.local_documents import LocalDocuments
from app.domain.exceptions import KnowledgeError
from tests.contracts.document_source_contract import DocumentSourceContract


class TestLocalDocuments(DocumentSourceContract):
    def make(self) -> LocalDocuments:
        return LocalDocuments()

    async def test_unreadable_path_raises_knowledge_error(self) -> None:
        (self.root / "dir.md").mkdir()  # a directory where a file is expected: not "missing"
        with pytest.raises(KnowledgeError):
            await self.make().read(str(self.root / "dir.md"))

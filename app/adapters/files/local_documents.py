from __future__ import annotations

import asyncio
from pathlib import Path

from app.domain.exceptions import KnowledgeError
from app.ports.documents import DocumentSourcePort


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as exc:
        raise KnowledgeError("document could not be read") from exc


class LocalDocuments(DocumentSourcePort):
    async def reachable(self, root: str) -> bool:
        return await asyncio.to_thread(Path(root).is_dir)

    async def read(self, path: str) -> str | None:
        return await asyncio.to_thread(_read, path)

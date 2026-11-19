from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from typing import TYPE_CHECKING, Any

from app.domain.device_grant import DeviceGrant
from app.domain.exceptions import ConfigError
from app.ports.device_grants import DeviceGrantStorePort

if TYPE_CHECKING:
    from pathlib import Path


class JsonDeviceGrantStore(DeviceGrantStorePort):
    """All grants in one JSON file, rewritten atomically on every change."""

    # ponytail: one file for a household's handful of devices; Postgres replaces it behind the port

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()
        try:
            raw: list[dict[str, Any]] = (
                json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
            )
            self._items = {
                g["hash"]: DeviceGrant(
                    g["hash"],
                    datetime.fromisoformat(g["created_at"]),
                    datetime.fromisoformat(g["last_used_at"]),
                )
                for g in raw
            }
        except (ValueError, KeyError, TypeError) as exc:
            # refuse to boot: starting empty would sign every device out without a word
            raise ConfigError(f"unreadable devices file: {path}") from exc

    async def get(self, token_hash: str) -> DeviceGrant | None:
        return self._items.get(token_hash)

    async def put(self, grant: DeviceGrant) -> None:
        self._items[grant.token_hash] = grant
        await self._save()

    async def remove(self, token_hash: str) -> None:
        if self._items.pop(token_hash, None) is not None:
            await self._save()

    async def _save(self) -> None:
        rows = [
            {
                "hash": g.token_hash,
                "created_at": g.created_at.isoformat(),
                "last_used_at": g.last_used_at.isoformat(),
            }
            for g in self._items.values()
        ]
        async with self._lock:
            await asyncio.to_thread(self._write, json.dumps(rows, indent=1))

    def _write(self, text: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, self._path)

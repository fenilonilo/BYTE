from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from typing import TYPE_CHECKING, Any

from app.domain.exceptions import ConfigError, ReminderNotFoundError
from app.domain.reminders import Reminder, ReminderKind
from app.ports.reminders import ReminderStorePort

if TYPE_CHECKING:
    from pathlib import Path


def _encode(r: Reminder) -> dict[str, str | None]:
    return {
        "id": r.id,
        "text": r.text,
        "at": r.at.isoformat(),
        "kind": r.kind.value,
        "expires_at": None if r.expires_at is None else r.expires_at.isoformat(),
    }


def _decode(raw: dict[str, Any]) -> Reminder:
    expires = raw["expires_at"]
    return Reminder(
        id=raw["id"],
        text=raw["text"],
        at=datetime.fromisoformat(raw["at"]),
        kind=ReminderKind(raw["kind"]),
        expires_at=None if expires is None else datetime.fromisoformat(expires),
    )


class JsonReminderStore(ReminderStorePort):
    """The whole list in one JSON file, rewritten atomically on every change."""

    # ponytail: one file, fine for a household's reminders; Postgres replaces it behind the port

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()
        try:
            raw: list[dict[str, Any]] = (
                json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
            )
            self._items = {r.id: r for r in map(_decode, raw)}
        except (ValueError, KeyError, TypeError) as exc:
            # refuse to boot: starting empty would silently drop every pending reminder
            raise ConfigError(f"unreadable reminders file: {path}") from exc

    async def all(self) -> tuple[Reminder, ...]:
        return tuple(sorted(self._items.values(), key=lambda r: r.at))

    async def put(self, reminder: Reminder) -> None:
        self._items[reminder.id] = reminder
        await self._save()

    async def remove(self, reminder_id: str) -> None:
        if self._items.pop(reminder_id, None) is None:
            raise ReminderNotFoundError(f"Unknown reminder: {reminder_id!r}")
        await self._save()

    async def _save(self) -> None:
        text = json.dumps([_encode(r) for r in self._items.values()], ensure_ascii=False)
        async with self._lock:
            await asyncio.to_thread(self._write, text)

    def _write(self, text: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, self._path)

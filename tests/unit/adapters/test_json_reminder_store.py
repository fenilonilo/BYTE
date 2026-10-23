from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.adapters.files.json_reminder_store import JsonReminderStore
from app.domain.exceptions import ConfigError
from tests.contracts.reminder_store_contract import ReminderStoreContract, reminder

if TYPE_CHECKING:
    from pathlib import Path


class TestJsonReminderStore(ReminderStoreContract):
    @pytest.fixture(autouse=True)
    def _dir(self, tmp_path: Path) -> None:
        self.path = tmp_path / "data" / "reminders.json"

    def make(self) -> JsonReminderStore:
        return JsonReminderStore(self.path)

    async def test_survives_a_restart(self) -> None:
        await self.make().put(reminder("a"))
        assert [r.id for r in await self.make().all()] == ["a"]

    def test_corrupt_file_refuses_to_boot(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{not json", encoding="utf-8")
        with pytest.raises(ConfigError, match="reminders"):
            self.make()

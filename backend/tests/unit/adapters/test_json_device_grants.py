from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.adapters.files.json_device_grants import JsonDeviceGrantStore
from app.domain.device_grant import DeviceGrant
from app.domain.exceptions import ConfigError
from tests.contracts.device_grant_store_contract import AT, DeviceGrantStoreContract

if TYPE_CHECKING:
    from pathlib import Path

    from app.ports.device_grants import DeviceGrantStorePort


@pytest.mark.unit
class TestJsonDeviceGrantStore(DeviceGrantStoreContract):
    @pytest.fixture(autouse=True)
    def _dir(self, tmp_path: Path) -> None:  # pyright: ignore[reportUnusedFunction]
        self.path = tmp_path / "data" / "devices.json"

    def make(self) -> DeviceGrantStorePort:
        return JsonDeviceGrantStore(self.path)

    async def test_survives_a_restart(self) -> None:
        await self.make().put(DeviceGrant("h1", AT, AT))
        assert await self.make().get("h1") is not None


@pytest.mark.unit
def test_a_corrupt_file_refuses_to_boot(tmp_path: Path) -> None:
    path = tmp_path / "devices.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError):
        JsonDeviceGrantStore(path)

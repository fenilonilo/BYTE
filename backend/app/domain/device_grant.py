from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime


@dataclass(frozen=True, slots=True)
class DeviceGrant:
    """A device's standing permission to mint access tokens. Only the hash is ever stored."""

    token_hash: str
    created_at: datetime
    last_used_at: datetime

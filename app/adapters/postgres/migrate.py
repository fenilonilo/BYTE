from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

MIGRATIONS = Path(__file__).resolve().parents[3] / "migrations"


def upgrade(url: str) -> None:
    """`alembic upgrade head` against `url`. Sync: call it through `asyncio.to_thread`."""
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    config.attributes["url"] = url  # not set_main_option: "%" in a password breaks interpolation
    command.upgrade(config, "head")

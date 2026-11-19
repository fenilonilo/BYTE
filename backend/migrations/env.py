from __future__ import annotations

import asyncio
import os

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.postgres.schema import metadata


def _url() -> str:
    url = context.config.attributes.get("url")
    return url if isinstance(url, str) else os.environ["BYTE_DATABASE_URL"]


def _run(connection: object) -> None:
    context.configure(connection=connection, target_metadata=metadata)  # pyright: ignore[reportArgumentType]
    with context.begin_transaction():
        context.run_migrations()


async def _online() -> None:
    engine = create_async_engine(_url())
    async with engine.connect() as conn:
        await conn.run_sync(_run)
        await conn.commit()
    await engine.dispose()


asyncio.run(_online())

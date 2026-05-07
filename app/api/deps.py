from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.agent.agno_agent import AgnoAgent
from app.adapters.logging.structlog_logger import StructlogLogger
from app.adapters.repository.postgres_repository import PostgresRepository
from app.config import Settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

    from app.ports.agent import AgentPort
    from app.ports.logger import LoggerPort
    from app.ports.repository import RepositoryPort


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_logger() -> LoggerPort:
    return StructlogLogger()


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url)


@lru_cache
def get_repo() -> RepositoryPort:
    return PostgresRepository(get_engine())


@lru_cache
def get_agent() -> AgentPort:
    return AgnoAgent(get_settings())

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from app.adapters.agent.stub_agent import StubAgent
from app.adapters.logging.structlog_logger import StructlogLogger
from app.adapters.repository.in_memory_repository import InMemoryRepository
from app.application.registry import Registry
from app.config import Settings

if TYPE_CHECKING:
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
def get_repo() -> RepositoryPort:
    return InMemoryRepository()


@lru_cache
def get_agents() -> Registry[AgentPort]:
    registry: Registry[AgentPort] = Registry()
    for segment in get_settings().segments:
        registry.register(segment, StubAgent(segment))
    return registry

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from app.adapters.llm.stub_llm import StubLLM
from app.adapters.logging.structlog_logger import StructlogLogger
from app.adapters.repository.in_memory_repository import InMemoryRepository
from app.config import Settings

if TYPE_CHECKING:
    from app.ports.llm import LLMPort
    from app.ports.logger import LoggerPort
    from app.ports.repository import RepositoryPort


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_logger() -> LoggerPort:
    return StructlogLogger()


@lru_cache
def get_llm() -> LLMPort:
    return StubLLM()


@lru_cache
def get_repo() -> RepositoryPort:
    return InMemoryRepository()

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.actions.open_project import OpenProjectAction
from app.adapters.actions.swap_model import SwapModelAction
from app.adapters.agent.gemini_agno_agent import GeminiAgnoAgent
from app.adapters.agent.groq_agno_agent import GroqAgnoAgent
from app.adapters.agent.routing_agno_agent import RoutingAgnoAgent
from app.adapters.logging.structlog_logger import StructlogLogger
from app.adapters.messaging.evolution_client import EvolutionClient
from app.adapters.shell.windows_shell_adapter import WindowsShellAdapter
from app.adapters.tools.developer_tool import DeveloperToolkit
from app.adapters.tools.filesystem_tool import FilesystemToolkit
from app.application.action_dispatcher import ActionDispatcher
from app.application.binding_resolver import StaticBindingResolver
from app.application.event_bus import InProcessEventBus
from app.application.model_state import ModelState
from app.application.registry import Registry
from app.config import Settings
from app.domain.gestures import Binding

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

    from app.ports.action import ActionPort
    from app.ports.agent import AgentPort
    from app.ports.event_bus import EventBusPort
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
    """Return PostgresRepository, falling back to InMemory when DB is unreachable."""
    import socket

    from sqlalchemy.engine import make_url

    from app.adapters.repository.in_memory_repository import InMemoryRepository

    url = make_url(get_settings().database_url)
    host = url.host or "localhost"
    port = url.port or 5432
    try:
        socket.setdefaulttimeout(1)
        with socket.create_connection((host, port), timeout=1):
            pass
        from app.adapters.repository.postgres_repository import PostgresRepository

        return PostgresRepository(get_engine())
    except OSError:
        return InMemoryRepository()


@lru_cache
def get_shell() -> WindowsShellAdapter:
    return WindowsShellAdapter()


@lru_cache
def get_filesystem_tool() -> FilesystemToolkit:
    settings = get_settings()
    root = Path(settings.workspace_path) if settings.workspace_path else None
    return FilesystemToolkit(workspace_root=root)


@lru_cache
def get_developer_tool() -> DeveloperToolkit:
    settings = get_settings()
    root = Path(settings.workspace_path) if settings.workspace_path else None
    return DeveloperToolkit(
        shell=get_shell(),
        workspace_root=root,
        pycharm_path=settings.pycharm_path,
    )


@lru_cache
def get_agent() -> AgentPort:
    settings = get_settings()
    fs_tool = get_filesystem_tool()
    dev_tool = get_developer_tool()
    return RoutingAgnoAgent(
        groq_agent=GroqAgnoAgent(settings, tools=[fs_tool, dev_tool]),
        gemini_agent=GeminiAgnoAgent(settings),
    )


@lru_cache
def get_event_bus() -> EventBusPort:
    return InProcessEventBus()


@lru_cache
def get_model_state() -> ModelState:
    return ModelState()


@lru_cache
def get_action_dispatcher() -> ActionDispatcher:
    registry: Registry[ActionPort] = Registry()
    registry.register("swap_model", SwapModelAction(get_model_state()))
    registry.register("open_project", OpenProjectAction(get_developer_tool()))

    # Built-in default bindings (Phase 5 config will override this resolver).
    resolver = StaticBindingResolver(
        {
            "freeze": Binding(
                effect="freeze", action="swap_model", action_params={"model": "gemini"}
            ),
            "portal": Binding(
                effect="portal", action="swap_model", action_params={"model": "groq"}
            ),
        }
    )
    return ActionDispatcher(registry=registry, resolver=resolver)


@lru_cache
def get_evolution_client() -> EvolutionClient:
    s = get_settings()
    return EvolutionClient(
        base_url=s.evolution_api_url,
        api_key=s.evolution_api_key,
        instance=s.evolution_instance_name,
    )

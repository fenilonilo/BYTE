from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.api import deps

if TYPE_CHECKING:
    from collections.abc import Iterator

_CACHED = (
    deps.get_settings,
    deps.get_logger,
    deps.get_store,
    deps.get_pending,
    deps.get_light,
    deps.get_climate,
    deps.get_music,
    deps.get_calendar,
    deps.get_expenses,
    deps.get_known_uris,
    deps.get_ducker,
    deps.get_tools,
    deps.get_runner,
    deps.get_openai,
    deps.get_chat_model,
    deps.get_live_slot,
    deps.get_live_port,
)


@pytest.fixture(autouse=True)
def clear_dependency_caches() -> Iterator[None]:
    """`lru_cache` singletons must not leak between tests."""
    for fn in _CACHED:
        fn.cache_clear()
    yield
    for fn in _CACHED:
        fn.cache_clear()

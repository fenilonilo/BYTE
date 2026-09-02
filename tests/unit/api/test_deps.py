from __future__ import annotations

import pytest

from app.api.deps import get_agents, get_settings


@pytest.mark.unit
def test_registry_holds_every_segment_plus_auto() -> None:
    get_settings.cache_clear()
    get_agents.cache_clear()
    agents = get_agents()

    for segment in get_settings().segments:
        assert agents.get(segment) is not None
    assert agents.get("auto") is not None

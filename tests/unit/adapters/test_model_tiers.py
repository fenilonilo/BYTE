from __future__ import annotations

import pytest

from app.adapters.agent.agno_agent import fallbacks_for, resolve_models
from app.config import Settings
from app.domain.exceptions import AgentError


def _settings(**kwargs: object) -> Settings:
    return Settings(_env_file=None, **kwargs)  # type: ignore[arg-type]


@pytest.mark.unit
def test_each_segment_gets_its_tier_model() -> None:
    settings = _settings()
    models = resolve_models(settings)

    assert models["home"][0] == settings.fast_model
    assert models["agenda"][0] == settings.balanced_model
    assert models["finance"][0] == settings.heavy_model
    assert models["auto"][0] == settings.router_model


@pytest.mark.unit
def test_an_error_falls_over_to_another_provider_first() -> None:
    for name, chain in resolve_models(_settings()).items():
        provider = chain[0].split(":")[0]
        assert fallbacks_for(chain).on_error[0].split(":")[0] != provider, name  # type: ignore[union-attr]


@pytest.mark.unit
def test_a_rate_limit_stays_on_the_same_provider_first() -> None:
    for name, chain in resolve_models(_settings()).items():
        provider = chain[0].split(":")[0]
        assert fallbacks_for(chain).on_rate_limit[0].split(":")[0] == provider, name  # type: ignore[union-attr]


@pytest.mark.unit
def test_segment_without_a_tier_fails_loudly() -> None:
    with pytest.raises(AgentError):
        resolve_models(_settings(segments=["home", "garden"]))

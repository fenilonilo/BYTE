from __future__ import annotations

from app.application.binding_resolver import StaticBindingResolver
from app.domain.gestures import Binding


def test_resolves_known_gesture() -> None:
    resolver = StaticBindingResolver(
        {"freeze": Binding(effect="freeze", action="swap_model", action_params={"model": "gemini"})}
    )
    b = resolver.resolve("freeze")
    assert b is not None and b.action == "swap_model"


def test_unknown_gesture_returns_none() -> None:
    resolver = StaticBindingResolver({})
    assert resolver.resolve("nope") is None


def test_lookup_is_case_insensitive() -> None:
    resolver = StaticBindingResolver(
        {"swipe": Binding(effect="wave", action=None, action_params={})}
    )
    assert resolver.resolve("SWIPE") is not None

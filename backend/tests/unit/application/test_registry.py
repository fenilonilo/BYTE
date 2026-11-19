from __future__ import annotations

import pytest

from app.application.registry import Registry
from app.domain.exceptions import RegistryDuplicateError, RegistryKeyError


def test_register_and_get_happy_path() -> None:
    registry: Registry[str] = Registry()
    registry.register("key", "value")
    assert registry.get("key") == "value"


def test_register_duplicate_raises() -> None:
    registry: Registry[str] = Registry()
    registry.register("key", "first")
    with pytest.raises(RegistryDuplicateError, match="key"):
        registry.register("key", "second")


def test_get_missing_key_raises() -> None:
    registry: Registry[str] = Registry()
    with pytest.raises(RegistryKeyError, match="missing"):
        registry.get("missing")


def test_lookup_case_insensitive() -> None:
    registry: Registry[str] = Registry()
    registry.register("Sales", "agent")
    assert registry.get("sales") == "agent"
    assert registry.get("SALES") == "agent"
    assert registry.get("Sales") == "agent"


def test_register_duplicate_case_insensitive() -> None:
    registry: Registry[str] = Registry()
    registry.register("SUPPORT", "agent")
    with pytest.raises(RegistryDuplicateError):
        registry.register("support", "other")


def test_registry_stores_same_instance() -> None:
    class MyService:
        pass

    svc = MyService()
    registry: Registry[MyService] = Registry()
    registry.register("svc", svc)
    assert registry.get("svc") is svc


def test_values_returns_every_registered_instance() -> None:
    registry: Registry[str] = Registry()
    registry.register("a", "one")
    registry.register("B", "two")
    assert registry.values() == ("one", "two")

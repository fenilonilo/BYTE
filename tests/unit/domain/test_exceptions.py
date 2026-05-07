from __future__ import annotations

import pytest

from app.domain.exceptions import (
    DomainError,
    MessageError,
    RegistryDuplicateError,
    RegistryError,
    RegistryKeyError,
)


def test_domain_error_is_exception() -> None:
    assert issubclass(DomainError, Exception)


def test_domain_error_can_be_raised() -> None:
    with pytest.raises(DomainError):
        raise DomainError("something went wrong")


def test_message_error_is_domain_error() -> None:
    assert issubclass(MessageError, DomainError)


def test_registry_error_is_domain_error() -> None:
    assert issubclass(RegistryError, DomainError)


def test_registry_duplicate_error_is_registry_error() -> None:
    assert issubclass(RegistryDuplicateError, RegistryError)


def test_registry_key_error_is_registry_error() -> None:
    assert issubclass(RegistryKeyError, RegistryError)

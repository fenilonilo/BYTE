from __future__ import annotations

import pytest

from app.domain.exceptions import (
    AgentError,
    ClimateError,
    ConfigError,
    DomainError,
    EventNotFoundError,
    LightError,
    LiveSessionError,
    MusicError,
    RegistryDuplicateError,
    RegistryError,
    RegistryKeyError,
    ToolArgumentError,
    UnknownClimateDeviceError,
    UnknownLightDeviceError,
    UnknownMusicDeviceError,
)


def test_domain_error_is_exception() -> None:
    assert issubclass(DomainError, Exception)


def test_domain_error_can_be_raised() -> None:
    with pytest.raises(DomainError):
        raise DomainError("something went wrong")


def test_registry_error_is_domain_error() -> None:
    assert issubclass(RegistryError, DomainError)


def test_registry_duplicate_error_is_registry_error() -> None:
    assert issubclass(RegistryDuplicateError, RegistryError)


def test_registry_key_error_is_registry_error() -> None:
    assert issubclass(RegistryKeyError, RegistryError)


@pytest.mark.parametrize(
    "error",
    [
        AgentError,
        LiveSessionError,
        ConfigError,
        ToolArgumentError,
        EventNotFoundError,
        ClimateError,
        LightError,
        MusicError,
    ],
)
def test_other_errors_are_domain_errors(error: type[DomainError]) -> None:
    assert issubclass(error, DomainError)


@pytest.mark.parametrize(
    ("unknown", "base"),
    [
        (UnknownClimateDeviceError, ClimateError),
        (UnknownLightDeviceError, LightError),
        (UnknownMusicDeviceError, MusicError),
    ],
)
def test_unknown_device_errors_specialise_their_group(
    unknown: type[DomainError], base: type[DomainError]
) -> None:
    assert issubclass(unknown, base)

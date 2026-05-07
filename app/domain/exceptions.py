from __future__ import annotations


class DomainError(Exception):
    """Base for all domain errors."""


class MessageError(DomainError):
    """Errors related to message processing."""


class RegistryError(DomainError):
    """Base for registry errors."""


class RegistryDuplicateError(RegistryError):
    """Raised when registering a key that already exists."""


class RegistryKeyError(RegistryError):
    """Raised when looking up a key that does not exist."""

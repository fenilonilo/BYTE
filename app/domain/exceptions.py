from __future__ import annotations


class DomainError(Exception):
    """Base for all domain errors."""


class RegistryError(DomainError):
    """Base for registry errors."""


class RegistryDuplicateError(RegistryError):
    """Raised when registering a key that already exists."""


class RegistryKeyError(RegistryError):
    """Raised when looking up a key that does not exist."""


class AgentError(DomainError):
    """Raised when an agent fails to produce a reply."""


class ClimateError(DomainError):
    """Raised when an air-conditioner operation is invalid or fails."""


class UnknownClimateDeviceError(ClimateError):
    """Raised when a climate device name is not in the configured list."""


class LightError(DomainError):
    """Raised when a light operation is invalid or fails."""


class UnknownLightDeviceError(LightError):
    """Raised when a light name is not in the configured list."""


class MusicError(DomainError):
    """Raised when a music operation is invalid or fails."""


class UnknownMusicDeviceError(MusicError):
    """Raised when a playback device name is not available."""


class LiveSessionError(DomainError):
    """Raised when a live (voice) session cannot be opened or breaks."""


class ConfigError(DomainError):
    """Raised at boot when settings are invalid."""


class ToolArgumentError(DomainError):
    """Raised when the model passes missing or mistyped tool arguments."""


class EventNotFoundError(DomainError):
    """Raised when a calendar event id does not exist."""

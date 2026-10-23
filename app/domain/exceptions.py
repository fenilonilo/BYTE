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


class MusicOfflineError(MusicError):
    """Raised when no playback device is reachable (offline, closed app, none active)."""


class GuardError(DomainError):
    """Raised when a safety rule refuses a tool call (unknown uri)."""


class UnknownUriError(GuardError, MusicError):
    """Raised when the model asks to play a uri no search or playlist returned."""


class LiveSessionError(DomainError):
    """Raised when a live (voice) session cannot be opened or breaks."""


class ConfigError(DomainError):
    """Raised at boot when settings are invalid."""


class ToolArgumentError(DomainError):
    """Raised when the model passes missing or mistyped tool arguments."""


class EventNotFoundError(DomainError):
    """Raised when a calendar event id does not exist."""


class CalendarError(DomainError):
    """Raised when the calendar service fails or refuses a request."""


class ReminderNotFoundError(DomainError):
    """Raised when a reminder id does not exist."""


class SpeechError(DomainError):
    """Raised when text-to-speech fails."""


def failure_reason(exc: BaseException) -> str:
    """Short, content-free category for logs: guard, offline, validation or upstream."""
    # ponytail: domain validators raise plain LightError/MusicError, so those read as upstream
    if isinstance(exc, GuardError):
        return "guard"
    if isinstance(exc, MusicOfflineError):
        return "offline"
    if isinstance(
        exc,
        ToolArgumentError
        | RegistryKeyError
        | EventNotFoundError
        | ReminderNotFoundError
        | UnknownLightDeviceError
        | UnknownClimateDeviceError
        | UnknownMusicDeviceError,
    ):
        return "validation"
    return "upstream"

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ModelState:
    """Mutable runtime holder for the active model override (set by gestures,
    read by the chat endpoint)."""

    active: str | None = None

from __future__ import annotations

from dataclasses import dataclass

PROJECT_NAME_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


@dataclass(frozen=True, slots=True)
class Project:
    """A registered project: the model names it, the config holds its folder and documents."""

    name: str
    path: str
    docs: tuple[str, ...]

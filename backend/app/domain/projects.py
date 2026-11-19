from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath

PROJECT_NAME_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


@dataclass(frozen=True, slots=True)
class Project:
    """A registered project: the model names it, the config holds its folder and documents."""

    name: str
    path: str
    docs: tuple[str, ...]


def is_inside(path: str) -> bool:
    """A relative path that cannot leave the folder it is joined to (no drive, root or `..`)."""
    win, posix = PureWindowsPath(path), PurePosixPath(path)
    return bool(path.strip()) and not (
        win.is_absolute() or win.anchor or posix.is_absolute() or ".." in win.parts
    )

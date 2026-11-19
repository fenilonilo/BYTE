from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


class ProjectTerminalPort(ABC):
    """One pseudo-terminal process at a time. Bytes in, bytes out: never interpreted."""

    @property
    @abstractmethod
    def alive(self) -> bool: ...

    @abstractmethod
    async def start(
        self, cwd: str, argv: Sequence[str], env: Mapping[str, str], cols: int, rows: int
    ) -> None:
        """Spawn `argv` in `cwd`. Raises ProjectError when it cannot."""

    @abstractmethod
    async def write(self, data: bytes) -> None: ...

    @abstractmethod
    async def resize(self, cols: int, rows: int) -> None: ...

    @abstractmethod
    async def read(self) -> bytes:
        """Next output; b"" once the process has ended."""

    @abstractmethod
    async def stop(self) -> None:
        """Kill the whole process tree. Idempotent."""

from __future__ import annotations

from abc import ABC, abstractmethod


class LoggerPort(ABC):
    @abstractmethod
    def debug(self, event: str, **fields: object) -> None: ...

    @abstractmethod
    def info(self, event: str, **fields: object) -> None: ...

    @abstractmethod
    def warning(self, event: str, **fields: object) -> None: ...

    @abstractmethod
    def error(self, event: str, **fields: object) -> None: ...

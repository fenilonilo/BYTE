from __future__ import annotations

from abc import ABC, abstractmethod


class ShellPort(ABC):
    @abstractmethod
    def run(self, command: list[str], cwd: str | None = None) -> str: ...

    @abstractmethod
    def send_to_window(self, window_title: str, text: str) -> None: ...

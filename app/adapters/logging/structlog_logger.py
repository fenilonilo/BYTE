# app/adapters/logging/structlog_logger.py
from __future__ import annotations

import structlog

from app.ports.logger import LoggerPort


class StructlogLogger(LoggerPort):
    def __init__(self) -> None:
        self._logger = structlog.get_logger()

    def debug(self, event: str, **fields: object) -> None:
        self._logger.debug(event, **fields)

    def info(self, event: str, **fields: object) -> None:
        self._logger.info(event, **fields)

    def warning(self, event: str, **fields: object) -> None:
        self._logger.warning(event, **fields)

    def error(self, event: str, **fields: object) -> None:
        self._logger.error(event, **fields)

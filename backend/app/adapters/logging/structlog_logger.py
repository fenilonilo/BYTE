from __future__ import annotations

import logging

import structlog

from app.ports.logger import LoggerPort


def configure_logging(level: str, *, json: bool) -> None:
    """JSON lines for containers, console rendering for a terminal."""
    renderer = structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelNamesMapping()[level]),
    )


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

from __future__ import annotations

import json

import pytest
import structlog

from app.adapters.logging.structlog_logger import StructlogLogger, configure_logging


@pytest.mark.unit
def test_json_mode_emits_one_json_object_per_line(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", json=True)
    StructlogLogger().info("tool.done", tool="list_lights")
    line = capsys.readouterr().out.strip()
    assert json.loads(line) | {"timestamp": "x"} == {
        "event": "tool.done",
        "tool": "list_lights",
        "level": "info",
        "timestamp": "x",
    }
    structlog.reset_defaults()


@pytest.mark.unit
def test_level_filters_lower_severities(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("WARNING", json=True)
    logger = StructlogLogger()
    logger.info("hidden")
    logger.debug("hidden")
    logger.error("shown")
    out = capsys.readouterr().out
    assert "shown" in out
    assert "hidden" not in out
    structlog.reset_defaults()


@pytest.mark.unit
def test_console_mode_is_human_readable(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", json=False)
    StructlogLogger().warning("careful")
    assert "careful" in capsys.readouterr().out
    structlog.reset_defaults()

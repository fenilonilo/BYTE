from __future__ import annotations

from datetime import UTC, datetime

from app.application.prompts import now_line, projects_line


def test_now_line_names_the_weekday_in_portuguese() -> None:
    assert now_line(datetime(2026, 10, 21, 12, 0, tzinfo=UTC)) == (
        "Agora: 2026-10-21T12:00+00:00, quarta-feira."
    )


def test_projects_line_lists_names() -> None:
    assert projects_line(["Byte", "FinFlow"]) == "Projetos: Byte, FinFlow."


def test_projects_line_empty_without_projects() -> None:
    assert projects_line([]) == ""

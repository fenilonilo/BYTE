from __future__ import annotations

from datetime import UTC, datetime

from app.application.prompts import now_line


def test_now_line_names_the_weekday_in_portuguese() -> None:
    assert now_line(datetime(2026, 10, 21, 12, 0, tzinfo=UTC)) == (
        "Agora: 2026-10-21T12:00+00:00, quarta-feira."
    )

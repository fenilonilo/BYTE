from __future__ import annotations

import pytest

from app.domain.affirmation import is_affirmative


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        "sim",
        "Sim!",
        "pode",
        "confirmo",
        "manda ver",
        "sim, pode fazer",
        "claro que sim",
        "OK",
        "pode sim",
    ],
)
def test_affirmative(text: str) -> None:
    assert is_affirmative(text) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "assim",
        "pode deixar",
        "pode esquecer",
        "nem pensar",
        "espera",
        "não",
        "não, cancela",
        "sim, mas depois",
        "que horas são",
        "o jogo começou e eu disse sim para ele agora mesmo",
    ],
)
def test_not_affirmative(text: str) -> None:
    assert is_affirmative(text) is False


@pytest.mark.unit
def test_accents_are_folded() -> None:
    assert is_affirmative("NÃO") is False
    assert is_affirmative("não") is False

from __future__ import annotations

import pytest
from pydantic import SecretStr

from app.api.auth import token_matches

TOKEN = SecretStr("s" * 32)


@pytest.mark.unit
def test_exact_bearer_token_matches() -> None:
    assert token_matches("Bearer " + "s" * 32, TOKEN) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "s" * 32,
        "bearer " + "s" * 32,
        "Bearer " + "s" * 31,
        "Bearer " + "s" * 33,
        "Bearer ",
        "Basic " + "s" * 32,
    ],
)
def test_anything_else_is_rejected(header: str | None) -> None:
    assert token_matches(header, TOKEN) is False

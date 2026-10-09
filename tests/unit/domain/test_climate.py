from __future__ import annotations

import pytest

from app.domain.climate import ClimateChange
from app.domain.exceptions import ClimateError


def test_empty_change_rejected() -> None:
    with pytest.raises(ClimateError):
        ClimateChange()


@pytest.mark.parametrize("temp", [17.0, 31.0, 22.5])
def test_bad_target_rejected(temp: float) -> None:
    with pytest.raises(ClimateError):
        ClimateChange(target_temperature=temp)


def test_bad_timer_rejected() -> None:
    with pytest.raises(ClimateError):
        ClimateChange(stop_in_minutes=-1)


def test_valid_change() -> None:
    assert ClimateChange(target_temperature=22, stop_in_minutes=0).power is None

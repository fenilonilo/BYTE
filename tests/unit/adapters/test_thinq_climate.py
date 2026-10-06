from __future__ import annotations

from app.adapters.thinq.thinq_climate import parse_state, to_payloads
from app.domain.climate import ClimateChange, ClimateMode, FanSpeed


def test_payloads_one_per_resource_power_first() -> None:
    change = ClimateChange(
        target_temperature=22.0,
        power=True,
        mode=ClimateMode.DRY,
        fan_speed=FanSpeed.NATURE,
        swing=False,
        power_save=True,
        display_light=False,
        stop_in_minutes=90,
        start_in_minutes=0,
        sleep_in_minutes=15,
    )
    assert to_payloads(change) == [
        {"operation": {"airConOperationMode": "POWER_ON"}},
        {"airConJobMode": {"currentJobMode": "AIR_DRY"}},
        {"temperature": {"targetTemperature": 22.0, "unit": "C"}},
        {"airFlow": {"windStrengthDetail": "NATURE"}},
        {"windDirection": {"rotateUpDown": False}},
        {"powerSave": {"powerSaveEnabled": True}},
        {"display": {"light": "OFF"}},
        {"timer": {"relativeHourToStop": 1, "relativeMinuteToStop": 30}},
        {"timer": {"relativeStartTimer": "UNSET"}},
        {"sleepTimer": {"relativeHourToStop": 0, "relativeMinuteToStop": 15}},
    ]


def test_fan_level_uses_wind_strength() -> None:
    assert to_payloads(ClimateChange(fan_speed=FanSpeed.HIGH)) == [
        {"airFlow": {"windStrength": "HIGH"}}
    ]


def test_parse_state() -> None:
    state = parse_state(
        {
            "operation": {"airConOperationMode": "POWER_ON"},
            "airConJobMode": {"currentJobMode": "AIR_DRY"},
            "temperature": {"currentTemperature": 24.5, "targetTemperature": 22},
            "airFlow": {"windStrength": "HIGH", "windStrengthDetail": "NATURE"},
            "windDirection": {"rotateUpDown": True},
            "display": {"light": "OFF"},
            "timer": {
                "relativeStopTimer": "SET",
                "relativeHourToStop": 1,
                "relativeMinuteToStop": 5,
                "relativeStartTimer": "UNSET",
            },
            "sleepTimer": {"relativeStopTimer": "UNSET"},
            "filterInfo": {"usedTime": 720},
            "runState": {"currentState": "NORMAL"},
        }
    )
    assert (state.power, state.mode, state.fan_speed) == (True, ClimateMode.DRY, FanSpeed.NATURE)
    assert (state.target_temperature, state.current_temperature) == (22.0, 24.5)
    assert (state.stop_timer_minutes, state.start_timer_minutes) == (65, None)
    assert (state.swing, state.display_light, state.has_error) == (True, False, False)

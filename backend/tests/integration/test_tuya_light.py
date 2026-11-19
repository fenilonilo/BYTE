from __future__ import annotations

import pytest
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.adapters.tuya.tuya_light import TuyaLight, TuyaLightDevice
from app.config import TuyaLightSettings  # noqa: TC001 - pydantic resolves it at runtime
from app.domain.light import Color, LightChange, LightMode, LightState


class _LampEnv(BaseSettings):
    """Just the lamp config: this test needs neither the API token nor the OpenAI key."""

    model_config = SettingsConfigDict(
        env_prefix="BYTE_", env_file=".env", env_ignore_empty=True, extra="ignore"
    )
    tuya_lights: dict[str, TuyaLightSettings] = {}


LIGHTS = _LampEnv().tuya_lights

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(not LIGHTS, reason="needs BYTE_TUYA_LIGHTS and the lamp on the LAN"),
]


async def test_real_lamp_round_trip() -> None:
    name, cfg = next(iter(LIGHTS.items()))
    light = TuyaLight(
        {name: TuyaLightDevice(cfg.device_id, cfg.address, cfg.local_key.get_secret_value())}
    )
    before: LightState = await light.get_state(name)
    try:
        lit = await light.apply(name, LightChange(color=Color(240, 100, 30)))
        assert (lit.power, lit.mode, lit.color) == (True, LightMode.COLOUR, Color(240, 100, 30))
        dim = await light.apply(name, LightChange(brightness=60))
        assert dim.color.brightness == 60
        white = await light.apply(name, LightChange(brightness=40, color_temperature=20))
        assert (white.mode, white.brightness, white.color_temperature) == (LightMode.WHITE, 40, 20)
        off = await light.apply(name, LightChange(power=False))
        assert off.power is False
    finally:
        await light.apply(
            name,
            LightChange(brightness=before.brightness, color_temperature=before.color_temperature),
        )
        await light.apply(name, LightChange(power=before.power))

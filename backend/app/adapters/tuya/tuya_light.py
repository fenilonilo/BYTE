from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

import tinytuya

from app.domain.exceptions import LightError, UnknownLightDeviceError
from app.domain.light import (
    MAX_SCENE_UNITS,
    Color,
    LightMode,
    LightState,
    SceneTransition,
    SceneUnit,
)
from app.ports.light import LightPort

if TYPE_CHECKING:
    from app.domain.light import LightChange

# Local protocol 3.3 data points of the "dj" light category (confirmed on the real lamp).
# 20 power, 21 mode, 22 white brightness 10-1000, 23 white temperature 0-1000,
# 24 colour 'HHHHSSSSVVVV' (H 0-360, S/V 0-1000), 25 scene, 26 countdown (s), 34 do-not-disturb.
# 27 (music) and 28 (control_data) are write-only streaming channels: not exposed.
_POWER, _MODE, _BRIGHT, _TEMP, _COLOUR, _SCENE, _TIMER, _DND = 20, 21, 22, 23, 24, 25, 26, 34
_MIN_RAW_BRIGHTNESS = 10
_UNIT_HEX = 26
_TRANSITIONS = (SceneTransition.STATIC, SceneTransition.JUMP, SceneTransition.GRADIENT)
_SCENE_NUM = 1

type Dps = dict[int, bool | int | str]


@dataclass(frozen=True, slots=True)
class TuyaLightDevice:
    device_id: str
    address: str
    local_key: str
    version: float = 3.3


def _pct(raw: int) -> int:
    return round(raw / 10)


def _decode_color(hex_value: str) -> Color:
    h, s, v = (int(hex_value[i : i + 4], 16) for i in (0, 4, 8))
    return Color(hue=min(h, 360), saturation=min(_pct(s), 100), brightness=min(_pct(v), 100))


def _decode_scene(hex_value: str) -> tuple[SceneUnit, ...]:
    body = hex_value[2:]
    if len(hex_value) < 2 + _UNIT_HEX or len(body) % _UNIT_HEX:
        return ()
    units: list[SceneUnit] = []
    for i in range(0, len(body), _UNIT_HEX):
        u = body[i : i + _UNIT_HEX]
        h, s, v, bright, temp = (int(u[6 + 4 * k : 10 + 4 * k], 16) for k in range(5))
        units.append(
            SceneUnit(
                transition=_TRANSITIONS[min(int(u[4:6], 16), 2)],
                switch_seconds=min(int(u[0:2], 16), 100),
                gradient_seconds=min(int(u[2:4], 16), 100),
                color=None if h == s == v == 0 else _decode_color(u[6:18]),
                brightness=min(_pct(bright), 100),
                temperature=min(_pct(temp), 100),
            )
        )
    return tuple(units)


def parse_state(dps: dict[str, Any]) -> LightState:
    try:
        scene = _decode_scene(str(dps.get(str(_SCENE), "")))
    except ValueError:
        scene = ()
    try:
        color = _decode_color(str(dps.get(str(_COLOUR), "")))
    except ValueError:
        color = Color(hue=0, saturation=0, brightness=0)
    try:
        mode = LightMode(dps.get(str(_MODE), "white"))
    except ValueError:
        mode = LightMode.WHITE
    return LightState(
        power=bool(dps.get(str(_POWER), False)),
        mode=mode,
        brightness=max(1, _pct(int(dps.get(str(_BRIGHT), 1000)))),
        color_temperature=_pct(int(dps.get(str(_TEMP), 0))),
        color=color,
        scene=scene,
        timer_seconds=int(dps.get(str(_TIMER), 0)),
        do_not_disturb=bool(dps.get(str(_DND), False)),
    )


def _encode_color(color: Color) -> str:
    return f"{color.hue:04x}{color.saturation * 10:04x}{color.brightness * 10:04x}"


def encode_scene(units: tuple[SceneUnit, ...]) -> str:
    if not 1 <= len(units) <= MAX_SCENE_UNITS:
        raise LightError(f"scene needs 1-{MAX_SCENE_UNITS} units")
    parts = [f"{_SCENE_NUM:02x}"]
    for u in units:
        parts.append(
            f"{u.switch_seconds:02x}{u.gradient_seconds:02x}{_TRANSITIONS.index(u.transition):02x}"
            f"{_encode_color(u.color) if u.color else '000000000000'}"
            f"{u.brightness * 10:04x}{u.temperature * 10:04x}"
        )
    return "".join(parts)


def to_dps(new: LightState, old: LightState) -> Dps:
    """Only the data points that differ, so an idempotent call writes nothing."""
    out: Dps = {}
    if new.power != old.power:
        out[_POWER] = new.power
    if new.mode != old.mode:
        out[_MODE] = new.mode.value
    if new.brightness != old.brightness:
        out[_BRIGHT] = max(_MIN_RAW_BRIGHTNESS, new.brightness * 10)
    if new.color_temperature != old.color_temperature:
        out[_TEMP] = new.color_temperature * 10
    if new.color != old.color:
        out[_COLOUR] = _encode_color(new.color)
    if new.scene != old.scene:
        out[_SCENE] = encode_scene(new.scene)
    if new.timer_seconds != old.timer_seconds:
        out[_TIMER] = new.timer_seconds
    if new.do_not_disturb != old.do_not_disturb:
        out[_DND] = new.do_not_disturb
    return out


class TuyaLight(LightPort):
    """Tuya Wi-Fi lights over the LAN (no cloud), addressed by a configured name."""

    def __init__(self, devices: dict[str, TuyaLightDevice], timeout_seconds: float = 5.0) -> None:
        self._devices = {name.lower(): d for name, d in devices.items()}
        self._timeout = timeout_seconds
        # The lamp accepts one local connection at a time.
        self._lock = asyncio.Lock()

    def _device(self, name: str) -> TuyaLightDevice:
        try:
            return self._devices[name.lower()]
        except KeyError:
            raise UnknownLightDeviceError(f"unknown light: {name!r}") from None

    def _connect(self, device: TuyaLightDevice) -> Any:  # noqa: ANN401
        # tinytuya's default (5 tries, 5 s apart) holds an offline lamp for ~50 s, and /state
        # with it: the panel's sign-in waits on that reply.
        conn = tinytuya.Device(
            device.device_id,
            device.address,
            device.local_key,
            version=device.version,
            connection_timeout=self._timeout,
            connection_retry_limit=1,
        )
        conn.set_socketTimeout(self._timeout)
        return conn

    @staticmethod
    def _checked(reply: Any) -> dict[str, Any]:  # noqa: ANN401
        # tinytuya reports failures as {"Error": ...} instead of raising.
        if not isinstance(reply, dict):
            raise LightError(f"tuya request failed: {reply!r}")
        body = cast("dict[str, Any]", reply)
        if "Error" in body:
            raise LightError(f"tuya request failed: {body['Error']}")
        return body

    def _read(self, device: TuyaLightDevice) -> LightState:
        reply = self._checked(self._connect(device).status())
        return parse_state(reply.get("dps", {}))

    def _write(self, device: TuyaLightDevice, change: LightChange) -> LightState:
        old = self._read(device)
        dps = to_dps(change.apply_to(old), old)
        if dps:
            self._checked(self._connect(device).set_multiple_values(dps))
            time.sleep(0.3)  # ponytail: fixed settle delay, poll status if the lamp lags
        return self._read(device)

    async def _run(self, fn: Any, *args: Any) -> LightState:  # noqa: ANN401
        async with self._lock:
            try:
                return await asyncio.to_thread(fn, *args)
            except (OSError, ValueError) as exc:
                raise LightError(f"tuya request failed: {exc}") from exc

    async def devices(self) -> tuple[str, ...]:
        return tuple(self._devices)

    async def get_state(self, device: str) -> LightState:
        return await self._run(self._read, self._device(device))

    async def apply(self, device: str, change: LightChange) -> LightState:
        return await self._run(self._write, self._device(device), change)

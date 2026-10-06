from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import aiohttp
from thinqconnect import ThinQApi, ThinQAPIException

from app.domain.climate import ClimateMode, ClimateState, FanSpeed
from app.domain.exceptions import ClimateError, UnknownClimateDeviceError
from app.ports.climate import ClimatePort

if TYPE_CHECKING:
    from app.domain.climate import ClimateChange

_AC_TYPE = "DEVICE_AIR_CONDITIONER"
_MODE_TO_THINQ = {
    ClimateMode.COOL: "COOL",
    ClimateMode.DRY: "AIR_DRY",
    ClimateMode.FAN: "FAN",
    ClimateMode.AUTO: "AUTO",
}
_MODE_FROM_THINQ = {v: k for k, v in _MODE_TO_THINQ.items()}


def _on_off(value: bool) -> str:
    return "ON" if value else "OFF"


def to_payloads(change: ClimateChange) -> list[dict[str, Any]]:
    """One ThinQ control body per resource; power first so settings land on a running unit."""
    out: list[dict[str, Any]] = []
    if change.power is not None:
        mode = "POWER_ON" if change.power else "POWER_OFF"
        out.append({"operation": {"airConOperationMode": mode}})
    if change.mode is not None:
        out.append({"airConJobMode": {"currentJobMode": _MODE_TO_THINQ[change.mode]}})
    if change.target_temperature is not None:
        out.append({"temperature": {"targetTemperature": change.target_temperature, "unit": "C"}})
    if change.fan_speed is FanSpeed.NATURE:
        out.append({"airFlow": {"windStrengthDetail": "NATURE"}})
    elif change.fan_speed is not None:
        out.append({"airFlow": {"windStrength": change.fan_speed.name}})
    if change.swing is not None:
        out.append({"windDirection": {"rotateUpDown": change.swing}})
    if change.power_save is not None:
        out.append({"powerSave": {"powerSaveEnabled": change.power_save}})
    if change.display_light is not None:
        out.append({"display": {"light": _on_off(change.display_light)}})
    if change.stop_in_minutes is not None:
        out.append(_timer("timer", "Stop", change.stop_in_minutes))
    if change.start_in_minutes is not None:
        out.append(_timer("timer", "Start", change.start_in_minutes))
    if change.sleep_in_minutes is not None:
        out.append(_timer("sleepTimer", "Stop", change.sleep_in_minutes))
    return out


def _timer(resource: str, edge: str, minutes: int) -> dict[str, Any]:
    if minutes == 0:
        return {resource: {f"relative{edge}Timer": "UNSET"}}
    return {
        resource: {
            f"relativeHourTo{edge}": minutes // 60,
            f"relativeMinuteTo{edge}": minutes % 60,
        }
    }


def _remaining(block: dict[str, Any], edge: str) -> int | None:
    if block.get(f"relative{edge}Timer") != "SET":
        return None
    return int(block.get(f"relativeHourTo{edge}", 0)) * 60 + int(
        block.get(f"relativeMinuteTo{edge}", 0)
    )


def parse_state(raw: dict[str, Any]) -> ClimateState:
    temp = raw.get("temperature", {})
    air = raw.get("airFlow", {})
    timer = raw.get("timer", {})
    fan = (
        FanSpeed.NATURE
        if air.get("windStrengthDetail") == "NATURE"
        else FanSpeed[air.get("windStrength", "AUTO")]
    )
    return ClimateState(
        power=raw.get("operation", {}).get("airConOperationMode") == "POWER_ON",
        mode=_MODE_FROM_THINQ.get(
            raw.get("airConJobMode", {}).get("currentJobMode", "COOL"), ClimateMode.COOL
        ),
        target_temperature=float(temp.get("targetTemperature", 0)),
        current_temperature=float(temp.get("currentTemperature", 0)),
        fan_speed=fan,
        swing=bool(raw.get("windDirection", {}).get("rotateUpDown", False)),
        power_save=bool(raw.get("powerSave", {}).get("powerSaveEnabled", False)),
        display_light=raw.get("display", {}).get("light") == "ON",
        stop_timer_minutes=_remaining(timer, "Stop"),
        start_timer_minutes=_remaining(timer, "Start"),
        sleep_timer_minutes=_remaining(raw.get("sleepTimer", {}), "Stop"),
        filter_used_hours=int(raw.get("filterInfo", {}).get("usedTime", 0)),
        has_error=raw.get("runState", {}).get("currentState") == "ERROR",
    )


class ThinQClimate(ClimatePort):
    """LG ThinQ Connect air conditioners, addressed by their app alias."""

    def __init__(self, access_token: str, country_code: str, client_id: str) -> None:
        self._token = access_token
        self._country = country_code
        self._client_id = client_id
        self._ids: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def _call(self, fn: str, *args: Any) -> Any:  # noqa: ANN401
        # ponytail: session per call, share one if latency or rate limits start to matter
        try:
            async with aiohttp.ClientSession() as session:
                api = ThinQApi(session, self._token, self._country, self._client_id)
                return await getattr(api, fn)(*args)
        except (ThinQAPIException, aiohttp.ClientError, TimeoutError) as exc:
            raise ClimateError(f"thinq request failed: {exc}") from exc

    async def _load(self) -> dict[str, str]:
        async with self._lock:
            if not self._ids:
                listed: list[dict[str, Any]] = await self._call("async_get_device_list") or []
                self._ids = {
                    d["deviceInfo"]["alias"].lower(): d["deviceId"]
                    for d in listed
                    if d["deviceInfo"]["deviceType"] == _AC_TYPE
                }
            return self._ids

    async def _device_id(self, device: str) -> str:
        try:
            return (await self._load())[device.lower()]
        except KeyError:
            raise UnknownClimateDeviceError(f"unknown climate device: {device!r}") from None

    async def devices(self) -> tuple[str, ...]:
        return tuple(await self._load())

    async def get_state(self, device: str) -> ClimateState:
        device_id = await self._device_id(device)
        return parse_state(await self._call("async_get_device_status", device_id))

    async def apply(self, device: str, change: ClimateChange) -> ClimateState:
        device_id = await self._device_id(device)
        for payload in to_payloads(change):
            await self._call("async_post_device_control", device_id, payload)
        return parse_state(await self._call("async_get_device_status", device_id))

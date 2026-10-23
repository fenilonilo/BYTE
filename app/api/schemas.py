from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.climate import ClimateMode, FanSpeed
from app.domain.light import LightMode
from app.domain.music import MediaKind, Repeat, Skip
from app.domain.reminders import ReminderKind

MAX_CONTENT_CHARS = 4000


class IncomingMessageSchema(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    content: str = Field(min_length=1, max_length=MAX_CONTENT_CHARS)
    segment: str = "auto"
    conversation_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")
    client: Literal["panel", "api"] = "api"


class PendingConfirmationSchema(BaseModel):
    summary: str


class MessageSchema(BaseModel):
    id: str
    role: str
    content: str
    conversation_id: str
    pending_confirmation: PendingConfirmationSchema | None = None


class LiveStartSchema(BaseModel):
    """First frame a live client sends."""

    model_config = ConfigDict(str_strip_whitespace=True)

    type: Literal["start"]
    segment: str = "auto"
    conversation_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")
    # routing, not security: every client holds the same owner token
    client: Literal["panel", "api"] = "api"


# --- web control panel -----------------------------------------------------------------------


class _Body(BaseModel):
    """Request body: unknown fields are rejected, so no raw id can sneak in."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class _View(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ColorSchema(_View):
    hue: int
    saturation: int
    brightness: int


class LightSchema(_View):
    name: str = ""  # filled by the router: the port state does not carry it
    power: bool
    mode: LightMode
    brightness: int
    color_temperature: int
    color: ColorSchema
    timer_seconds: int
    do_not_disturb: bool


class LightsSchema(BaseModel):
    lights: list[LightSchema]


class ClimateSchema(_View):
    name: str = ""  # filled by the router
    power: bool
    mode: ClimateMode
    target_temperature: float
    current_temperature: float
    fan_speed: FanSpeed
    swing: bool
    power_save: bool
    display_light: bool
    has_error: bool


class ClimatesSchema(BaseModel):
    climates: list[ClimateSchema]


class MusicItemSchema(_View):
    uri: str
    name: str
    kind: MediaKind
    artist: str


class MusicItemsSchema(BaseModel):
    items: list[MusicItemSchema]


class MusicDeviceSchema(_View):
    name: str
    active: bool
    volume: int | None


class MusicDevicesSchema(BaseModel):
    devices: list[MusicDeviceSchema]
    default: str | None


class MusicSchema(_View):
    playing: bool
    item: MusicItemSchema | None
    progress_ms: int
    duration_ms: int
    volume: int
    shuffle: bool
    repeat: Repeat
    device: str


class EventSchema(_View):
    id: str
    title: str
    start: dt.datetime
    duration_minutes: int


class EventsSchema(BaseModel):
    events: list[EventSchema]


class ExpenseSchema(BaseModel):
    amount_cents: int
    category: str
    description: str
    date: dt.date


class ExpensesSchema(BaseModel):
    expenses: list[ExpenseSchema]
    total_cents: int


class ReminderSchema(_View):
    id: str
    text: str
    at: dt.datetime
    kind: ReminderKind


class RemindersSchema(BaseModel):
    reminders: list[ReminderSchema]


class StateSchema(BaseModel):
    lights: list[LightSchema] | None
    climates: list[ClimateSchema] | None
    music: MusicSchema | None
    pending_confirmation: PendingConfirmationSchema | None
    errors: list[str]


class ActionSchema(BaseModel):
    status: Literal["done", "pending_confirmation", "cancelled"]
    message: str = ""
    pending_confirmation: PendingConfirmationSchema | None = None


class LightPatchSchema(_Body):
    power: bool | None = None
    brightness: int | None = Field(default=None, ge=1, le=100)
    color_temperature: int | None = Field(default=None, ge=0, le=100)
    hue: int | None = Field(default=None, ge=0, le=360)
    saturation: int | None = Field(default=None, ge=0, le=100)
    timer_minutes: int | None = Field(default=None, ge=0, le=1440)
    do_not_disturb: bool | None = None


class ClimatePatchSchema(_Body):
    power: bool | None = None
    mode: ClimateMode | None = None
    target_temperature: float | None = Field(default=None, ge=18, le=30)
    fan_speed: FanSpeed | None = None
    swing: bool | None = None
    power_save: bool | None = None


class MusicPlaySchema(_Body):
    uri: str | None = Field(default=None, min_length=1, max_length=200)
    device: str | None = Field(default=None, min_length=1, max_length=64)


class MusicDeviceSelectSchema(_Body):
    name: str = Field(min_length=1, max_length=64)


class MusicControlSchema(_Body):
    paused: bool | None = None
    volume: int | None = Field(default=None, ge=0, le=100)
    shuffle: bool | None = None
    repeat: Repeat | None = None
    skip: Skip | None = None


class EventCreateSchema(_Body):
    title: str = Field(min_length=1, max_length=200)
    start: dt.datetime
    duration_minutes: int = Field(gt=0, le=1440)


class ExpenseCreateSchema(_Body):
    amount_cents: int = Field(gt=0)
    category: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=200)
    date: dt.date


class ReminderCreateSchema(_Body):
    text: str = Field(min_length=1, max_length=200)
    at: dt.datetime
    kind: ReminderKind


class ConfirmSchema(_Body):
    approve: bool

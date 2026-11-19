from __future__ import annotations

import asyncio
import datetime as dt  # noqa: TC003 - FastAPI reads the query annotation at runtime
import json
from typing import TYPE_CHECKING, Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.api.auth import require_token
from app.api.deps import (
    get_calendar,
    get_climate,
    get_expenses,
    get_known_uris,
    get_light,
    get_music,
    get_pending,
    get_reminder_store,
    get_runner,
    get_settings,
    get_weather,
    get_weather_display,
)
from app.api.schemas import (
    ActionSchema,
    ClimatePatchSchema,
    ClimateSchema,
    ClimatesSchema,
    ColorSchema,
    ConfirmSchema,
    EventCreateSchema,
    EventsSchema,
    ExpenseCreateSchema,
    ExpenseSchema,
    ExpensesSchema,
    LightPatchSchema,
    LightSchema,
    LightsSchema,
    MusicControlSchema,
    MusicDeviceSelectSchema,
    MusicDevicesSchema,
    MusicItemsSchema,
    MusicPlaySchema,
    MusicSchema,
    PendingConfirmationSchema,
    PlaceSchema,
    ReminderCreateSchema,
    RemindersSchema,
    StateSchema,
    WeatherForecastSchema,
    WeatherSchema,
)
from app.application.pending_actions import NOTHING_PENDING, PendingActionStore
from app.application.tool_runner import CONFIRM_ACTION, UNKNOWN_STATE, ToolRunner

# FastAPI resolves these annotations at runtime, so they are real imports.
from app.application.tools.music import KnownUris  # noqa: TC001
from app.application.weather_display import WeatherDisplay
from app.config import Settings  # noqa: TC001
from app.domain.climate import ClimateMode, FanSpeed
from app.domain.exceptions import (
    DomainError,
    EventNotFoundError,
    MusicOfflineError,
    UnknownMusicDeviceError,
)
from app.domain.light import LightMode
from app.domain.music import MediaKind
from app.domain.tools import ToolCall
from app.ports.calendar import CalendarPort  # noqa: TC001
from app.ports.climate import ClimatePort  # noqa: TC001
from app.ports.expenses import ExpensesPort  # noqa: TC001
from app.ports.light import LightPort  # noqa: TC001
from app.ports.music import MusicPort  # noqa: TC001
from app.ports.reminders import ReminderStorePort  # noqa: TC001
from app.ports.weather import WeatherPort

if TYPE_CHECKING:
    from pydantic import BaseModel

    from app.domain.weather import Forecast, Place

# One owner, one panel: all direct-control actions share one conversation, so there is one
# pending action at a time and it can never be confirmed from chat or live.
PANEL = "panel"
ERROR_PREFIX = "erro: "
INTERNAL_FAILURE = "erro: falha interna na ferramenta"

router = APIRouter(dependencies=[Depends(require_token)])

Name = Annotated[str, Path(min_length=1, max_length=64)]
Runner = Annotated[ToolRunner, Depends(get_runner)]
Pending = Annotated[PendingActionStore, Depends(get_pending)]
Weather = Annotated[WeatherPort, Depends(get_weather)]
Display = Annotated[WeatherDisplay, Depends(get_weather_display)]


async def _run(runner: ToolRunner, tool: str, args: dict[str, object]) -> str:
    call = ToolCall(id=uuid4().hex, name=tool, arguments=json.dumps(args))
    return (await runner.run(call, PANEL, None)).output


def _action(
    output: str, pending: PendingActionStore, *, conflict: str | None = None
) -> ActionSchema:
    if output.startswith("needs_confirmation"):
        action = pending.peek(PANEL)
        summary = "" if action is None else action.summary
        return ActionSchema(
            status="pending_confirmation",
            pending_confirmation=PendingConfirmationSchema(summary=summary),
        )
    if output.startswith(UNKNOWN_STATE):
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, detail=output)
    if output == INTERNAL_FAILURE:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error")
    if output.startswith(ERROR_PREFIX):
        code = status.HTTP_409_CONFLICT if output == conflict else 422
        raise HTTPException(code, detail=output.removeprefix(ERROR_PREFIX))
    return ActionSchema(status="done", message=output)


async def _act(
    runner: ToolRunner, pending: PendingActionStore, tool: str, args: dict[str, object]
) -> ActionSchema:
    pending.drop(PANEL)  # any new request supersedes an unconfirmed one
    return _action(await _run(runner, tool, args), pending)


def _args(body: BaseModel, **extra: object) -> dict[str, object]:
    return {**body.model_dump(mode="json", exclude_none=True), **extra}


async def _light(light: LightPort, name: str) -> LightSchema:
    try:
        return LightSchema.model_validate(await light.get_state(name)).model_copy(
            update={"name": name}
        )
    except DomainError:
        # An unreachable lamp (owner away, unplugged) still shows, greyed out.
        return LightSchema(
            name=name,
            available=False,
            power=False,
            mode=LightMode.WHITE,
            brightness=0,
            color_temperature=0,
            color=ColorSchema(hue=0, saturation=0, brightness=0),
            timer_seconds=0,
            do_not_disturb=False,
        )


async def _climate(climate: ClimatePort, name: str) -> ClimateSchema:
    try:
        return ClimateSchema.model_validate(await climate.get_state(name)).model_copy(
            update={"name": name}
        )
    except DomainError:
        return ClimateSchema(
            name=name,
            available=False,
            power=False,
            mode=ClimateMode.COOL,
            target_temperature=0,
            current_temperature=0,
            fan_speed=FanSpeed.AUTO,
            swing=False,
            power_save=False,
            display_light=False,
            has_error=False,
        )


async def _lights(light: LightPort) -> list[LightSchema]:
    return list(await asyncio.gather(*(_light(light, n) for n in await light.devices())))


async def _climates(climate: ClimatePort) -> list[ClimateSchema]:
    return list(await asyncio.gather(*(_climate(climate, n) for n in await climate.devices())))


async def _music_state(music: MusicPort) -> MusicSchema:
    return MusicSchema.model_validate(await music.state())


@router.get("/state", response_model=StateSchema)
async def state(
    light: Annotated[LightPort, Depends(get_light)],
    climate: Annotated[ClimatePort, Depends(get_climate)],
    music: Annotated[MusicPort, Depends(get_music)],
    pending: Pending,
) -> StateSchema:
    # A dead vendor must not blank the whole panel: each section fails on its own, and they
    # run together so an offline lamp's timeout is not added to the others'.
    got_lights, got_climates, got_music = await asyncio.gather(
        _lights(light), _climates(climate), _music_state(music), return_exceptions=True
    )
    results = {"lights": got_lights, "climates": got_climates, "music": got_music}
    for result in results.values():
        if isinstance(result, BaseException) and not isinstance(result, DomainError):
            raise result
    errors = [name for name, result in results.items() if isinstance(result, DomainError)]
    lights = None if isinstance(got_lights, BaseException) else got_lights
    climates = None if isinstance(got_climates, BaseException) else got_climates
    playback = None if isinstance(got_music, BaseException) else got_music
    waiting = pending.peek(PANEL)
    return StateSchema(
        lights=lights,
        climates=climates,
        music=playback,
        pending_confirmation=(
            None if waiting is None else PendingConfirmationSchema(summary=waiting.summary)
        ),
        errors=errors,
    )


@router.get("/lights", response_model=LightsSchema)
async def list_lights(light: Annotated[LightPort, Depends(get_light)]) -> LightsSchema:
    return LightsSchema(lights=await _lights(light))


@router.patch("/lights/{name}", response_model=ActionSchema)
async def set_light(
    name: Name, body: LightPatchSchema, runner: Runner, pending: Pending
) -> ActionSchema:
    return await _act(runner, pending, "set_light", _args(body, name=name))


@router.get("/climate", response_model=ClimatesSchema)
async def list_climates(climate: Annotated[ClimatePort, Depends(get_climate)]) -> ClimatesSchema:
    return ClimatesSchema(climates=await _climates(climate))


@router.patch("/climate/{name}", response_model=ActionSchema)
async def set_climate(
    name: Name, body: ClimatePatchSchema, runner: Runner, pending: Pending
) -> ActionSchema:
    return await _act(runner, pending, "set_climate", _args(body, name=name))


@router.get("/music/state", response_model=MusicSchema)
async def music_state(music: Annotated[MusicPort, Depends(get_music)]) -> MusicSchema:
    return await _music_state(music)


@router.get("/music/devices", response_model=MusicDevicesSchema)
async def music_devices(
    music: Annotated[MusicPort, Depends(get_music)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MusicDevicesSchema:
    return MusicDevicesSchema.model_validate(
        {"devices": await music.list_devices(), "default": settings.spotify_device or None}
    )


@router.post("/music/device", response_model=ActionSchema)
async def select_music_device(
    body: MusicDeviceSelectSchema,
    music: Annotated[MusicPort, Depends(get_music)],
    pending: Pending,
) -> ActionSchema:
    pending.drop(PANEL)
    try:
        await music.select_device(body.name)
    except UnknownMusicDeviceError as exc:
        raise HTTPException(422, detail=f"Aparelho desconhecido: {body.name}") from exc
    except MusicOfflineError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    return ActionSchema(status="done", message=f"Reprodução movida para {body.name}")


@router.get("/music/search", response_model=MusicItemsSchema)
async def search_music(
    music: Annotated[MusicPort, Depends(get_music)],
    known: Annotated[KnownUris, Depends(get_known_uris)],
    q: Annotated[str, Query(min_length=1, max_length=200)],
    kind: MediaKind = MediaKind.TRACK,
) -> MusicItemsSchema:
    items = await music.search(q, kind)
    known.remember(items)  # only uris a search/playlist returned can be played
    return MusicItemsSchema.model_validate({"items": items})


@router.get("/music/playlists", response_model=MusicItemsSchema)
async def list_playlists(
    music: Annotated[MusicPort, Depends(get_music)],
    known: Annotated[KnownUris, Depends(get_known_uris)],
) -> MusicItemsSchema:
    items = await music.playlists()
    known.remember(items)
    return MusicItemsSchema.model_validate({"items": items})


@router.post("/music/play", response_model=ActionSchema)
async def play_music(body: MusicPlaySchema, runner: Runner, pending: Pending) -> ActionSchema:
    return await _act(runner, pending, "play_music", _args(body))


@router.post("/music/control", response_model=ActionSchema)
async def control_music(body: MusicControlSchema, runner: Runner, pending: Pending) -> ActionSchema:
    return await _act(runner, pending, "control_music", _args(body))


@router.get("/agenda", response_model=EventsSchema)
async def list_events(
    calendar: Annotated[CalendarPort, Depends(get_calendar)], date: dt.date
) -> EventsSchema:
    return EventsSchema.model_validate({"events": await calendar.list_events(date)})


@router.post("/agenda", response_model=ActionSchema)
async def create_event(body: EventCreateSchema, runner: Runner, pending: Pending) -> ActionSchema:
    return await _act(runner, pending, "create_event", _args(body))


@router.delete("/agenda/{event_id}", response_model=ActionSchema)
async def delete_event(
    event_id: Name,
    runner: Runner,
    pending: Pending,
    calendar: Annotated[CalendarPort, Depends(get_calendar)],
) -> ActionSchema:
    try:
        event = await calendar.get_event(event_id)
    except EventNotFoundError as exc:
        pending.drop(PANEL)
        raise HTTPException(422, detail=str(exc)) from exc
    return await _act(runner, pending, "delete_event", {"event_id": event_id, "title": event.title})


@router.get("/finance/expenses", response_model=ExpensesSchema)
async def list_expenses(
    expenses: Annotated[ExpensesPort, Depends(get_expenses)],
    year: Annotated[int, Query(ge=2000, le=2100)],
    month: Annotated[int, Query(ge=1, le=12)],
) -> ExpensesSchema:
    rows = await expenses.list_expenses(year, month)
    return ExpensesSchema(
        expenses=[
            ExpenseSchema(
                amount_cents=e.amount_cents,
                category=e.category,
                description=e.description,
                date=e.day,
            )
            for e in rows
        ],
        total_cents=await expenses.month_total(year, month),
    )


@router.post("/finance/expenses", response_model=ActionSchema)
async def add_expense(body: ExpenseCreateSchema, runner: Runner, pending: Pending) -> ActionSchema:
    return await _act(runner, pending, "add_expense", _args(body))


@router.get("/reminders", response_model=RemindersSchema)
async def list_reminders(
    store: Annotated[ReminderStorePort, Depends(get_reminder_store)],
) -> RemindersSchema:
    # calendar warnings are derived from the agenda, which the panel already shows
    reminders = [r for r in await store.all() if not r.is_calendar]
    return RemindersSchema.model_validate({"reminders": reminders})


@router.post("/reminders", response_model=ActionSchema)
async def create_reminder(
    body: ReminderCreateSchema, runner: Runner, pending: Pending
) -> ActionSchema:
    return await _act(runner, pending, "create_reminder", _args(body))


@router.delete("/reminders/{reminder_id}", response_model=ActionSchema)
async def cancel_reminder(reminder_id: Name, runner: Runner, pending: Pending) -> ActionSchema:
    return await _act(runner, pending, "cancel_reminder", {"id": reminder_id})


@router.post("/confirm", response_model=ActionSchema)
async def confirm(body: ConfirmSchema, runner: Runner, pending: Pending) -> ActionSchema:
    if not body.approve:
        pending.drop(PANEL)
        return ActionSchema(status="cancelled")
    # The explicit Confirm click is the "next utterance": it arms the action, and only the
    # argument-free confirm path can run it.
    pending.on_user_utterance(PANEL, "sim")
    output = await _run(runner, CONFIRM_ACTION, {})
    return _action(output, pending, conflict=f"{ERROR_PREFIX}{NOTHING_PENDING}")


async def _forecast(weather: WeatherPort, place: Place) -> Forecast | None:
    try:
        return await weather.forecast(place)
    except DomainError:
        return None


async def _weather(weather: WeatherPort, display: WeatherDisplay) -> WeatherSchema:
    # Like /state: the shown city and the bar chip fail on their own, never the whole body.
    try:
        place, home = await display.shown(), await display.home()
    except DomainError:
        return WeatherSchema(
            is_home=True, home=None, forecast=None, home_now=None, errors=["forecast", "home"]
        )
    shown = await _forecast(weather, place)
    at_home = shown if place == home else await _forecast(weather, home)
    return WeatherSchema(
        is_home=place == home,
        home=PlaceSchema.model_validate(home),
        forecast=None if shown is None else WeatherForecastSchema.model_validate(shown),
        home_now=None if at_home is None else WeatherForecastSchema.model_validate(at_home).current,
        errors=[name for name, f in (("forecast", shown), ("home", at_home)) if f is None],
    )


@router.get("/weather", response_model=WeatherSchema)
async def weather_now(weather: Weather, display: Display) -> WeatherSchema:
    return await _weather(weather, display)


@router.delete("/weather/display", response_model=WeatherSchema)
async def weather_home(
    runner: Runner, pending: Pending, weather: Weather, display: Display
) -> WeatherSchema:
    await _act(runner, pending, "show_weather", {})
    return await _weather(weather, display)

from __future__ import annotations

from typing import TYPE_CHECKING

from app.application.registry import Registry
from app.application.tools.agenda import CreateEvent, DeleteEvent, ListEvents
from app.application.tools.climate import ListClimates, SetClimate
from app.application.tools.finance import AddExpense, MonthTotal
from app.application.tools.lights import ListLights, SetLight
from app.application.tools.music import (
    ControlMusic,
    KnownUris,
    ListMusicDevices,
    ListPlaylists,
    MusicState,
    PlayMusic,
    QueueMusic,
    SearchMusic,
)
from app.application.tools.projects import CloseProject, OpenProject, SearchProjects
from app.application.tools.reminders import CancelReminder, CreateReminder, ListReminders
from app.application.tools.weather import GetWeather, ShowWeather

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from datetime import datetime

    from app.application.project_session import ProjectSession
    from app.application.tool import Tool
    from app.application.weather_display import WeatherDisplay
    from app.ports.calendar import CalendarPort
    from app.ports.climate import ClimatePort
    from app.ports.embedder import EmbedderPort
    from app.ports.expenses import ExpensesPort
    from app.ports.knowledge import KnowledgeStorePort
    from app.ports.light import LightPort
    from app.ports.music import MusicPort
    from app.ports.reminders import ReminderStorePort
    from app.ports.weather import WeatherPort


def build_tool_registry(
    light: LightPort,
    climate: ClimatePort,
    music: MusicPort,
    calendar: CalendarPort,
    expenses: ExpensesPort,
    *,
    known: KnownUris | None = None,
    on_volume: Callable[[int], None] | None = None,
    reminders: tuple[ReminderStorePort, Callable[[], datetime]] | None = None,
    knowledge: tuple[KnowledgeStorePort, EmbedderPort, Sequence[str]] | None = None,
    session: ProjectSession | None = None,
    weather: tuple[WeatherPort, WeatherDisplay] | None = None,
) -> Registry[Tool]:
    """`reminders` is the store plus the owner's wall clock; without it there are no reminders.

    `knowledge` is the index, the embedder and the project names; without it, no projects.
    `session` is the project terminal; without it, nothing opens a project.
    `weather` is the forecast source plus what the panel shows; without it, no weather."""
    known = known or KnownUris()
    registry: Registry[Tool] = Registry()
    tools: tuple[Tool, ...] = (
        ListLights(light),
        SetLight(light),
        ListClimates(climate),
        SetClimate(climate),
        MusicState(music),
        ListMusicDevices(music),
        SearchMusic(music, known),
        ListPlaylists(music, known),
        PlayMusic(music, known),
        ControlMusic(music, on_volume),
        QueueMusic(music, known),
        ListEvents(calendar),
        CreateEvent(calendar),
        DeleteEvent(calendar),
        AddExpense(expenses),
        MonthTotal(expenses),
    )
    if reminders is not None:
        store, clock = reminders
        tools += (CreateReminder(store, clock), ListReminders(store, clock), CancelReminder(store))
    if knowledge is not None:
        tools += (SearchProjects(*knowledge),)
    if session is not None:
        tools += (OpenProject(session), CloseProject(session))
    if weather is not None:
        tools += (GetWeather(*weather), ShowWeather(*weather))
    for tool in tools:
        registry.register(tool.spec.name, tool)
    return registry

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

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.application.tool import Tool
    from app.ports.calendar import CalendarPort
    from app.ports.climate import ClimatePort
    from app.ports.expenses import ExpensesPort
    from app.ports.light import LightPort
    from app.ports.music import MusicPort


def build_tool_registry(
    light: LightPort,
    climate: ClimatePort,
    music: MusicPort,
    calendar: CalendarPort,
    expenses: ExpensesPort,
    known: KnownUris | None = None,
    on_volume: Callable[[int], None] | None = None,
) -> Registry[Tool]:
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
    for tool in tools:
        registry.register(tool.spec.name, tool)
    return registry

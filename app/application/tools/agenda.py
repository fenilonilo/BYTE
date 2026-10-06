from __future__ import annotations

from typing import TYPE_CHECKING

from app.application.tool import Tool
from app.application.tools.args import (
    date_arg,
    datetime_arg,
    int_arg,
    object_schema,
    str_arg,
)
from app.domain.exceptions import ToolArgumentError
from app.domain.tools import ToolSpec

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.ports.calendar import CalendarPort


class ListEvents(Tool):
    spec = ToolSpec(
        name="list_events",
        description="Lista os eventos de um dia.",
        parameters=object_schema({"date": ("string", "Dia no formato AAAA-MM-DD.")}),
        segment="agenda",
    )

    def __init__(self, calendar: CalendarPort) -> None:
        self._calendar = calendar

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        events = await self._calendar.list_events(date_arg(args, "date"))
        lines = [f"{e.id}: {e.start:%H:%M} {e.title} ({e.duration_minutes} min)" for e in events]
        return "; ".join(lines) or "nenhum evento"


class CreateEvent(Tool):
    spec = ToolSpec(
        name="create_event",
        description="Cria um evento no calendário.",
        parameters=object_schema(
            {
                "title": ("string", "Título do evento."),
                "start": ("string", "Início em ISO 8601, ex.: 2026-10-06T15:00:00-03:00."),
                "duration_minutes": ("integer", "Duração em minutos."),
            }
        ),
        segment="agenda",
    )

    def __init__(self, calendar: CalendarPort) -> None:
        self._calendar = calendar

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        duration = int_arg(args, "duration_minutes")
        if duration <= 0:
            raise ToolArgumentError("duration_minutes deve ser positivo")
        event = await self._calendar.create_event(
            key, str_arg(args, "title"), datetime_arg(args, "start"), duration
        )
        return f"Evento criado: {event.id} {event.start:%d/%m %H:%M} {event.title}"


class DeleteEvent(Tool):
    spec = ToolSpec(
        name="delete_event",
        description="Apaga um evento do calendário. Exige confirmação do usuário.",
        parameters=object_schema({"event_id": ("string", "Id do evento, como em list_events.")}),
        segment="agenda",
        requires_confirmation=True,
    )

    def __init__(self, calendar: CalendarPort) -> None:
        self._calendar = calendar

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        event_id = str_arg(args, "event_id")
        await self._calendar.delete_event(event_id)
        return f"Evento {event_id} apagado"

    def summarize(self, args: Mapping[str, object]) -> str:
        return f"Apagar o evento {str_arg(args, 'event_id')}"

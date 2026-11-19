from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from app.application.tool import Tool
from app.application.tools.args import datetime_arg, object_schema, opt_enum, str_arg
from app.domain.exceptions import ToolArgumentError
from app.domain.reminders import Reminder, ReminderKind
from app.domain.tools import ToolSpec

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from datetime import datetime

    from app.ports.reminders import ReminderStorePort


def _local(at: datetime, now: datetime) -> datetime:
    return at.astimezone(now.tzinfo)


class CreateReminder(Tool):
    spec = ToolSpec(
        name="create_reminder",
        description="Cria um lembrete (falado uma vez) ou alarme (toca até o usuário parar).",
        parameters=object_schema(
            {
                "text": ("string", "O que lembrar, curto."),
                "at": ("string", "Quando, ISO 8601."),
                "kind": ("string", "lembrete ou alarme."),
            }
        ),
        segment="agenda",
    )

    def __init__(self, store: ReminderStorePort, clock: Callable[[], datetime]) -> None:
        self._store = store
        self._clock = clock

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        now = self._clock()
        at = datetime_arg(args, "at")
        if at.tzinfo is None:
            at = at.replace(tzinfo=now.tzinfo)
        if at <= now:
            raise ToolArgumentError("esse horário já passou")
        kind = opt_enum(args, "kind", ReminderKind)
        if kind is None:
            raise ToolArgumentError("argumento 'kind' ausente")
        # short ids: the model reads them back, and every character is a token
        rid = hashlib.sha256(key.encode()).hexdigest()[:6]
        await self._store.put(Reminder(rid, str_arg(args, "text"), at, kind))
        return f"{kind} {rid} {_local(at, now):%d/%m %H:%M}"


class ListReminders(Tool):
    spec = ToolSpec(
        name="list_reminders",
        description="Lista lembretes e alarmes pendentes.",
        parameters=object_schema({}),
        segment="agenda",
    )

    def __init__(self, store: ReminderStorePort, clock: Callable[[], datetime]) -> None:
        self._store = store
        self._clock = clock

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        now = self._clock()
        lines = [
            f"{r.id}: {_local(r.at, now):%d/%m %H:%M} {r.kind} {r.text}"
            for r in await self._store.all()
            if not r.is_calendar
        ]
        return "; ".join(lines) or "nenhum lembrete"


class CancelReminder(Tool):
    spec = ToolSpec(
        name="cancel_reminder",
        description="Cancela um lembrete ou alarme.",
        parameters=object_schema({"id": ("string", "Id, como em list_reminders.")}),
        segment="agenda",
    )

    def __init__(self, store: ReminderStorePort) -> None:
        self._store = store

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        rid = str_arg(args, "id")
        await self._store.remove(rid)
        return f"{rid} cancelado"

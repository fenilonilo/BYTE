from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from app.adapters.memory.in_memory_calendar import InMemoryCalendar
from app.adapters.memory.in_memory_climate import InMemoryClimate
from app.adapters.memory.in_memory_expenses import InMemoryExpenses
from app.adapters.memory.in_memory_light import InMemoryLight
from app.adapters.memory.in_memory_music import InMemoryMusic
from app.application.tools.args import (
    int_arg,
    opt_bool,
    opt_enum,
    opt_float,
    opt_int,
    opt_str,
    str_arg,
)
from app.application.tools.catalog import build_tool_registry
from app.application.tools.climate import describe_climate
from app.domain.climate import ClimateMode
from app.domain.exceptions import (
    ClimateError,
    LightError,
    MusicError,
    ToolArgumentError,
    UnknownClimateDeviceError,
    UnknownLightDeviceError,
    UnknownMusicDeviceError,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.application.registry import Registry
    from app.application.tool import Tool

EXPENSE = {
    "amount_cents": 5000,
    "category": "mercado",
    "description": "feira",
    "date": "2026-10-06",
}
EVENT = {"title": "dentista", "start": "2026-10-06T15:00:00+00:00", "duration_minutes": 60}
WHITE = "modo white, brilho 100%, temperatura de cor 50%"


@pytest.fixture
def registry() -> Registry[Tool]:
    return build_tool_registry(
        InMemoryLight(("lampada", "quarto")),
        InMemoryClimate(),
        InMemoryMusic(),
        InMemoryCalendar(),
        InMemoryExpenses(),
    )


async def run(
    registry: Registry[Tool], name: str, args: Mapping[str, object], key: str = "k"
) -> str:
    return await registry.get(name).execute(args, key)


@pytest.mark.unit
def test_catalog_has_sixteen_tools_in_four_segments(registry: Registry[Tool]) -> None:
    specs = [t.spec for t in registry.values()]
    assert {s.name for s in specs} == {
        "list_lights",
        "set_light",
        "list_climates",
        "set_climate",
        "music_state",
        "list_music_devices",
        "search_music",
        "list_playlists",
        "play_music",
        "control_music",
        "queue_music",
        "list_events",
        "create_event",
        "delete_event",
        "add_expense",
        "month_total",
    }
    assert {s.segment for s in specs} == {"home", "music", "agenda", "finance"}


@pytest.mark.unit
def test_irreversible_data_changes_always_ask(registry: Registry[Tool]) -> None:
    flagged = {t.spec.name for t in registry.values() if t.spec.requires_confirmation}
    assert flagged == {"delete_event", "add_expense"}


@pytest.mark.unit
def test_switching_devices_on_or_off_never_asks(registry: Registry[Tool]) -> None:
    climate = registry.get("set_climate")
    assert climate.needs_confirmation({"name": "ar-condicionado", "power": True}) is False
    assert climate.needs_confirmation({"name": "ar-condicionado", "power": False}) is False
    assert registry.get("set_light").needs_confirmation({"name": "lampada", "power": True}) is False


@pytest.mark.unit
def test_every_schema_is_a_strict_object_and_requires_only_known_fields(
    registry: Registry[Tool],
) -> None:
    for tool in registry.values():
        params = tool.spec.parameters
        assert params["type"] == "object"
        assert params["additionalProperties"] is False
        properties = params["properties"]
        assert isinstance(properties, dict)
        assert set(params["required"]) <= set(properties)  # type: ignore[call-overload]
    # A partial-update tool that required every field would force the model to invent values.
    assert registry.get("set_light").spec.parameters["required"] == []
    assert registry.get("set_climate").spec.parameters["required"] == ["name"]


@pytest.mark.unit
async def test_lights(registry: Registry[Tool]) -> None:
    listed = await run(registry, "list_lights", {})
    assert listed == f"lampada: desligada, {WHITE}; quarto: desligada, {WHITE}"
    assert await run(registry, "set_light", {"name": "lampada", "power": True}) == (
        f"lampada: ligada, {WHITE}"
    )
    dimmed = await run(registry, "set_light", {"name": "lampada", "brightness": 30})
    assert dimmed == "lampada: ligada, modo white, brilho 30%, temperatura de cor 50%"
    colour = await run(registry, "set_light", {"name": "Quarto", "hue": 120, "brightness": 40})
    assert colour == "Quarto: ligada, cor (matiz 120, saturação 100%, brilho 40%)"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("args", "error"),
    [
        ({"name": "cofre", "power": True}, UnknownLightDeviceError),
        ({"name": "lampada", "brightness": 0}, LightError),
        ({"name": "lampada", "hue": 120, "color_temperature": 10}, LightError),
        ({"name": "lampada"}, LightError),
        ({"name": "lampada", "brightness": "alto"}, ToolArgumentError),
        ({"power": True}, UnknownLightDeviceError),  # two lamps: which one?
    ],
)
async def test_bad_light_requests(
    registry: Registry[Tool], args: dict[str, object], error: type[Exception]
) -> None:
    with pytest.raises(error):
        await run(registry, "set_light", args)


@pytest.mark.unit
async def test_a_lamp_switches_back_and_forth_without_waiting(registry: Registry[Tool]) -> None:
    await run(registry, "set_light", {"name": "lampada", "power": True})
    assert (await run(registry, "set_light", {"name": "lampada", "power": False})).startswith(
        "lampada: desligada"
    )


@pytest.mark.unit
async def test_with_a_single_lamp_any_name_or_none_means_it() -> None:
    registry = build_tool_registry(
        InMemoryLight(("lampada",)),
        InMemoryClimate(),
        InMemoryMusic(),
        InMemoryCalendar(),
        InMemoryExpenses(),
    )
    assert (await run(registry, "set_light", {"power": True})).startswith("lampada: ligada")
    off = await run(registry, "set_light", {"name": "luz do quarto", "power": False})
    assert off.startswith("lampada: desligada")


@pytest.mark.unit
async def test_climate(registry: Registry[Tool]) -> None:
    assert await run(registry, "list_climates", {}) == (
        "ar-condicionado: desligado, modo cool, alvo 24°C, ambiente 25°C, ventilador auto"
    )
    changed = await run(
        registry,
        "set_climate",
        {"name": "ar-condicionado", "power": True, "mode": "dry", "target_temperature": 22},
    )
    assert changed == (
        "ar-condicionado: ligado, modo dry, alvo 22°C, ambiente 25°C, ventilador auto"
    )
    timer = await run(registry, "set_climate", {"name": "ar-condicionado", "stop_in_minutes": 30})
    assert timer.startswith("ar-condicionado: ligado")
    await run(registry, "set_climate", {"name": "ar-condicionado", "display_light": False})


@pytest.mark.unit
async def test_a_unit_reporting_an_error_says_so() -> None:
    state = replace(await InMemoryClimate().get_state("ar-condicionado"), has_error=True)
    assert describe_climate("ar-condicionado", state).endswith("ATENÇÃO: o aparelho reporta erro")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("args", "error"),
    [
        ({"name": "ar-condicionado", "target_temperature": 40}, ClimateError),
        ({"name": "ar-condicionado"}, ClimateError),
        ({"name": "sala", "power": True}, UnknownClimateDeviceError),
        ({"name": "ar-condicionado", "mode": "heat"}, ToolArgumentError),
        ({"name": "ar-condicionado", "swing": "sim"}, ToolArgumentError),
    ],
)
async def test_bad_climate_requests(
    registry: Registry[Tool], args: dict[str, object], error: type[Exception]
) -> None:
    with pytest.raises(error):
        await run(registry, "set_climate", args)


@pytest.mark.unit
async def test_music(registry: Registry[Tool]) -> None:
    assert await run(registry, "music_state", {}) == (
        "pausado: nada no aparelho nest mini, volume 50%"
    )
    assert await run(registry, "list_music_devices", {}) == "nest mini"
    assert await run(registry, "search_music", {"query": "queen"}) == (
        "spotify:track:1 | Bohemian Rhapsody Queen"
    )
    assert await run(registry, "search_music", {"query": "xyz"}) == "nada encontrado"
    assert await run(registry, "list_playlists", {}) == "spotify:playlist:1 | Treino"
    await run(registry, "search_music", {"query": "aquarela"})
    playing = await run(registry, "play_music", {"uri": "spotify:track:2"})
    assert playing == "tocando: Aquarela Toquinho no aparelho nest mini, volume 50%"
    louder = await run(registry, "control_music", {"volume": 20, "shuffle": True})
    assert louder == "tocando: Aquarela Toquinho no aparelho nest mini, volume 20%"
    assert await run(registry, "queue_music", {"uri": "spotify:track:2"}) == "adicionada à fila"
    assert (await run(registry, "play_music", {})).startswith("tocando")


@pytest.mark.unit
async def test_the_model_cannot_play_a_uri_it_never_searched_for(
    registry: Registry[Tool],
) -> None:
    for tool in ("play_music", "queue_music"):
        with pytest.raises(MusicError, match="search_music"):
            await run(registry, tool, {"uri": "spotify:track:2"})
    await run(registry, "list_playlists", {})  # playlists count as "returned by the API" too
    assert (await run(registry, "play_music", {"uri": "spotify:playlist:1"})).startswith("tocando")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("tool", "args", "error"),
    [
        ("play_music", {"device": "geladeira"}, UnknownMusicDeviceError),
        ("control_music", {}, MusicError),
        ("control_music", {"volume": 101}, MusicError),
        ("control_music", {"repeat": "forever"}, ToolArgumentError),
        ("search_music", {"query": "queen", "kind": "podcast"}, ToolArgumentError),
        ("search_music", {}, ToolArgumentError),
    ],
)
async def test_bad_music_requests(
    registry: Registry[Tool], tool: str, args: dict[str, object], error: type[Exception]
) -> None:
    with pytest.raises(error):
        await run(registry, tool, args)


@pytest.mark.unit
async def test_agenda_tools(registry: Registry[Tool]) -> None:
    first = await run(registry, "create_event", EVENT, "same-key")
    assert await run(registry, "create_event", EVENT, "same-key") == first
    listed = await run(registry, "list_events", {"date": "2026-10-06"})
    assert listed.count("dentista") == 1
    assert "evt-1" in listed
    assert await run(registry, "delete_event", {"event_id": "evt-1"}) == "Evento evt-1 apagado"
    assert await run(registry, "list_events", {"date": "2026-10-06"}) == "nenhum evento"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("list_events", {"date": "amanhã"}),
        ("create_event", {**EVENT, "start": "ontem"}),
        ("create_event", {**EVENT, "duration_minutes": 0}),
        ("add_expense", {**EXPENSE, "amount_cents": -5}),
        ("add_expense", {**EXPENSE, "amount_cents": True}),
        ("month_total", {"year": 2026, "month": 13}),
    ],
)
async def test_bad_arguments_raise_tool_argument_error(
    registry: Registry[Tool], tool: str, args: dict[str, object]
) -> None:
    with pytest.raises(ToolArgumentError):
        await run(registry, tool, args)


@pytest.mark.unit
async def test_finance_tools_and_idempotency(registry: Registry[Tool]) -> None:
    await run(registry, "add_expense", EXPENSE, "pending-1")
    await run(registry, "add_expense", EXPENSE, "pending-1")
    total = await run(registry, "month_total", {"year": 2026, "month": 10})
    assert total == "Total de 10/2026: R$ 50,00"


@pytest.mark.unit
def test_confirmation_summaries_come_from_code(registry: Registry[Tool]) -> None:
    summary = registry.get("add_expense").summarize({**EXPENSE, "amount_cents": 12345})
    assert summary == "Registrar gasto de R$ 123,45 em mercado: feira"
    delete = registry.get("delete_event").summarize({"event_id": "evt-1"})
    assert delete == "Apagar o evento evt-1"


@pytest.mark.unit
def test_required_argument_helpers_reject_wrong_types() -> None:
    with pytest.raises(ToolArgumentError):
        str_arg({"a": 3}, "a")
    with pytest.raises(ToolArgumentError):
        str_arg({"a": "   "}, "a")
    with pytest.raises(ToolArgumentError):
        int_arg({"a": "3"}, "a")
    with pytest.raises(ToolArgumentError):
        int_arg({"a": True}, "a")
    assert int_arg({"a": 3}, "a") == 3


@pytest.mark.unit
def test_optional_argument_helpers_treat_missing_and_null_as_absent() -> None:
    assert opt_str({}, "a") is None
    assert opt_int({"a": None}, "a") is None
    assert opt_bool({"a": None}, "a") is None
    assert opt_float({}, "a") is None
    assert opt_enum({"a": None}, "a", ClimateMode) is None


@pytest.mark.unit
def test_optional_argument_helpers_validate_what_is_present() -> None:
    assert opt_int({"a": 4}, "a") == 4
    assert opt_float({"a": 22}, "a") == 22.0
    assert opt_float({"a": 22.5}, "a") == 22.5
    assert opt_bool({"a": False}, "a") is False
    assert opt_str({"a": " x "}, "a") == "x"
    assert opt_enum({"a": "dry"}, "a", ClimateMode) is ClimateMode.DRY
    for bad in (
        lambda: opt_bool({"a": "sim"}, "a"),
        lambda: opt_float({"a": True}, "a"),
        lambda: opt_float({"a": "22"}, "a"),
        lambda: opt_int({"a": 1.5}, "a"),
    ):
        with pytest.raises(ToolArgumentError):
            bad()
    with pytest.raises(ToolArgumentError, match="cool, dry, fan, auto"):
        opt_enum({"a": "heat"}, "a", ClimateMode)

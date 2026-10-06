from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from app.domain.exceptions import ToolArgumentError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


def object_schema(
    properties: Mapping[str, tuple[str, str]], required: Sequence[str] | None = None
) -> dict[str, object]:
    """JSON schema for a tool. `properties` maps name -> (json type, description).

    Every property is required unless `required` lists the ones that are."""
    return {
        "type": "object",
        "properties": {
            name: {"type": json_type, "description": description}
            for name, (json_type, description) in properties.items()
        },
        "required": list(properties if required is None else required),
        "additionalProperties": False,
    }


def _invalid(name: str) -> ToolArgumentError:
    return ToolArgumentError(f"argumento {name!r} ausente ou inválido")


def str_arg(args: Mapping[str, object], name: str) -> str:
    value = args.get(name)
    if not isinstance(value, str) or not value.strip():
        raise _invalid(name)
    return value.strip()


def int_arg(args: Mapping[str, object], name: str) -> int:
    value = args.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise _invalid(name)
    return value


def date_arg(args: Mapping[str, object], name: str) -> date:
    try:
        return date.fromisoformat(str_arg(args, name))
    except ValueError as exc:
        raise ToolArgumentError(f"argumento {name!r} deve ser AAAA-MM-DD") from exc


def datetime_arg(args: Mapping[str, object], name: str) -> datetime:
    try:
        return datetime.fromisoformat(str_arg(args, name))
    except ValueError as exc:
        raise ToolArgumentError(f"argumento {name!r} deve ser ISO 8601") from exc


# Optional arguments: absent or null (models often send null) means "leave it alone".


def opt_str(args: Mapping[str, object], name: str) -> str | None:
    return None if args.get(name) is None else str_arg(args, name)


def opt_int(args: Mapping[str, object], name: str) -> int | None:
    return None if args.get(name) is None else int_arg(args, name)


def opt_float(args: Mapping[str, object], name: str) -> float | None:
    value = args.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _invalid(name)
    return float(value)


def opt_bool(args: Mapping[str, object], name: str) -> bool | None:
    value = args.get(name)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise _invalid(name)
    return value


def opt_enum[E: StrEnum](args: Mapping[str, object], name: str, enum_type: type[E]) -> E | None:
    value = args.get(name)
    if value is None:
        return None
    try:
        return enum_type(value)
    except ValueError as exc:
        allowed = ", ".join(member.value for member in enum_type)
        raise ToolArgumentError(f"argumento {name!r} deve ser um de: {allowed}") from exc

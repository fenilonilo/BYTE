from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.domain.gesture_definition import GestureDefinition, MotionSpec, PoseSpec
from app.domain.gestures import Binding
from app.ports.gesture_def_repo import GestureDefinitionRepositoryPort


def _to_dict(d: GestureDefinition) -> dict[str, object]:
    return asdict(d)


def _from_dict(raw: dict[str, Any]) -> GestureDefinition:
    pose = raw["pose"]
    motion = raw["motion"]
    binding = raw["binding"]
    return GestureDefinition(
        id=str(raw["id"]),
        name=str(raw["name"]),
        pose=PoseSpec(shape=str(pose["shape"]), hands=int(pose["hands"])),
        motion=MotionSpec(type=str(motion["type"]), params=dict(motion["params"])),
        binding=Binding(
            effect=str(binding["effect"]),
            action=binding["action"],
            action_params=dict(binding["action_params"]),
        ),
    )


class JsonGestureDefinitionRepository(GestureDefinitionRepositoryPort):
    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def _read(self) -> dict[str, GestureDefinition]:
        if not self._path.exists():
            return {}
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        return {item["id"]: _from_dict(item) for item in raw}

    def _write(self, defs: dict[str, GestureDefinition]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = [_to_dict(d) for d in defs.values()]
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    async def list_all(self) -> tuple[GestureDefinition, ...]:
        defs = await asyncio.to_thread(self._read)
        return tuple(defs.values())

    async def get(self, def_id: str) -> GestureDefinition | None:
        defs = await asyncio.to_thread(self._read)
        return defs.get(def_id)

    async def save(self, definition: GestureDefinition) -> None:
        def _op() -> None:
            defs = self._read()
            defs[definition.id] = definition
            self._write(defs)

        await asyncio.to_thread(_op)

    async def delete(self, def_id: str) -> None:
        def _op() -> None:
            defs = self._read()
            defs.pop(def_id, None)
            self._write(defs)

        await asyncio.to_thread(_op)

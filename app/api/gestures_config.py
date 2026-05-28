from __future__ import annotations

import contextlib

import httpx
from fastapi import APIRouter

from app.api.deps import get_binding_resolver, get_gesture_def_repo
from app.api.schemas import GestureDefinitionSchema
from app.application.use_cases.delete_gesture_definition import DeleteGestureDefinition
from app.application.use_cases.list_gesture_definitions import ListGestureDefinitions
from app.application.use_cases.save_gesture_definition import SaveGestureDefinition

router = APIRouter()

_RELOAD_URL = "http://127.0.0.1:8001/reload"


async def _refresh() -> None:
    await get_binding_resolver().reload()
    with contextlib.suppress(Exception):
        async with httpx.AsyncClient(timeout=2.0) as client:
            await client.post(_RELOAD_URL)


@router.get("/gestures", response_model=list[GestureDefinitionSchema])
async def list_gestures() -> list[GestureDefinitionSchema]:
    defs = await ListGestureDefinitions(get_gesture_def_repo()).execute()
    return [GestureDefinitionSchema.from_domain(d) for d in defs]


@router.put("/gestures/{def_id}", response_model=GestureDefinitionSchema)
async def upsert_gesture(def_id: str, body: GestureDefinitionSchema) -> GestureDefinitionSchema:
    definition = body.to_domain()
    await SaveGestureDefinition(get_gesture_def_repo()).execute(definition)
    await _refresh()
    return GestureDefinitionSchema.from_domain(definition)


@router.delete("/gestures/{def_id}")
async def delete_gesture(def_id: str) -> dict[str, bool]:
    await DeleteGestureDefinition(get_gesture_def_repo()).execute(def_id)
    await _refresh()
    return {"ok": True}

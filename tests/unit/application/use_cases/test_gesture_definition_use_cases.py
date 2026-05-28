from __future__ import annotations

import pytest

from app.application.use_cases.delete_gesture_definition import DeleteGestureDefinition
from app.application.use_cases.list_gesture_definitions import ListGestureDefinitions
from app.application.use_cases.save_gesture_definition import SaveGestureDefinition
from app.domain.exceptions import DomainError
from app.domain.gesture_definition import GestureDefinition, MotionSpec, PoseSpec
from app.domain.gestures import Binding
from app.ports.gesture_def_repo import GestureDefinitionRepositoryPort


class _FakeRepo(GestureDefinitionRepositoryPort):
    def __init__(self) -> None:
        self._store: dict[str, GestureDefinition] = {}

    async def list_all(self) -> tuple[GestureDefinition, ...]:
        return tuple(self._store.values())

    async def get(self, def_id: str) -> GestureDefinition | None:
        return self._store.get(def_id)

    async def save(self, definition: GestureDefinition) -> None:
        self._store[definition.id] = definition

    async def delete(self, def_id: str) -> None:
        self._store.pop(def_id, None)


def _def(def_id: str) -> GestureDefinition:
    return GestureDefinition(
        id=def_id,
        name=def_id,
        pose=PoseSpec(shape="fist", hands=2),
        motion=MotionSpec(type="hold", params={}),
        binding=Binding(effect="freeze", action=None, action_params={}),
    )


@pytest.mark.asyncio
async def test_save_then_list() -> None:
    repo = _FakeRepo()
    await SaveGestureDefinition(repo).execute(_def("a"))
    result = await ListGestureDefinitions(repo).execute()
    assert [d.id for d in result] == ["a"]


@pytest.mark.asyncio
async def test_save_rejects_empty_id() -> None:
    repo = _FakeRepo()
    with pytest.raises(DomainError):
        await SaveGestureDefinition(repo).execute(_def(""))


@pytest.mark.asyncio
async def test_delete() -> None:
    repo = _FakeRepo()
    await SaveGestureDefinition(repo).execute(_def("a"))
    await DeleteGestureDefinition(repo).execute("a")
    assert await ListGestureDefinitions(repo).execute() == ()

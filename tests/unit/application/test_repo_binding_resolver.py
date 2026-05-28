from __future__ import annotations

import pytest

from app.application.repo_binding_resolver import RepoBindingResolver
from app.domain.gesture_definition import GestureDefinition, MotionSpec, PoseSpec
from app.domain.gestures import Binding
from app.ports.gesture_def_repo import GestureDefinitionRepositoryPort


class _FakeRepo(GestureDefinitionRepositoryPort):
    def __init__(self, defs: list[GestureDefinition]) -> None:
        self._defs = defs

    async def list_all(self) -> tuple[GestureDefinition, ...]:
        return tuple(self._defs)

    async def get(self, def_id: str) -> GestureDefinition | None:
        return next((d for d in self._defs if d.id == def_id), None)

    async def save(self, definition: GestureDefinition) -> None: ...
    async def delete(self, def_id: str) -> None: ...


def _def(def_id: str, action: str | None) -> GestureDefinition:
    return GestureDefinition(
        id=def_id,
        name=def_id,
        pose=PoseSpec(shape="fist", hands=2),
        motion=MotionSpec(type="hold", params={}),
        binding=Binding(effect="freeze", action=action, action_params={}),
    )


@pytest.mark.asyncio
async def test_reload_then_resolve() -> None:
    repo = _FakeRepo([_def("freeze", "swap_model")])
    resolver = RepoBindingResolver(repo)
    await resolver.reload()
    b = resolver.resolve("freeze")
    assert b is not None and b.action == "swap_model"


@pytest.mark.asyncio
async def test_resolve_before_reload_is_none() -> None:
    resolver = RepoBindingResolver(_FakeRepo([_def("freeze", None)]))
    assert resolver.resolve("freeze") is None

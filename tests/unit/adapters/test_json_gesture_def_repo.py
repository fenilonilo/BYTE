from __future__ import annotations

import pytest

from app.adapters.repository.json_gesture_def_repo import JsonGestureDefinitionRepository
from app.domain.gesture_definition import GestureDefinition, MotionSpec, PoseSpec
from app.domain.gestures import Binding


def _def(def_id: str) -> GestureDefinition:
    return GestureDefinition(
        id=def_id,
        name=def_id.title(),
        pose=PoseSpec(shape="fist", hands=2),
        motion=MotionSpec(type="hold", params={}),
        binding=Binding(effect="freeze", action=None, action_params={}),
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_save_then_list_and_get(tmp_path) -> None:
    repo = JsonGestureDefinitionRepository(tmp_path / "defs.json")
    await repo.save(_def("a"))
    await repo.save(_def("b"))
    all_defs = await repo.list_all()
    assert {d.id for d in all_defs} == {"a", "b"}
    got = await repo.get("a")
    assert got is not None and got.pose.shape == "fist"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_save_upserts_and_delete(tmp_path) -> None:
    repo = JsonGestureDefinitionRepository(tmp_path / "defs.json")
    await repo.save(_def("a"))
    await repo.save(_def("a"))
    assert len(await repo.list_all()) == 1
    await repo.delete("a")
    assert await repo.get("a") is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_persists_across_instances(tmp_path) -> None:
    path = tmp_path / "defs.json"
    await JsonGestureDefinitionRepository(path).save(_def("a"))
    reloaded = await JsonGestureDefinitionRepository(path).get("a")
    assert reloaded is not None and reloaded.name == "A"

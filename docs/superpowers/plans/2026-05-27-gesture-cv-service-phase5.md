# Gesture CV Service — Phase 5: Gesture Config System (Data + Backend)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. **Prerequisite: Phases 3 and 4 complete** (binds against existing effects + actions).

**Goal:** Persist `GestureDefinition`s, recognize custom poses via KNN, expose a config CRUD API, and let the gesture-service record poses, reload definitions, and report the live-detected gesture for testing — all without code.

**Architecture:** Backend owns the logical `GestureDefinition` (id, name, pose, motion, binding) in a JSON repository, exposed via a REST API and consumed by a repo-backed binding resolver (replacing Phase 4's static one). The gesture-service owns CV-specific data: normalized-landmark **pose templates** classified by a pure KNN, recorded through a capture endpoint, plus a `/current` endpoint that reports the live-matched gesture for the wizard's test step. The service fetches definitions from the backend on startup and on a reload poke.

**Tech Stack:** Python, hexagonal layering; pure-Python KNN (no scikit dependency).

**Shared interfaces:** `Binding` + `BindingResolverPort` (Phase 4), `GestureDefinition` JSON shape (PLAN-INDEX), `HandLandmarks` (Phase 1).

---

## File Structure

| File | Responsibility | Tested |
|------|----------------|--------|
| `app/domain/gesture_definition.py` | `PoseSpec`, `MotionSpec`, `GestureDefinition` (frozen) | TDD |
| `app/ports/gesture_def_repo.py` | `GestureDefinitionRepositoryPort` (ABC, async) | — |
| `app/adapters/repository/json_gesture_def_repo.py` | JSON file repo | integration |
| `app/application/use_cases/save_gesture_definition.py` | `SaveGestureDefinition` | TDD |
| `app/application/use_cases/list_gesture_definitions.py` | `ListGestureDefinitions` | TDD |
| `app/application/use_cases/delete_gesture_definition.py` | `DeleteGestureDefinition` | TDD |
| `app/application/repo_binding_resolver.py` | `RepoBindingResolver` (cached, async reload) | TDD |
| `app/api/gestures_config.py` | REST CRUD + service reload poke | manual |
| `app/api/schemas.py` (modify) | `GestureDefinitionSchema` | TDD |
| `app/api/deps.py` (modify) | repo + resolver singletons; repoint dispatcher | — |
| `gesture_service/features.py` | normalize landmarks → feature vector (pure) | TDD |
| `gesture_service/knn.py` | KNN pose classifier (pure) | TDD |
| `gesture_service/pose_store.py` | persist/load pose templates (JSON) | TDD |
| `gesture_service/config_api.py` | `/poses/{label}` capture, `/current`, `/reload` | manual |
| `gesture_service/main.py` (modify) | expose latest gesture; mount config_api | manual |

---

### Task 1: GestureDefinition domain

**Files:**
- Create: `app/domain/gesture_definition.py`
- Test: `tests/unit/domain/test_gesture_definition.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import pytest

from app.domain.gesture_definition import GestureDefinition, MotionSpec, PoseSpec
from app.domain.gestures import Binding


def _def() -> GestureDefinition:
    return GestureDefinition(
        id="punho_duplo",
        name="Punho duplo",
        pose=PoseSpec(shape="fist", hands=2),
        motion=MotionSpec(type="hold", params={}),
        binding=Binding(effect="freeze", action="swap_model", action_params={"model": "gemini"}),
    )


def test_fields() -> None:
    d = _def()
    assert d.id == "punho_duplo"
    assert d.pose.shape == "fist"
    assert d.pose.hands == 2
    assert d.motion.type == "hold"
    assert d.binding.effect == "freeze"


def test_frozen() -> None:
    d = _def()
    with pytest.raises(Exception):
        d.id = "x"  # type: ignore[misc]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/unit/domain/test_gesture_definition.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `app/domain/gesture_definition.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from app.domain.gestures import Binding


@dataclass(frozen=True, slots=True)
class PoseSpec:
    shape: str   # 'fist'|'open'|'pinch'|'point' or a custom template label
    hands: int


@dataclass(frozen=True, slots=True)
class MotionSpec:
    type: str    # 'hold'|'swipe'|'circle'|'approach'|'none'
    params: dict[str, object]


@dataclass(frozen=True, slots=True)
class GestureDefinition:
    id: str
    name: str
    pose: PoseSpec
    motion: MotionSpec
    binding: Binding
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/unit/domain/test_gesture_definition.py -v --no-cov`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add app/domain/gesture_definition.py tests/unit/domain/test_gesture_definition.py
git commit -m "feat(domain): add GestureDefinition model"
```

---

### Task 2: Repository port + JSON adapter

**Files:**
- Create: `app/ports/gesture_def_repo.py`
- Create: `app/adapters/repository/json_gesture_def_repo.py`
- Test: `tests/unit/adapters/test_json_gesture_def_repo.py`

- [ ] **Step 1: Write the port**

Create `app/ports/gesture_def_repo.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.gesture_definition import GestureDefinition


class GestureDefinitionRepositoryPort(ABC):
    @abstractmethod
    async def list_all(self) -> tuple[GestureDefinition, ...]: ...

    @abstractmethod
    async def get(self, def_id: str) -> GestureDefinition | None: ...

    @abstractmethod
    async def save(self, definition: GestureDefinition) -> None: ...

    @abstractmethod
    async def delete(self, def_id: str) -> None: ...
```

- [ ] **Step 2: Write the failing integration test**

```python
from __future__ import annotations

import pytest

from app.adapters.repository.json_gesture_def_repo import JsonGestureDefinitionRepository
from app.domain.gesture_definition import GestureDefinition, MotionSpec, PoseSpec
from app.domain.gestures import Binding


def _def(def_id: str) -> GestureDefinition:
    return GestureDefinition(
        id=def_id, name=def_id.title(),
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
    await repo.save(_def("a"))  # upsert, not duplicate
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/unit/adapters/test_json_gesture_def_repo.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Write the JSON adapter**

Create `app/adapters/repository/json_gesture_def_repo.py`:

```python
from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from app.domain.gesture_definition import GestureDefinition, MotionSpec, PoseSpec
from app.domain.gestures import Binding
from app.ports.gesture_def_repo import GestureDefinitionRepositoryPort


def _to_dict(d: GestureDefinition) -> dict[str, object]:
    return asdict(d)


def _from_dict(raw: dict[str, object]) -> GestureDefinition:
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/unit/adapters/test_json_gesture_def_repo.py -v --no-cov`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add app/ports/gesture_def_repo.py app/adapters/repository/json_gesture_def_repo.py tests/unit/adapters/test_json_gesture_def_repo.py
git commit -m "feat: add gesture-definition repository port + JSON adapter"
```

---

### Task 3: CRUD use cases

**Files:**
- Create: `app/application/use_cases/save_gesture_definition.py`
- Create: `app/application/use_cases/list_gesture_definitions.py`
- Create: `app/application/use_cases/delete_gesture_definition.py`
- Test: `tests/unit/application/use_cases/test_gesture_definition_use_cases.py`

- [ ] **Step 1: Write the failing test (uses an in-memory fake repo)**

```python
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

    async def list_all(self):  # noqa: ANN201
        return tuple(self._store.values())

    async def get(self, def_id: str):  # noqa: ANN201
        return self._store.get(def_id)

    async def save(self, definition: GestureDefinition) -> None:
        self._store[definition.id] = definition

    async def delete(self, def_id: str) -> None:
        self._store.pop(def_id, None)


def _def(def_id: str) -> GestureDefinition:
    return GestureDefinition(
        id=def_id, name=def_id,
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/unit/application/use_cases/test_gesture_definition_use_cases.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the use cases**

Create `app/application/use_cases/save_gesture_definition.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain.exceptions import DomainError

if TYPE_CHECKING:
    from app.domain.gesture_definition import GestureDefinition
    from app.ports.gesture_def_repo import GestureDefinitionRepositoryPort


class SaveGestureDefinition:
    def __init__(self, repo: GestureDefinitionRepositoryPort) -> None:
        self._repo = repo

    async def execute(self, definition: GestureDefinition) -> None:
        if not definition.id.strip():
            raise DomainError("GestureDefinition id must not be empty")
        await self._repo.save(definition)
```

Create `app/application/use_cases/list_gesture_definitions.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.gesture_definition import GestureDefinition
    from app.ports.gesture_def_repo import GestureDefinitionRepositoryPort


class ListGestureDefinitions:
    def __init__(self, repo: GestureDefinitionRepositoryPort) -> None:
        self._repo = repo

    async def execute(self) -> tuple[GestureDefinition, ...]:
        return await self._repo.list_all()
```

Create `app/application/use_cases/delete_gesture_definition.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.ports.gesture_def_repo import GestureDefinitionRepositoryPort


class DeleteGestureDefinition:
    def __init__(self, repo: GestureDefinitionRepositoryPort) -> None:
        self._repo = repo

    async def execute(self, def_id: str) -> None:
        await self._repo.delete(def_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/unit/application/use_cases/test_gesture_definition_use_cases.py -v --no-cov`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add app/application/use_cases/save_gesture_definition.py app/application/use_cases/list_gesture_definitions.py app/application/use_cases/delete_gesture_definition.py tests/unit/application/use_cases/test_gesture_definition_use_cases.py
git commit -m "feat(application): add gesture-definition CRUD use cases"
```

---

### Task 4: Repo-backed binding resolver

**Files:**
- Create: `app/application/repo_binding_resolver.py`
- Test: `tests/unit/application/test_repo_binding_resolver.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import pytest

from app.application.repo_binding_resolver import RepoBindingResolver
from app.domain.gesture_definition import GestureDefinition, MotionSpec, PoseSpec
from app.domain.gestures import Binding
from app.ports.gesture_def_repo import GestureDefinitionRepositoryPort


class _FakeRepo(GestureDefinitionRepositoryPort):
    def __init__(self, defs: list[GestureDefinition]) -> None:
        self._defs = defs

    async def list_all(self):  # noqa: ANN201
        return tuple(self._defs)

    async def get(self, def_id: str):  # noqa: ANN201
        return next((d for d in self._defs if d.id == def_id), None)

    async def save(self, definition: GestureDefinition) -> None: ...
    async def delete(self, def_id: str) -> None: ...


def _def(def_id: str, action: str | None) -> GestureDefinition:
    return GestureDefinition(
        id=def_id, name=def_id,
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
    assert resolver.resolve("freeze") is None  # cache empty until reload()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/unit/application/test_repo_binding_resolver.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `app/application/repo_binding_resolver.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from app.ports.binding_resolver import BindingResolverPort

if TYPE_CHECKING:
    from app.domain.gestures import Binding
    from app.ports.gesture_def_repo import GestureDefinitionRepositoryPort


class RepoBindingResolver(BindingResolverPort):
    """Caches gesture->binding in memory; resolve() is sync (called per event).
    Call reload() after any config change."""

    def __init__(self, repo: GestureDefinitionRepositoryPort) -> None:
        self._repo = repo
        self._cache: dict[str, Binding] = {}

    async def reload(self) -> None:
        defs = await self._repo.list_all()
        self._cache = {d.id.lower(): d.binding for d in defs}

    def resolve(self, gesture: str) -> Binding | None:
        return self._cache.get(gesture.lower())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/unit/application/test_repo_binding_resolver.py -v --no-cov`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add app/application/repo_binding_resolver.py tests/unit/application/test_repo_binding_resolver.py
git commit -m "feat(application): add repo-backed cached binding resolver"
```

---

### Task 5: Config CRUD API + dep rewiring

**Files:**
- Modify: `app/api/schemas.py`
- Create: `app/api/gestures_config.py`
- Modify: `app/api/deps.py`
- Modify: `main.py`
- Test: `tests/unit/api/test_gesture_definition_schema.py`

- [ ] **Step 1: Write the failing schema test**

```python
from __future__ import annotations

from app.api.schemas import GestureDefinitionSchema


def test_round_trips_to_domain() -> None:
    raw = {
        "id": "punho_duplo", "name": "Punho duplo",
        "pose": {"shape": "fist", "hands": 2},
        "motion": {"type": "hold", "params": {}},
        "binding": {"effect": "freeze", "action": "swap_model", "action_params": {"model": "gemini"}},
    }
    schema = GestureDefinitionSchema.model_validate(raw)
    domain = schema.to_domain()
    assert domain.id == "punho_duplo"
    assert domain.binding.action == "swap_model"
    back = GestureDefinitionSchema.from_domain(domain)
    assert back.pose.shape == "fist"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/unit/api/test_gesture_definition_schema.py -v --no-cov`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Add the schema**

Append to `app/api/schemas.py`:

```python
from app.domain.gesture_definition import GestureDefinition, MotionSpec, PoseSpec
from app.domain.gestures import Binding


class PoseSpecSchema(BaseModel):
    shape: str
    hands: int


class MotionSpecSchema(BaseModel):
    type: str
    params: dict[str, object] = {}


class BindingSchema(BaseModel):
    effect: str
    action: str | None = None
    action_params: dict[str, object] = {}


class GestureDefinitionSchema(BaseModel):
    id: str
    name: str
    pose: PoseSpecSchema
    motion: MotionSpecSchema
    binding: BindingSchema

    def to_domain(self) -> GestureDefinition:
        return GestureDefinition(
            id=self.id, name=self.name,
            pose=PoseSpec(shape=self.pose.shape, hands=self.pose.hands),
            motion=MotionSpec(type=self.motion.type, params=self.motion.params),
            binding=Binding(
                effect=self.binding.effect,
                action=self.binding.action,
                action_params=self.binding.action_params,
            ),
        )

    @classmethod
    def from_domain(cls, d: GestureDefinition) -> GestureDefinitionSchema:
        return cls(
            id=d.id, name=d.name,
            pose=PoseSpecSchema(shape=d.pose.shape, hands=d.pose.hands),
            motion=MotionSpecSchema(type=d.motion.type, params=d.motion.params),
            binding=BindingSchema(
                effect=d.binding.effect,
                action=d.binding.action,
                action_params=d.binding.action_params,
            ),
        )
```

- [ ] **Step 4: Run schema test**

Run: `.venv\Scripts\python -m pytest tests/unit/api/test_gesture_definition_schema.py -v --no-cov`
Expected: PASS (1 passed)

- [ ] **Step 5: Wire repo + resolver singletons; repoint dispatcher**

In `app/api/deps.py` add (imports at top):

```python
from pathlib import Path

import httpx

from app.adapters.repository.json_gesture_def_repo import JsonGestureDefinitionRepository
from app.application.repo_binding_resolver import RepoBindingResolver
from app.ports.gesture_def_repo import GestureDefinitionRepositoryPort

_GESTURE_DEFS_PATH = Path("data/gesture_definitions.json")
_GESTURE_SERVICE_RELOAD_URL = "http://127.0.0.1:8001/reload"


@lru_cache
def get_gesture_def_repo() -> GestureDefinitionRepositoryPort:
    return JsonGestureDefinitionRepository(_GESTURE_DEFS_PATH)


@lru_cache
def get_binding_resolver() -> RepoBindingResolver:
    return RepoBindingResolver(get_gesture_def_repo())
```

Then change `get_action_dispatcher()` (from Phase 4) to use the repo resolver instead of the static one:

```python
@lru_cache
def get_action_dispatcher() -> ActionDispatcher:
    registry: Registry[ActionPort] = Registry()
    registry.register("swap_model", SwapModelAction(get_model_state()))
    registry.register("open_project", OpenProjectAction(get_developer_tool()))
    return ActionDispatcher(registry=registry, resolver=get_binding_resolver())
```

(Remove the now-unused `StaticBindingResolver`/`Binding` import from deps if it triggers a lint error; the static resolver remains available for tests.)

- [ ] **Step 6: Write the config API**

Create `app/api/gestures_config.py`:

```python
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
```

- [ ] **Step 7: Mount router + reload resolver on startup**

In `main.py`:
- add import: `from app.api.gestures_config import router as gestures_config_router`
- add import: `from app.api.deps import get_binding_resolver`
- in `lifespan` before `yield`: `await get_binding_resolver().reload()`
- after the other `include_router` calls: `app.include_router(gestures_config_router, prefix="/api/v1")`

Add `httpx` to the `api` optional deps in `pyproject.toml` if not already present (it ships with `fastapi[standard]`/`evolution_client`; verify with `.venv\Scripts\python -c "import httpx"`).

- [ ] **Step 8: Manual verify CRUD**

Start backend. Run:
`.venv\Scripts\python -c "import httpx; print(httpx.put('http://127.0.0.1:8000/api/v1/gestures/test', json={'id':'test','name':'T','pose':{'shape':'fist','hands':2},'motion':{'type':'hold','params':{}},'binding':{'effect':'freeze','action':None,'action_params':{}}}).json())"`
Then GET `http://127.0.0.1:8000/api/v1/gestures` in a browser.
Expected: the definition is created, listed, and `data/gesture_definitions.json` exists. (The reload POST to 8001 fails silently if the service is down — that is fine.)

- [ ] **Step 9: Commit**

```bash
git add app/api/schemas.py app/api/gestures_config.py app/api/deps.py main.py pyproject.toml tests/unit/api/test_gesture_definition_schema.py
git commit -m "feat(api): gesture-definition CRUD API; dispatcher uses repo bindings"
```

---

### Task 6: gesture-service — feature vector + KNN

**Files:**
- Create: `gesture_service/features.py`
- Create: `gesture_service/knn.py`
- Test: `tests/unit/gesture_service/test_features.py`
- Test: `tests/unit/gesture_service/test_knn.py`

- [ ] **Step 1: Write the failing features test**

```python
from __future__ import annotations

import pytest

from gesture_service.features import feature_vector
from gesture_service.landmarks import HandLandmarks, Landmark


def _hand(offset: float) -> HandLandmarks:
    pts = tuple(Landmark(0.1 * i + offset, 0.1 * i + offset, 0.0) for i in range(21))
    return HandLandmarks(points=pts, handedness="right")


def test_vector_length_is_63() -> None:
    assert len(feature_vector(_hand(0.0))) == 63


def test_translation_invariant() -> None:
    a = feature_vector(_hand(0.0))
    b = feature_vector(_hand(0.3))  # same shape, shifted
    for x, y in zip(a, b, strict=True):
        assert x == pytest.approx(y, abs=1e-6)
```

- [ ] **Step 2: Run test (fails)**

Run: `.venv\Scripts\python -m pytest tests/unit/gesture_service/test_features.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write features.py**

```python
from __future__ import annotations

from gesture_service.landmarks import HandLandmarks, distance

WRIST = 0
MIDDLE_MCP = 9


def feature_vector(hand: HandLandmarks) -> tuple[float, ...]:
    """Translation- and scale-invariant 63-d vector: each landmark relative to
    the wrist, divided by hand size (wrist->middle-MCP distance)."""
    p = hand.points
    origin = p[WRIST]
    scale = distance(p[WRIST], p[MIDDLE_MCP]) or 1.0
    out: list[float] = []
    for lm in p:
        out.append((lm.x - origin.x) / scale)
        out.append((lm.y - origin.y) / scale)
        out.append((lm.z - origin.z) / scale)
    return tuple(out)
```

- [ ] **Step 4: Run features test (pass)**

Run: `.venv\Scripts\python -m pytest tests/unit/gesture_service/test_features.py -v --no-cov`
Expected: PASS (2 passed)

- [ ] **Step 5: Write the failing KNN test**

```python
from __future__ import annotations

from gesture_service.knn import KnnClassifier


def test_classifies_nearest_label() -> None:
    clf = KnnClassifier(threshold=0.5)
    clf.add("fist", (0.0, 0.0, 0.0))
    clf.add("open", (10.0, 10.0, 10.0))
    assert clf.classify((0.1, 0.1, 0.1)) == "fist"
    assert clf.classify((9.9, 9.9, 9.9)) == "open"


def test_returns_none_when_far() -> None:
    clf = KnnClassifier(threshold=0.5)
    clf.add("fist", (0.0, 0.0, 0.0))
    assert clf.classify((50.0, 50.0, 50.0)) is None


def test_empty_classifier_returns_none() -> None:
    assert KnnClassifier(threshold=0.5).classify((0.0,)) is None
```

- [ ] **Step 6: Run KNN test (fails)**

Run: `.venv\Scripts\python -m pytest tests/unit/gesture_service/test_knn.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 7: Write knn.py**

```python
from __future__ import annotations

from dataclasses import dataclass, field

Vector = tuple[float, ...]


def _dist(a: Vector, b: Vector) -> float:
    n = min(len(a), len(b))
    return sum((a[i] - b[i]) ** 2 for i in range(n)) ** 0.5


@dataclass
class KnnClassifier:
    threshold: float = 0.6
    _templates: list[tuple[str, Vector]] = field(default_factory=list)

    def add(self, label: str, vector: Vector) -> None:
        self._templates.append((label, vector))

    def classify(self, vector: Vector) -> str | None:
        best_label: str | None = None
        best_dist = float("inf")
        for label, tpl in self._templates:
            d = _dist(vector, tpl)
            if d < best_dist:
                best_dist = d
                best_label = label
        if best_label is not None and best_dist <= self.threshold:
            return best_label
        return None
```

- [ ] **Step 8: Run KNN test (pass)**

Run: `.venv\Scripts\python -m pytest tests/unit/gesture_service/test_knn.py -v --no-cov`
Expected: PASS (3 passed)

- [ ] **Step 9: Commit**

```bash
git add gesture_service/features.py gesture_service/knn.py tests/unit/gesture_service/test_features.py tests/unit/gesture_service/test_knn.py
git commit -m "feat(gesture-service): add normalized feature vector + KNN pose classifier"
```

---

### Task 7: Pose template store

**Files:**
- Create: `gesture_service/pose_store.py`
- Test: `tests/unit/gesture_service/test_pose_store.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

from gesture_service.pose_store import PoseStore


def test_save_and_load_roundtrip(tmp_path) -> None:
    path = tmp_path / "poses.json"
    store = PoseStore(path)
    store.add_sample("wave_hand", (0.1, 0.2, 0.3))
    store.add_sample("wave_hand", (0.11, 0.21, 0.31))
    store.persist()

    reloaded = PoseStore(path)
    reloaded.load()
    samples = reloaded.samples()
    assert len(samples) == 2
    assert all(label == "wave_hand" for label, _ in samples)
```

- [ ] **Step 2: Run test (fails)**

Run: `.venv\Scripts\python -m pytest tests/unit/gesture_service/test_pose_store.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write pose_store.py**

```python
from __future__ import annotations

import json
from pathlib import Path

Vector = tuple[float, ...]


class PoseStore:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._samples: list[tuple[str, Vector]] = []

    def add_sample(self, label: str, vector: Vector) -> None:
        self._samples.append((label, vector))

    def samples(self) -> list[tuple[str, Vector]]:
        return list(self._samples)

    def labels(self) -> set[str]:
        return {label for label, _ in self._samples}

    def load(self) -> None:
        if not self._path.exists():
            self._samples = []
            return
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        self._samples = [(item["label"], tuple(item["vector"])) for item in raw]

    def persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = [{"label": label, "vector": list(vec)} for label, vec in self._samples]
        self._path.write_text(json.dumps(payload), encoding="utf-8")
```

- [ ] **Step 4: Run test (pass)**

Run: `.venv\Scripts\python -m pytest tests/unit/gesture_service/test_pose_store.py -v --no-cov`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add gesture_service/pose_store.py tests/unit/gesture_service/test_pose_store.py
git commit -m "feat(gesture-service): add pose template store"
```

---

### Task 8: Service config API — capture, current, reload (manual verify)

**Files:**
- Create: `gesture_service/config_api.py`
- Modify: `gesture_service/main.py`

This wires custom poses into detection and exposes the wizard's endpoints. The KNN augments rule-based poses: in `capture.py`'s per-hand loop, after `classify_pose`, if the result is `Pose.NONE`, consult the KNN over the hand's feature vector and treat a matched custom label as a recognized pose name.

- [ ] **Step 1: Add a shared latest-gesture holder + KNN to main.py**

In `gesture_service/main.py`, add module state:

```python
from gesture_service.knn import KnnClassifier
from gesture_service.pose_store import PoseStore
from pathlib import Path

_pose_store = PoseStore(Path("data/gesture_poses.json"))
_knn = KnnClassifier(threshold=0.6)
_latest_gesture: dict[str, object] = {"gesture": "none", "phase": "idle"}


def _rebuild_knn() -> None:
    _knn._templates.clear()
    for label, vec in _pose_store.samples():
        _knn.add(label, vec)
```

Call `_pose_store.load()` and `_rebuild_knn()` in `lifespan` startup. In `_on_frame`, after computing the event, record the latest gesture:

```python
    if event is not None:
        _latest_gesture["gesture"] = event.gesture
        _latest_gesture["phase"] = event.phase
        _publisher.publish(event)
```

- [ ] **Step 2: Write the config API router**

Create `gesture_service/config_api.py`:

```python
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class CaptureRequest(BaseModel):
    vectors: list[list[float]]  # feature vectors captured client-side or by /capture helper


def build_router(pose_store, rebuild_knn, latest_gesture) -> APIRouter:  # noqa: ANN001
    @router.post("/poses/{label}")
    def add_pose(label: str, body: CaptureRequest) -> dict[str, int]:
        for vec in body.vectors:
            pose_store.add_sample(label, tuple(vec))
        pose_store.persist()
        rebuild_knn()
        return {"samples": len(pose_store.samples())}

    @router.get("/current")
    def current() -> dict[str, object]:
        return dict(latest_gesture)

    @router.post("/reload")
    def reload() -> dict[str, bool]:
        # Future: re-fetch GestureDefinitions from backend. For now, rebuild KNN.
        pose_store.load()
        rebuild_knn()
        return {"ok": True}

    return router
```

In `gesture_service/main.py`, mount it:

```python
from gesture_service.config_api import build_router

app.include_router(build_router(_pose_store, _rebuild_knn, _latest_gesture))
```

- [ ] **Step 3: Use KNN as a fallback pose in capture.py**

In `gesture_service/capture.py`, accept an optional `knn` and `feature_fn` and, when `classify_pose` returns `Pose.NONE`, try the KNN. Minimal change: import and call a module-level hook. The simplest wiring that keeps `capture.py` pure-ish is to pass a `pose_override: Callable[[HandLandmarks], str | None] | None` parameter to `run_capture_loop` and, when it returns a label, set the HandFrame's pose to a custom marker. Since `HandFrame.pose` is a `Pose` enum, extend matching by adding the custom label to `GestureParams`/event downstream is out of scope; for Phase 5 the custom pose participates via the matcher only if the matcher is taught the label. **Scope for Phase 5:** custom poses are *recorded and classifiable* (proven by `/poses` + KNN tests); wiring a custom-pose gesture end-to-end into the matcher is a follow-on once the matcher reads `GestureDefinition`s. Document this in the commit.

- [ ] **Step 4: Manual verify**

Start the service. POST a few feature vectors:
`.venv\Scripts\python -c "import httpx; print(httpx.post('http://127.0.0.1:8001/poses/wave_hand', json={'vectors':[[0.0]*63,[0.01]*63]}).json())"`
Then GET `http://127.0.0.1:8001/current` while gesturing.
Expected: `/poses` returns a sample count and writes `data/gesture_poses.json`; `/current` reflects the live gesture name/phase.

- [ ] **Step 5: Commit**

```bash
git add gesture_service/config_api.py gesture_service/main.py
git commit -m "feat(gesture-service): pose capture, live /current, reload endpoints"
```

---

### Task 9: Phase close

- [ ] **Step 1: Full backend suite (incl. integration)**

Run: `.venv\Scripts\python -m pytest`
Expected: all pass (integration tests run; they use tmp_path). Coverage ≥80% on `app`.

- [ ] **Step 2: Lint + types**

Run: `.venv\Scripts\python -m ruff check app gesture_service && .venv\Scripts\python -m pyright app gesture_service`
Expected: no lint errors; pyright 0 errors.

- [ ] **Step 3: Manual integration**

Create a gesture via the backend API, confirm `get_binding_resolver().reload()` picks it up (the dispatcher now fires its action), and the service `/reload` is poked.

- [ ] **Step 4: Final commit (if fixes needed)**

```bash
git add -A
git commit -m "chore: phase 5 lint/type/integration pass"
```

---

## Self-Review Notes

- **Spec coverage (Phase 5 §):** 5.1 domain + JSON repo → Tasks 1,2. 5.2 pose-capture endpoint → Task 8. 5.3 KNN custom poses → Tasks 6,7 (recorded + classifiable). 5.4 CRUD API + reload → Tasks 3,5. 5.5 live-test → Task 8 (`/current`).
- **Async-first honored:** repository port is async; `RepoBindingResolver.resolve` stays sync (called per gesture event) backed by an async `reload()` cache.
- **Explicit scope boundary:** Task 8 Step 3 states that end-to-end custom-pose→matcher wiring is a follow-on once the matcher consumes `GestureDefinition`s; Phase 5 delivers recording + classification + persistence + CRUD. This is a stated scope edge, not a silent gap.
- **Type consistency:** `GestureDefinition`, `GestureDefinitionSchema.to_domain/from_domain`, `get_gesture_def_repo`, `get_binding_resolver`, `RepoBindingResolver.reload/resolve`, endpoints `/api/v1/gestures` are fixed and consumed by Phase 6.

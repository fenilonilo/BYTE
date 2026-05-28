# Gesture CV Service — Phase 4: Action Dispatch

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. **Prerequisite: Phase 2 complete** (independent of Phase 3).

**Goal:** Gestures trigger backend actions. A bus subscriber resolves a gesture → binding → action and executes it. Ship two actions: `swap_model` and `open_project`. Built-in default bindings make this work before the config UI exists.

**Architecture:** `ActionPort` (ABC) + an action `Registry[ActionPort]` (reusing `app/application/registry.py`). A `BindingResolverPort` answers "what does gesture X do"; Phase 4 ships a `StaticBindingResolver`; Phase 5 swaps in a repo-backed one. `ActionDispatcher` subscribes to the event bus and fires once per gesture activation (`phase in {instant, start}`). `swap_model` flips a shared `ModelState` that `ws_chat` reads as the model override.

**Tech Stack:** Python, hexagonal layering (domain/ports/application/adapters).

**Shared interfaces:** consumes `GestureEvent` (Phase 2 domain) + `get_event_bus()` (Phase 2 deps).

---

## File Structure

| File | Responsibility | Tested |
|------|----------------|--------|
| `app/domain/gestures.py` (modify) | add `Binding` (frozen) | TDD |
| `app/ports/action.py` | `ActionPort` (ABC) | — |
| `app/ports/binding_resolver.py` | `BindingResolverPort` (ABC) | — |
| `app/application/model_state.py` | mutable `ModelState` (active model override) | TDD |
| `app/application/binding_resolver.py` | `StaticBindingResolver` | TDD |
| `app/application/action_dispatcher.py` | `ActionDispatcher` (bus subscriber) | TDD |
| `app/adapters/actions/swap_model.py` | `SwapModelAction` | TDD |
| `app/adapters/actions/open_project.py` | `OpenProjectAction` | manual |
| `app/api/deps.py` (modify) | registry/dispatcher/model-state singletons | — |
| `app/api/ws_chat.py` (modify) | read `ModelState` for `model_override` | manual |
| `main.py` (modify) | subscribe dispatcher to the bus | — |
| `tests/unit/domain/test_bindings.py` | Binding test | — |
| `tests/unit/application/test_model_state.py` | model state test | — |
| `tests/unit/application/test_binding_resolver.py` | resolver test | — |
| `tests/unit/application/test_action_dispatcher.py` | dispatcher tests | — |
| `tests/unit/adapters/test_swap_model_action.py` | swap_model test | — |

---

### Task 1: Binding domain + ports

**Files:**
- Modify: `app/domain/gestures.py`
- Create: `app/ports/action.py`
- Create: `app/ports/binding_resolver.py`
- Test: `tests/unit/domain/test_bindings.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import pytest

from app.domain.gestures import Binding


def test_binding_fields() -> None:
    b = Binding(effect="freeze", action="swap_model", action_params={"model": "gemini"})
    assert b.effect == "freeze"
    assert b.action == "swap_model"
    assert b.action_params == {"model": "gemini"}


def test_binding_action_optional() -> None:
    b = Binding(effect="attract", action=None, action_params={})
    assert b.action is None


def test_binding_frozen() -> None:
    b = Binding(effect="freeze", action=None, action_params={})
    with pytest.raises(Exception):
        b.effect = "x"  # type: ignore[misc]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/unit/domain/test_bindings.py -v --no-cov`
Expected: FAIL — `ImportError: cannot import name 'Binding'`

- [ ] **Step 3: Add `Binding` to the domain**

Append to `app/domain/gestures.py`:

```python
@dataclass(frozen=True, slots=True)
class Binding:
    effect: str
    action: str | None
    action_params: dict[str, object]
```

- [ ] **Step 4: Write the ports**

Create `app/ports/action.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod


class ActionPort(ABC):
    @abstractmethod
    async def execute(self, params: dict[str, object]) -> None: ...
```

Create `app/ports/binding_resolver.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.gestures import Binding


class BindingResolverPort(ABC):
    @abstractmethod
    def resolve(self, gesture: str) -> Binding | None: ...
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/unit/domain/test_bindings.py -v --no-cov`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add app/domain/gestures.py app/ports/action.py app/ports/binding_resolver.py tests/unit/domain/test_bindings.py
git commit -m "feat: add Binding domain + ActionPort + BindingResolverPort"
```

---

### Task 2: ModelState

**Files:**
- Create: `app/application/model_state.py`
- Test: `tests/unit/application/test_model_state.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

from app.application.model_state import ModelState


def test_default_active_is_none() -> None:
    assert ModelState().active is None


def test_set_active() -> None:
    state = ModelState()
    state.active = "gemini"
    assert state.active == "gemini"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/unit/application/test_model_state.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.application.model_state'`

- [ ] **Step 3: Write the implementation**

Create `app/application/model_state.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ModelState:
    """Mutable runtime holder for the active model override (set by gestures,
    read by the chat endpoint)."""

    active: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/unit/application/test_model_state.py -v --no-cov`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add app/application/model_state.py tests/unit/application/test_model_state.py
git commit -m "feat(application): add mutable ModelState for active model override"
```

---

### Task 3: StaticBindingResolver

**Files:**
- Create: `app/application/binding_resolver.py`
- Test: `tests/unit/application/test_binding_resolver.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

from app.application.binding_resolver import StaticBindingResolver
from app.domain.gestures import Binding


def test_resolves_known_gesture() -> None:
    resolver = StaticBindingResolver({
        "freeze": Binding(effect="freeze", action="swap_model", action_params={"model": "gemini"}),
    })
    b = resolver.resolve("freeze")
    assert b is not None and b.action == "swap_model"


def test_unknown_gesture_returns_none() -> None:
    resolver = StaticBindingResolver({})
    assert resolver.resolve("nope") is None


def test_lookup_is_case_insensitive() -> None:
    resolver = StaticBindingResolver({
        "swipe": Binding(effect="wave", action=None, action_params={}),
    })
    assert resolver.resolve("SWIPE") is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/unit/application/test_binding_resolver.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `app/application/binding_resolver.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from app.ports.binding_resolver import BindingResolverPort

if TYPE_CHECKING:
    from app.domain.gestures import Binding


class StaticBindingResolver(BindingResolverPort):
    def __init__(self, bindings: dict[str, Binding]) -> None:
        self._bindings = {k.lower(): v for k, v in bindings.items()}

    def resolve(self, gesture: str) -> Binding | None:
        return self._bindings.get(gesture.lower())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/unit/application/test_binding_resolver.py -v --no-cov`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add app/application/binding_resolver.py tests/unit/application/test_binding_resolver.py
git commit -m "feat(application): add static binding resolver"
```

---

### Task 4: ActionDispatcher

**Files:**
- Create: `app/application/action_dispatcher.py`
- Test: `tests/unit/application/test_action_dispatcher.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import pytest

from app.application.action_dispatcher import ActionDispatcher
from app.application.binding_resolver import StaticBindingResolver
from app.application.registry import Registry
from app.domain.gestures import Binding, GestureEvent, GestureParams
from app.ports.action import ActionPort


class _SpyAction(ActionPort):
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def execute(self, params: dict[str, object]) -> None:
        self.calls.append(params)


def _event(gesture: str, phase: str) -> GestureEvent:
    return GestureEvent(gesture=gesture, phase=phase, hands=2, params=GestureParams(), ts=0.0)


def _dispatcher(spy: _SpyAction) -> ActionDispatcher:
    registry: Registry[ActionPort] = Registry()
    registry.register("swap_model", spy)
    resolver = StaticBindingResolver({
        "freeze": Binding(effect="freeze", action="swap_model", action_params={"model": "gemini"}),
        "swipe": Binding(effect="wave", action=None, action_params={}),
    })
    return ActionDispatcher(registry=registry, resolver=resolver)


@pytest.mark.asyncio
async def test_fires_action_on_instant() -> None:
    spy = _SpyAction()
    d = _dispatcher(spy)
    await d.handle(_event("freeze", "instant"))
    assert spy.calls == [{"model": "gemini"}]


@pytest.mark.asyncio
async def test_fires_on_start_once_not_on_hold() -> None:
    spy = _SpyAction()
    d = _dispatcher(spy)
    await d.handle(_event("freeze", "start"))
    await d.handle(_event("freeze", "hold"))
    assert len(spy.calls) == 1


@pytest.mark.asyncio
async def test_noop_when_binding_has_no_action() -> None:
    spy = _SpyAction()
    d = _dispatcher(spy)
    await d.handle(_event("swipe", "instant"))
    assert spy.calls == []


@pytest.mark.asyncio
async def test_noop_when_no_binding() -> None:
    spy = _SpyAction()
    d = _dispatcher(spy)
    await d.handle(_event("unknown", "instant"))
    assert spy.calls == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/unit/application/test_action_dispatcher.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `app/application/action_dispatcher.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain.exceptions import RegistryKeyError

if TYPE_CHECKING:
    from app.application.registry import Registry
    from app.domain.gestures import GestureEvent
    from app.ports.action import ActionPort
    from app.ports.binding_resolver import BindingResolverPort

_TRIGGER_PHASES = frozenset({"instant", "start"})


class ActionDispatcher:
    def __init__(
        self,
        registry: Registry[ActionPort],
        resolver: BindingResolverPort,
    ) -> None:
        self._registry = registry
        self._resolver = resolver

    async def handle(self, event: GestureEvent) -> None:
        if event.phase not in _TRIGGER_PHASES:
            return
        binding = self._resolver.resolve(event.gesture)
        if binding is None or binding.action is None:
            return
        try:
            action = self._registry.get(binding.action)
        except RegistryKeyError:
            return
        await action.execute(binding.action_params)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/unit/application/test_action_dispatcher.py -v --no-cov`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add app/application/action_dispatcher.py tests/unit/application/test_action_dispatcher.py
git commit -m "feat(application): add action dispatcher firing on gesture activation"
```

---

### Task 5: SwapModelAction

**Files:**
- Create: `app/adapters/actions/__init__.py`
- Create: `app/adapters/actions/swap_model.py`
- Test: `tests/unit/adapters/test_swap_model_action.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import pytest

from app.adapters.actions.swap_model import SwapModelAction
from app.application.model_state import ModelState


@pytest.mark.asyncio
async def test_swap_sets_active_model() -> None:
    state = ModelState()
    action = SwapModelAction(state)
    await action.execute({"model": "gemini"})
    assert state.active == "gemini"


@pytest.mark.asyncio
async def test_swap_ignores_missing_model() -> None:
    state = ModelState(active="groq")
    action = SwapModelAction(state)
    await action.execute({})
    assert state.active == "groq"
```

Create `tests/unit/adapters/__init__.py` (empty) if it does not exist.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/unit/adapters/test_swap_model_action.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `app/adapters/actions/__init__.py` (empty).

Create `app/adapters/actions/swap_model.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from app.ports.action import ActionPort

if TYPE_CHECKING:
    from app.application.model_state import ModelState


class SwapModelAction(ActionPort):
    def __init__(self, model_state: ModelState) -> None:
        self._state = model_state

    async def execute(self, params: dict[str, object]) -> None:
        model = params.get("model")
        if isinstance(model, str) and model:
            self._state.active = model
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/unit/adapters/test_swap_model_action.py -v --no-cov`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add app/adapters/actions/__init__.py app/adapters/actions/swap_model.py tests/unit/adapters/
git commit -m "feat(adapters): add SwapModelAction setting the active model override"
```

---

### Task 6: OpenProjectAction (manual verify)

**Files:**
- Create: `app/adapters/actions/open_project.py`

- [ ] **Step 1: Write the implementation**

Create `app/adapters/actions/open_project.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from app.ports.action import ActionPort

if TYPE_CHECKING:
    from app.adapters.tools.developer_tool import DeveloperToolkit


class OpenProjectAction(ActionPort):
    """Open a dev environment for a project named in params['project'].
    Reuses the existing DeveloperToolkit."""

    def __init__(self, dev_tool: DeveloperToolkit) -> None:
        self._dev = dev_tool

    async def execute(self, params: dict[str, object]) -> None:
        project = params.get("project")
        if isinstance(project, str) and project:
            self._dev.open_dev_environment(project)
```

- [ ] **Step 2: Verify import**

Run: `.venv\Scripts\python -c "import app.adapters.actions.open_project; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add app/adapters/actions/open_project.py
git commit -m "feat(adapters): add OpenProjectAction over the developer toolkit"
```

---

### Task 7: Wire registry, dispatcher, default bindings, model override

**Files:**
- Modify: `app/api/deps.py`
- Modify: `app/api/ws_chat.py`
- Modify: `main.py`

- [ ] **Step 1: Add singletons + default bindings to deps**

Append to `app/api/deps.py` (add imports at top as needed):

```python
from app.adapters.actions.open_project import OpenProjectAction
from app.adapters.actions.swap_model import SwapModelAction
from app.application.action_dispatcher import ActionDispatcher
from app.application.binding_resolver import StaticBindingResolver
from app.application.model_state import ModelState
from app.application.registry import Registry
from app.domain.gestures import Binding
from app.ports.action import ActionPort


@lru_cache
def get_model_state() -> ModelState:
    return ModelState()


@lru_cache
def get_action_dispatcher() -> ActionDispatcher:
    registry: Registry[ActionPort] = Registry()
    registry.register("swap_model", SwapModelAction(get_model_state()))
    registry.register("open_project", OpenProjectAction(get_developer_tool()))

    # Built-in default bindings (Phase 5 config will override this resolver).
    resolver = StaticBindingResolver({
        "freeze": Binding(effect="freeze", action="swap_model", action_params={"model": "gemini"}),
        "portal": Binding(effect="portal", action="swap_model", action_params={"model": "groq"}),
    })
    return ActionDispatcher(registry=registry, resolver=resolver)
```

- [ ] **Step 2: Read the model override in ws_chat**

In `app/api/ws_chat.py`, import the dep and use it when building the `IncomingMessage`:

Add to imports:
```python
from app.api.deps import get_model_state
```

Inside `ws_chat`, after `dev_tool = get_developer_tool()`:
```python
    model_state = get_model_state()
```

Change the `IncomingMessage(...)` construction's `model_override=None` to:
```python
                model_override=model_state.active,
```

- [ ] **Step 3: Subscribe the dispatcher to the bus**

In `main.py`, add to imports:
```python
from app.api.deps import get_action_dispatcher
```

In `lifespan`, alongside the `frontend_bridge` subscription:
```python
    get_event_bus().subscribe(get_action_dispatcher().handle)
```

- [ ] **Step 4: Manual end-to-end verify**

Start backend + gesture-service + vite. Perform `freeze` (two fists).
Expected: backend sets the active model to `gemini`; the next chat message routes through Gemini (verify via the agent's response/log). Perform `portal` → switches back to `groq`.

- [ ] **Step 5: Commit**

```bash
git add app/api/deps.py app/api/ws_chat.py main.py
git commit -m "feat(api): dispatch gesture actions; chat honors gesture-set model override"
```

---

### Task 8: Phase close

- [ ] **Step 1: Full suite + coverage**

Run: `.venv\Scripts\python -m pytest`
Expected: all pass; `app` coverage ≥80% (new application code is covered by the new unit tests).

- [ ] **Step 2: Lint + types**

Run: `.venv\Scripts\python -m ruff check app && .venv\Scripts\python -m pyright app`
Expected: no lint errors; pyright 0 errors.

- [ ] **Step 3: Final commit (if fixes were needed)**

```bash
git add -A
git commit -m "chore: phase 4 lint/type pass"
```

---

## Self-Review Notes

- **Spec coverage (Phase 4 §):** 4.1 ActionPort + registry → Task 1 + Task 7 (registry wiring). 4.2 ActionDispatcher → Task 4. 4.3 swap_model → Task 5. 4.4 open_file/open_project → Task 6. 4.5 default bindings → Task 7.
- **Fire-once semantics:** dispatcher acts only on `phase ∈ {instant, start}`, so a held sustained gesture fires its action exactly once. Matches the Phase 1 matcher's lifecycle.
- **Phase 5 seam:** `BindingResolverPort` is the swap point — Phase 5 provides a repo-backed resolver and `get_action_dispatcher` is repointed to it.
- **Type consistency:** `Binding`, `ActionPort`, `BindingResolverPort`, `ActionDispatcher.handle`, `ModelState.active`, registry key `"swap_model"`/`"open_project"` are fixed and reused in Phase 5.

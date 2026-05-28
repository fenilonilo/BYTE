# Gesture CV Service — Phase 2: Event Bus + Frontend Bridge

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. **Prerequisite: Phase 1 complete.**

**Goal:** Gestures detected by the service flow over WebSocket into a backend event bus, fan out to a frontend bridge, and reach the browser — replacing the in-browser MediaPipe path. The webcam preview comes from the service.

**Architecture:** A new `EventBusPort` + in-process implementation lives in the backend application layer. The gesture-service gains a publisher that connects to a backend ingest WebSocket. A `FrontendBridge` bus subscriber forwards every event to connected browsers over a second WebSocket. The browser drops `getUserMedia`/MediaPipe and instead consumes events from a thin WS client.

**Tech Stack:** Python, FastAPI WebSockets, `websockets` client lib, Svelte 5 / TypeScript.

**Shared interfaces:** see the PLAN-INDEX "Shared interface reference". `GestureEvent` JSON shape is fixed there.

---

## File Structure

| File | Responsibility | Tested |
|------|----------------|--------|
| `app/domain/gestures.py` | Domain `Vec3`, `GestureParams`, `GestureEvent` (frozen) | TDD |
| `app/ports/event_bus.py` | `EventBusPort` (ABC) | — |
| `app/application/event_bus.py` | `InProcessEventBus` | TDD |
| `app/api/schemas.py` (modify) | `GestureEventSchema` (Pydantic) + `to_domain()` | TDD |
| `app/api/ws_gesture.py` | Browser WS `/ws/gesture` + connection manager + `FrontendBridge` | manual |
| `app/api/gesture_ingest.py` | Ingest WS `/ws/gesture-ingest` (service → bus) | manual |
| `app/api/deps.py` (modify) | `get_event_bus()` singleton | — |
| `main.py` (modify) | mount routers, subscribe `FrontendBridge` | — |
| `gesture_service/publisher.py` | WS client → backend ingest | manual |
| `gesture_service/main.py` (modify) | push events through publisher | manual |
| `gesture_service/config.py` (modify) | `backend_ingest_url` | — |
| `marcelo-ui/src/lib/gesture-types.ts` | TS `GestureEvent` types | — |
| `marcelo-ui/src/lib/gesture-client.ts` | WS client → store + engine adapter | manual |
| `marcelo-ui/src/stores/gesture.svelte.ts` (modify) | consume `GestureEvent` | — |
| `marcelo-ui/src/components/ParticleCanvas.svelte` (modify) | remove MediaPipe; connect client | manual |
| `marcelo-ui/src/components/WebcamView.svelte` (modify) | show service `/preview` | manual |
| `tests/unit/domain/test_gestures.py` | domain tests | — |
| `tests/unit/application/test_event_bus.py` | bus tests | — |
| `tests/unit/api/test_gesture_schema.py` | schema tests | — |

---

### Task 1: Domain gesture model

**Files:**
- Create: `app/domain/gestures.py`
- Test: `tests/unit/domain/test_gestures.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import pytest

from app.domain.gestures import GestureEvent, GestureParams, Vec3


def test_vec3_defaults() -> None:
    assert Vec3() == Vec3(0.0, 0.0, 0.0)


def test_gesture_event_fields() -> None:
    ev = GestureEvent(
        gesture="pinch", phase="start", hands=1,
        params=GestureParams(points=(Vec3(0.5, 0.5, 0.0),)), ts=1.0,
    )
    assert ev.gesture == "pinch"
    assert ev.params.points[0].x == 0.5


def test_gesture_event_frozen() -> None:
    ev = GestureEvent(gesture="none", phase="idle", hands=0, params=GestureParams(), ts=0.0)
    with pytest.raises(Exception):
        ev.gesture = "x"  # type: ignore[misc]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/unit/domain/test_gestures.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.domain.gestures'`

- [ ] **Step 3: Write the implementation**

Create `app/domain/gestures.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Vec3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass(frozen=True, slots=True)
class GestureParams:
    points: tuple[Vec3, ...] = ()
    vector: Vec3 = field(default_factory=Vec3)
    center: Vec3 = field(default_factory=Vec3)
    radius: float = 0.0
    magnitude: float = 0.0


@dataclass(frozen=True, slots=True)
class GestureEvent:
    gesture: str
    phase: str
    hands: int
    params: GestureParams
    ts: float
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/unit/domain/test_gestures.py -v --no-cov`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add app/domain/gestures.py tests/unit/domain/test_gestures.py
git commit -m "feat(domain): add gesture event domain model"
```

---

### Task 2: EventBusPort

**Files:**
- Create: `app/ports/event_bus.py`

- [ ] **Step 1: Write the port (no test — pure ABC)**

Create `app/ports/event_bus.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.gestures import GestureEvent

GestureHandler = Callable[["GestureEvent"], Awaitable[None]]


class EventBusPort(ABC):
    @abstractmethod
    def subscribe(self, handler: GestureHandler) -> None: ...

    @abstractmethod
    async def publish(self, event: GestureEvent) -> None: ...
```

- [ ] **Step 2: Commit**

```bash
git add app/ports/event_bus.py
git commit -m "feat(ports): add EventBusPort"
```

---

### Task 3: InProcessEventBus

**Files:**
- Create: `app/application/event_bus.py`
- Test: `tests/unit/application/test_event_bus.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import pytest

from app.application.event_bus import InProcessEventBus
from app.domain.gestures import GestureEvent, GestureParams


def _event(name: str) -> GestureEvent:
    return GestureEvent(gesture=name, phase="instant", hands=1, params=GestureParams(), ts=0.0)


@pytest.mark.asyncio
async def test_publish_fans_out_to_all_subscribers() -> None:
    bus = InProcessEventBus()
    seen_a: list[str] = []
    seen_b: list[str] = []

    async def a(ev: GestureEvent) -> None:
        seen_a.append(ev.gesture)

    async def b(ev: GestureEvent) -> None:
        seen_b.append(ev.gesture)

    bus.subscribe(a)
    bus.subscribe(b)
    await bus.publish(_event("pinch"))

    assert seen_a == ["pinch"]
    assert seen_b == ["pinch"]


@pytest.mark.asyncio
async def test_publish_with_no_subscribers_is_noop() -> None:
    bus = InProcessEventBus()
    await bus.publish(_event("swipe"))  # must not raise


@pytest.mark.asyncio
async def test_one_failing_subscriber_does_not_block_others() -> None:
    bus = InProcessEventBus()
    seen: list[str] = []

    async def bad(ev: GestureEvent) -> None:
        raise RuntimeError("boom")

    async def good(ev: GestureEvent) -> None:
        seen.append(ev.gesture)

    bus.subscribe(bad)
    bus.subscribe(good)
    await bus.publish(_event("freeze"))

    assert seen == ["freeze"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/unit/application/test_event_bus.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.application.event_bus'`

- [ ] **Step 3: Write the implementation**

Create `app/application/event_bus.py`:

```python
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from app.ports.event_bus import EventBusPort, GestureHandler

if TYPE_CHECKING:
    from app.domain.gestures import GestureEvent


class InProcessEventBus(EventBusPort):
    def __init__(self) -> None:
        self._handlers: list[GestureHandler] = []

    def subscribe(self, handler: GestureHandler) -> None:
        self._handlers.append(handler)

    async def publish(self, event: GestureEvent) -> None:
        results = await asyncio.gather(
            *(h(event) for h in self._handlers), return_exceptions=True
        )
        # Failing subscribers must not break the fan-out; they are swallowed here.
        # (Subscribers do their own logging.)
        _ = results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/unit/application/test_event_bus.py -v --no-cov`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add app/application/event_bus.py tests/unit/application/test_event_bus.py
git commit -m "feat(application): add in-process event bus with isolated fan-out"
```

---

### Task 4: GestureEventSchema (API boundary)

**Files:**
- Modify: `app/api/schemas.py`
- Test: `tests/unit/api/test_gesture_schema.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

from app.api.schemas import GestureEventSchema


def test_schema_parses_and_converts_to_domain() -> None:
    raw = {
        "gesture": "portal",
        "phase": "start",
        "hands": 2,
        "params": {
            "points": [{"x": 0.3, "y": 0.5, "z": 0.0}, {"x": 0.7, "y": 0.5, "z": 0.0}],
            "vector": {"x": 0.0, "y": 0.0, "z": 0.0},
            "center": {"x": 0.5, "y": 0.5, "z": 0.0},
            "radius": 0.2,
            "magnitude": 0.0,
        },
        "ts": 12.0,
    }
    schema = GestureEventSchema.model_validate(raw)
    domain = schema.to_domain()
    assert domain.gesture == "portal"
    assert domain.hands == 2
    assert domain.params.center.x == 0.5
    assert domain.params.radius == 0.2
    assert len(domain.params.points) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/unit/api/test_gesture_schema.py -v --no-cov`
Expected: FAIL — `ImportError: cannot import name 'GestureEventSchema'`

- [ ] **Step 3: Add the schema**

Append to `app/api/schemas.py`:

```python
from app.domain.gestures import GestureEvent, GestureParams, Vec3


class Vec3Schema(BaseModel):
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def to_domain(self) -> Vec3:
        return Vec3(self.x, self.y, self.z)


class GestureParamsSchema(BaseModel):
    points: list[Vec3Schema] = []
    vector: Vec3Schema = Vec3Schema()
    center: Vec3Schema = Vec3Schema()
    radius: float = 0.0
    magnitude: float = 0.0

    def to_domain(self) -> GestureParams:
        return GestureParams(
            points=tuple(p.to_domain() for p in self.points),
            vector=self.vector.to_domain(),
            center=self.center.to_domain(),
            radius=self.radius,
            magnitude=self.magnitude,
        )


class GestureEventSchema(BaseModel):
    gesture: str
    phase: str
    hands: int
    params: GestureParamsSchema
    ts: float

    def to_domain(self) -> GestureEvent:
        return GestureEvent(
            gesture=self.gesture,
            phase=self.phase,
            hands=self.hands,
            params=self.params.to_domain(),
            ts=self.ts,
        )
```

Note: if `app/api/schemas.py` does not already `from pydantic import BaseModel`, add that import at the top.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/unit/api/test_gesture_schema.py -v --no-cov`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add app/api/schemas.py tests/unit/api/test_gesture_schema.py
git commit -m "feat(api): add GestureEvent boundary schema with domain conversion"
```

---

### Task 5: Browser WS endpoint + FrontendBridge

**Files:**
- Create: `app/api/ws_gesture.py`

- [ ] **Step 1: Write the implementation**

Create `app/api/ws_gesture.py`:

```python
from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import TYPE_CHECKING

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

if TYPE_CHECKING:
    from app.domain.gestures import GestureEvent

router = APIRouter()


class _ConnectionManager:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def add(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    async def remove(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, event: GestureEvent) -> None:
        payload = {
            "gesture": event.gesture,
            "phase": event.phase,
            "hands": event.hands,
            "params": asdict(event.params),
            "ts": event.ts,
        }
        async with self._lock:
            targets = list(self._clients)
        for ws in targets:
            try:
                await ws.send_json(payload)
            except Exception:
                await self.remove(ws)


manager = _ConnectionManager()


async def frontend_bridge(event: GestureEvent) -> None:
    """Bus subscriber: forward every gesture event to connected browsers."""
    await manager.broadcast(event)


@router.websocket("/ws/gesture")
async def ws_gesture(websocket: WebSocket) -> None:
    await manager.add(websocket)
    try:
        while True:
            await websocket.receive_text()  # keepalive; browser sends nothing meaningful
    except WebSocketDisconnect:
        await manager.remove(websocket)
```

- [ ] **Step 2: Verify import**

Run: `.venv\Scripts\python -c "import app.api.ws_gesture; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add app/api/ws_gesture.py
git commit -m "feat(api): add browser gesture WS + FrontendBridge subscriber"
```

---

### Task 6: Ingest endpoint (service → bus)

**Files:**
- Create: `app/api/gesture_ingest.py`
- Modify: `app/api/deps.py`

- [ ] **Step 1: Add the bus singleton to deps**

Append to `app/api/deps.py` (inside the non-TYPE_CHECKING area; add the import at top):

```python
from app.application.event_bus import InProcessEventBus
from app.ports.event_bus import EventBusPort


@lru_cache
def get_event_bus() -> EventBusPort:
    return InProcessEventBus()
```

- [ ] **Step 2: Write the ingest endpoint**

Create `app/api/gesture_ingest.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.deps import get_event_bus, get_logger
from app.api.schemas import GestureEventSchema

router = APIRouter()


@router.websocket("/ws/gesture-ingest")
async def ws_gesture_ingest(websocket: WebSocket) -> None:
    await websocket.accept()
    bus = get_event_bus()
    log = get_logger()
    try:
        while True:
            raw = await websocket.receive_json()
            try:
                event = GestureEventSchema.model_validate(raw).to_domain()
            except Exception as exc:  # malformed payload from service
                log.info("gesture-ingest-invalid", error=str(exc))
                continue
            await bus.publish(event)
    except WebSocketDisconnect:
        pass
```

- [ ] **Step 3: Verify import**

Run: `.venv\Scripts\python -c "import app.api.gesture_ingest; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add app/api/gesture_ingest.py app/api/deps.py
git commit -m "feat(api): add gesture ingest WS publishing to the event bus"
```

---

### Task 7: Wire routers + subscriber in main.py

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Mount routers and subscribe the bridge**

In `main.py`, add imports near the other router imports:

```python
from app.api.deps import get_event_bus
from app.api.gesture_ingest import router as gesture_ingest_router
from app.api.ws_gesture import frontend_bridge
from app.api.ws_gesture import router as ws_gesture_router
```

In the `lifespan` function, before `yield`, subscribe the bridge:

```python
    get_event_bus().subscribe(frontend_bridge)
```

After the existing `app.include_router(ws_chat_router)` line, add:

```python
app.include_router(ws_gesture_router)
app.include_router(gesture_ingest_router)
```

- [ ] **Step 2: Verify the app boots**

Run: `.venv\Scripts\python -c "import main; print([r.path for r in main.app.routes if 'gesture' in getattr(r, 'path', '')])"`
Expected: prints a list containing `/ws/gesture` and `/ws/gesture-ingest`.

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat(api): wire gesture bus, ingest, and browser WS into the app"
```

---

### Task 8: gesture-service publisher

**Files:**
- Create: `gesture_service/publisher.py`
- Modify: `gesture_service/config.py`
- Modify: `gesture_service/main.py`

- [ ] **Step 1: Add backend URL to config**

In `gesture_service/config.py`, add to `CameraSettings` a sibling settings dataclass:

```python
@dataclass(frozen=True, slots=True)
class ServiceSettings:
    backend_ingest_url: str = "ws://127.0.0.1:8000/ws/gesture-ingest"
    reconnect_seconds: float = 2.0
```

- [ ] **Step 2: Add `websockets` to the vision deps**

In `pyproject.toml`, add `"websockets>=13.0"` to the `vision` optional group, then run:
`.venv\Scripts\python -m pip install -e ".[vision]"`
Expected: installs `websockets`.

- [ ] **Step 3: Write the publisher**

Create `gesture_service/publisher.py`:

```python
from __future__ import annotations

import asyncio
import contextlib
import json
import queue
import threading
from dataclasses import asdict

import websockets

from gesture_service.config import ServiceSettings
from gesture_service.events import GestureEvent


class EventPublisher:
    """Thread-safe queue drained by a background asyncio loop that ships
    events to the backend ingest WebSocket, reconnecting on drop."""

    def __init__(self, settings: ServiceSettings | None = None) -> None:
        self._settings = settings or ServiceSettings()
        self._queue: queue.Queue[GestureEvent] = queue.Queue(maxsize=256)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._stop = threading.Event()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def publish(self, event: GestureEvent) -> None:
        with contextlib.suppress(queue.Full):
            self._queue.put_nowait(event)

    def _payload(self, ev: GestureEvent) -> str:
        return json.dumps({
            "gesture": ev.gesture,
            "phase": ev.phase,
            "hands": ev.hands,
            "params": asdict(ev.params),
            "ts": ev.ts,
        })

    def _run(self) -> None:
        asyncio.run(self._loop())

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                async with websockets.connect(self._settings.backend_ingest_url) as ws:
                    while not self._stop.is_set():
                        try:
                            ev = self._queue.get(timeout=0.1)
                        except queue.Empty:
                            await asyncio.sleep(0)
                            continue
                        await ws.send(self._payload(ev))
            except Exception:
                await asyncio.sleep(self._settings.reconnect_seconds)
```

- [ ] **Step 4: Push events through the publisher in main.py**

In `gesture_service/main.py`, replace the `_on_frame` body's logging with publishing. Add at module level:

```python
from gesture_service.publisher import EventPublisher

_publisher = EventPublisher()
```

Change `_on_frame` to also publish:

```python
def _on_frame(frames: list[HandFrame], annotated: object) -> None:
    set_latest_frame(annotated)
    import time

    event = _matcher.update(frames, now=time.monotonic())
    if event is not None:
        _publisher.publish(event)
        log.info("gesture", gesture=event.gesture, phase=event.phase, hands=event.hands)
```

In `lifespan`, start/stop the publisher around the camera thread:

```python
    _publisher.start()
    thread = threading.Thread(... )   # existing
    thread.start()
    log.info("capture-thread-started")
    yield
    _stop.set()
    _publisher.stop()
```

- [ ] **Step 5: Manual end-to-end verify**

Run the backend (`.venv\Scripts\uvicorn main:app --port 8000`) and the service (`.venv\Scripts\python -m gesture_service.main`).
Expected: backend logs no ingest errors; performing a gesture, the service logs it and the backend receives it (add a temporary print in the ingest loop if needed, then remove).

- [ ] **Step 6: Commit**

```bash
git add gesture_service/publisher.py gesture_service/config.py gesture_service/main.py pyproject.toml
git commit -m "feat(gesture-service): publish gesture events to backend ingest WS"
```

---

### Task 9: Frontend — consume events, retire browser MediaPipe

**Files:**
- Create: `marcelo-ui/src/lib/gesture-types.ts`
- Create: `marcelo-ui/src/lib/gesture-client.ts`
- Modify: `marcelo-ui/src/stores/gesture.svelte.ts`
- Modify: `marcelo-ui/src/components/ParticleCanvas.svelte`
- Modify: `marcelo-ui/src/components/WebcamView.svelte`
- Delete (usage): `marcelo-ui/src/lib/gesture-engine.ts`

- [ ] **Step 1: Add TS types**

Create `marcelo-ui/src/lib/gesture-types.ts`:

```typescript
export interface WireVec3 { x: number; y: number; z: number }

export interface WireGestureParams {
  points: WireVec3[]
  vector: WireVec3
  center: WireVec3
  radius: number
  magnitude: number
}

export interface WireGestureEvent {
  gesture: string
  phase: 'start' | 'hold' | 'end' | 'instant' | 'idle'
  hands: 0 | 1 | 2
  params: WireGestureParams
  ts: number
}
```

- [ ] **Step 2: Add the WS client**

Create `marcelo-ui/src/lib/gesture-client.ts`:

```typescript
import type { WireGestureEvent } from './gesture-types'

type Listener = (ev: WireGestureEvent) => void

let socket: WebSocket | null = null
let listener: Listener | null = null
let reconnectTimer: number | null = null

export function connectGestures(onEvent: Listener): void {
  listener = onEvent
  open()
}

function open(): void {
  // Vite proxies /ws → ws://localhost:8000 (see vite.config.ts)
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  socket = new WebSocket(`${proto}://${location.host}/ws/gesture`)

  socket.onmessage = (msg) => {
    try {
      const ev = JSON.parse(msg.data) as WireGestureEvent
      listener?.(ev)
    } catch { /* ignore malformed frame */ }
  }
  socket.onclose = () => {
    reconnectTimer = window.setTimeout(open, 2000)
  }
}

export function disconnectGestures(): void {
  if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
  socket?.close()
  socket = null
  listener = null
}
```

- [ ] **Step 3: Update the gesture store to hold the wire event**

Replace `marcelo-ui/src/stores/gesture.svelte.ts` with:

```typescript
import type { WireGestureEvent } from '../lib/gesture-types'

export const gestureState = $state<WireGestureEvent>({
  gesture: 'none',
  phase: 'idle',
  hands: 0,
  params: {
    points: [],
    vector: { x: 0, y: 0, z: 0 },
    center: { x: 0, y: 0, z: 0 },
    radius: 0,
    magnitude: 0,
  },
  ts: 0,
})

export function updateGestureState(next: WireGestureEvent): void {
  gestureState.gesture = next.gesture
  gestureState.phase = next.phase
  gestureState.hands = next.hands
  gestureState.params = next.params
  gestureState.ts = next.ts
}
```

- [ ] **Step 4: Rewrite ParticleCanvas to use the client (interim bridge to the existing CPU engine)**

Replace `marcelo-ui/src/components/ParticleCanvas.svelte` with:

```svelte
<script lang="ts">
  import { onMount, onDestroy } from 'svelte'
  import * as THREE from 'three'
  import * as ParticleEngine from '../lib/particle-engine'
  import { connectGestures, disconnectGestures } from '../lib/gesture-client'
  import { updateGestureState } from '../stores/gesture.svelte'
  import type { WireGestureEvent } from '../lib/gesture-types'

  let canvasEl: HTMLCanvasElement

  // Interim adapter: map the wire event to the existing engine's UnifiedGestureState.
  // Phase 3 replaces particle-engine entirely and consumes the wire event directly.
  function toUnified(ev: WireGestureEvent) {
    return {
      gesture: ev.gesture as any,
      handCount: ev.hands,
      swipeSign: ev.params.vector.x >= 0 ? 1 : -1,
      orbitAnchor: new THREE.Vector3(ev.params.center.x, ev.params.center.y, 0),
      portalCenter: new THREE.Vector3(ev.params.center.x, ev.params.center.y, 0),
      portalRadius: ev.params.radius * 50,
      phase: ev.phase === 'instant' ? 'blast' : ev.phase,
    }
  }

  onMount(() => {
    ParticleEngine.init(canvasEl)
    connectGestures((ev) => {
      updateGestureState(ev)
      ParticleEngine.applyGesture(toUnified(ev))
    })
  })

  onDestroy(() => {
    disconnectGestures()
    ParticleEngine.dispose()
  })
</script>

<canvas
  bind:this={canvasEl}
  style="position:fixed;inset:0;z-index:0;width:100vw;height:100vh;display:block;"
></canvas>
```

(The hidden `<video>` element and `GestureEngine` import are removed — the browser no longer touches the camera.)

- [ ] **Step 5: Point WebcamView at the service preview**

Replace `marcelo-ui/src/components/WebcamView.svelte` body with an `<img>` corner preview:

```svelte
<script lang="ts">
  const PREVIEW_URL = 'http://localhost:8001/preview'
</script>

<img
  src={PREVIEW_URL}
  alt="webcam"
  style="position:fixed;right:16px;top:16px;width:220px;height:auto;
         border-radius:10px;opacity:0.85;z-index:5;border:1px solid #2a3a4a;"
/>
```

- [ ] **Step 6: Verify gesture-engine.ts is unreferenced**

Run: `cd marcelo-ui && npx svelte-check --tsconfig ./tsconfig.json`
Expected: no errors. If `gesture-engine.ts` produces unused-import or dead-type errors, delete the now-unused legacy types it referenced. Leave the file only if it has no remaining importers (it should have none).

- [ ] **Step 7: Manual end-to-end verify (full stack)**

Start all three: backend (8000), gesture-service (8001), vite (5173). Open `http://localhost:5173`.
Expected: the corner shows the live annotated webcam; performing a gesture updates the HUD and visibly affects the particles. The browser never prompts for camera permission.

- [ ] **Step 8: Commit**

```bash
git add marcelo-ui/src/lib/gesture-types.ts marcelo-ui/src/lib/gesture-client.ts marcelo-ui/src/stores/gesture.svelte.ts marcelo-ui/src/components/ParticleCanvas.svelte marcelo-ui/src/components/WebcamView.svelte
git commit -m "feat(ui): consume gesture events over WS; retire in-browser MediaPipe"
```

---

### Task 10: Phase close

- [ ] **Step 1: Backend full suite + coverage**

Run: `.venv\Scripts\python -m pytest`
Expected: all pass; `app` coverage gate satisfied.

- [ ] **Step 2: Lint + type check (backend)**

Run: `.venv\Scripts\python -m ruff check app gesture_service && .venv\Scripts\python -m pyright app gesture_service`
Expected: no lint errors; pyright 0 errors.

- [ ] **Step 3: Frontend type check**

Run: `cd marcelo-ui && npx svelte-check --tsconfig ./tsconfig.json`
Expected: 0 errors.

- [ ] **Step 4: Regression pass**

With the full stack running, confirm chat, projects list, and voice still work (no regressions from router/store changes).

- [ ] **Step 5: Final commit (if fixes were needed)**

```bash
git add -A
git commit -m "chore(gesture): phase 2 lint/type/regression pass"
```

---

## Self-Review Notes

- **Spec coverage (Phase 2 §):** 2.1 EventBus → Tasks 2,3. 2.2 ingest → Task 6. 2.3 FrontendBridge → Task 5. 2.4 frontend consumes + retire browser MediaPipe → Task 9. 2.5 preview corner → Task 9 Step 5.
- **Interim engine bridge:** Task 9 maps the wire event to the existing `applyGesture(UnifiedGestureState)` so particles keep reacting before Phase 3. Spatial fidelity (orbit/portal world anchors) is approximate here and is done properly in Phase 3.
- **Type consistency:** `GestureEvent`/`GestureParams`/`Vec3` (domain) mirror `gesture_service.events`; `GestureEventSchema.to_domain()`, `get_event_bus()`, `frontend_bridge`, `WireGestureEvent` names are fixed and reused by Phases 3–6.

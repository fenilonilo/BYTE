# Gesture + Particle System — Full Rebuild (CV Service Architecture)

**Date:** 2026-05-27
**Branch:** `feat/ui-v2-svelte` (new branch likely: `feat/gesture-cv-service`)
**Status:** Design approved — pending spec review

> **Supersedes** `2026-05-27-gesture-particle-redesign.md` (the in-browser `UnifiedGesture` redesign, already implemented). That spec stays for history; this one re-architects the whole stack around a separate CV service, an event bus, GPGPU particles, and configurable gestures.

---

## Problem & Motivation

The current gesture system (`gesture-engine.ts` + `particle-engine.ts`) works but is structurally limited for where the project needs to go:

1. **Computer vision runs on the browser main thread.** MediaPipe Hands is loaded from a CDN and processes every frame in the same thread that renders particles. This caps fluidity and couples detection quality to client load.
2. **Gestures are hardcoded.** The 7 gestures live in a `switch` in `_classifyUnified`. Adding or tuning a gesture means editing TypeScript. There is no way to *configure* a gesture without code.
3. **Particle motion runs on the CPU.** A 20k-particle JS loop recomputes every particle every frame. It cannot scale to "wow"-level fluidity.
4. **No path to actions.** Gestures only drive particle visuals. There is no mechanism to make a gesture *do* something (swap the active model, open a file), which is a core future requirement.

This rebuild reorganizes the whole interaction stack around four approved decisions so that gestures become a first-class, configurable input channel that drives both visuals **and** application actions.

### Goals

- Move computer vision into a **separate Python service** that owns the camera.
- Make **any gesture configurable** without writing code (record a pose by video, compose motion, bind an action).
- Rebuild particles on the **GPU** for high-fluidity reactions driven by gesture data.
- Decouple gesture → reaction via an **event bus** so future actions plug in without touching detection or rendering.
- Show a **live webcam preview** (with landmark overlay) in a corner of the web app.

### Non-Goals

- Multi-user / remote camera support. This is a single-user, all-local app (camera, backend, browser on one machine).
- WebGPU compute (deferred; GPGPU on WebGL2 now, migrate later without architectural change).
- Replacing the chat / projects / voice features. Those are untouched.

---

## Approved Decisions

| # | Decision | Choice |
|---|----------|--------|
| 1 | Where CV runs | **A** — separate Python service, owns the camera, pushes semantic gesture events; re-streams an annotated webcam preview to the browser corner |
| 2 | How a gesture is defined | **3 (hybrid)** — record the hand *pose* by example (few-shot KNN), then *declare* the motion + compose, then bind to effect + action |
| 3 | Gesture → reaction wiring | **C (event bus)** — gesture emits a named event; independent subscribers react (particles, backend action, UI). New functions just subscribe |
| 4 | Particle engine | **2 (GPGPU / WebGL2)** — position & velocity in textures, physics in fragment shaders; gesture enters as a force uniform |

---

## System Architecture

Three zones. Arrows point in the direction of data flow.

```
┌─────────────────────────────────────────────────────────────────┐
│ gesture-service   (separate Python process, owns the camera)      │
│                                                                   │
│   Camera ─► MediaPipe Hands (21 landmarks/hand)                   │
│          ─► Pose recognizer   (rule primitives + KNN few-shot)    │
│          ─► Motion analyzer   (velocity / trajectory)             │
│          ─► Gesture matcher   (pose + motion + hands → named)     │
│                                                                   │
│   also: annotated preview stream · pose-capture for config        │
└───────────────┬───────────────────────────────────────────────────┘
                │ GestureEvent {gesture, phase, params, hands}  (WS)
                ▼
┌─────────────────────────────────────────────────────────────────┐
│ backend  (existing FastAPI, hexagonal)  — hosts the EVENT BUS     │
│                                                                   │
│   EventBus.publish(GestureEvent) ─► fan-out to subscribers:       │
│     • ActionDispatcher  → backend action (swap_model, open_file)  │
│     • FrontendBridge     → forward event to browser over /ws      │
│     • (future subscribers just .subscribe())                      │
│                                                                   │
│   GestureDefinition store (JSON)  ·  config CRUD API              │
└───────────────┬───────────────────────────────────────────────────┘
                │ event over /ws        preview frames (direct from service)
                ▼                       ▼
┌─────────────────────────────────────────────────────────────────┐
│ frontend  (Svelte)                                                │
│   • GPGPU particle engine — GestureEvent params → force uniforms  │
│   • Webcam preview corner — annotated frames from gesture-service │
│   • Gesture config UI — record pose · compose · bind effect+action│
└───────────────────────────────────────────────────────────────────┘
```

**Full flow:** camera → gesture-service → `GestureEvent` → bus → *(action in backend)* + *(force on particles + HUD in browser)*.

**Config flow:** config UI records a pose via the gesture-service, composes the gesture (pose + motion + hands), and saves a `GestureDefinition` + binding through the backend config API.

### Process topology

- `gesture-service` and `backend` are **separate processes**. The service has heavy native dependencies (MediaPipe, OpenCV) and owns hardware (the camera); isolating it means it can restart independently and never blocks the API.
- The service connects to the backend as a client and **publishes** `GestureEvent`s to an ingest endpoint. The backend is the bus authority.
- The webcam preview is served **directly** by the gesture-service to the browser (it already has the frames); it does not round-trip through the backend.

### Hexagonal placement (backend)

Respecting the project's dependency rule (`domain` ← `application` ← `adapters`/`api`):

- **domain/**: `GestureEvent`, `GestureDefinition`, effect/action id value objects — frozen dataclasses, no Pydantic.
- **ports/**: `EventBusPort` (publish/subscribe), `ActionPort` (execute a named action), `GestureDefinitionRepositoryPort`.
- **application/**: in-process `EventBus` implementation; `ActionDispatcher` as a bus subscriber; action registry (reuse the `Registry[T]` pattern from `application/registry.py`).
- **adapters/**: JSON `GestureDefinitionRepository`; concrete actions (`SwapModelAction` over the agent registry, `OpenFileAction` over `filesystem_tool` / `developer_tool`).
- **api/**: ingest WS endpoint (`/ws/gesture-ingest`), frontend forward over existing `/ws`, config CRUD routes. Pydantic `*Schema` DTOs live here.

The `gesture-service` is its own top-level package (e.g. `gesture_service/`) with its own minimal internal structure; it is *not* inside `app/` because it is a distinct runtime.

---

## Integration Contract (the spine)

Everything communicates through two data structures. Getting these right lets the three zones plug together without coupling.

### GestureEvent — travels on the bus

```jsonc
{
  "gesture": "punho_duplo",                 // named gesture id
  "phase": "start" | "hold" | "end" | "instant",  // lifecycle
  "hands": 0 | 1 | 2,
  "params": {                               // normalized spatial data → shader forces
    "points":  [{ "x": 0, "y": 0, "z": 0 }], // hand anchors / positions
    "vector":  { "x": 0, "y": 0, "z": 0 },   // direction (swipe, beam)
    "center":  { "x": 0, "y": 0, "z": 0 },   // orbit / portal center
    "radius":  0.0,
    "magnitude": 0.0                         // velocity / intensity
  },
  "ts": 0
}
```

- `phase` distinguishes **sustained** gestures (orbit/portal emit `start`→`hold`*→`end`) from **one-shot** gestures (shockwave emits a single `instant`). This replaces the per-effect boolean "fired" guards in the current engine.
- `params` are normalized to the particle world space convention so the frontend can feed them straight into shader uniforms.

### GestureDefinition — what config persists

```jsonc
{
  "id": "punho_duplo",
  "name": "Punho duplo",
  "pose":   { "shape": "<ref to recorded KNN template>", "hands": 2 },  // Phase 1 (video)
  "motion": { "type": "hold" | "swipe" | "circle" | "approach" | "none", "params": {} }, // Phase 2
  "binding": { "effect": "freeze", "action": "swap_model" | null }
}
```

### Catalogs (independent, referenced by id only)

- **Effects** (GPGPU force primitives): `attract`, `repel`, `freeze`, `shockwave`, `vortex`, `orbit`, `portal`, `beam`, `wave`, `breathe`.
- **Actions** (backend): `swap_model(model)`, `open_file(path)` / `open_project`, plus future actions that register themselves in the dispatcher.

Adding a new effect **or** a new action means registering it in its catalog — no change to detection or to gesture definitions. Bindings reference catalog ids, so the layers stay decoupled.

---

## Zone Detail

### gesture-service (Python)

- **Camera capture + MediaPipe Hands** → 21 landmarks per hand, up to 2 hands.
- **Pose recognizer:** rule-based primitives (`fist`/`open`/`pinch`/`point`) ship built-in; custom poses come from a **KNN classifier** over normalized landmark vectors recorded during config (Phase 1). Normalization makes poses scale/translation invariant.
- **Motion analyzer:** derives velocity and short trajectories from landmark history → `hold`/`swipe`/`circle`/`approach`.
- **Gesture matcher:** combines `(pose, motion, hands)` against the loaded `GestureDefinition`s → a named gesture + lifecycle `phase`. Emits `GestureEvent`.
- **Preview:** annotated frames (skeleton overlay) streamed to the browser corner.
- **Config support:** a pose-capture endpoint records N frames and builds a KNN template; a live-test endpoint reports the currently-detected gesture without firing actions.

### backend (FastAPI)

- **EventBus** (`application/`): in-process publish/subscribe. Subscribers register a coroutine; publish fans out concurrently.
- **Ingest** (`api/`): `gesture-service` publishes `GestureEvent`s here; the endpoint validates and calls `EventBus.publish`.
- **FrontendBridge** subscriber: forwards every `GestureEvent` to connected browsers over the existing `/ws` channel.
- **ActionDispatcher** subscriber: looks up the bound action for the gesture and executes it via the action registry. Actions reuse existing capabilities (agent registry for model swap, `filesystem_tool`/`developer_tool` for files).
- **GestureDefinition store + config API:** JSON-backed repository; CRUD routes; on change, instructs the gesture-service to reload definitions.

### frontend (Svelte)

- **GPGPU particle engine:** `GPUComputationRenderer` with position & velocity textures; physics in a compute (fragment) shader; render shader draws instanced points with bloom. Particle "state" (idle/listening/thinking/speaking) and gesture forces are shader uniforms.
- **Gesture force mapping:** the gesture store receives `GestureEvent`s (over `/ws`) and writes uniforms — `phase` decides whether a force is sustained or a one-shot impulse.
- **Webcam preview corner:** a small component rendering the annotated stream from the gesture-service.
- **Gesture config UI:** the 3-step wizard below.

### Config UI — 3-step wizard

1. **Record pose** — live webcam + skeleton, name the pose, "hold the pose" captures ~15 frames (progress bar) → KNN template saved.
2. **Compose gesture** — choose pose + number of hands + motion type; live-test confirms detection.
3. **Bind** — choose effect (with live preview) + action (with params, e.g. which model) → save as `GestureDefinition`.

A **main screen** lists configured gestures (`gesture → effect + action`) with edit / test / delete, and a "+ New gesture" entry point.

---

## Phased Roadmap

The order is fixed (foundation → beauty → utility → configurability). Each phase is split into small, **isolated, independently testable** steps. A step should be shippable/demoable on its own and not require later steps to be meaningful.

### Phase 1 — CV service foundation (camera → events)

- **1.1** `gesture-service` skeleton: separate process, camera capture, MediaPipe Hands wired, logs landmark count per frame. *Verify: camera opens, landmarks flow.*
- **1.2** Rule-based pose primitives (`fist`/`open`/`pinch`/`point`) → emit a pose label per hand. *Verify: each pose prints the right label.*
- **1.3** Motion analyzer: landmark history → velocity + `hold`/`swipe`/`circle`/`approach`. *Verify: moving a hand logs the right motion.*
- **1.4** Define the `GestureEvent` schema; gesture matcher combines pose + motion + hands → built-in named gestures with `phase`. *Verify: built-in gestures emit correct events incl. lifecycle.*
- **1.5** Annotated preview stream endpoint (skeleton overlay). *Verify: open the stream URL, see the overlay.*

### Phase 2 — Event bus + frontend bridge (events reach the browser)

- **2.1** Backend `EventBusPort` + in-process `EventBus` (application layer) with a subscriber interface. *Unit-tested (TDD): publish fans out to all subscribers.*
- **2.2** Ingest endpoint: `gesture-service` publishes `GestureEvent`s to the backend, which publishes to the bus. *Verify: events arrive and hit the bus.*
- **2.3** `FrontendBridge` subscriber forwards events to the browser over `/ws`. *Verify: browser console logs incoming events.*
- **2.4** Frontend gesture store consumes events into reactive state; **retire** the browser `gesture-engine.ts` MediaPipe path. *Verify: HUD reflects gestures sourced from the service.*
- **2.5** Webcam preview corner component renders the service stream. *Verify: live preview visible in the corner.*

### Phase 3 — GPGPU particle engine (it gets beautiful)

- **3.1** GPGPU scaffold: `GPUComputationRenderer`, position + velocity textures, basic render shader → static particle cloud. *Verify: cloud renders at 60fps with 100k+ particles.*
- **3.2** Port the four ambient states (idle/listening/thinking/speaking) to shader uniforms. *Verify: state changes animate as before.*
- **3.3** Force-primitive framework: gesture `params` → force uniforms consumed by the compute shader; `phase`-aware (sustained vs one-shot). *Verify: a test uniform visibly pushes particles.*
- **3.4** Implement the effect catalog as shader forces (`attract`/`repel`/`freeze`/`shockwave`/`vortex`/`orbit`/`portal`/`beam`/`wave`/`breathe`). *Verify each effect individually.*
- **3.5** Wire the gesture store → particle forces end-to-end; **retire** the CPU `particle-engine.ts` loop. *Verify: real gestures drive fluid particle reactions.*

### Phase 4 — Action dispatch (it gets useful)

- **4.1** `ActionPort` + action `Registry` (application). *Unit-tested (TDD).*
- **4.2** `ActionDispatcher` bus subscriber: maps gesture → bound action, executes via registry. *Unit-tested.*
- **4.3** `SwapModelAction` over the agent registry. *Verify: a gesture swaps the active model.*
- **4.4** `OpenFileAction` / `OpenProjectAction` over `filesystem_tool` / `developer_tool`. *Verify: a gesture opens a file/project.*
- **4.5** Default (config-less) bindings for built-in gestures so actions work before the config UI exists. *Verify: built-in gesture → action without any config.*

### Phase 5 — Gesture config system (data + backend)

- **5.1** `GestureDefinition` domain model + JSON `GestureDefinitionRepository` (port + adapter). *Unit-tested (TDD) for the repository contract.*
- **5.2** Pose-capture endpoint in the gesture-service: record N frames → normalized KNN template. *Verify: capturing a pose persists a template.*
- **5.3** KNN pose classifier augments the rule-based primitives so custom poses are recognized. *Verify: a recorded custom pose is detected.*
- **5.4** Config CRUD API (backend) for `GestureDefinition`s; on change, the gesture-service reloads definitions. *Unit-tested for the use cases; verify reload.*
- **5.5** Live-test endpoint: report the currently-detected gesture without firing actions. *Verify: test mode detects but does not act.*

### Phase 6 — Config UI (frontend)

- **6.1** Gesture list screen (configured gestures, edit/test/delete, "+ New"). *Verify: list reflects stored definitions.*
- **6.2** Wizard step 1 — record pose (webcam + skeleton + progress). *Verify: a pose can be recorded from the UI.*
- **6.3** Wizard step 2 — compose (pose + hands + motion) + live test. *Verify: composition detects live.*
- **6.4** Wizard step 3 — binding (effect preview + action + params) + save. *Verify: a full gesture is created end-to-end from the UI.*

---

## Testing Strategy

Per project conventions (`CLAUDE.md`):

- **TDD required** for: `EventBus`, `ActionDispatcher`, action `Registry`, `GestureDefinitionRepository` contract, config use cases, and any domain entity with logic.
- **Integration tests** for adapters that touch real resources (JSON repo, action execution against the agent registry / filesystem).
- **Manual verification** for CV detection quality and particle fluidity (camera + GPU cannot be meaningfully unit-tested). Each roadmap step lists its manual *Verify* check.
- Coverage targets unchanged: `domain/` + `application/` ≥ 80%.
- `gesture-service` carries its own lightweight tests for the pose/motion/matcher logic (pure functions over landmark fixtures); camera I/O is excluded.

---

## Risks & Mitigations

- **Two processes to run.** Mitigation: document the dev workflow (uvicorn + vite + gesture-service); consider a single start script. Acceptable for a solo local dev who already runs two processes.
- **WS event latency adds up vs. browser-local detection.** Mitigation: events are tiny semantic messages (not frames); all-local loopback keeps latency low. Preview frames are the only heavy stream and are isolated to a direct service→browser path.
- **GPGPU complexity.** Mitigation: use the well-trodden `GPUComputationRenderer`; build the scaffold (3.1) before any effect; keep WebGPU as a later migration that does not change the architecture.
- **KNN pose robustness.** Mitigation: normalize landmarks (scale/translation invariant); rule-based primitives remain the reliable baseline; custom poses are additive.
- **Camera ownership conflicts** (service vs. browser both wanting the camera). Mitigation: only the service touches the camera; the browser shows the re-streamed preview, never `getUserMedia`.

---

## Success Criteria

- Computer vision runs in a separate process; the browser never calls `getUserMedia`.
- A live, skeleton-annotated webcam preview shows in a corner of the web app.
- Built-in gestures produce fluid GPU particle reactions and trigger backend actions (model swap, open file).
- A new gesture can be created entirely from the UI — record pose, compose, bind effect + action — with no code changes.
- Adding a new effect or a new action requires only registering it in its catalog; detection and rendering are untouched.
- Particle rendering sustains 60fps at 100k+ particles.
```

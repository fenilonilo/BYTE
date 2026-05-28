# Gesture CV Service — Full Implementation Program (All Phases)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement each phase task-by-task. Steps use checkbox (`- [ ]`) syntax. Execute phases in order — each builds on the previous.

**Goal:** Replace the in-browser gesture+particle system with a separate Python CV service, a backend event bus, a GPGPU particle engine, action dispatch, and a no-code gesture configuration system.

**Source spec:** `docs/superpowers/specs/2026-05-27-gesture-cv-service-rebuild-design.md`

**This is an index.** The work is composed of six phase plans. Each is an independently executable, end-to-end-verifiable plan. Do them in order.

| Phase | File | Delivers | Stack |
|-------|------|----------|-------|
| 1 | [`...-phase1.md`](2026-05-27-gesture-cv-service-phase1.md) | Standalone gesture-service: camera → built-in gestures → logs + preview | Python, MediaPipe, OpenCV, FastAPI |
| 2 | [`...-phase2.md`](2026-05-27-gesture-cv-service-phase2.md) | Event bus + bridge: gestures flow service → backend bus → browser; retire browser MediaPipe | Python, FastAPI WS, Svelte/TS |
| 3 | [`...-phase3.md`](2026-05-27-gesture-cv-service-phase3.md) | GPGPU particle engine driven by gesture forces; retire CPU engine | Three.js, GLSL, TS |
| 4 | [`...-phase4.md`](2026-05-27-gesture-cv-service-phase4.md) | Action dispatch: gestures trigger swap_model / open_file | Python |
| 5 | [`...-phase5.md`](2026-05-27-gesture-cv-service-phase5.md) | Gesture config system: GestureDefinition persistence, KNN custom poses, CRUD + live-test API | Python, scikit-style KNN |
| 6 | [`...-phase6.md`](2026-05-27-gesture-cv-service-phase6.md) | Config UI: gesture list + 3-step record/compose/bind wizard | Svelte/TS |

---

## Shared interface reference (stable across phases)

These contracts are defined once and consumed everywhere. Phases must not diverge from them.

### GestureEvent (wire + domain)

```jsonc
{
  "gesture": "punho_duplo",
  "phase": "start" | "hold" | "end" | "instant" | "idle",
  "hands": 0 | 1 | 2,
  "params": {
    "points":  [{ "x": 0, "y": 0, "z": 0 }],
    "vector":  { "x": 0, "y": 0, "z": 0 },
    "center":  { "x": 0, "y": 0, "z": 0 },
    "radius":  0.0,
    "magnitude": 0.0
  },
  "ts": 0.0
}
```

- Python source-of-truth: `gesture_service/events.py` (Phase 1). Phase 2 adds a mirror domain model `app/domain/gestures.py` + a Pydantic `GestureEventSchema` at the API boundary.
- TS source-of-truth: `marcelo-ui/src/lib/gesture-types.ts` (Phase 2).

### GestureDefinition (config, Phase 5)

```jsonc
{
  "id": "punho_duplo",
  "name": "Punho duplo",
  "pose":   { "shape": "fist", "hands": 2 },
  "motion": { "type": "hold" | "swipe" | "circle" | "approach" | "none", "params": {} },
  "binding": { "effect": "freeze", "action": "swap_model" | null, "action_params": {} }
}
```

### Catalogs

- **Effects** (frontend GPGPU forces, Phase 3): `attract`, `repel`, `freeze`, `shockwave`, `vortex`, `orbit`, `portal`, `beam`, `wave`, `breathe`.
- **Actions** (backend, Phase 4): `swap_model(model)`, `open_file(path)` / `open_project(name)`. Future actions register in the action `Registry`.

### Coordinate convention

MediaPipe image-normalized coordinates (`x`, `y` ∈ `[0,1]`, `z` relative). The frontend maps to particle world space (Phase 3).

### Process / port map

| Process | Port | Role |
|---------|------|------|
| gesture-service | 8001 | camera, detection, preview (`/preview`), publishes events |
| backend (FastAPI) | 8000 | event bus, ingest (`/ws/gesture-ingest`), browser stream (`/ws/gesture`), config API |
| vite dev | 5173 | frontend |

---

## Dependency order & rationale

```
Phase 1 (service emits events, standalone)
   │
Phase 2 (events reach backend bus + browser; browser MediaPipe retired)
   ├──────────────┬───────────────────┐
Phase 3        Phase 4            (3 & 4 both consume the bus;
(particles)    (actions)          independent, can run in either order)
   └──────────────┴───────────────────┘
                  │
Phase 5 (config persistence + custom poses + API)
   │
Phase 6 (config UI on top of Phase 5 API)
```

- **1 → 2:** the bus needs events to carry; the service must emit first.
- **2 → 3 and 2 → 4:** both subscribe to the bus. Independent of each other; the index lists 3 before 4 (beauty before utility) but they may swap.
- **(3,4) → 5:** config binds gestures to *existing* effects (Phase 3) and actions (Phase 4); those catalogs must exist to bind against.
- **5 → 6:** the UI is a client of the Phase 5 config API.

## Cross-phase verification

Each phase ends with its own checks. After Phase 2, after Phase 4, and after Phase 6, run the full local stack (gesture-service + backend + vite) and confirm no regressions in chat/projects/voice.

## Honesty note on later-phase code

Phases 2, 4, 5 (Python backend) follow the existing hexagonal patterns and their code is stable. Phase 3 (GLSL/GPGPU) and Phase 6 (Svelte UI) include complete *initial* implementations; visual code is expected to be tuned against the running engine. Where a later phase consumes a symbol from an earlier one, the symbol name is fixed in the Shared Interface Reference above so the phases stay consistent.

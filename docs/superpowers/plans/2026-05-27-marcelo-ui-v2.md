# Marcelo UI v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the Marcelo frontend from vanilla HTML/JS to a Svelte 5 + Vite app with glass overlays, full-screen particle canvas, and an expanded bimanual gesture system.

**Architecture:** Full-screen Three.js canvas with fixed-position Svelte overlays (chat bottom-left, projects bottom-right, gesture HUD top-center). Three.js and MediaPipe run as pure TS modules outside Svelte's reactivity. Svelte stores hold UI state only; the particle engine's RAF loop is never interrupted.

**Tech Stack:** Svelte 5 (Runes), Vite, TypeScript strict, Three.js, MediaPipe Hands, UnoCSS, lucide-svelte, Web Audio API, WebSocket

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `marcelo-ui/package.json` | Create | npm workspace config, all deps |
| `marcelo-ui/vite.config.ts` | Create | Vite config, port 5173 |
| `marcelo-ui/tsconfig.json` | Create | strict TS config |
| `marcelo-ui/uno.config.ts` | Create | UnoCSS config, design tokens |
| `marcelo-ui/index.html` | Create | Entry, black bg, no-flash |
| `marcelo-ui/src/main.ts` | Create | Mount App.svelte |
| `marcelo-ui/src/App.svelte` | Create | Root shell: canvas + all overlays |
| `marcelo-ui/src/lib/particle-engine.ts` | Create | Three.js scene, 20k particles, bloom — TS port |
| `marcelo-ui/src/lib/gesture-engine.ts` | Create | MediaPipe + bimanual state machine |
| `marcelo-ui/src/lib/audio-analyzer.ts` | Create | Web Audio TTS/mic amplitude analysis |
| `marcelo-ui/src/lib/ws-client.ts` | Create | Typed WebSocket client, streaming |
| `marcelo-ui/src/stores/gesture.svelte.ts` | Create | $state GestureState — two hand tracks |
| `marcelo-ui/src/stores/chat.svelte.ts` | Create | $state chat messages, streaming, preview |
| `marcelo-ui/src/stores/projects.svelte.ts` | Create | $state projects list, polling |
| `marcelo-ui/src/components/ParticleCanvas.svelte` | Create | Mount canvas, lifecycle bridge to particle-engine |
| `marcelo-ui/src/components/ChatOverlay.svelte` | Create | Chat panel glass, collapsible |
| `marcelo-ui/src/components/ProjectsOverlay.svelte` | Create | Projects minimal list, collapsible |
| `marcelo-ui/src/components/GestureHUD.svelte` | Create | Gesture active badge, freeze ice overlay |
| `marcelo-ui/src/components/WebcamView.svelte` | Create | Webcam feed, top-right corner |
| `marcelo-ui/src/components/StatusBadge.svelte` | Create | idle/listening/thinking/speaking indicator |
| `app/config.py` | Modify | Add `workspace_path: Path` field |
| `app/api/router.py` | Modify | Add `GET /api/v1/projects` endpoint |

---

## Task 1: Project Scaffold

**Files:**
- Create: `marcelo-ui/package.json`
- Create: `marcelo-ui/vite.config.ts`
- Create: `marcelo-ui/tsconfig.json`
- Create: `marcelo-ui/uno.config.ts`
- Create: `marcelo-ui/index.html`
- Create: `marcelo-ui/src/main.ts`
- Create: `marcelo-ui/src/App.svelte`

- [ ] **Step 1: Create `marcelo-ui/package.json`**

```json
{
  "name": "marcelo-ui",
  "version": "2.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "typecheck": "svelte-check --tsconfig ./tsconfig.json"
  },
  "dependencies": {
    "svelte": "^5.0.0",
    "three": "^0.170.0",
    "lucide-svelte": "^0.460.0"
  },
  "devDependencies": {
    "@sveltejs/vite-plugin-svelte": "^4.0.0",
    "@unocss/svelte-scoped": "^0.64.0",
    "@unocss/vite": "^0.64.0",
    "svelte-check": "^4.0.0",
    "typescript": "^5.6.0",
    "unocss": "^0.64.0",
    "vite": "^6.0.0"
  }
}
```

- [ ] **Step 2: Install dependencies**

Run from `marcelo-ui/`:
```
npm install
```

- [ ] **Step 3: Create `marcelo-ui/vite.config.ts`**

```typescript
import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'
import UnoCSS from '@unocss/vite'

export default defineConfig({
  plugins: [
    UnoCSS(),
    svelte(),
  ],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
})
```

- [ ] **Step 4: Create `marcelo-ui/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ESNext",
    "useDefineForClassFields": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "noImplicitAny": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "lib": ["ESNext", "DOM", "DOM.Iterable"]
  },
  "include": ["src/**/*.ts", "src/**/*.svelte"]
}
```

- [ ] **Step 5: Create `marcelo-ui/uno.config.ts`**

```typescript
import { defineConfig } from 'unocss'

export default defineConfig({
  theme: {
    colors: {
      bg: '#060a0f',
      blue: 'rgba(99,179,255,1)',
      violet: 'rgba(150,80,255,1)',
      green: 'rgba(150,255,180,1)',
      amber: 'rgba(255,200,80,1)',
      red: 'rgba(255,100,80,1)',
      ice: 'rgba(150,220,255,1)',
    },
    fontFamily: {
      sans: 'Inter, system-ui, sans-serif',
      mono: "'JetBrains Mono', monospace",
    },
  },
})
```

- [ ] **Step 6: Create `marcelo-ui/index.html`**

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Marcelo</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body { width: 100%; height: 100%; background: #060a0f; overflow: hidden; }
  </style>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500&family=JetBrains+Mono&display=swap" rel="stylesheet" />
</head>
<body>
  <div id="app"></div>
  <script type="module" src="/src/main.ts"></script>
</body>
</html>
```

- [ ] **Step 7: Create `marcelo-ui/src/main.ts`**

```typescript
import 'virtual:uno.css'
import { mount } from 'svelte'
import App from './App.svelte'

mount(App, { target: document.getElementById('app')! })
```

- [ ] **Step 8: Create `marcelo-ui/src/App.svelte` (skeleton)**

```svelte
<script lang="ts">
  // Filled in Task 9 after all components exist
</script>

<div style="width:100vw;height:100vh;background:#060a0f;display:flex;align-items:center;justify-content:center;">
  <span style="color:rgba(99,179,255,0.4);font-family:monospace">marcelo ui v2 — loading</span>
</div>
```

- [ ] **Step 9: Verify dev server starts**

Run from `marcelo-ui/`:
```
npm run dev
```
Expected: Vite server on `http://localhost:5173`. Browser shows dark screen with loading text.

- [ ] **Step 10: Commit**

```bash
git add marcelo-ui/
git commit -m "feat(ui-v2): scaffold Svelte 5 + Vite project"
```

---

## Task 2: Types & Shared Interfaces

**Files:**
- Create: `marcelo-ui/src/lib/types.ts`

All shared types live here. Every other module imports from this file.

- [ ] **Step 1: Create `marcelo-ui/src/lib/types.ts`**

```typescript
import type { Vector3 } from 'three'

// ─── Gesture ─────────────────────────────────────────────────────────────────

export type HandGesture = 'none' | 'open' | 'pinch' | 'fist' | 'point' | 'swipe' | 'breathe' | 'idle'

export type BimanualGesture =
  | 'prayer-explosion'
  | 'implosion'
  | 'orbit'
  | 'freeze'
  | 'dual-pinch'
  | 'portal'

export interface HandState {
  gesture: HandGesture
  worldPos: Vector3
  velocity: Vector3
  /** milliseconds this gesture has been held continuously */
  age: number
}

export interface BimanualPattern {
  active: boolean
  pattern: BimanualGesture | null
  phase: string
  /** 0..1 completion progress for phase transitions */
  progress: number
}

export interface GestureState {
  left: HandState
  right: HandState
  bimanual: BimanualPattern
}

// ─── Chat ─────────────────────────────────────────────────────────────────────

export type MessageRole = 'user' | 'assistant' | 'interim'

export interface ChatMessage {
  id: string
  role: MessageRole
  text: string
  timestamp: number
}

export interface ChatState {
  messages: ChatMessage[]
  /** STT in-progress transcript, null when not listening */
  interim: string | null
  /** Claude Code task preview awaiting approve/cancel */
  preview: string | null
  streaming: boolean
  connected: boolean
}

// ─── Projects ─────────────────────────────────────────────────────────────────

export interface ProjectItem {
  name: string
  path: string
  /** Unix timestamp seconds (from backend mtime) */
  mtime: number
}

export interface ProjectsState {
  items: ProjectItem[]
  loading: boolean
}

// ─── Particle engine state ────────────────────────────────────────────────────

export type ParticleState = 'idle' | 'listening' | 'thinking' | 'speaking'
```

- [ ] **Step 2: Verify TypeScript compiles**

Run from `marcelo-ui/`:
```
npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add marcelo-ui/src/lib/types.ts
git commit -m "feat(ui-v2): add shared TypeScript types"
```

---

## Task 3: Backend — `workspace_path` Config + `/api/v1/projects` Endpoint

**Files:**
- Modify: `app/config.py`
- Modify: `app/api/router.py`
- Test: `tests/unit/api/test_projects_endpoint.py`

- [ ] **Step 1: Write failing test**

Create `tests/unit/api/test_projects_endpoint.py`:

```python
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def tmp_workspace(tmp_path: Path) -> Path:
    """Create 3 fake project directories with varying mtimes."""
    for name in ("alpha", "beta", "gamma"):
        d = tmp_path / name
        d.mkdir()
    # force mtime order: gamma newest
    now = time.time()
    os.utime(tmp_path / "alpha", (now - 200, now - 200))
    os.utime(tmp_path / "beta",  (now - 100, now - 100))
    os.utime(tmp_path / "gamma", (now,       now))
    return tmp_path


def test_projects_returns_dirs_sorted_by_mtime(tmp_workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARCELO_WORKSPACE_PATH", str(tmp_workspace))
    # re-import after env patch
    from importlib import reload
    import app.config as cfg_mod
    reload(cfg_mod)
    import app.api.router as router_mod
    reload(router_mod)
    from app.main import app
    client = TestClient(app)

    resp = client.get("/api/v1/projects")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    names = [d["name"] for d in data]
    # newest first
    assert names[0] == "gamma"
    assert names[-1] == "alpha"
    for item in data:
        assert "name" in item
        assert "path" in item
        assert "mtime" in item


def test_projects_skips_files(tmp_workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_workspace / "README.md").write_text("hello")
    monkeypatch.setenv("MARCELO_WORKSPACE_PATH", str(tmp_workspace))
    from importlib import reload
    import app.config as cfg_mod
    reload(cfg_mod)
    import app.api.router as router_mod
    reload(router_mod)
    from app.main import app
    client = TestClient(app)

    resp = client.get("/api/v1/projects")
    data = resp.json()
    names = [d["name"] for d in data]
    assert "README.md" not in names
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/unit/api/test_projects_endpoint.py -v
```
Expected: FAIL — `MARCELO_WORKSPACE_PATH` not in Settings / endpoint does not exist.

- [ ] **Step 3: Add `workspace_path` to `app/config.py`**

```python
# app/config.py
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "marcelo"
    log_level: str = "INFO"
    default_channel: str = "api"
    workspace_path: Path = Path("D:/Projetos/Projetos_Marcelo")

    model_config = SettingsConfigDict(
        env_prefix="MARCELO_",
        env_file=".env",
        env_file_encoding="utf-8",
    )
```

- [ ] **Step 4: Add `GET /api/v1/projects` to `app/api/router.py`**

Add after the existing imports and before `router = APIRouter()`:

```python
import os
from pathlib import Path

from app.config import Settings

_settings = Settings()
```

Add after the existing `/messages` route:

```python
@router.get("/projects")
async def list_projects() -> list[dict]:
    """Return directories in workspace_path sorted by mtime descending."""
    workspace: Path = _settings.workspace_path
    if not workspace.is_dir():
        return []

    entries = []
    with os.scandir(workspace) as it:
        for entry in it:
            if entry.is_dir():
                entries.append({
                    "name": entry.name,
                    "path": str(entry.path),
                    "mtime": entry.stat().st_mtime,
                })

    entries.sort(key=lambda e: e["mtime"], reverse=True)
    return entries
```

- [ ] **Step 5: Run tests — verify pass**

```
pytest tests/unit/api/test_projects_endpoint.py -v
```
Expected: 2 tests PASS.

- [ ] **Step 6: Run full test suite**

```
pytest --tb=short -q
```
Expected: no regressions.

- [ ] **Step 7: Commit**

```bash
git add app/config.py app/api/router.py tests/unit/api/test_projects_endpoint.py
git commit -m "feat(api): add workspace_path config + GET /api/v1/projects endpoint"
```

---

## Task 4: `particle-engine.ts` — TypeScript Port + New Effect Methods

**Files:**
- Create: `marcelo-ui/src/lib/particle-engine.ts`

This is a direct TypeScript port of the existing `particle-engine.js` plus 9 new effect methods. The core animation loop is unchanged.

- [ ] **Step 1: Create `marcelo-ui/src/lib/particle-engine.ts`**

```typescript
import * as THREE from 'three'
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js'
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js'
import type { ParticleState } from './types'

// ─── Constants ────────────────────────────────────────────────────────────────

const COUNT       = 20_000
const HAND_RADIUS = 25
const MOUSE_RADIUS = 15

const STATE_PARAMS: Record<ParticleState, {
  hue: number; sat: number; bloom: number; rotSpeed: number; spread: number; core: number
}> = {
  idle:      { hue: 0.78, sat: 0.85, bloom: 1.8, rotSpeed: 0.15, spread: 10.4, core: 10 },
  listening: { hue: 0.60, sat: 0.90, bloom: 2.2, rotSpeed: 0.20, spread: 15.0, core: 8  },
  thinking:  { hue: 0.12, sat: 0.95, bloom: 2.5, rotSpeed: 0.50, spread: 18.0, core: 6  },
  speaking:  { hue: 0.35, sat: 0.80, bloom: 3.0, rotSpeed: 0.25, spread: 12.0, core: 9  },
}

// ─── Module-level state ───────────────────────────────────────────────────────

let scene: THREE.Scene
let camera: THREE.PerspectiveCamera
let renderer: THREE.WebGLRenderer
let composer: EffectComposer
let bloomPass: UnrealBloomPass
let instancedMesh: THREE.InstancedMesh
let clock: THREE.Clock

const positions:  THREE.Vector3[] = []
const velocities: THREE.Vector3[] = []
const dummy = new THREE.Object3D()
const color = new THREE.Color()
const target = new THREE.Vector3()

let currentState  = 'idle' as ParticleState
let currentHue    = STATE_PARAMS.idle.hue
let currentSat    = STATE_PARAMS.idle.sat
let currentBloom  = STATE_PARAMS.idle.bloom
let currentRot    = STATE_PARAMS.idle.rotSpeed
let currentSpread = STATE_PARAMS.idle.spread
let currentCore   = STATE_PARAMS.idle.core

let uAmplitude = 0.0
let smoothAmp  = 0.0

// One-shot effects active this frame
interface ActiveEffect {
  type: 'shockwave' | 'vortex' | 'orbit' | 'freeze' | 'split' | 'portal' | 'beam' | 'wave' | 'breathe'
  origin?: THREE.Vector3
  target?: THREE.Vector3
  pointA?: THREE.Vector3
  pointB?: THREE.Vector3
  direction?: THREE.Vector3
  dirSign?: number
  radius?: number
  force?: number
  strength?: number
  speed?: number
  expiresAt?: number   // Date.now() + duration
}

const activeEffects: ActiveEffect[] = []

// Hand state
let handActive   = false
let handPos      = new THREE.Vector3()
let handGesture  = 'none'
let handVelocity = new THREE.Vector3()

let mouseNDC   = new THREE.Vector2(9999, 9999)
let isDragging = false

// Freeze state
let frozenUntil = 0

// ─── Shader material ──────────────────────────────────────────────────────────

const material = new THREE.ShaderMaterial({
  uniforms: {
    uTime:      { value: 0 },
    uAmplitude: { value: 0 },
  },
  vertexShader: `
    varying vec2 vUv;
    varying vec3 vColor;
    void main() {
      vUv = uv;
      vColor = instanceColor;
      gl_Position = projectionMatrix * modelViewMatrix * instanceMatrix * vec4(position, 1.0);
    }
  `,
  fragmentShader: `
    varying vec2 vUv;
    varying vec3 vColor;
    uniform float uTime;
    uniform float uAmplitude;
    float rand(vec2 n) { return fract(sin(dot(n, vec2(12.9898,4.1414))) * 43758.5453); }
    float noise(vec2 p) {
      vec2 ip = floor(p); vec2 u = fract(p); u = u*u*(3.0-2.0*u);
      return mix(
        mix(rand(ip), rand(ip+vec2(1,0)), u.x),
        mix(rand(ip+vec2(0,1)), rand(ip+vec2(1,1)), u.x),
        u.y
      );
    }
    void main() {
      float dist = distance(vUv, vec2(0.5));
      float n = noise(vUv * 5.0 + uTime * 0.5);
      float alpha = (1.0 - smoothstep(0.2, 0.5, dist)) * (0.5 + 0.5 * n);
      if (alpha < 0.1) discard;
      float ca = uAmplitude * 0.003;
      gl_FragColor = vec4(vColor.r + ca, vColor.g, vColor.b - ca, alpha * 0.8);
    }
  `,
  transparent: true,
  depthWrite: false,
  side: THREE.DoubleSide,
  blending: THREE.AdditiveBlending,
})

// ─── Public API ───────────────────────────────────────────────────────────────

export function init(canvas: HTMLCanvasElement): void {
  scene = new THREE.Scene()
  scene.fog = new THREE.FogExp2(0x000000, 0.01)

  camera = new THREE.PerspectiveCamera(60, canvas.clientWidth / canvas.clientHeight, 0.1, 2000)
  camera.position.set(0, 0, 100)

  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' })
  renderer.setSize(canvas.clientWidth, canvas.clientHeight)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))

  composer = new EffectComposer(renderer)
  composer.addPass(new RenderPass(scene, camera))
  bloomPass = new UnrealBloomPass(
    new THREE.Vector2(canvas.clientWidth, canvas.clientHeight),
    1.8, 0.4, 0,
  )
  composer.addPass(bloomPass)

  const geometry = new THREE.PlaneGeometry(0.8, 0.8)
  instancedMesh = new THREE.InstancedMesh(geometry, material, COUNT)
  instancedMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage)
  scene.add(instancedMesh)

  for (let i = 0; i < COUNT; i++) {
    positions.push(new THREE.Vector3(
      (Math.random() - 0.5) * 100,
      (Math.random() - 0.5) * 100,
      (Math.random() - 0.5) * 100,
    ))
    velocities.push(new THREE.Vector3())
    instancedMesh.setColorAt(i, color.setHSL(0.78, 0.85, 0.3))
  }

  clock = new THREE.Clock()

  window.addEventListener('resize', _onResize)
  _animate()
}

export function getCamera(): THREE.PerspectiveCamera { return camera }

export function setState(state: ParticleState): void {
  if (STATE_PARAMS[state]) currentState = state
}

export function setAmplitude(value: number): void {
  uAmplitude = Math.max(0, Math.min(1, value))
}

export function applyHandForce(worldPos: THREE.Vector3, gesture: string, velocity: THREE.Vector3): void {
  handActive   = true
  handPos.copy(worldPos)
  handGesture  = gesture
  handVelocity.copy(velocity)
}

export function clearHandForce(): void {
  handActive  = false
  handGesture = 'none'
}

export function setMouseNDC(ndcX: number, ndcY: number, dragging: boolean): void {
  mouseNDC.set(ndcX, ndcY)
  isDragging = dragging
}

export function dispose(): void {
  window.removeEventListener('resize', _onResize)
  renderer.dispose()
}

// ─── New effect methods ───────────────────────────────────────────────────────

/** Radial shockwave from origin — prayer-explosion. Bloom flashes white for 400ms. */
export function shockwave(origin: THREE.Vector3, radius: number, force: number): void {
  activeEffects.push({ type: 'shockwave', origin: origin.clone(), radius, force })
  // Temporary bloom spike
  const saved = currentBloom
  bloomPass.strength = 6.0
  setTimeout(() => { bloomPass.strength = saved }, 400)
}

/** Vortex collapse toward target — implosion. */
export function vortex(targetPos: THREE.Vector3, strength: number): void {
  activeEffects.push({ type: 'vortex', target: targetPos.clone(), strength })
}

/** Orbit anchor — particles orbit around anchor continuously while active. Call clearHandForce() to stop. */
export function orbitAnchor(anchor: THREE.Vector3, radius: number): void {
  // Remove previous orbit
  const idx = activeEffects.findIndex(e => e.type === 'orbit')
  if (idx >= 0) activeEffects.splice(idx, 1)
  activeEffects.push({ type: 'orbit', origin: anchor.clone(), radius })
}

/** Freeze particles in place for durationMs. Color shifts to ice hue. */
export function crystallize(durationMs: number): void {
  frozenUntil = Date.now() + durationMs
  // Shift hue to ice
  currentHue = 0.58
  currentSat = 0.4
}

/** Two gravitational poles — dual-pinch. Replaces existing orbit if any. */
export function splitField(pointA: THREE.Vector3, pointB: THREE.Vector3): void {
  const idx = activeEffects.findIndex(e => e.type === 'split')
  if (idx >= 0) activeEffects.splice(idx, 1)
  activeEffects.push({ type: 'split', pointA: pointA.clone(), pointB: pointB.clone() })
}

/** Clear splitField effect. */
export function clearSplitField(): void {
  const idx = activeEffects.findIndex(e => e.type === 'split')
  if (idx >= 0) activeEffects.splice(idx, 1)
}

/** Portal ring — particles orbit a ring. Active while called each frame. */
export function portalRing(center: THREE.Vector3, ringRadius: number): void {
  const idx = activeEffects.findIndex(e => e.type === 'portal')
  if (idx >= 0) activeEffects.splice(idx, 1)
  activeEffects.push({ type: 'portal', origin: center.clone(), radius: ringRadius })
}

/** Clear portal effect. */
export function clearPortal(): void {
  const idx = activeEffects.findIndex(e => e.type === 'portal')
  if (idx >= 0) activeEffects.splice(idx, 1)
}

/** Directional beam — point gesture. Particles stream toward tip along direction. */
export function directionalBeam(tip: THREE.Vector3, direction: THREE.Vector3): void {
  const idx = activeEffects.findIndex(e => e.type === 'beam')
  if (idx >= 0) activeEffects.splice(idx, 1)
  activeEffects.push({ type: 'beam', origin: tip.clone(), direction: direction.clone().normalize() })
}

/** Clear beam effect. */
export function clearBeam(): void {
  const idx = activeEffects.findIndex(e => e.type === 'beam')
  if (idx >= 0) activeEffects.splice(idx, 1)
}

/** Lateral pressure wave — swipe. One-shot. dirSign: +1 = right, -1 = left. */
export function lateralWave(origin: THREE.Vector3, dirSign: number, speed: number): void {
  activeEffects.push({ type: 'wave', origin: origin.clone(), dirSign, speed })
}

/** Breathe pulse — rhythmic expansion from center while held. */
export function breathePulse(center: THREE.Vector3): void {
  const idx = activeEffects.findIndex(e => e.type === 'breathe')
  if (idx >= 0) activeEffects.splice(idx, 1)
  activeEffects.push({ type: 'breathe', origin: center.clone() })
}

/** Clear breathe effect. */
export function clearBreath(): void {
  const idx = activeEffects.findIndex(e => e.type === 'breathe')
  if (idx >= 0) activeEffects.splice(idx, 1)
}

// ─── Private helpers ──────────────────────────────────────────────────────────

function _onResize(): void {
  camera.aspect = window.innerWidth / window.innerHeight
  camera.updateProjectionMatrix()
  renderer.setSize(window.innerWidth, window.innerHeight)
  composer.setSize(window.innerWidth, window.innerHeight)
}

function _ndcToWorld(ndcX: number, ndcY: number): THREE.Vector3 {
  const v = new THREE.Vector3(ndcX, ndcY, 0.5)
  v.unproject(camera)
  const dir = v.sub(camera.position).normalize()
  const t = -camera.position.z / dir.z
  return camera.position.clone().add(dir.multiplyScalar(t))
}

function _tangent(v: THREE.Vector3): THREE.Vector3 {
  return new THREE.Vector3(-v.z, 0, v.x).normalize()
}

function _animate(): void {
  requestAnimationFrame(_animate)

  const now = Date.now()
  const frozen = now < frozenUntil

  // When freeze expires, restore state hue
  if (frozen === false && frozenUntil > 0 && now >= frozenUntil) {
    frozenUntil = 0
    currentHue = STATE_PARAMS[currentState].hue
    currentSat = STATE_PARAMS[currentState].sat
  }

  const delta = clock.getDelta()
  const time  = clock.getElapsedTime()

  const p = STATE_PARAMS[currentState]
  const lerpRate = 0.02
  if (!frozen) {
    currentHue    += (p.hue      - currentHue)    * lerpRate
    currentSat    += (p.sat      - currentSat)    * lerpRate
    currentBloom  += (p.bloom    - currentBloom)  * lerpRate
    currentRot    += (p.rotSpeed - currentRot)    * lerpRate
    currentSpread += (p.spread   - currentSpread) * lerpRate
    currentCore   += (p.core     - currentCore)   * lerpRate
  }

  smoothAmp += (uAmplitude - smoothAmp) * 0.1
  if (!frozen) bloomPass.strength = currentBloom + smoothAmp * 1.5

  material.uniforms.uTime.value      = time * 0.4
  material.uniforms.uAmplitude.value = smoothAmp

  const t    = time * 1.086
  const rotT = t * currentRot
  const cosR = Math.cos(rotT)
  const sinR = Math.sin(rotT)
  const mouseWorld = _ndcToWorld(mouseNDC.x, mouseNDC.y)

  // Expire one-shot wave effects after 1 frame
  for (let ei = activeEffects.length - 1; ei >= 0; ei--) {
    if (activeEffects[ei].type === 'wave' || activeEffects[ei].type === 'shockwave') {
      activeEffects.splice(ei, 1)
    }
  }

  for (let i = 0; i < COUNT; i++) {
    if (frozen) {
      // Crystallize: freeze pos, shift to ice color
      dummy.position.copy(positions[i])
      dummy.updateMatrix()
      instancedMesh.setMatrixAt(i, dummy.matrix)
      color.setHSL(0.58, 0.4, 0.4 + Math.random() * 0.1)
      instancedMesh.setColorAt(i, color)
      continue
    }

    const n1 = Math.abs((Math.sin(i * 12.9898) * 43758.5453) % 1.0)
    const n2 = Math.abs((Math.sin(i * 78.233)  * 43758.5453) % 1.0)
    const n3 = Math.abs((Math.sin(i * 93.989)  * 43758.5453) % 1.0)

    const radiusDist    = Math.pow(n3, 5.0)
    const currentRadius = currentCore + currentSpread * radiusDist
    const theta = n1 * Math.PI * 2.0
    const phi   = Math.acos((n2 * 2.0) - 1.0)

    let xBase = Math.cos(theta) * Math.sin(phi) * currentRadius
    let yBase = Math.sin(theta) * Math.sin(phi) * currentRadius
    let zBase = Math.cos(phi) * currentRadius

    const motion  = t + (n1 * 15.0)
    const breathe = Math.sin(t * 2.0) * (1.0 - radiusDist) * 0.5
                  + smoothAmp * Math.sin(t * 8.0 + i * 0.01) * 3.0

    xBase += Math.sin(motion + yBase * 0.2) * 0.8 + breathe
    yBase += Math.cos(motion + zBase * 0.2) * 0.8 + breathe
    zBase += Math.sin(motion + xBase * 0.2) * 0.8 + breathe

    const fx = xBase * cosR - zBase * sinR
    const fz = xBase * sinR + zBase * cosR
    target.set(fx, yBase, fz)

    // ── Hand force (existing gestures) ────────────────────────────────────
    if (handActive) {
      const toHand = handPos.clone().sub(positions[i])
      const dist   = toHand.length()
      const inf    = Math.max(0, 1 - dist / HAND_RADIUS) ** 2
      if (inf > 0) {
        switch (handGesture) {
          case 'flow':   velocities[i].add(handVelocity.clone().multiplyScalar(inf * 0.8)); break
          case 'rotate': velocities[i].add(_tangent(toHand).multiplyScalar(inf * 2.0)); break
          case 'attract':velocities[i].add(toHand.normalize().multiplyScalar(inf * 2.0)); break
          case 'explode':velocities[i].add(toHand.normalize().multiplyScalar(-inf * 5.0)); break
          case 'pinch':  velocities[i].add(toHand.multiplyScalar(inf * 3.0)); break
          case 'repel':  velocities[i].add(toHand.normalize().multiplyScalar(-inf * 1.5)); break
        }
      }
    }

    // ── New effects ───────────────────────────────────────────────────────
    for (const fx of activeEffects) {
      switch (fx.type) {
        case 'shockwave': {
          const away = positions[i].clone().sub(fx.origin!)
          const d = away.length()
          if (d < (fx.radius ?? 40)) {
            const inf = (1 - d / (fx.radius ?? 40)) ** 2
            velocities[i].add(away.normalize().multiplyScalar(inf * (fx.force ?? 6)))
          }
          break
        }
        case 'vortex': {
          const toTarget = fx.target!.clone().sub(positions[i])
          const d = toTarget.length()
          const inf = Math.max(0, 1 - d / 60) ** 2
          velocities[i].add(toTarget.normalize().multiplyScalar(inf * (fx.strength ?? 3)))
          velocities[i].add(_tangent(toTarget).multiplyScalar(inf * 1.5))
          break
        }
        case 'orbit': {
          const toAnchor = fx.origin!.clone().sub(positions[i])
          const d = toAnchor.length()
          const orbitR = fx.radius ?? 20
          const pullStr = d > orbitR ? 2.0 : -0.5
          velocities[i].add(toAnchor.normalize().multiplyScalar(pullStr * delta * 60))
          velocities[i].add(_tangent(toAnchor).multiplyScalar(1.8 * delta * 60))
          break
        }
        case 'split': {
          const toA = fx.pointA!.clone().sub(positions[i])
          const toB = fx.pointB!.clone().sub(positions[i])
          const dA  = toA.length(); const dB = toB.length()
          const nearest = dA < dB ? toA : toB
          const inf = Math.max(0, 1 - Math.min(dA, dB) / 35) ** 2
          velocities[i].add(nearest.normalize().multiplyScalar(inf * 2.5))
          break
        }
        case 'portal': {
          const toC = fx.origin!.clone().sub(positions[i])
          const d = toC.length()
          const rr = fx.radius ?? 15
          if (Math.abs(d - rr) < 10) {
            velocities[i].add(_tangent(toC).multiplyScalar(2.0 * delta * 60))
          } else {
            const pull = d > rr ? 1.5 : -0.8
            velocities[i].add(toC.normalize().multiplyScalar(pull * delta * 60))
          }
          break
        }
        case 'beam': {
          const toTip = fx.origin!.clone().sub(positions[i])
          const proj  = toTip.dot(fx.direction!)
          if (proj > 0 && proj < 30) {
            const perp = toTip.clone().sub(fx.direction!.clone().multiplyScalar(proj))
            if (perp.length() < 5) {
              velocities[i].add(fx.direction!.clone().multiplyScalar(1.5 * delta * 60))
            }
          }
          break
        }
        case 'wave': {
          const fromOrigin = positions[i].clone().sub(fx.origin!)
          const inf = Math.max(0, 1 - fromOrigin.length() / 50) ** 2
          velocities[i].x += (fx.dirSign ?? 1) * inf * (fx.speed ?? 4)
          break
        }
        case 'breathe': {
          const fromCenter = positions[i].clone().sub(fx.origin!)
          const d = fromCenter.length()
          const pulse = Math.sin(time * 2.5) * 0.8
          if (d < 30) {
            velocities[i].add(fromCenter.normalize().multiplyScalar(pulse * delta * 60))
          }
          break
        }
      }
    }

    // Mouse force
    const toMouse = mouseWorld.clone().sub(positions[i])
    const mDist   = toMouse.length()
    if (mDist < MOUSE_RADIUS) {
      const mInf     = (1 - mDist / MOUSE_RADIUS) ** 2
      const strength = isDragging ? 3.0 : 0.3
      velocities[i].add(toMouse.normalize().multiplyScalar(-mInf * strength))
    }

    positions[i].add(velocities[i].clone().multiplyScalar(delta))
    velocities[i].multiplyScalar(0.85)

    const speed = velocities[i].length()
    const lerpF = Math.max(0.03, 0.1 - speed * 0.01)
    positions[i].lerp(target, lerpF)

    dummy.position.copy(positions[i])
    dummy.updateMatrix()
    instancedMesh.setMatrixAt(i, dummy.matrix)

    const h = currentHue + (n1 * 0.08)
    const s = currentSat + (n2 * 0.15)
    const l = 0.15 + (1.0 - radiusDist) * 0.45 + smoothAmp * 0.2
    color.setHSL(h, s, l)
    instancedMesh.setColorAt(i, color)
  }

  instancedMesh.instanceMatrix.needsUpdate = true
  if (instancedMesh.instanceColor) instancedMesh.instanceColor.needsUpdate = true
  composer.render()
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```
cd marcelo-ui && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add marcelo-ui/src/lib/particle-engine.ts
git commit -m "feat(ui-v2): particle-engine TS port + 9 new effect methods"
```

---

## Task 5: `gesture-engine.ts` — Bimanual State Machine

**Files:**
- Create: `marcelo-ui/src/lib/gesture-engine.ts`

Replaces `hand-tracker.js`. Supports 2 hands simultaneously. Each hand tracked independently. Bimanual patterns detected from combined state.

- [ ] **Step 1: Create `marcelo-ui/src/lib/gesture-engine.ts`**

```typescript
import * as THREE from 'three'
import type { HandGesture, BimanualGesture, HandState, BimanualPattern, GestureState } from './types'

// ─── Config ───────────────────────────────────────────────────────────────────

const PINCH_DIST    = 0.06   // normalized landmark distance
const PRAYER_DIST   = 0.08   // palms touching threshold (normalized)
const PRAYER_VEL    = 0.8    // separation velocity to trigger blast
const IMPLOSION_VEL = 0.3    // max approach velocity
const IMPLOSION_DIST = 0.15  // distance to trigger vortex
const ORBIT_HOLD_MS = 500    // ms pinch must be stable before orbit activates
const FREEZE_WINDOW = 300    // ms both fists must close within

// ─── Module state ─────────────────────────────────────────────────────────────

let camera3D: THREE.PerspectiveCamera | null = null

interface PerHandInternal {
  state: HandState
  gestureStartTime: number
  prevPos: THREE.Vector3
  prevTime: number
  breatheStartTime: number | null
  lastFistTime: number | null
}

const _hands: Record<'left' | 'right', PerHandInternal> = {
  left:  _emptyHand(),
  right: _emptyHand(),
}

let _bimanual: BimanualPattern = {
  active: false, pattern: null, phase: 'idle', progress: 0
}

// prayer state
let _prayerContactTime: number | null = null
let _prayerPhase: 'none' | 'contact' | 'release' | 'blast' = 'none'

// orbit state
let _orbitAnchorHand: 'left' | 'right' | null = null
let _orbitAnchorSince: number | null = null
let _orbitAngles: number[] = []

// freeze
let _lastFistTimes: Record<'left' | 'right', number | null> = { left: null, right: null }

export type GestureCallback = (state: GestureState) => void

let _onGesture: GestureCallback | null = null
let _rafHandle: number | null = null

// ─── Public API ───────────────────────────────────────────────────────────────

export async function init(
  videoEl: HTMLVideoElement,
  camera: THREE.PerspectiveCamera,
  onGesture: GestureCallback,
): Promise<void> {
  camera3D    = camera
  _onGesture  = onGesture

  await _loadScript('https://cdn.jsdelivr.net/npm/@mediapipe/hands/hands.js')
  await _loadScript('https://cdn.jsdelivr.net/npm/@mediapipe/camera_utils/camera_utils.js')

  const hands = new (window as any).Hands({
    locateFile: (f: string) => `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${f}`,
  })

  hands.setOptions({
    maxNumHands: 2,
    modelComplexity: 1,
    minDetectionConfidence: 0.7,
    minTrackingConfidence: 0.5,
  })

  hands.onResults(_processResults)

  const mpCamera = new (window as any).Camera(videoEl, {
    onFrame: async () => { await hands.send({ image: videoEl }) },
    width: 320,
    height: 240,
  })
  mpCamera.start()
}

export function dispose(): void {
  if (_rafHandle !== null) cancelAnimationFrame(_rafHandle)
}

// ─── Internal result handler ──────────────────────────────────────────────────

function _processResults(results: any): void {
  const now = performance.now()

  // Reset both hands to none
  _hands.left.state.gesture  = 'none'
  _hands.right.state.gesture = 'none'

  const lms  = results.multiHandLandmarks ?? []
  const hand = results.multiHandedness ?? []

  for (let hi = 0; hi < lms.length; hi++) {
    const landmarks = lms[hi]
    // MediaPipe labels: "Left" = user's left (mirrored = right in image) — use as-is
    const side: 'left' | 'right' = (hand[hi]?.label ?? 'Right') === 'Left' ? 'left' : 'right'
    const h = _hands[side]

    const gesture  = _classify(landmarks, h)
    const worldPos = _landmarkToWorld(landmarks[9])
    const dt       = Math.max((now - h.prevTime) / 1000, 0.001)

    const velocity = new THREE.Vector3(
      (worldPos.x - h.prevPos.x) / dt,
      (worldPos.y - h.prevPos.y) / dt,
      (worldPos.z - h.prevPos.z) / dt,
    )

    // Breathe detection
    if (gesture === 'open') {
      const speed = velocity.length()
      if (speed < 0.05 * 60) { // units/s threshold (world space)
        if (h.breatheStartTime === null) h.breatheStartTime = now
        if (now - h.breatheStartTime > 1000) {
          h.state.gesture = 'breathe'
        } else {
          h.state.gesture = 'open'
        }
      } else {
        h.breatheStartTime = null
        // Swipe detection
        if (Math.abs(velocity.x) > 1.5 * 60) {
          h.state.gesture = 'swipe'
        } else {
          h.state.gesture = 'open'
        }
      }
    } else {
      h.breatheStartTime = null
      h.state.gesture = gesture
    }

    h.state.worldPos.copy(worldPos)
    h.state.velocity.copy(velocity)
    h.state.age = h.state.gesture === gesture
      ? now - h.gestureStartTime
      : 0

    if (h.state.gesture !== gesture) h.gestureStartTime = now

    h.prevPos.copy(worldPos)
    h.prevTime = now

    // Freeze: track fist times
    if (gesture === 'fist') {
      if (_lastFistTimes[side] === null) _lastFistTimes[side] = now
    } else {
      _lastFistTimes[side] = null
    }
  }

  _detectBimanual(now)

  if (_onGesture) {
    _onGesture({
      left:     { ..._hands.left.state, worldPos: _hands.left.state.worldPos.clone(), velocity: _hands.left.state.velocity.clone() },
      right:    { ..._hands.right.state, worldPos: _hands.right.state.worldPos.clone(), velocity: _hands.right.state.velocity.clone() },
      bimanual: { ..._bimanual },
    })
  }
}

function _detectBimanual(now: number): void {
  const L = _hands.left.state
  const R = _hands.right.state

  if (L.gesture === 'none' || R.gesture === 'none') {
    _resetBimanual()
    return
  }

  // ── FREEZE: both fists within window ──────────────────────────────────────
  if (L.gesture === 'fist' && R.gesture === 'fist') {
    const lt = _lastFistTimes.left; const rt = _lastFistTimes.right
    if (lt !== null && rt !== null && Math.abs(lt - rt) < FREEZE_WINDOW) {
      _bimanual = { active: true, pattern: 'freeze', phase: 'instant', progress: 1 }
      return
    }
  }

  // ── DUAL-PINCH ────────────────────────────────────────────────────────────
  if (L.gesture === 'pinch' && R.gesture === 'pinch') {
    _bimanual = { active: true, pattern: 'dual-pinch', phase: 'sustained', progress: 1 }
    return
  }

  // ── PRAYER-EXPLOSION: both open, palms approaching / contact ─────────────
  if (L.gesture === 'open' && R.gesture === 'open') {
    const dist = L.worldPos.distanceTo(R.worldPos)

    if (dist < PRAYER_DIST * 100) { // convert normalized to world-ish (camera-projected)
      if (_prayerPhase === 'none') {
        _prayerPhase = 'contact'
        _prayerContactTime = now
      } else if (_prayerPhase === 'contact') {
        // Detect release velocity
        const sepVel = L.velocity.clone().sub(R.velocity).length()
        if (sepVel > PRAYER_VEL * 60) {
          _prayerPhase = 'blast'
          _bimanual = { active: true, pattern: 'prayer-explosion', phase: 'blast', progress: 1 }
          setTimeout(() => { _prayerPhase = 'none'; _prayerContactTime = null }, 500)
          return
        }
      }
      _bimanual = { active: true, pattern: 'prayer-explosion', phase: _prayerPhase, progress: 0.5 }
      return
    } else {
      if (_prayerPhase !== 'blast') _prayerPhase = 'none'
    }

    // ── IMPLOSION: both open, approaching slowly ────────────────────────────
    const approachVel = R.worldPos.clone().sub(L.worldPos).normalize()
      .dot(L.velocity.clone().sub(R.velocity)) / 60
    if (approachVel > 0 && L.velocity.length() / 60 < IMPLOSION_VEL) {
      const progress = Math.min(1, 1 - dist / 80)
      if (dist < IMPLOSION_DIST * 100) {
        _bimanual = { active: true, pattern: 'implosion', phase: 'vortex', progress: 1 }
      } else {
        _bimanual = { active: true, pattern: 'implosion', phase: 'approach', progress }
      }
      return
    }
  }

  // ── ORBIT: one pinch stable, other hand circling ──────────────────────────
  const pinchSide   = L.gesture === 'pinch' ? 'left' : R.gesture === 'pinch' ? 'right' : null
  const freeSide    = pinchSide === 'left' ? 'right' : pinchSide === 'right' ? 'left' : null

  if (pinchSide && freeSide) {
    const pinchH = _hands[pinchSide]
    if (_orbitAnchorHand !== pinchSide) {
      _orbitAnchorHand  = pinchSide
      _orbitAnchorSince = now
      _orbitAngles      = []
    }

    if (now - (_orbitAnchorSince ?? now) > ORBIT_HOLD_MS) {
      const anchor = _hands[pinchSide].state.worldPos
      const free   = _hands[freeSide].state.worldPos
      const dx = free.x - anchor.x; const dy = free.y - anchor.y
      const angle = Math.atan2(dy, dx)
      _orbitAngles.push(angle)
      if (_orbitAngles.length > 30) _orbitAngles.shift()

      // Check if angle swept > 180 degrees
      if (_orbitAngles.length >= 10) {
        const spread = Math.max(..._orbitAngles) - Math.min(..._orbitAngles)
        if (spread > Math.PI) {
          _bimanual = { active: true, pattern: 'orbit', phase: 'orbit', progress: 1 }
          return
        }
      }
      _bimanual = { active: true, pattern: 'orbit', phase: 'anchor', progress: 0.5 }
      return
    }
  } else {
    _orbitAnchorHand  = null
    _orbitAnchorSince = null
  }

  // ── PORTAL: fingertips of both hands form a rough ring ───────────────────
  // Approximate: use wrist + fingertip distances to check ring shape.
  // Simpler proxy: index fingers and pinkies of both hands are the "ring points".
  // We check that the 4 extremity landmarks are roughly equidistant from center.
  if (
    (L.gesture === 'open' || L.gesture === 'pinch') &&
    (R.gesture === 'open' || R.gesture === 'pinch')
  ) {
    const mid = L.worldPos.clone().add(R.worldPos).multiplyScalar(0.5)
    const dL  = L.worldPos.distanceTo(mid)
    const dR  = R.worldPos.distanceTo(mid)
    // Ring detected when hands are symmetric and close enough
    if (Math.abs(dL - dR) < 5 && dL > 5 && dL < 30) {
      _bimanual = { active: true, pattern: 'portal', phase: 'sustained', progress: 1 }
      return
    }
  }

  _resetBimanual()
}

function _resetBimanual(): void {
  if (_bimanual.pattern !== 'freeze') {
    _bimanual = { active: false, pattern: null, phase: 'idle', progress: 0 }
  }
}

// ─── Landmark helpers ─────────────────────────────────────────────────────────

function _classify(lm: any[], h: PerHandInternal): HandGesture {
  const thumbTip  = lm[4]; const indexTip  = lm[8]
  const middleTip = lm[12]; const ringTip  = lm[16]; const pinkyTip = lm[20]

  if (_dist(thumbTip, indexTip) < PINCH_DIST) return 'pinch'

  const indexCurled  = indexTip.y  > lm[6].y
  const middleCurled = middleTip.y > lm[10].y
  const ringCurled   = ringTip.y   > lm[14].y
  const pinkyCurled  = pinkyTip.y  > lm[18].y

  if (indexCurled && middleCurled && ringCurled && pinkyCurled) return 'fist'

  // Point: only index extended
  if (!indexCurled && middleCurled && ringCurled && pinkyCurled) return 'point'

  const allOpen = !indexCurled && !middleCurled && !ringCurled && !pinkyCurled
  if (allOpen) return 'open'

  return 'none'
}

function _dist(a: {x:number;y:number;z:number}, b: {x:number;y:number;z:number}): number {
  return Math.sqrt((a.x-b.x)**2 + (a.y-b.y)**2 + (a.z-b.z)**2)
}

function _landmarkToWorld(lm: {x:number;y:number;z:number}): THREE.Vector3 {
  if (!camera3D) return new THREE.Vector3()
  const ndcX =  lm.x * 2 - 1
  const ndcY = -lm.y * 2 + 1
  const v = new THREE.Vector3(ndcX, ndcY, 0.5)
  v.unproject(camera3D)
  const dir = v.sub(camera3D.position).normalize()
  const t   = -camera3D.position.z / dir.z
  return camera3D.position.clone().add(dir.multiplyScalar(t))
}

function _loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${src}"]`)) { resolve(); return }
    const s = document.createElement('script')
    s.src = src; s.onload = () => resolve(); s.onerror = reject
    document.head.appendChild(s)
  })
}

function _emptyHand(): PerHandInternal {
  return {
    state: {
      gesture: 'none',
      worldPos: new THREE.Vector3(),
      velocity: new THREE.Vector3(),
      age: 0,
    },
    gestureStartTime: 0,
    prevPos: new THREE.Vector3(),
    prevTime: performance.now(),
    breatheStartTime: null,
    lastFistTime: null,
  }
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```
cd marcelo-ui && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add marcelo-ui/src/lib/gesture-engine.ts
git commit -m "feat(ui-v2): gesture-engine with bimanual state machine"
```

---

## Task 6: `audio-analyzer.ts` + `ws-client.ts`

**Files:**
- Create: `marcelo-ui/src/lib/audio-analyzer.ts`
- Create: `marcelo-ui/src/lib/ws-client.ts`

- [ ] **Step 1: Create `marcelo-ui/src/lib/audio-analyzer.ts`**

Direct TypeScript port of `audio-analyzer.js`.

```typescript
let ctx: AudioContext | null = null

function _getCtx(): AudioContext {
  if (!ctx) ctx = new AudioContext()
  return ctx
}

/**
 * Decode and play an audio ArrayBuffer. Calls onAmplitude (0..1) each animation frame.
 * Returns a Promise that resolves when playback ends.
 */
export async function playAndAnalyze(
  arrayBuffer: ArrayBuffer,
  onAmplitude: (amp: number) => void,
): Promise<void> {
  const audioCtx = _getCtx()
  const decoded  = await audioCtx.decodeAudioData(arrayBuffer)

  const source   = audioCtx.createBufferSource()
  source.buffer  = decoded

  const analyser = audioCtx.createAnalyser()
  analyser.fftSize = 256
  source.connect(analyser)
  analyser.connect(audioCtx.destination)

  const data = new Uint8Array(analyser.frequencyBinCount)

  let rafId: number
  function tick() {
    analyser.getByteFrequencyData(data)
    const avg = data.reduce((a, b) => a + b, 0) / data.length
    onAmplitude(avg / 255)
    rafId = requestAnimationFrame(tick)
  }

  return new Promise((resolve) => {
    source.onended = () => {
      cancelAnimationFrame(rafId)
      onAmplitude(0)
      resolve()
    }
    source.start()
    tick()
  })
}

/**
 * Analyse mic stream amplitude in real-time.
 * Returns a stop() function.
 */
export function analyzeMicStream(
  stream: MediaStream,
  onAmplitude: (amp: number) => void,
): () => void {
  const audioCtx = _getCtx()
  const source   = audioCtx.createMediaStreamSource(stream)
  const analyser = audioCtx.createAnalyser()
  analyser.fftSize = 256
  source.connect(analyser)

  const data = new Uint8Array(analyser.frequencyBinCount)
  let rafId: number
  let running = true

  function tick() {
    if (!running) return
    analyser.getByteFrequencyData(data)
    const avg = data.reduce((a, b) => a + b, 0) / data.length
    onAmplitude(avg / 255)
    rafId = requestAnimationFrame(tick)
  }
  tick()

  return () => {
    running = false
    cancelAnimationFrame(rafId)
    onAmplitude(0)
    source.disconnect()
  }
}
```

- [ ] **Step 2: Create `marcelo-ui/src/lib/ws-client.ts`**

```typescript
import { playAndAnalyze, analyzeMicStream } from './audio-analyzer'
import type { ChatState, ChatMessage, MessageRole } from './types'

type StateCallback    = (s: 'idle' | 'listening' | 'thinking' | 'speaking') => void
type ChunkCallback    = (text: string) => void
type InterimCallback  = (text: string | null) => void
type PreviewCallback  = (text: string) => void
type DoneCallback     = (text: string) => void
type ErrorCallback    = (msg: string) => void
type AmpCallback      = (amp: number) => void

interface WsClientOptions {
  wsUrl:      string
  ttsUrl:     string
  onState:    StateCallback
  onChunk:    ChunkCallback
  /** Called with in-progress STT text, null when mic stops */
  onInterim:  InterimCallback
  onPreview:  PreviewCallback
  onDone:     DoneCallback
  onError:    ErrorCallback
}

export class WsClient {
  private _ws:           WebSocket | null = null
  private _recognition:  SpeechRecognition | null = null
  private _micStream:    MediaStream | null = null
  private _micStopFn:    (() => void) | null = null
  private _silenceTimer: ReturnType<typeof setTimeout> | null = null
  private _onAmp:        AmpCallback | null = null
  private _sessionId = 'ui-session'

  constructor(private readonly _opts: WsClientOptions) {}

  connect(): void {
    this._ws = new WebSocket(this._opts.wsUrl)

    this._ws.onopen = () => {
      this._opts.onState('idle')
    }

    this._ws.onmessage = async (ev: MessageEvent) => {
      const msg = JSON.parse(ev.data as string) as { type: string; text?: string }

      if (msg.type === 'chunk') {
        this._opts.onChunk(msg.text ?? '')
        await this._speakTTS(msg.text ?? '')
        this._opts.onState('idle')
      } else if (msg.type === 'preview') {
        this._opts.onPreview(msg.text ?? '')
      } else if (msg.type === 'done') {
        this._opts.onDone(msg.text ?? '')
        this._opts.onState('idle')
      } else if (msg.type === 'error') {
        this._opts.onError(msg.text ?? 'Unknown error')
        this._opts.onState('idle')
      }
    }

    this._ws.onerror = () => this._opts.onError('WebSocket error')
    this._ws.onclose = () => { setTimeout(() => this.connect(), 2000) }
  }

  sendText(text: string): void {
    const trimmed = text.trim()
    if (!trimmed || this._ws?.readyState !== WebSocket.OPEN) return
    this._opts.onState('thinking')
    this._ws.send(JSON.stringify({ type: 'message', message: trimmed, session_id: this._sessionId }))
  }

  approve(): void {
    this._ws?.send(JSON.stringify({ type: 'approve_send' }))
  }

  cancel(): void {
    this._ws?.send(JSON.stringify({ type: 'cancel_send' }))
  }

  async startMic(): Promise<void> {
    if (this._recognition) return
    try {
      this._micStream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch {
      this._opts.onError('Microphone permission denied')
      return
    }

    this._opts.onState('listening')
    if (this._onAmp) {
      this._micStopFn = analyzeMicStream(this._micStream, this._onAmp)
    }

    const SR = (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition
    if (!SR) { this._opts.onError('Web Speech API not supported'); return }

    this._recognition = new SR() as SpeechRecognition
    this._recognition.lang = 'pt-BR'
    this._recognition.continuous = false
    this._recognition.interimResults = true

    this._recognition.onresult = (ev: SpeechRecognitionEvent) => {
      const transcript = Array.from(ev.results).map(r => r[0].transcript).join('')
      // Interim: show in-progress text without adding to message history
      this._opts.onInterim(transcript)

      clearTimeout(this._silenceTimer!)
      this._silenceTimer = setTimeout(() => this._finalizeMic(), 2000)

      if (ev.results[ev.results.length - 1].isFinal) {
        this._opts.onInterim(null)  // clear interim
        this._finalizeMic()
        this.sendText(transcript)
      }
    }

    this._recognition.onerror  = () => { this._opts.onInterim(null); this._finalizeMic() }
    this._recognition.onend    = () => { this._recognition = null }
    this._recognition.start()
  }

  stopMic(): void { this._finalizeMic() }

  setAmpCallback(fn: AmpCallback): void { this._onAmp = fn }

  private _finalizeMic(): void {
    this._micStopFn?.(); this._micStopFn = null
    this._recognition?.stop(); this._recognition = null
    this._micStream?.getTracks().forEach(t => t.stop()); this._micStream = null
    if (this._silenceTimer) clearTimeout(this._silenceTimer)
  }

  private async _speakTTS(text: string): Promise<void> {
    this._opts.onState('speaking')
    try {
      const res = await fetch(this._opts.ttsUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      })
      if (!res.ok) throw new Error(`TTS HTTP ${res.status}`)
      const buf = await res.arrayBuffer()
      await playAndAnalyze(buf, amp => this._onAmp?.(amp))
    } catch (err) {
      this._opts.onError(`TTS error: ${(err as Error).message}`)
    }
  }
}
```

- [ ] **Step 3: Verify TypeScript compiles**

```
cd marcelo-ui && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add marcelo-ui/src/lib/audio-analyzer.ts marcelo-ui/src/lib/ws-client.ts
git commit -m "feat(ui-v2): audio-analyzer and ws-client TypeScript ports"
```

---

## Task 7: Svelte Stores

**Files:**
- Create: `marcelo-ui/src/stores/gesture.svelte.ts`
- Create: `marcelo-ui/src/stores/chat.svelte.ts`
- Create: `marcelo-ui/src/stores/projects.svelte.ts`

- [ ] **Step 1: Create `marcelo-ui/src/stores/gesture.svelte.ts`**

```typescript
import * as THREE from 'three'
import type { GestureState } from '../lib/types'

export const gestureState = $state<GestureState>({
  left: {
    gesture: 'none',
    worldPos: new THREE.Vector3(),
    velocity: new THREE.Vector3(),
    age: 0,
  },
  right: {
    gesture: 'none',
    worldPos: new THREE.Vector3(),
    velocity: new THREE.Vector3(),
    age: 0,
  },
  bimanual: {
    active: false,
    pattern: null,
    phase: 'idle',
    progress: 0,
  },
})

export function updateGestureState(next: GestureState): void {
  gestureState.left  = next.left
  gestureState.right = next.right
  gestureState.bimanual = next.bimanual
}
```

- [ ] **Step 2: Create `marcelo-ui/src/stores/chat.svelte.ts`**

```typescript
import type { ChatMessage, ChatState } from '../lib/types'

let _idCounter = 0
function _id(): string { return `msg-${++_idCounter}` }

export const chatState = $state<ChatState>({
  messages: [],
  interim:  null,
  preview:  null,
  streaming: false,
  connected: false,
})

export function addMessage(role: ChatMessage['role'], text: string): void {
  chatState.messages.push({ id: _id(), role, text, timestamp: Date.now() })
}

export function appendChunk(text: string): void {
  const last = chatState.messages.at(-1)
  if (last?.role === 'assistant') {
    last.text += text
  } else {
    chatState.messages.push({ id: _id(), role: 'assistant', text, timestamp: Date.now() })
  }
}

export function setInterim(text: string | null): void {
  chatState.interim = text
}

export function setPreview(text: string | null): void {
  chatState.preview = text
}
```

- [ ] **Step 3: Create `marcelo-ui/src/stores/projects.svelte.ts`**

```typescript
import type { ProjectItem, ProjectsState } from '../lib/types'

export const projectsState = $state<ProjectsState>({
  items:   [],
  loading: false,
})

export async function fetchProjects(): Promise<void> {
  projectsState.loading = true
  try {
    const res = await fetch('/api/v1/projects')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    projectsState.items = await res.json() as ProjectItem[]
  } catch {
    // Keep stale data on error — silent fail
  } finally {
    projectsState.loading = false
  }
}

/** Start polling every 30s. Returns a cleanup function. */
export function startPolling(): () => void {
  fetchProjects()
  const id = setInterval(fetchProjects, 30_000)
  return () => clearInterval(id)
}
```

- [ ] **Step 4: Verify TypeScript compiles**

```
cd marcelo-ui && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add marcelo-ui/src/stores/
git commit -m "feat(ui-v2): Svelte 5 runes stores for gesture, chat, projects"
```

---

## Task 8: `ParticleCanvas.svelte` + `WebcamView.svelte`

**Files:**
- Create: `marcelo-ui/src/components/ParticleCanvas.svelte`
- Create: `marcelo-ui/src/components/WebcamView.svelte`

- [ ] **Step 1: Create `marcelo-ui/src/components/ParticleCanvas.svelte`**

```svelte
<script lang="ts">
  import { onMount, onDestroy } from 'svelte'
  import * as ParticleEngine from '../lib/particle-engine'
  import * as GestureEngine from '../lib/gesture-engine'
  import { updateGestureState } from '../stores/gesture.svelte'
  import type { GestureState } from '../lib/types'
  import * as THREE from 'three'
  import {
    shockwave, vortex, orbitAnchor, crystallize,
    splitField, clearSplitField, portalRing, clearPortal,
    directionalBeam, clearBeam, lateralWave, breathePulse, clearBreath,
    applyHandForce, clearHandForce, setState,
  } from '../lib/particle-engine'

  let canvasEl: HTMLCanvasElement
  let videoEl: HTMLVideoElement

  onMount(async () => {
    ParticleEngine.init(canvasEl)
    const cam = ParticleEngine.getCamera()

    await GestureEngine.init(videoEl, cam, (state: GestureState) => {
      updateGestureState(state)
      _applyGestureToParticles(state)
    })
  })

  onDestroy(() => {
    GestureEngine.dispose()
    ParticleEngine.dispose()
  })

  function _applyGestureToParticles(state: GestureState): void {
    const { left, right, bimanual } = state

    // Bimanual effects take priority
    if (bimanual.active && bimanual.pattern) {
      switch (bimanual.pattern) {
        case 'prayer-explosion':
          if (bimanual.phase === 'blast') {
            const mid = left.worldPos.clone().add(right.worldPos).multiplyScalar(0.5)
            shockwave(mid, 60, 8)
          }
          break
        case 'implosion':
          if (bimanual.phase === 'vortex') {
            const mid = left.worldPos.clone().add(right.worldPos).multiplyScalar(0.5)
            vortex(mid, 4)
          }
          break
        case 'orbit': {
          const pinchHand = left.gesture === 'pinch' ? left : right
          orbitAnchor(pinchHand.worldPos, 20)
          break
        }
        case 'freeze':
          crystallize(3000)
          break
        case 'dual-pinch':
          splitField(left.worldPos, right.worldPos)
          break
        case 'portal': {
          const mid = left.worldPos.clone().add(right.worldPos).multiplyScalar(0.5)
          portalRing(mid, left.worldPos.distanceTo(right.worldPos) * 0.5)
          break
        }
      }
      // Non-portal bimanual: clear persistent single-hand effects
      if (bimanual.pattern !== 'portal') clearPortal()
      if (bimanual.pattern !== 'dual-pinch') clearSplitField()

      // Still apply free-hand unimanual for orbit (free hand)
      if (bimanual.pattern === 'orbit') {
        const freeHand = left.gesture !== 'pinch' ? left : right
        if (freeHand.gesture !== 'none') {
          applyHandForce(freeHand.worldPos, freeHand.gesture, freeHand.velocity)
        }
      }
      return
    }

    // Single-hand effects (apply both hands independently)
    clearSplitField()
    clearPortal()

    for (const hand of [left, right]) {
      if (hand.gesture === 'none') continue
      switch (hand.gesture) {
        case 'pinch':
        case 'fist':
        case 'open':
          applyHandForce(hand.worldPos, hand.gesture === 'fist' ? 'attract' : hand.gesture === 'open' ? 'repel' : 'pinch', hand.velocity)
          break
        case 'point':
          directionalBeam(hand.worldPos, hand.velocity.clone().normalize())
          break
        case 'swipe':
          lateralWave(hand.worldPos, Math.sign(hand.velocity.x), hand.velocity.length() / 60)
          clearBeam()
          break
        case 'breathe':
          breathePulse(hand.worldPos)
          clearBeam()
          break
        default:
          clearBeam()
          clearBreath()
          clearHandForce()
      }
    }

    if (left.gesture === 'none' && right.gesture === 'none') {
      clearHandForce()
      clearBeam()
      clearBreath()
    }
  }
</script>

<canvas
  bind:this={canvasEl}
  style="position:fixed;inset:0;z-index:0;width:100vw;height:100vh;display:block;"
></canvas>

<!-- Hidden video for MediaPipe -->
<video
  bind:this={videoEl}
  autoplay
  playsinline
  muted
  style="position:fixed;top:-9999px;left:-9999px;width:320px;height:240px;"
></video>
```

- [ ] **Step 2: Create `marcelo-ui/src/components/WebcamView.svelte`**

```svelte
<script lang="ts">
  import { onMount } from 'svelte'

  let videoEl: HTMLVideoElement
  let visible = $state(false)

  onMount(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false })
      videoEl.srcObject = stream
      visible = true
    } catch {
      // No webcam available — hide silently
    }
  })
</script>

{#if visible}
  <div style="
    position:fixed;
    top:16px;
    right:16px;
    z-index:10;
    width:120px;
    aspect-ratio:4/3;
    border-radius:8px;
    overflow:hidden;
    border:1px solid rgba(255,255,255,0.08);
    background:rgba(6,10,15,0.5);
  ">
    <video
      bind:this={videoEl}
      autoplay
      playsinline
      muted
      style="width:100%;height:100%;object-fit:cover;transform:scaleX(-1);"
    ></video>
  </div>
{/if}
```

- [ ] **Step 3: Verify TypeScript compiles**

```
cd marcelo-ui && npx tsc --noEmit
```

- [ ] **Step 4: Commit**

```bash
git add marcelo-ui/src/components/ParticleCanvas.svelte marcelo-ui/src/components/WebcamView.svelte
git commit -m "feat(ui-v2): ParticleCanvas and WebcamView components"
```

---

## Task 9: `StatusBadge.svelte` + `GestureHUD.svelte`

**Files:**
- Create: `marcelo-ui/src/components/StatusBadge.svelte`
- Create: `marcelo-ui/src/components/GestureHUD.svelte`

- [ ] **Step 1: Create `marcelo-ui/src/components/StatusBadge.svelte`**

```svelte
<script lang="ts">
  import type { ParticleState } from '../lib/types'

  let { state }: { state: ParticleState } = $props()

  const labels: Record<ParticleState, string> = {
    idle:      'IDLE',
    listening: 'OUVINDO',
    thinking:  'PENSANDO',
    speaking:  'FALANDO',
  }

  const colors: Record<ParticleState, string> = {
    idle:      'rgba(99,179,255,0.5)',
    listening: 'rgba(150,255,180,0.7)',
    thinking:  'rgba(255,200,80,0.7)',
    speaking:  'rgba(150,80,255,0.7)',
  }
</script>

<span style="
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: {colors[state]};
  display: inline-flex;
  align-items: center;
  gap: 5px;
">
  <span style="
    width:5px;height:5px;border-radius:50%;
    background:{colors[state]};
    box-shadow:0 0 6px {colors[state]};
    flex-shrink:0;
  "></span>
  {labels[state]}
</span>
```

- [ ] **Step 2: Create `marcelo-ui/src/components/GestureHUD.svelte`**

```svelte
<script lang="ts">
  import { gestureState } from '../stores/gesture.svelte'
  import type { BimanualGesture, HandGesture } from '../lib/types'

  // Freeze ice overlay: tracked via crystallize bimanual
  let frozen = $state(false)
  let freezeTimer: ReturnType<typeof setTimeout> | null = null

  // Badge visible timer
  let badgeText = $state<string | null>(null)
  let badgeTimer: ReturnType<typeof setTimeout> | null = null

  const bimanualLabels: Record<BimanualGesture, string> = {
    'prayer-explosion': '🙏 EXPLOSÃO',
    'implosion':        '🌀 IMPLOSÃO',
    'orbit':            '🌌 ÓRBITA',
    'freeze':           '❄️ CONGELAR',
    'dual-pinch':       '⚡ CAMPO DUPLO',
    'portal':           '🔮 PORTAL',
  }

  const unimanualLabels: Partial<Record<HandGesture, string>> = {
    pinch:   '👌 PINCH',
    fist:    '✊ BURST',
    open:    '🖐 REPELIR',
    point:   '☝️ APONTAR',
    swipe:   '🌊 ONDA',
    breathe: '💫 RESPIRAR',
  }

  $effect(() => {
    const { bimanual, left, right } = gestureState

    if (bimanual.active && bimanual.pattern) {
      _showBadge(bimanualLabels[bimanual.pattern])
      if (bimanual.pattern === 'freeze') {
        frozen = true
        freezeTimer && clearTimeout(freezeTimer)
        freezeTimer = setTimeout(() => { frozen = false }, 3000)
      }
      return
    }

    const activeGesture = left.gesture !== 'none' ? left.gesture : right.gesture
    const label = unimanualLabels[activeGesture]
    if (label) _showBadge(label)
  })

  function _showBadge(text: string): void {
    badgeText = text
    badgeTimer && clearTimeout(badgeTimer)
    badgeTimer = setTimeout(() => { badgeText = null }, 1500)
  }
</script>

<!-- Freeze ice overlay -->
{#if frozen}
  <div style="
    position:fixed;inset:0;z-index:25;pointer-events:none;
    background:rgba(150,220,255,0.04);
    animation:iceIn 400ms ease;
  " class="freeze-overlay"></div>
{/if}

<!-- Gesture badge -->
{#if badgeText}
  <div style="
    position:fixed;
    top:16px;
    left:50%;
    transform:translateX(-50%);
    z-index:30;
    background:rgba(6,10,15,0.85);
    backdrop-filter:blur(8px);
    border:1px solid rgba(255,255,255,0.1);
    border-radius:20px;
    padding:6px 16px;
    font-family:'JetBrains Mono',monospace;
    font-size:11px;
    letter-spacing:2px;
    color:rgba(255,255,255,0.8);
    pointer-events:none;
    animation:fadeIn 100ms ease;
  ">
    {badgeText}
  </div>
{/if}

<style>
  @keyframes iceIn {
    from { opacity: 0; }
    to   { opacity: 1; }
  }
  @keyframes fadeIn {
    from { opacity: 0; transform: translateX(-50%) translateY(-4px); }
    to   { opacity: 1; transform: translateX(-50%) translateY(0); }
  }
</style>
```

- [ ] **Step 3: Commit**

```bash
git add marcelo-ui/src/components/StatusBadge.svelte marcelo-ui/src/components/GestureHUD.svelte
git commit -m "feat(ui-v2): StatusBadge and GestureHUD components"
```

---

## Task 10: `ChatOverlay.svelte`

**Files:**
- Create: `marcelo-ui/src/components/ChatOverlay.svelte`

- [ ] **Step 1: Create `marcelo-ui/src/components/ChatOverlay.svelte`**

```svelte
<script lang="ts">
  import { onMount, tick } from 'svelte'
  import { chatState, addMessage, appendChunk, setInterim, setPreview } from '../stores/chat.svelte'
  import { WsClient } from '../lib/ws-client'
  import StatusBadge from './StatusBadge.svelte'
  import type { ParticleState } from '../lib/types'
  import { setState as setParticleState, setAmplitude } from '../lib/particle-engine'

  let collapsed = $state(false)
  let inputText = $state('')
  let transcriptEl: HTMLDivElement
  let particleState = $state<ParticleState>('idle')

  let client: WsClient

  onMount(() => {
    client = new WsClient({
      wsUrl:  `ws://${window.location.host}/ws/chat`,
      ttsUrl: '/api/v1/tts',
      onState: (s) => {
        particleState = s as ParticleState
        setParticleState(s as ParticleState)
      },
      onChunk: (text) => {
        // WS streaming chunk — adds/appends to assistant message history
        appendChunk(text)
        _scrollToBottom()
      },
      onInterim: (text) => {
        // STT in-progress — shown separately, NOT added to message history
        setInterim(text)
      },
      onPreview: (text) => {
        setPreview(text)
      },
      onDone: () => {
        chatState.streaming = false
      },
      onError: (msg) => {
        addMessage('assistant', `⚠ ${msg}`)
      },
    })

    client.setAmpCallback((amp) => setAmplitude(amp))
    client.connect()
  })

  async function _scrollToBottom() {
    await tick()
    transcriptEl?.scrollTo({ top: transcriptEl.scrollHeight, behavior: 'smooth' })
  }

  function sendText() {
    const t = inputText.trim()
    if (!t) return
    addMessage('user', t)
    client.sendText(t)
    inputText = ''
    _scrollToBottom()
  }

  function onKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendText() }
  }

  function toggleMic() {
    if (particleState === 'listening') {
      client.stopMic()
    } else {
      client.startMic()
    }
  }

  function approve() { client.approve(); setPreview(null) }
  function cancel()  { client.cancel();  setPreview(null) }
</script>

<div style="
  position:fixed;
  bottom:24px;
  left:24px;
  z-index:20;
  width:340px;
  max-height:480px;
  background:rgba(6,10,15,0.75);
  backdrop-filter:blur(12px);
  border:1px solid rgba(255,255,255,0.08);
  border-radius:12px;
  display:flex;
  flex-direction:column;
  overflow:hidden;
  transition:max-height 200ms ease, opacity 200ms ease;
  {collapsed ? 'max-height:48px;' : ''}
">
  <!-- Header -->
  <div
    onclick={() => collapsed = !collapsed}
    style="
      display:flex;align-items:center;justify-content:space-between;
      padding:12px 14px;cursor:pointer;flex-shrink:0;
      border-bottom:1px solid {collapsed ? 'transparent' : 'rgba(255,255,255,0.05)'};
    "
  >
    <span style="font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:2px;color:rgba(99,179,255,0.7);text-transform:uppercase;">
      💬 chat
    </span>
    <StatusBadge state={particleState} />
  </div>

  {#if !collapsed}
    <!-- Transcript -->
    <div
      bind:this={transcriptEl}
      style="
        flex:1;overflow-y:auto;padding:12px 14px;
        display:flex;flex-direction:column;gap:8px;
        scrollbar-width:thin;scrollbar-color:rgba(255,255,255,0.1) transparent;
      "
    >
      {#each chatState.messages as msg (msg.id)}
        <div style="
          display:flex;
          flex-direction:column;
          align-items:{msg.role === 'user' ? 'flex-end' : 'flex-start'};
        ">
          <div style="
            max-width:85%;
            background:{msg.role === 'user' ? 'rgba(150,80,255,0.1)' : 'rgba(99,179,255,0.07)'};
            border:1px solid {msg.role === 'user' ? 'rgba(150,80,255,0.2)' : 'rgba(99,179,255,0.15)'};
            border-radius:8px;
            padding:7px 10px;
            font-family:Inter,sans-serif;
            font-size:13px;
            color:rgba(255,255,255,0.82);
            line-height:1.5;
            white-space:pre-wrap;word-break:break-word;
          ">
            {msg.text}
          </div>
        </div>
      {/each}

      {#if chatState.interim}
        <div style="
          font-size:12px;color:rgba(255,255,255,0.3);
          font-style:italic;padding:4px 2px;
        ">{chatState.interim}…</div>
      {/if}
    </div>

    <!-- Preview card -->
    {#if chatState.preview}
      <div style="
        margin:0 14px 10px;
        background:rgba(255,200,80,0.05);
        border:1px solid rgba(255,200,80,0.2);
        border-radius:8px;padding:10px;
      ">
        <div style="font-family:'JetBrains Mono',monospace;font-size:9px;letter-spacing:1px;color:rgba(255,200,80,0.6);margin-bottom:6px;">
          ⚡ CLAUDE CODE — CONFIRMAR?
        </div>
        <div style="font-size:12px;color:rgba(255,255,255,0.6);margin-bottom:8px;white-space:pre-wrap;">{chatState.preview}</div>
        <div style="display:flex;gap:6px;">
          <button
            onclick={approve}
            style="flex:1;padding:5px;border-radius:5px;border:1px solid rgba(150,255,180,0.3);background:rgba(150,255,180,0.08);color:rgba(150,255,180,0.8);font-size:11px;cursor:pointer;font-family:'JetBrains Mono',monospace;"
          >✓ ENVIAR</button>
          <button
            onclick={cancel}
            style="flex:1;padding:5px;border-radius:5px;border:1px solid rgba(255,100,80,0.3);background:rgba(255,100,80,0.06);color:rgba(255,100,80,0.7);font-size:11px;cursor:pointer;font-family:'JetBrains Mono',monospace;"
          >✕ CANCELAR</button>
        </div>
      </div>
    {/if}

    <!-- Input dock -->
    <div style="
      padding:10px 12px;
      display:flex;gap:6px;align-items:center;
      border-top:1px solid rgba(255,255,255,0.05);flex-shrink:0;
    ">
      <input
        bind:value={inputText}
        onkeydown={onKeydown}
        placeholder="mensagem…"
        style="
          flex:1;background:rgba(255,255,255,0.03);
          border:1px solid rgba(255,255,255,0.08);
          border-radius:6px;padding:7px 10px;
          color:rgba(255,255,255,0.8);
          font-family:Inter,sans-serif;font-size:13px;
          outline:none;
        "
      />
      <button
        onclick={toggleMic}
        title={particleState === 'listening' ? 'Parar microfone' : 'Iniciar microfone'}
        style="
          width:32px;height:32px;border-radius:50%;
          border:1px solid {particleState === 'listening' ? 'rgba(150,255,180,0.5)' : 'rgba(255,255,255,0.12)'};
          background:{particleState === 'listening' ? 'rgba(150,255,180,0.12)' : 'rgba(255,255,255,0.04)'};
          color:rgba(255,255,255,0.6);font-size:13px;cursor:pointer;
          display:flex;align-items:center;justify-content:center;
        "
      >🎤</button>
      <button
        onclick={sendText}
        style="
          width:32px;height:32px;border-radius:50%;
          border:1px solid rgba(99,179,255,0.3);
          background:rgba(99,179,255,0.1);
          color:rgba(99,179,255,0.8);font-size:13px;cursor:pointer;
          display:flex;align-items:center;justify-content:center;
        "
      >↑</button>
    </div>
  {/if}
</div>
```

- [ ] **Step 2: Commit**

```bash
git add marcelo-ui/src/components/ChatOverlay.svelte
git commit -m "feat(ui-v2): ChatOverlay with streaming, STT, TTS, preview card"
```

---

## Task 11: `ProjectsOverlay.svelte`

**Files:**
- Create: `marcelo-ui/src/components/ProjectsOverlay.svelte`

- [ ] **Step 1: Create `marcelo-ui/src/components/ProjectsOverlay.svelte`**

```svelte
<script lang="ts">
  import { onMount, onDestroy } from 'svelte'
  import { projectsState, startPolling } from '../stores/projects.svelte'
  import type { ProjectItem } from '../lib/types'

  let collapsed = $state(false)
  let expanded  = $state(false)
  let stopPolling: () => void

  const SHOW_LIMIT = 5

  onMount(() => { stopPolling = startPolling() })
  onDestroy(() => stopPolling?.())

  /** Returns 'today' | '2d' | '5d' | '3sem' etc. */
  function _relTime(mtime: number): string {
    const diff = (Date.now() / 1000) - mtime
    if (diff < 86_400)           return 'hoje'
    if (diff < 86_400 * 7)       return `${Math.floor(diff / 86_400)}d`
    if (diff < 86_400 * 30)      return `${Math.floor(diff / (86_400 * 7))}sem`
    return `${Math.floor(diff / (86_400 * 30))}m`
  }

  /** Green = today, amber = <7d, grey = older */
  function _dotColor(mtime: number): string {
    const diff = (Date.now() / 1000) - mtime
    if (diff < 86_400)      return '#96ff64'
    if (diff < 86_400 * 7)  return 'rgba(255,200,80,0.8)'
    return 'rgba(255,255,255,0.2)'
  }

  function _dotGlow(mtime: number): string {
    const diff = (Date.now() / 1000) - mtime
    if (diff < 86_400)      return '0 0 5px #96ff64'
    return 'none'
  }

  async function _openProject(item: ProjectItem): Promise<void> {
    // Calls open_dev_environment via the WebSocket / tool — for now POST to a
    // dedicated endpoint. If that endpoint doesn't exist yet, opens in explorer.
    try {
      await fetch('/api/v1/open-project', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: item.path }),
      })
    } catch {
      // Fallback: no-op silently
    }
  }

  let displayed = $derived(
    expanded
      ? projectsState.items
      : projectsState.items.slice(0, SHOW_LIMIT)
  )

  let hiddenCount = $derived(
    Math.max(0, projectsState.items.length - SHOW_LIMIT)
  )
</script>

<div style="
  position:fixed;
  bottom:24px;
  right:24px;
  z-index:20;
  width:220px;
  background:rgba(6,10,15,0.75);
  backdrop-filter:blur(12px);
  border:1px solid rgba(255,255,255,0.07);
  border-radius:12px;
  overflow:hidden;
  transition:max-height 200ms ease;
  max-height:{collapsed ? '48px' : '400px'};
">
  <!-- Header -->
  <div
    onclick={() => collapsed = !collapsed}
    style="
      padding:12px 14px;
      display:flex;align-items:center;justify-content:space-between;
      cursor:pointer;
      border-bottom:1px solid {collapsed ? 'transparent' : 'rgba(255,255,255,0.05)'};
    "
  >
    <span style="font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:2px;color:rgba(150,255,180,0.6);text-transform:uppercase;">
      ◈ projetos
    </span>
    {#if projectsState.loading}
      <span style="font-size:9px;color:rgba(255,255,255,0.2);">…</span>
    {/if}
  </div>

  {#if !collapsed}
    <div style="padding:6px 0;">
      {#each displayed as item (item.path)}
        <div
          onclick={() => _openProject(item)}
          style="
            display:flex;align-items:center;gap:8px;
            padding:6px 14px;cursor:pointer;
            transition:background 100ms;
          "
          onmouseenter={(e) => (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.03)'}
          onmouseleave={(e) => (e.currentTarget as HTMLElement).style.background = 'transparent'}
        >
          <span style="
            width:6px;height:6px;border-radius:50%;flex-shrink:0;
            background:{_dotColor(item.mtime)};
            box-shadow:{_dotGlow(item.mtime)};
          "></span>
          <span style="
            flex:1;font-family:Inter,sans-serif;font-size:12px;
            color:rgba(255,255,255,0.65);
            white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
          ">{item.name}</span>
          <span style="
            font-family:'JetBrains Mono',monospace;font-size:9px;
            color:rgba(255,255,255,0.2);flex-shrink:0;
          ">{_relTime(item.mtime)}</span>
        </div>
      {/each}

      {#if hiddenCount > 0 && !expanded}
        <div
          onclick={() => expanded = true}
          style="
            padding:5px 14px;
            font-family:'JetBrains Mono',monospace;font-size:9px;
            color:rgba(255,255,255,0.2);letter-spacing:1px;cursor:pointer;
          "
        >+ {hiddenCount} projetos…</div>
      {/if}
    </div>
  {/if}
</div>
```

- [ ] **Step 2: Commit**

```bash
git add marcelo-ui/src/components/ProjectsOverlay.svelte
git commit -m "feat(ui-v2): ProjectsOverlay minimal list with recency dots"
```

---

## Task 12: Wire Everything in `App.svelte`

**Files:**
- Modify: `marcelo-ui/src/App.svelte`

- [ ] **Step 1: Replace skeleton `App.svelte` with complete shell**

```svelte
<script lang="ts">
  import ParticleCanvas    from './components/ParticleCanvas.svelte'
  import WebcamView        from './components/WebcamView.svelte'
  import ChatOverlay       from './components/ChatOverlay.svelte'
  import ProjectsOverlay   from './components/ProjectsOverlay.svelte'
  import GestureHUD        from './components/GestureHUD.svelte'
</script>

<ParticleCanvas />
<WebcamView />
<GestureHUD />
<ChatOverlay />
<ProjectsOverlay />
```

- [ ] **Step 2: Run dev server**

```
cd marcelo-ui && npm run dev
```
Expected: `http://localhost:5173` opens. Dark canvas with particles visible, webcam in corner, overlays visible.

- [ ] **Step 3: Start backend**

```
cd D:\Projetos\Marcelo && python -m uvicorn app.main:app --reload --port 8000
```

- [ ] **Step 4: Smoke-test checklist**

Open `http://localhost:5173` in browser and verify:
- [ ] Particle canvas fills screen (no white flash on load)
- [ ] Webcam feed appears top-right (if camera available)
- [ ] Chat overlay visible bottom-left, collapsible on header click
- [ ] Projects overlay visible bottom-right, lists `D:\Projetos\Projetos_Marcelo` contents
- [ ] Type message in chat → sends to backend → response streams back
- [ ] Mic button toggles listening state (blue pill changes)
- [ ] Hand in webcam → particles react (pinch attracts, open repels)
- [ ] Prayer gesture (both hands together → apart fast) → particle shockwave

- [ ] **Step 5: Commit**

```bash
git add marcelo-ui/src/App.svelte
git commit -m "feat(ui-v2): wire all components in App.svelte"
```

---

## Task 13: Typecheck + Build Verification

**Files:** No new files — verification only.

- [ ] **Step 1: Full TypeScript check**

```
cd marcelo-ui && npx tsc --noEmit
```
Expected: zero errors.

- [ ] **Step 2: Svelte typecheck**

```
cd marcelo-ui && npm run typecheck
```
Expected: zero errors.

- [ ] **Step 3: Production build**

```
cd marcelo-ui && npm run build
```
Expected: build succeeds, no critical warnings.

- [ ] **Step 4: Run Python test suite**

```
cd D:\Projetos\Marcelo && pytest --tb=short -q
```
Expected: all tests pass including new projects endpoint tests.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore(ui-v2): verified typecheck and build clean"
```

---

## Completion Checklist

- [ ] `marcelo-ui/` runs with `vite dev` and connects to FastAPI on port 8000
- [ ] All 6 bimanual gestures detected with particle effects
- [ ] All 3 new unimanual gestures (point, swipe, breathe) + 3 existing working
- [ ] Chat overlay: streaming, STT, TTS, preview card, collapsible
- [ ] Projects overlay: correct list from `D:\Projetos\Projetos_Marcelo`, recency dots
- [ ] Layout: glass overlays over full-screen canvas
- [ ] `tsc --noEmit` passes
- [ ] `vite build` passes
- [ ] Python `pytest` passes (including projects endpoint)

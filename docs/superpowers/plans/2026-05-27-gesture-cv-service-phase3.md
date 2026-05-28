# Gesture CV Service — Phase 3: GPGPU Particle Engine

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. **Prerequisite: Phase 2 complete.**

**Goal:** Replace the CPU particle loop with a GPU simulation (`GPUComputationRenderer`, WebGL2). Particle position & velocity live in textures; physics runs in fragment shaders. Gesture events enter as force uniforms via the effect catalog. Retire `particle-engine.ts`.

**Architecture:** `gpgpu/engine.ts` owns the renderer, the two compute variables (position, velocity), the render points mesh, and per-frame uniform updates. `gpgpu/shaders.ts` holds the GLSL. `gpgpu/effects.ts` maps an effect name → a numeric force mode + parameters, and holds the built-in gesture→effect map used until Phase 5 supplies configured bindings. `ParticleCanvas.svelte` feeds wire events straight into the engine.

**Tech Stack:** Three.js `GPUComputationRenderer` (addons), GLSL, TypeScript, Svelte 5.

**Note on testing:** the frontend has no JS test runner configured; adding one is out of scope. Phase 3 is verified manually (visual) per step, except the pure effect-map function, which is exercised by a tiny `console.assert` smoke check in the engine init (documented below).

**Particle grid:** 256×256 = 65,536 particles (raise to 512×512 = 262,144 once stable if the GPU allows).

---

## File Structure

| File | Responsibility | Verify |
|------|----------------|--------|
| `marcelo-ui/src/lib/gpgpu/shaders.ts` | GLSL strings: position, velocity, render vertex/fragment | manual |
| `marcelo-ui/src/lib/gpgpu/effects.ts` | effect name → force mode + params; built-in gesture→effect map | smoke |
| `marcelo-ui/src/lib/gpgpu/engine.ts` | renderer, compute vars, mesh, uniforms, animate loop, public API | manual |
| `marcelo-ui/src/components/ParticleCanvas.svelte` (modify) | feed wire events into the GPGPU engine | manual |
| `marcelo-ui/src/lib/particle-engine.ts` | **retired** (deleted) | — |
| `marcelo-ui/src/lib/gesture-engine.ts` | **retired** if still present (deleted) | — |

---

### Task 1: GPGPU scaffold — static cloud

**Files:**
- Create: `marcelo-ui/src/lib/gpgpu/shaders.ts`
- Create: `marcelo-ui/src/lib/gpgpu/engine.ts`
- Modify: `marcelo-ui/src/components/ParticleCanvas.svelte`

- [ ] **Step 1: Write the shaders (scaffold versions)**

Create `marcelo-ui/src/lib/gpgpu/shaders.ts`:

```typescript
// Compute shader: integrate position from velocity.
export const positionShader = /* glsl */ `
  uniform float uDelta;
  void main() {
    vec2 uv = gl_FragCoord.xy / resolution.xy;
    vec4 pos = texture2D( texturePosition, uv );
    vec4 vel = texture2D( textureVelocity, uv );
    pos.xyz += vel.xyz * uDelta;
    gl_FragColor = pos;
  }
`

// Compute shader: forces -> velocity. uForceMode selects the active effect.
export const velocityShader = /* glsl */ `
  uniform float uDelta;
  uniform float uTime;
  uniform float uSpread;     // target sphere-shell radius
  uniform float uCore;       // inner radius
  uniform int   uForceMode;  // 0 none .. see effects.ts FORCE_MODE
  uniform vec3  uForceCenter;
  uniform vec3  uForceVector;
  uniform float uForceRadius;
  uniform float uForceStrength;

  // deterministic per-particle pseudo-random target on a sphere shell
  vec3 targetFor(vec2 uv) {
    float n1 = fract(sin(dot(uv, vec2(12.9898, 78.233))) * 43758.5453);
    float n2 = fract(sin(dot(uv, vec2(39.3468, 11.135))) * 24634.6345);
    float n3 = fract(sin(dot(uv, vec2(73.156, 52.235))) * 91237.1234);
    float r = uCore + uSpread * pow(n3, 0.5);
    float theta = n1 * 6.28318530718;
    float phi = acos(n2 * 2.0 - 1.0);
    return vec3(
      cos(theta) * sin(phi),
      sin(theta) * sin(phi),
      cos(phi)
    ) * r;
  }

  vec3 tangent(vec3 v) { return normalize(vec3(-v.z, 0.0, v.x)); }

  void main() {
    vec2 uv = gl_FragCoord.xy / resolution.xy;
    vec4 pos = texture2D( texturePosition, uv );
    vec4 vel = texture2D( textureVelocity, uv );

    // base: spring toward procedural target
    vec3 target = targetFor(uv);
    vec3 toTarget = target - pos.xyz;
    vel.xyz += toTarget * 0.6 * uDelta;

    // active force
    if (uForceMode != 0) {
      vec3 toC = uForceCenter - pos.xyz;
      float d = length(toC);
      vec3 dir = d > 0.0001 ? toC / d : vec3(0.0);
      float falloff = max(0.0, 1.0 - d / max(uForceRadius, 0.0001));

      if (uForceMode == 1) {            // attract
        vel.xyz += dir * uForceStrength * falloff * uDelta * 60.0;
      } else if (uForceMode == 2) {     // repel
        vel.xyz -= dir * uForceStrength * falloff * uDelta * 60.0;
      } else if (uForceMode == 3) {     // freeze
        vel.xyz *= 0.5;
      } else if (uForceMode == 4) {     // shockwave (one-shot, strength decays CPU-side)
        vel.xyz -= dir * uForceStrength * falloff * uDelta * 60.0;
      } else if (uForceMode == 5) {     // vortex
        vel.xyz += dir * uForceStrength * falloff * uDelta * 30.0;
        vel.xyz += tangent(toC) * uForceStrength * falloff * uDelta * 30.0;
      } else if (uForceMode == 6) {     // orbit
        float ring = uForceRadius;
        vel.xyz += (d > ring ? dir : -dir) * uForceStrength * uDelta * 40.0;
        vel.xyz += tangent(toC) * uForceStrength * uDelta * 40.0;
      } else if (uForceMode == 7) {     // portal
        float ring = uForceRadius;
        if (abs(d - ring) < ring * 0.4) {
          vel.xyz += tangent(toC) * uForceStrength * uDelta * 40.0;
        } else {
          vel.xyz += (d > ring ? dir : -dir) * uForceStrength * uDelta * 30.0;
        }
      } else if (uForceMode == 8) {     // beam (along uForceVector)
        vel.xyz += normalize(uForceVector) * uForceStrength * uDelta * 40.0;
      } else if (uForceMode == 9) {     // wave (lateral sweep, one-shot)
        vel.x += uForceVector.x * uForceStrength * uDelta * 40.0;
      } else if (uForceMode == 10) {    // breathe
        vel.xyz += -dir * sin(uTime * 2.5) * uForceStrength * falloff * uDelta * 30.0;
      }
    }

    vel.xyz *= 0.90;  // damping
    gl_FragColor = vel;
  }
`

export const renderVertexShader = /* glsl */ `
  uniform sampler2D texturePosition;
  uniform sampler2D textureVelocity;
  uniform float uHue;
  varying vec3 vColor;

  vec3 hsl2rgb(vec3 c) {
    vec3 rgb = clamp(abs(mod(c.x * 6.0 + vec3(0.0, 4.0, 2.0), 6.0) - 3.0) - 1.0, 0.0, 1.0);
    return c.z + c.y * (rgb - 0.5) * (1.0 - abs(2.0 * c.z - 1.0));
  }

  void main() {
    vec3 pos = texture2D( texturePosition, uv ).xyz;
    float speed = length( texture2D( textureVelocity, uv ).xyz );
    vColor = hsl2rgb(vec3(uHue + speed * 0.02, 0.85, 0.45 + min(speed * 0.1, 0.4)));
    vec4 mv = modelViewMatrix * vec4(pos, 1.0);
    gl_PointSize = 2.0 + 60.0 / max(-mv.z, 1.0);
    gl_Position = projectionMatrix * mv;
  }
`

export const renderFragmentShader = /* glsl */ `
  varying vec3 vColor;
  void main() {
    float d = length(gl_PointCoord - vec2(0.5));
    if (d > 0.5) discard;
    float alpha = (1.0 - d * 2.0);
    gl_FragColor = vec4(vColor, alpha * 0.8);
  }
`
```

- [ ] **Step 2: Write the engine (scaffold: static cloud, no gestures yet)**

Create `marcelo-ui/src/lib/gpgpu/engine.ts`:

```typescript
import * as THREE from 'three'
import { GPUComputationRenderer } from 'three/addons/misc/GPUComputationRenderer.js'
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js'
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js'
import {
  positionShader, velocityShader, renderVertexShader, renderFragmentShader,
} from './shaders'

const SIZE = 256 // grid edge -> SIZE*SIZE particles

let renderer: THREE.WebGLRenderer
let scene: THREE.Scene
let camera: THREE.PerspectiveCamera
let composer: EffectComposer
let gpu: GPUComputationRenderer
let positionVar: any
let velocityVar: any
let renderUniforms: Record<string, THREE.IUniform>
let clock: THREE.Clock
let points: THREE.Points

function fillPositionTexture(tex: THREE.DataTexture): void {
  const data = tex.image.data as Float32Array
  for (let i = 0; i < data.length; i += 4) {
    const r = 10 + Math.random() * 6
    const theta = Math.random() * Math.PI * 2
    const phi = Math.acos(Math.random() * 2 - 1)
    data[i] = r * Math.cos(theta) * Math.sin(phi)
    data[i + 1] = r * Math.sin(theta) * Math.sin(phi)
    data[i + 2] = r * Math.cos(phi)
    data[i + 3] = 1
  }
}

function fillVelocityTexture(tex: THREE.DataTexture): void {
  const data = tex.image.data as Float32Array
  for (let i = 0; i < data.length; i += 4) {
    data[i] = data[i + 1] = data[i + 2] = 0
    data[i + 3] = 1
  }
}

export function init(canvas: HTMLCanvasElement): void {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' })
  renderer.setSize(canvas.clientWidth, canvas.clientHeight)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))

  scene = new THREE.Scene()
  scene.fog = new THREE.FogExp2(0x000000, 0.01)
  camera = new THREE.PerspectiveCamera(60, canvas.clientWidth / canvas.clientHeight, 0.1, 2000)
  camera.position.set(0, 0, 70)

  gpu = new GPUComputationRenderer(SIZE, SIZE, renderer)
  const pos0 = gpu.createTexture()
  const vel0 = gpu.createTexture()
  fillPositionTexture(pos0)
  fillVelocityTexture(vel0)

  positionVar = gpu.addVariable('texturePosition', positionShader, pos0)
  velocityVar = gpu.addVariable('textureVelocity', velocityShader, vel0)
  gpu.setVariableDependencies(positionVar, [positionVar, velocityVar])
  gpu.setVariableDependencies(velocityVar, [positionVar, velocityVar])

  positionVar.material.uniforms.uDelta = { value: 0 }
  Object.assign(velocityVar.material.uniforms, {
    uDelta: { value: 0 }, uTime: { value: 0 },
    uSpread: { value: 18 }, uCore: { value: 8 },
    uForceMode: { value: 0 }, uForceCenter: { value: new THREE.Vector3() },
    uForceVector: { value: new THREE.Vector3() }, uForceRadius: { value: 20 },
    uForceStrength: { value: 0 },
  })

  const err = gpu.init()
  if (err !== null) console.error('GPUComputationRenderer init error:', err)

  // render mesh: one vertex per texel, uv = texel center
  const count = SIZE * SIZE
  const positions = new Float32Array(count * 3)
  const uvs = new Float32Array(count * 2)
  let p = 0
  let u = 0
  for (let y = 0; y < SIZE; y++) {
    for (let x = 0; x < SIZE; x++) {
      positions[p++] = 0; positions[p++] = 0; positions[p++] = 0
      uvs[u++] = (x + 0.5) / SIZE
      uvs[u++] = (y + 0.5) / SIZE
    }
  }
  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  geo.setAttribute('uv', new THREE.BufferAttribute(uvs, 2))

  renderUniforms = {
    texturePosition: { value: null },
    textureVelocity: { value: null },
    uHue: { value: 0.78 },
  }
  const mat = new THREE.ShaderMaterial({
    uniforms: renderUniforms,
    vertexShader: renderVertexShader,
    fragmentShader: renderFragmentShader,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  })
  points = new THREE.Points(geo, mat)
  points.frustumCulled = false
  scene.add(points)

  composer = new EffectComposer(renderer)
  composer.addPass(new RenderPass(scene, camera))
  composer.addPass(new UnrealBloomPass(
    new THREE.Vector2(canvas.clientWidth, canvas.clientHeight), 1.8, 0.4, 0,
  ))

  clock = new THREE.Clock()
  window.addEventListener('resize', onResize)
  animate()
}

function onResize(): void {
  camera.aspect = window.innerWidth / window.innerHeight
  camera.updateProjectionMatrix()
  renderer.setSize(window.innerWidth, window.innerHeight)
  composer.setSize(window.innerWidth, window.innerHeight)
}

function animate(): void {
  requestAnimationFrame(animate)
  const delta = Math.min(clock.getDelta(), 0.05)
  const time = clock.getElapsedTime()

  positionVar.material.uniforms.uDelta.value = delta
  velocityVar.material.uniforms.uDelta.value = delta
  velocityVar.material.uniforms.uTime.value = time

  gpu.compute()
  renderUniforms.texturePosition.value = gpu.getCurrentRenderTarget(positionVar).texture
  renderUniforms.textureVelocity.value = gpu.getCurrentRenderTarget(velocityVar).texture
  composer.render()
}

export function dispose(): void {
  window.removeEventListener('resize', onResize)
  renderer.dispose()
}
```

- [ ] **Step 3: Point ParticleCanvas at the new engine (no gestures yet)**

In `marcelo-ui/src/components/ParticleCanvas.svelte`, change the import and init to the GPGPU engine, removing the CPU engine and the interim adapter:

```svelte
<script lang="ts">
  import { onMount, onDestroy } from 'svelte'
  import * as Engine from '../lib/gpgpu/engine'

  let canvasEl: HTMLCanvasElement

  onMount(() => { Engine.init(canvasEl) })
  onDestroy(() => { Engine.dispose() })
</script>

<canvas
  bind:this={canvasEl}
  style="position:fixed;inset:0;z-index:0;width:100vw;height:100vh;display:block;"
></canvas>
```

- [ ] **Step 4: Manual verify**

Run vite; open `http://localhost:5173`.
Expected: a glowing particle sphere renders at a stable 60fps (check devtools perf). No console errors from `GPUComputationRenderer`.

- [ ] **Step 5: Commit**

```bash
git add marcelo-ui/src/lib/gpgpu/shaders.ts marcelo-ui/src/lib/gpgpu/engine.ts marcelo-ui/src/components/ParticleCanvas.svelte
git commit -m "feat(ui): add GPGPU particle engine scaffold (static cloud)"
```

---

### Task 2: Ambient states as uniforms

**Files:**
- Modify: `marcelo-ui/src/lib/gpgpu/engine.ts`

Port the four ambient states (idle/listening/thinking/speaking) to drive `uSpread`, `uCore`, `uHue`, and bloom — lerped per frame.

- [ ] **Step 1: Add state params + setState + per-frame lerp**

In `engine.ts`, add near the top:

```typescript
type ParticleState = 'idle' | 'listening' | 'thinking' | 'speaking'

const STATE_PARAMS: Record<ParticleState, { hue: number; spread: number; core: number; bloom: number }> = {
  idle:      { hue: 0.78, spread: 18, core: 8, bloom: 1.8 },
  listening: { hue: 0.60, spread: 22, core: 7, bloom: 2.2 },
  thinking:  { hue: 0.12, spread: 26, core: 6, bloom: 2.6 },
  speaking:  { hue: 0.35, spread: 20, core: 8, bloom: 3.0 },
}

let currentState: ParticleState = 'idle'
let bloomPass: UnrealBloomPass

export function setState(state: ParticleState): void {
  if (STATE_PARAMS[state]) currentState = state
}
```

Capture the bloom pass when created (replace the inline `addPass(new UnrealBloomPass(...))` with):

```typescript
  bloomPass = new UnrealBloomPass(
    new THREE.Vector2(canvas.clientWidth, canvas.clientHeight), 1.8, 0.4, 0,
  )
  composer.addPass(bloomPass)
```

In `animate()`, after computing `time`, lerp toward the active state:

```typescript
  const sp = STATE_PARAMS[currentState]
  const vu = velocityVar.material.uniforms
  vu.uSpread.value += (sp.spread - vu.uSpread.value) * 0.02
  vu.uCore.value += (sp.core - vu.uCore.value) * 0.02
  renderUniforms.uHue.value += (sp.hue - renderUniforms.uHue.value) * 0.02
  bloomPass.strength += (sp.bloom - bloomPass.strength) * 0.02
```

- [ ] **Step 2: Manual verify**

Temporarily call `Engine.setState('thinking')` from the console (`window` export not required — use a breakpoint or a temporary button). Expected: the cloud shifts hue/size smoothly. Revert any temporary hook.

- [ ] **Step 3: Commit**

```bash
git add marcelo-ui/src/lib/gpgpu/engine.ts
git commit -m "feat(ui): drive GPGPU ambient states via lerped uniforms"
```

---

### Task 3: Effect catalog (effect name → force mode)

**Files:**
- Create: `marcelo-ui/src/lib/gpgpu/effects.ts`

- [ ] **Step 1: Write the effect map + gesture→effect defaults**

Create `marcelo-ui/src/lib/gpgpu/effects.ts`:

```typescript
import type { WireGestureEvent } from '../gesture-types'

export const FORCE_MODE = {
  none: 0, attract: 1, repel: 2, freeze: 3, shockwave: 4,
  vortex: 5, orbit: 6, portal: 7, beam: 8, wave: 9, breathe: 10,
} as const

export type EffectName = keyof typeof FORCE_MODE

// Built-in gesture -> effect map (Phase 5 config overrides this).
export const GESTURE_EFFECT: Record<string, EffectName> = {
  none: 'none',
  pinch: 'attract',
  swipe: 'wave',
  freeze: 'freeze',
  orbit: 'orbit',
  portal: 'portal',
}

// One-shot effects: their strength decays to 0 after firing.
export const ONE_SHOT: ReadonlySet<EffectName> = new Set<EffectName>(['shockwave', 'wave'])

export interface ResolvedForce {
  mode: number
  center: [number, number, number]   // world space
  vector: [number, number, number]
  radius: number
  strength: number
  oneShot: boolean
}

// Map normalized [0,1] image coords to world space (centered, scaled).
function toWorld(x: number, y: number, z: number): [number, number, number] {
  const SCALE = 60
  return [(x - 0.5) * SCALE, -(y - 0.5) * SCALE, z * SCALE]
}

export function resolveForce(ev: WireGestureEvent): ResolvedForce {
  const effect = GESTURE_EFFECT[ev.gesture] ?? 'none'
  const mode = FORCE_MODE[effect]
  const center = toWorld(ev.params.center.x || 0.5, ev.params.center.y || 0.5, ev.params.center.z)
  const vector: [number, number, number] = [ev.params.vector.x, -ev.params.vector.y, ev.params.vector.z]
  const radius = Math.max(ev.params.radius * 60, 12)
  const strength = effect === 'none' ? 0 : 1.2
  return { mode, center, vector, radius, strength, oneShot: ONE_SHOT.has(effect) }
}
```

- [ ] **Step 2: Smoke check (documented assertion, no runner)**

This pure function is checked at engine init (Task 4 Step 2 adds `console.assert(resolveForce(...).mode === FORCE_MODE.attract)` for a `pinch` event). No standalone test runner is added.

- [ ] **Step 3: Commit**

```bash
git add marcelo-ui/src/lib/gpgpu/effects.ts
git commit -m "feat(ui): add effect catalog and gesture-to-effect mapping"
```

---

### Task 4: Apply gesture forces in the engine

**Files:**
- Modify: `marcelo-ui/src/lib/gpgpu/engine.ts`

- [ ] **Step 1: Add `applyGestureEvent` + force state + decay**

In `engine.ts`, add imports and force state:

```typescript
import { resolveForce, FORCE_MODE, type ResolvedForce } from './effects'
import type { WireGestureEvent } from '../gesture-types'

let activeForce: ResolvedForce | null = null
```

Add the public API:

```typescript
export function applyGestureEvent(ev: WireGestureEvent): void {
  if (ev.phase === 'end' || ev.gesture === 'none') {
    activeForce = null
    return
  }
  activeForce = resolveForce(ev)
}
```

In `animate()`, after the ambient lerp, push the active force into the velocity uniforms and decay one-shots:

```typescript
  const f = activeForce
  if (f) {
    vu.uForceMode.value = f.mode
    vu.uForceCenter.value.set(f.center[0], f.center[1], f.center[2])
    vu.uForceVector.value.set(f.vector[0], f.vector[1], f.vector[2])
    vu.uForceRadius.value = f.radius
    vu.uForceStrength.value += (f.strength - vu.uForceStrength.value) * 0.2
    if (f.oneShot) {
      f.strength = 0                       // decay target to zero after first frame
      if (vu.uForceStrength.value < 0.02) activeForce = null
    }
  } else {
    vu.uForceMode.value = FORCE_MODE.none
    vu.uForceStrength.value += (0 - vu.uForceStrength.value) * 0.2
  }
```

- [ ] **Step 2: Add the documented smoke assertion at the end of `init()`**

```typescript
  console.assert(
    resolveForce({
      gesture: 'pinch', phase: 'start', hands: 1,
      params: { points: [], vector: { x: 0, y: 0, z: 0 }, center: { x: 0.5, y: 0.5, z: 0 }, radius: 0, magnitude: 0 },
      ts: 0,
    } as WireGestureEvent).mode === FORCE_MODE.attract,
    'resolveForce(pinch) should map to attract',
  )
```

- [ ] **Step 3: Manual verify (with a synthetic event)**

Temporarily, in `ParticleCanvas.svelte` `onMount`, call `Engine.applyGestureEvent({ gesture: 'attract'... })` — or wait for Task 5 wiring. Minimum check now: no compile errors via `npx svelte-check`.

- [ ] **Step 4: Commit**

```bash
git add marcelo-ui/src/lib/gpgpu/engine.ts
git commit -m "feat(ui): apply gesture forces to GPGPU sim with one-shot decay"
```

---

### Task 5: Wire gesture events end-to-end + retire CPU engine

**Files:**
- Modify: `marcelo-ui/src/components/ParticleCanvas.svelte`
- Delete: `marcelo-ui/src/lib/particle-engine.ts`
- Delete: `marcelo-ui/src/lib/gesture-engine.ts` (if still present)

- [ ] **Step 1: Connect the WS client to the engine**

Replace `marcelo-ui/src/components/ParticleCanvas.svelte` with:

```svelte
<script lang="ts">
  import { onMount, onDestroy } from 'svelte'
  import * as Engine from '../lib/gpgpu/engine'
  import { connectGestures, disconnectGestures } from '../lib/gesture-client'
  import { updateGestureState } from '../stores/gesture.svelte'

  let canvasEl: HTMLCanvasElement

  onMount(() => {
    Engine.init(canvasEl)
    connectGestures((ev) => {
      updateGestureState(ev)
      Engine.applyGestureEvent(ev)
    })
  })

  onDestroy(() => {
    disconnectGestures()
    Engine.dispose()
  })
</script>

<canvas
  bind:this={canvasEl}
  style="position:fixed;inset:0;z-index:0;width:100vw;height:100vh;display:block;"
></canvas>
```

- [ ] **Step 2: Delete the retired CPU engine and legacy gesture engine**

```bash
git rm marcelo-ui/src/lib/particle-engine.ts
git rm marcelo-ui/src/lib/gesture-engine.ts
```

(If `git rm` reports a file is already gone or untracked, skip it.)

- [ ] **Step 3: Resolve dangling references**

Run: `cd marcelo-ui && npx svelte-check --tsconfig ./tsconfig.json`
Expected: 0 errors. Fix any import of the deleted files (e.g. in `GestureHUD.svelte`, switch any `UnifiedGesture` usage to read `gestureState.gesture` / `gestureState.phase` from the store).

- [ ] **Step 4: Manual end-to-end verify (full stack)**

Start backend (8000), gesture-service (8001), vite (5173). Open the app.
Expected:
- pinch → particles contract toward the hand point (attract);
- swipe → lateral wave sweeps across, then settles;
- freeze → motion damps sharply;
- orbit → particles swirl around the anchor;
- portal → particles form a ring between the hands.
No particles vanish permanently; transitions are smooth; 60fps holds.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(ui): drive GPGPU particles from live gesture events; remove CPU engine"
```

---

### Task 6: Phase close

- [ ] **Step 1: Frontend type check**

Run: `cd marcelo-ui && npx svelte-check --tsconfig ./tsconfig.json`
Expected: 0 errors.

- [ ] **Step 2: Build**

Run: `cd marcelo-ui && npm run build`
Expected: production build succeeds.

- [ ] **Step 3: Regression pass**

Confirm chat, projects, voice still render and function with the new engine mounted.

- [ ] **Step 4: Final commit (if fixes were needed)**

```bash
git add -A
git commit -m "chore(ui): phase 3 type-check/build pass"
```

---

## Self-Review Notes

- **Spec coverage (Phase 3 §):** 3.1 scaffold → Task 1. 3.2 ambient states → Task 2. 3.3 force framework → Task 4. 3.4 effect catalog → Tasks 3 (mapping) + shaders (Task 1 velocity shader implements all 11 modes). 3.5 wire + retire CPU → Task 5.
- **Coordinate handling:** normalized image coords → world via `toWorld()` (`effects.ts`), fixing the Phase 2 interim approximation.
- **One-shot decay:** `shockwave`/`wave` strengths lerp to 0 then clear `activeForce` — handled CPU-side in `animate()`, matching the `phase: 'instant'` contract.
- **Type consistency:** consumes `WireGestureEvent` (Phase 2). Exposes `Engine.init/dispose/setState/applyGestureEvent`. `FORCE_MODE`, `GESTURE_EFFECT`, `resolveForce` are the Phase 5 override points (config supplies bindings later).
- **Deferred:** `explosion`/`beam`/`vortex`/`breathe` exist as force modes but are not in the built-in `GESTURE_EFFECT` map until corresponding gestures/bindings exist (Phase 5). They are reachable, not stubs.

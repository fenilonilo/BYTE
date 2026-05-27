# Gesture + Particle Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the broken dual-motion-system gesture architecture with a unified gesture engine that outputs `UnifiedGestureState` and a modifier-based particle system that eliminates competing motion systems.

**Architecture:** GestureEngine outputs a single `UnifiedGestureState` instead of `{ left, right, bimanual }`. ParticleEngine gains an `applyGesture(state)` function that sets parameter multipliers (`spreadMult`, `coreMult`, `rotMult`, `bloomAdd`) — the existing lerp-to-target animation loop applies them, eliminating velocity-based continuous gestures entirely.

**Tech Stack:** Svelte 5, TypeScript strict, Three.js, MediaPipe Hands, Vite

**Spec:** `docs/superpowers/specs/2026-05-27-gesture-particle-redesign.md`

---

## Task 1: Update `src/lib/types.ts` — add unified gesture types

**Files:**
- Modify: `marcelo-ui/src/lib/types.ts`

- [ ] **Step 1: Add `UnifiedGesture` and `UnifiedGestureState` to types.ts**

Open `marcelo-ui/src/lib/types.ts`. Add these exports BEFORE the existing `HandGesture` line (keep all old types — they are still used by GestureHUD until Task 5):

```typescript
import type { Vector3 } from 'three'

// ─── Unified Gesture (new architecture) ──────────────────────────────────────

export type UnifiedGesture =
  | 'none' | 'pinch' | 'swipe'
  | 'explosion' | 'orbit' | 'freeze' | 'portal'

export interface UnifiedGestureState {
  gesture:      UnifiedGesture
  handCount:    0 | 1 | 2
  swipeSign:    number           // +1 right, -1 left; only meaningful for 'swipe'
  orbitAnchor:  Vector3          // world position of pinch hand; only for 'orbit'
  portalCenter: Vector3          // midpoint between hands; only for 'portal'
  portalRadius: number           // half-distance between hands; only for 'portal'
  phase:        string           // 'idle' | 'contact' | 'blast' | 'sustained' | 'instant'
}

// ─── Legacy gesture types (kept until GestureHUD migrates in Task 5) ─────────
```

Keep the existing `HandGesture`, `BimanualGesture`, `HandState`, `BimanualPattern`, `GestureState` types unchanged for now. Final file should have `UnifiedGesture` and `UnifiedGestureState` at the top, then the legacy block.

- [ ] **Step 2: Commit**

```bash
cd marcelo-ui
git add src/lib/types.ts
git commit -m "feat(ui-v2): add UnifiedGesture + UnifiedGestureState to types"
```

---

## Task 2: Rewrite `src/lib/gesture-engine.ts`

**Files:**
- Modify: `marcelo-ui/src/lib/gesture-engine.ts`

This is a full file replacement. The new engine outputs `UnifiedGestureState` instead of `{ left, right, bimanual }`.

- [ ] **Step 1: Replace gesture-engine.ts with the new implementation**

Replace the entire contents of `marcelo-ui/src/lib/gesture-engine.ts` with:

```typescript
import * as THREE from 'three'
import type { UnifiedGesture, UnifiedGestureState } from './types'

// ─── Config ───────────────────────────────────────────────────────────────────

const PINCH_DIST    = 0.06   // normalized landmark distance (thumb-index)
const PRAYER_DIST   = 15     // world units: hands "touching" threshold
const PRAYER_VEL    = 18     // world units/s separation velocity → blast
const FREEZE_WINDOW = 300    // ms: both fists must close within this window
const ORBIT_HOLD_MS = 500    // ms: pinch must be stable before orbit activates
const HOLD_FRAMES   = 5      // consecutive frames before single-hand gesture commits
const BIMANUAL_HOLD = 3      // consecutive frames before bimanual gesture commits
const MEMORY_FRAMES = 5      // frames of no-hand before committed gesture resets

// ─── Internal types ───────────────────────────────────────────────────────────

type RawGesture = 'pinch' | 'fist' | 'open' | 'none'

interface PerHandInternal {
  worldPos:          THREE.Vector3
  velocity:          THREE.Vector3
  prevPos:           THREE.Vector3
  prevTime:          number
  fistSince:         number | null   // timestamp when fist first detected
  rawGesture:        RawGesture
  detectedThisFrame: boolean
}

// ─── Module state ─────────────────────────────────────────────────────────────

let camera3D: THREE.PerspectiveCamera | null = null
let _mpCamera: any = null

const _hands: Record<'left' | 'right', PerHandInternal> = {
  left:  _emptyHand(),
  right: _emptyHand(),
}

// Smoothing state
let _candidate: UnifiedGesture    = 'none'
let _candidateCount: number       = 0
let _committed: UnifiedGesture    = 'none'
let _noHandCount: number          = 0

// Prayer / explosion state machine
let _prayerPhase: 'none' | 'contact' | 'blast' = 'none'
let _blastExpiresAt: number | null              = null

// Orbit tracking
let _orbitAnchorHand: 'left' | 'right' | null = null
let _orbitAnchorSince: number | null          = null
let _orbitTotalDelta: number                  = 0
let _orbitPrevAngle: number | null            = null

// Freeze tracking
let _lastFistTimes: Record<'left' | 'right', number | null> = { left: null, right: null }
let _freezeExpiresAt: number | null = null

export type GestureCallback = (state: UnifiedGestureState) => void
let _onGesture: GestureCallback | null = null

// ─── Public API ───────────────────────────────────────────────────────────────

export async function init(
  videoEl: HTMLVideoElement,
  camera: THREE.PerspectiveCamera,
  onGesture: GestureCallback,
): Promise<void> {
  camera3D   = camera
  _onGesture = onGesture

  await _loadScript('https://cdn.jsdelivr.net/npm/@mediapipe/hands/hands.js')
  await _loadScript('https://cdn.jsdelivr.net/npm/@mediapipe/camera_utils/camera_utils.js')

  const hands = new (window as any).Hands({
    locateFile: (f: string) => `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${f}`,
  })

  hands.setOptions({
    maxNumHands:           2,
    modelComplexity:       1,
    minDetectionConfidence: 0.7,
    minTrackingConfidence:  0.5,
  })

  hands.onResults(_processResults)

  _mpCamera = new (window as any).Camera(videoEl, {
    onFrame: async () => { await hands.send({ image: videoEl }) },
    width:  320,
    height: 240,
  })
  _mpCamera.start()
}

export function dispose(): void {
  _mpCamera?.stop()
  _mpCamera     = null
  _onGesture    = null
  camera3D      = null
  _prayerPhase  = 'none'
  _blastExpiresAt = null
  _freezeExpiresAt = null
  _hands.left  = _emptyHand()
  _hands.right = _emptyHand()
}

// ─── Result handler ───────────────────────────────────────────────────────────

function _processResults(results: any): void {
  const now = performance.now()

  // Mark both hands as not-detected this frame
  _hands.left.detectedThisFrame  = false
  _hands.right.detectedThisFrame = false

  const lms  = results.multiHandLandmarks  ?? []
  const meta = results.multiHandedness     ?? []

  for (let hi = 0; hi < lms.length; hi++) {
    const landmarks = lms[hi]
    const side: 'left' | 'right' = (meta[hi]?.label ?? 'Right') === 'Left' ? 'left' : 'right'
    const h = _hands[side]

    const raw     = _classifyRaw(landmarks)
    const worldPos = _landmarkToWorld(landmarks[9])
    const dt       = Math.max((now - h.prevTime) / 1000, 0.001)

    h.velocity.set(
      (worldPos.x - h.prevPos.x) / dt,
      (worldPos.y - h.prevPos.y) / dt,
      (worldPos.z - h.prevPos.z) / dt,
    )
    h.worldPos.copy(worldPos)
    h.rawGesture        = raw
    h.detectedThisFrame = true

    // Track fist onset for freeze detection
    if (raw === 'fist') {
      if (_lastFistTimes[side] === null) _lastFistTimes[side] = now
      if (h.fistSince === null) h.fistSince = now
    } else {
      _lastFistTimes[side] = null
      h.fistSince = null
    }

    h.prevPos.copy(worldPos)
    h.prevTime = now
  }

  const handCount = ((_hands.left.detectedThisFrame ? 1 : 0) + (_hands.right.detectedThisFrame ? 1 : 0)) as 0 | 1 | 2

  const rawGesture = _classifyUnified(handCount, now)
  const smoothed   = _smooth(rawGesture, handCount)

  const state = _buildState(smoothed, handCount, now)

  if (_onGesture) _onGesture(state)
}

// ─── Classification ───────────────────────────────────────────────────────────

function _classifyUnified(handCount: 0 | 1 | 2, now: number): UnifiedGesture {
  if (handCount === 0) return 'none'

  // Expire blast
  if (_blastExpiresAt !== null && now >= _blastExpiresAt) {
    _blastExpiresAt = null
    _prayerPhase    = 'none'
  }

  if (handCount === 2) {
    const L = _hands.left
    const R = _hands.right

    // ── 1. FREEZE: both fists within FREEZE_WINDOW ──────────────────────────
    if (L.rawGesture === 'fist' && R.rawGesture === 'fist') {
      const lt = _lastFistTimes.left; const rt = _lastFistTimes.right
      if (lt !== null && rt !== null && Math.abs(lt - rt) < FREEZE_WINDOW) {
        _freezeExpiresAt = now + 3000
        return 'freeze'
      }
    }

    // Sustain freeze until it expires
    if (_freezeExpiresAt !== null && now < _freezeExpiresAt) return 'freeze'
    if (_freezeExpiresAt !== null && now >= _freezeExpiresAt) _freezeExpiresAt = null

    // ── 2. EXPLOSION: prayer contact → fast separation ───────────────────────
    if (_prayerPhase === 'blast' && _blastExpiresAt !== null) return 'explosion'

    if (L.rawGesture === 'open' && R.rawGesture === 'open') {
      const dist = L.worldPos.distanceTo(R.worldPos)
      if (dist < PRAYER_DIST) {
        if (_prayerPhase === 'none') _prayerPhase = 'contact'
        // Check separation velocity
        const sepVel = L.velocity.clone().sub(R.velocity).length()
        if (_prayerPhase === 'contact' && sepVel > PRAYER_VEL) {
          _prayerPhase    = 'blast'
          _blastExpiresAt = now + 600
          return 'explosion'
        }
        return 'none' // contact phase — no gesture yet
      } else {
        if (_prayerPhase === 'contact') _prayerPhase = 'none'
      }
    } else {
      if (_prayerPhase === 'contact') _prayerPhase = 'none'
    }

    // ── 3. ORBIT: one pinch stable ≥ 500ms + other hand circles ≥ 180° ──────
    const pinchSide = L.rawGesture === 'pinch' ? 'left'
                    : R.rawGesture === 'pinch' ? 'right'
                    : null
    const freeSide  = pinchSide === 'left' ? 'right' : pinchSide === 'right' ? 'left' : null

    if (pinchSide && freeSide) {
      if (_orbitAnchorHand !== pinchSide) {
        _orbitAnchorHand  = pinchSide
        _orbitAnchorSince = now
        _orbitTotalDelta  = 0
        _orbitPrevAngle   = null
      }

      if (now - (_orbitAnchorSince ?? now) >= ORBIT_HOLD_MS) {
        const anchor = _hands[pinchSide].worldPos
        const free   = _hands[freeSide].worldPos
        const dx     = free.x - anchor.x
        const dy     = free.y - anchor.y
        const angle  = Math.atan2(dy, dx)

        if (_orbitPrevAngle !== null) {
          let delta = angle - _orbitPrevAngle
          if (delta >  Math.PI) delta -= 2 * Math.PI
          if (delta < -Math.PI) delta += 2 * Math.PI
          _orbitTotalDelta += Math.abs(delta)
        }
        _orbitPrevAngle = angle

        if (_orbitTotalDelta > Math.PI) return 'orbit'
      }
    } else {
      _orbitAnchorHand  = null
      _orbitAnchorSince = null
      _orbitTotalDelta  = 0
      _orbitPrevAngle   = null
    }

    // ── 4. PORTAL: both hands same height, 15–60 world units apart ───────────
    if (
      (L.rawGesture === 'open' || L.rawGesture === 'pinch') &&
      (R.rawGesture === 'open' || R.rawGesture === 'pinch')
    ) {
      const dist  = L.worldPos.distanceTo(R.worldPos)
      const yDiff = Math.abs(L.worldPos.y - R.worldPos.y)
      if (dist >= 15 && dist <= 60 && yDiff < 10) return 'portal'
    }

    return 'none'
  }

  // ── Single hand ──────────────────────────────────────────────────────────────
  const active = _hands.left.detectedThisFrame ? _hands.left : _hands.right

  if (active.rawGesture === 'pinch') return 'pinch'

  if (active.rawGesture === 'open') {
    // Swipe: horizontal velocity exceeds threshold
    if (Math.abs(active.velocity.x) > PRAYER_VEL) return 'swipe'
  }

  return 'none'
}

function _smooth(raw: UnifiedGesture, handCount: 0 | 1 | 2): UnifiedGesture {
  const holdFrames = handCount === 2 ? BIMANUAL_HOLD : HOLD_FRAMES

  if (handCount === 0) {
    _noHandCount++
    if (_noHandCount > MEMORY_FRAMES) {
      _committed      = 'none'
      _candidate      = 'none'
      _candidateCount = 0
    }
    return _committed
  }

  _noHandCount = 0

  if (raw === _candidate) {
    _candidateCount = Math.min(_candidateCount + 1, holdFrames + 1)
  } else {
    _candidate      = raw
    _candidateCount = 1
  }

  if (_candidateCount >= holdFrames) _committed = raw
  return _committed
}

function _buildState(gesture: UnifiedGesture, handCount: 0 | 1 | 2, now: number): UnifiedGestureState {
  let swipeSign    = 0
  let orbitAnchor  = new THREE.Vector3()
  let portalCenter = new THREE.Vector3()
  let portalRadius = 0
  let phase        = 'idle'

  switch (gesture) {
    case 'swipe': {
      const active = _hands.left.detectedThisFrame ? _hands.left : _hands.right
      swipeSign = Math.sign(active.velocity.x)
      phase     = 'instant'
      break
    }
    case 'explosion':
      phase = _prayerPhase === 'blast' ? 'blast' : 'contact'
      break
    case 'orbit': {
      if (_orbitAnchorHand) orbitAnchor.copy(_hands[_orbitAnchorHand].worldPos)
      phase = 'sustained'
      break
    }
    case 'portal': {
      portalCenter = _hands.left.worldPos.clone().add(_hands.right.worldPos).multiplyScalar(0.5)
      portalRadius = _hands.left.worldPos.distanceTo(_hands.right.worldPos) * 0.5
      phase        = 'sustained'
      break
    }
    case 'freeze':
      phase = 'instant'
      break
    case 'pinch':
      phase = 'sustained'
      break
    default:
      phase = 'idle'
  }

  return { gesture, handCount, swipeSign, orbitAnchor, portalCenter, portalRadius, phase }
}

// ─── Landmark helpers ─────────────────────────────────────────────────────────

function _classifyRaw(lm: any[]): RawGesture {
  const thumbTip  = lm[4]; const indexTip  = lm[8]
  const middleTip = lm[12]; const ringTip  = lm[16]; const pinkyTip = lm[20]

  if (_dist(thumbTip, indexTip) < PINCH_DIST) return 'pinch'

  const indexCurled  = indexTip.y  > lm[6].y
  const middleCurled = middleTip.y > lm[10].y
  const ringCurled   = ringTip.y   > lm[14].y
  const pinkyCurled  = pinkyTip.y  > lm[18].y

  if (indexCurled && middleCurled && ringCurled && pinkyCurled) return 'fist'

  if (!indexCurled && !middleCurled && !ringCurled && !pinkyCurled) return 'open'

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
    worldPos:          new THREE.Vector3(),
    velocity:          new THREE.Vector3(),
    prevPos:           new THREE.Vector3(),
    prevTime:          performance.now(),
    fistSince:         null,
    rawGesture:        'none',
    detectedThisFrame: false,
  }
}
```

- [ ] **Step 2: Verify file compiles**

```bash
cd marcelo-ui
npx tsc --noEmit 2>&1 | head -30
```

Expected: zero errors from `gesture-engine.ts`. There may be type errors in other files (`ParticleCanvas.svelte`, `gesture.svelte.ts`) because they still use the old `GestureState` type — those are fixed in Tasks 4-5.

- [ ] **Step 3: Commit**

```bash
git add src/lib/gesture-engine.ts
git commit -m "feat(ui-v2): rewrite gesture-engine with unified output + priority classification"
```

---

## Task 3: Add `applyGesture()` + modifier system to `src/lib/particle-engine.ts`

**Files:**
- Modify: `marcelo-ui/src/lib/particle-engine.ts`

Add the new `applyGesture` API and modifier system WITHOUT removing the old exports (`setGlobalGesture`, `clearGlobalGesture`, `applyHandForce`, `clearHandForce`). The old `_globalGesture` velocity code stays in `_animate` temporarily — it becomes dead code once `ParticleCanvas.svelte` stops calling it, but removing it now would break the current component. Task 6 cleans it up.

- [ ] **Step 1: Add GestureModifier interface and GESTURE_MODIFIERS after the imports**

In `marcelo-ui/src/lib/particle-engine.ts`, add this block right after the `import type { ParticleState } from './types'` line (line 6):

```typescript
import type { UnifiedGesture, UnifiedGestureState } from './types'
```

- [ ] **Step 2: Add modifier state variables after the `frozenUntil` variable**

Find the line `let frozenUntil = 0` (around line 82) and add after it:

```typescript
// ─── Gesture modifier system ──────────────────────────────────────────────────

interface GestureModifier {
  spreadMult: number
  coreMult:   number
  rotMult:    number
  bloomAdd:   number
}

const GESTURE_MODIFIERS: Record<UnifiedGesture, GestureModifier> = {
  none:      { spreadMult: 1.0, coreMult: 1.0, rotMult: 1.0, bloomAdd: 0.0 },
  pinch:     { spreadMult: 0.1, coreMult: 0.2, rotMult: 0.5, bloomAdd: 0.3 },
  swipe:     { spreadMult: 1.2, coreMult: 1.0, rotMult: 4.0, bloomAdd: 0.5 },
  freeze:    { spreadMult: 1.0, coreMult: 1.0, rotMult: 0.0, bloomAdd: 0.0 },
  orbit:     { spreadMult: 0.8, coreMult: 0.8, rotMult: 2.0, bloomAdd: 0.4 },
  portal:    { spreadMult: 0.6, coreMult: 0.6, rotMult: 1.5, bloomAdd: 0.6 },
  explosion: { spreadMult: 1.0, coreMult: 1.0, rotMult: 1.0, bloomAdd: 0.0 },
}

let _targetMod: GestureModifier = { ...GESTURE_MODIFIERS.none }
let _activeMod: GestureModifier = { ...GESTURE_MODIFIERS.none }

// One-shot guards — prevent multi-fire within a single gesture hold
let _blastFired:  boolean = false
let _swipeFired:  boolean = false
let _freezeFired: boolean = false
```

- [ ] **Step 3: Add `applyGesture()` function in the Public API section**

Find the line `export function clearBreath(): void {` and add after the entire `clearBreath` function:

```typescript
/** Apply a unified gesture state: sets modifier targets and fires one-shot effects. */
export function applyGesture(state: UnifiedGestureState): void {
  _targetMod = GESTURE_MODIFIERS[state.gesture] ?? GESTURE_MODIFIERS.none

  // ONE-SHOT: explosion blast (fires once per blast phase entry)
  if (state.gesture === 'explosion') {
    if (!_blastFired && state.phase === 'blast') {
      shockwave(new THREE.Vector3(0, 0, 0), 80, 10)
      _blastFired = true
    }
  } else {
    _blastFired = false
  }

  // ONE-SHOT: swipe wave (fires once per swipe gesture commit)
  if (state.gesture === 'swipe') {
    if (!_swipeFired) {
      activeEffects.push({
        type: 'wave',
        origin: new THREE.Vector3(0, 0, 0),
        dirSign: state.swipeSign >= 0 ? 1 : -1,
        speed: 3,
      })
      _swipeFired = true
    }
  } else {
    _swipeFired = false
  }

  // ONE-SHOT: freeze (fires crystallize once per freeze gesture commit)
  if (state.gesture === 'freeze') {
    if (!_freezeFired) {
      crystallize(3000)
      _freezeFired = true
    }
  } else {
    _freezeFired = false
  }

  // PERSISTENT: orbit (update or remove)
  const orbitIdx = activeEffects.findIndex(e => e.type === 'orbit')
  if (state.gesture === 'orbit') {
    if (orbitIdx >= 0) activeEffects.splice(orbitIdx, 1)
    activeEffects.push({ type: 'orbit', origin: state.orbitAnchor.clone(), radius: 20 })
  } else if (orbitIdx >= 0) {
    activeEffects.splice(orbitIdx, 1)
  }

  // PERSISTENT: portal (update or remove)
  const portalIdx = activeEffects.findIndex(e => e.type === 'portal')
  if (state.gesture === 'portal') {
    if (portalIdx >= 0) activeEffects.splice(portalIdx, 1)
    activeEffects.push({ type: 'portal', origin: state.portalCenter.clone(), radius: state.portalRadius })
  } else if (portalIdx >= 0) {
    activeEffects.splice(portalIdx, 1)
  }
}
```

- [ ] **Step 4: Apply modifier lerp in `_animate` — step A: add lerp block after `smoothAmp` update**

Find this line in `_animate` (around line 356):
```typescript
  smoothAmp += (uAmplitude - smoothAmp) * 0.1
  if (!frozen) bloomPass.strength = currentBloom + smoothAmp * 1.5
```

Replace with:
```typescript
  smoothAmp += (uAmplitude - smoothAmp) * 0.1

  // Lerp active modifier toward target
  const mLerp = 0.05
  _activeMod.spreadMult += (_targetMod.spreadMult - _activeMod.spreadMult) * mLerp
  _activeMod.coreMult   += (_targetMod.coreMult   - _activeMod.coreMult)   * mLerp
  _activeMod.rotMult    += (_targetMod.rotMult    - _activeMod.rotMult)    * mLerp
  _activeMod.bloomAdd   += (_targetMod.bloomAdd   - _activeMod.bloomAdd)   * mLerp

  if (!frozen) bloomPass.strength = currentBloom + _activeMod.bloomAdd + smoothAmp * 1.5
```

- [ ] **Step 5: Apply modifier to rotT computation**

Find this line in `_animate`:
```typescript
  const t    = time * 1.086
  const rotT = t * currentRot
```

Replace with:
```typescript
  const t    = time * 1.086
  const rotT = t * currentRot * _activeMod.rotMult
```

- [ ] **Step 6: Apply modifier to `currentRadius` computation in the particle loop**

Find this block inside the particle loop (around line 390):
```typescript
    const radiusDist    = Math.pow(n3, 5.0)
    const currentRadius = currentCore + currentSpread * radiusDist
```

Replace with:
```typescript
    const radiusDist    = Math.pow(n3, 5.0)
    const effCore       = currentCore   * _activeMod.coreMult
    const effSpread     = currentSpread * _activeMod.spreadMult
    const currentRadius = effCore + effSpread * radiusDist
```

- [ ] **Step 7: Verify the file still compiles**

```bash
cd marcelo-ui
npx tsc --noEmit 2>&1 | head -30
```

Expected: no new errors from `particle-engine.ts`. (Errors in other files from old gesture types are fine — fixed in Tasks 4-5.)

- [ ] **Step 8: Commit**

```bash
git add src/lib/particle-engine.ts
git commit -m "feat(ui-v2): add applyGesture() + GestureModifier system to particle-engine"
```

---

## Task 4: Update gesture store + thin ParticleCanvas bridge

**Files:**
- Modify: `marcelo-ui/src/stores/gesture.svelte.ts`
- Modify: `marcelo-ui/src/components/ParticleCanvas.svelte`

- [ ] **Step 1: Replace gesture store with UnifiedGestureState**

Replace the entire contents of `marcelo-ui/src/stores/gesture.svelte.ts` with:

```typescript
import * as THREE from 'three'
import type { UnifiedGestureState } from '../lib/types'

export const gestureState = $state<UnifiedGestureState>({
  gesture:      'none',
  handCount:    0,
  swipeSign:    0,
  orbitAnchor:  new THREE.Vector3(),
  portalCenter: new THREE.Vector3(),
  portalRadius: 0,
  phase:        'idle',
})

export function updateGestureState(next: UnifiedGestureState): void {
  gestureState.gesture      = next.gesture
  gestureState.handCount    = next.handCount
  gestureState.swipeSign    = next.swipeSign
  gestureState.orbitAnchor  = next.orbitAnchor
  gestureState.portalCenter = next.portalCenter
  gestureState.portalRadius = next.portalRadius
  gestureState.phase        = next.phase
}
```

- [ ] **Step 2: Replace ParticleCanvas.svelte with the thin bridge**

Replace the entire contents of `marcelo-ui/src/components/ParticleCanvas.svelte` with:

```svelte
<script lang="ts">
  import { onMount, onDestroy } from 'svelte'
  import * as ParticleEngine from '../lib/particle-engine'
  import * as GestureEngine from '../lib/gesture-engine'
  import { updateGestureState } from '../stores/gesture.svelte'

  let canvasEl: HTMLCanvasElement
  let videoEl: HTMLVideoElement

  onMount(async () => {
    ParticleEngine.init(canvasEl)
    await GestureEngine.init(videoEl, ParticleEngine.getCamera(), (state) => {
      updateGestureState(state)
      ParticleEngine.applyGesture(state)
    })
  })

  onDestroy(() => {
    GestureEngine.dispose()
    ParticleEngine.dispose()
  })
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

- [ ] **Step 3: Run typecheck — expect remaining errors only in GestureHUD.svelte**

```bash
cd marcelo-ui
npx tsc --noEmit 2>&1
```

Expected errors: only `src/components/GestureHUD.svelte` will complain about `GestureState` / `BimanualGesture` / `HandGesture` from the old store shape — that is fixed in Task 5. All other files should be clean.

If there are errors elsewhere, fix them before committing.

- [ ] **Step 4: Commit**

```bash
git add src/stores/gesture.svelte.ts src/components/ParticleCanvas.svelte
git commit -m "feat(ui-v2): update gesture store + thin ParticleCanvas bridge"
```

---

## Task 5: Adapt `GestureHUD.svelte` to `UnifiedGestureState`

**Files:**
- Modify: `marcelo-ui/src/components/GestureHUD.svelte`

- [ ] **Step 1: Replace GestureHUD.svelte**

Replace the entire contents of `marcelo-ui/src/components/GestureHUD.svelte` with:

```svelte
<script lang="ts">
  import { onDestroy } from 'svelte'
  import { gestureState } from '../stores/gesture.svelte'
  import type { UnifiedGesture } from '../lib/types'

  // Freeze countdown
  let freezeCountdown = $state(0)
  let _freezeInterval: ReturnType<typeof setInterval> | null = null

  // Badge visible timer
  let badgeVisible = $state(false)
  let _badgeTimer: ReturnType<typeof setTimeout> | null = null

  const LABELS: Record<UnifiedGesture, string> = {
    none:      '',
    pinch:     '👌 PINCH',
    swipe:     '🌊 ONDA',
    explosion: '🙏 EXPLOSÃO',
    orbit:     '🌌 ÓRBITA',
    freeze:    '❄️ CONGELAR',
    portal:    '🔮 PORTAL',
  }

  $effect(() => {
    const g = gestureState.gesture
    if (g === 'none') { badgeVisible = false; return }

    badgeVisible = true
    _badgeTimer && clearTimeout(_badgeTimer)
    _badgeTimer = setTimeout(() => { badgeVisible = false }, 1500)

    // Start freeze countdown
    if (g === 'freeze' && !_freezeInterval) {
      freezeCountdown = 3
      _freezeInterval = setInterval(() => {
        freezeCountdown = Math.max(0, freezeCountdown - 1)
        if (freezeCountdown <= 0) {
          clearInterval(_freezeInterval!)
          _freezeInterval = null
        }
      }, 1000)
    }
    // Reset freeze countdown if gesture changed away from freeze
    if (g !== 'freeze' && _freezeInterval) {
      clearInterval(_freezeInterval)
      _freezeInterval = null
      freezeCountdown = 0
    }
  })

  onDestroy(() => {
    _badgeTimer   && clearTimeout(_badgeTimer)
    _freezeInterval && clearInterval(_freezeInterval)
  })
</script>

<!-- Freeze ice overlay -->
{#if gestureState.gesture === 'freeze'}
  <div style="
    position:fixed;inset:0;z-index:25;pointer-events:none;
    background:rgba(150,220,255,0.04);
    animation:iceIn 400ms ease;
  "></div>
{/if}

<!-- Gesture badge -->
{#if badgeVisible && gestureState.gesture !== 'none'}
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
    display:flex;gap:8px;align-items:center;
  ">
    {LABELS[gestureState.gesture]}

    {#if gestureState.gesture === 'swipe'}
      <span>{gestureState.swipeSign >= 0 ? '→' : '←'}</span>
    {/if}

    {#if gestureState.gesture === 'orbit'}
      <span style="opacity:0.6;font-size:9px;">âncora ativa</span>
    {/if}

    {#if gestureState.gesture === 'portal'}
      <span style="opacity:0.6;font-size:9px;">r={Math.round(gestureState.portalRadius)}</span>
    {/if}

    {#if gestureState.gesture === 'freeze' && freezeCountdown > 0}
      <span style="opacity:0.6;font-size:9px;">{freezeCountdown}s</span>
    {/if}

    {#if gestureState.handCount > 0}
      <span style="
        background:rgba(255,255,255,0.1);border-radius:10px;
        padding:1px 6px;font-size:9px;opacity:0.7;
      ">{gestureState.handCount}✋</span>
    {/if}
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

- [ ] **Step 2: Run full typecheck — should be zero errors**

```bash
cd marcelo-ui
npx tsc --noEmit 2>&1
```

Expected: no errors.

- [ ] **Step 3: Run svelte-check**

```bash
cd marcelo-ui
npx svelte-check --tsconfig tsconfig.json 2>&1 | tail -10
```

Expected: `0 errors` and `0 warnings` (or warnings only from node_modules).

- [ ] **Step 4: Commit**

```bash
git add src/components/GestureHUD.svelte
git commit -m "feat(ui-v2): adapt GestureHUD to UnifiedGestureState with PT-BR labels"
```

---

## Task 6: Cleanup + full build verification

**Files:**
- Modify: `marcelo-ui/src/lib/types.ts` — remove old gesture types
- Modify: `marcelo-ui/src/lib/particle-engine.ts` — remove old gesture API (`setGlobalGesture`, `clearGlobalGesture`, `applyHandForce`, `clearHandForce`, `_globalGesture`, `_globalOrigin`)

- [ ] **Step 1: Remove old gesture types from types.ts**

In `marcelo-ui/src/lib/types.ts`, remove the entire legacy block:

```typescript
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
```

Also remove the `// ─── Legacy gesture types...` comment added in Task 1.

Also remove the `import type { Vector3 } from 'three'` line if it is no longer needed (it IS needed for `UnifiedGestureState.orbitAnchor` — keep it).

- [ ] **Step 2: Remove old gesture API from particle-engine.ts**

In `marcelo-ui/src/lib/particle-engine.ts`:

**Remove** these module-level variables (around line 70-75):
```typescript
// Hand state
let handActive   = false
let handPos      = new THREE.Vector3()
let handGesture  = 'none'
let handVelocity = new THREE.Vector3()

// Global gesture state (replaces hand-cursor approach for continuous gestures)
let _globalGesture: 'none' | 'attract' | 'repel' | 'breathe' = 'none'
let _globalOrigin  = new THREE.Vector3()  // center of effect (default scene origin)
```

**Remove** these exported functions:
```typescript
export function applyHandForce(worldPos: THREE.Vector3, gesture: string, velocity: THREE.Vector3): void { ... }
export function clearHandForce(): void { ... }
export function setGlobalGesture(type: 'none' | 'attract' | 'repel' | 'breathe', origin?: THREE.Vector3): void { ... }
export function clearGlobalGesture(): void { ... }
```

**Remove** the hand-force block from `_animate` (inside the particle loop, around lines 437-451):
```typescript
    // ── Hand force (KEEP for legacy mouse drag / beam direction) ─────────────
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
```

**Remove** the global gesture block from `_animate` (around lines 411-434):
```typescript
    // ── Global gesture (affects all particles from _globalOrigin) ──────────
    if (_globalGesture !== 'none') {
      const fromOrigin = positions[i].clone().sub(_globalOrigin)
      const d = fromOrigin.length() + 0.01  // avoid div-by-zero
      switch (_globalGesture) {
        case 'attract': { ... }
        case 'repel':   { ... }
        case 'breathe': { ... }
      }
    }
```

Also remove the `HAND_RADIUS` constant if it is now unused:
```typescript
const HAND_RADIUS = 25
```

Also remove the `dispose()` line that references `_globalGesture`:
```typescript
  _globalGesture = 'none'
```

- [ ] **Step 3: Run typecheck — must be zero errors**

```bash
cd marcelo-ui
npx tsc --noEmit 2>&1
```

Expected: zero errors. If there are errors, fix them before proceeding.

- [ ] **Step 4: Run svelte-check — must be zero errors**

```bash
cd marcelo-ui
npx svelte-check --tsconfig tsconfig.json 2>&1 | tail -20
```

Expected: `0 errors`.

- [ ] **Step 5: Run build**

```bash
cd marcelo-ui
npm run build 2>&1 | tail -20
```

Expected: `built in X.XXs` with no errors.

- [ ] **Step 6: Commit cleanup**

```bash
git add src/lib/types.ts src/lib/particle-engine.ts
git commit -m "refactor(ui-v2): remove legacy gesture API from types + particle-engine"
```

---

## Success Criteria

After all 6 tasks:

- `pinch` → visible particle contraction toward center; release → natural expansion back
- `swipe` → visible directional wave sweeping particles left or right
- `explosion` → bloom flash + particle burst from center
- `freeze` → particles crystallize to ice blue for 3s; HUD shows countdown
- `orbit` → particles orbit anchor point while one hand holds pinch
- `portal` → particles orbit ring between hands
- No gesture causes particles to disappear or fly off-screen permanently
- Gesture transitions are smooth (no pop/flash between gestures)
- No competing motion systems (no velocity-impulse globals for continuous gestures)
- `tsc --noEmit`: 0 errors
- `svelte-check`: 0 errors
- `npm run build`: succeeds

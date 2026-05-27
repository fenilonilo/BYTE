# Gesture + Particle System Redesign

**Date:** 2026-05-27  
**Branch:** `feat/ui-v2-svelte`  
**Status:** Approved — ready for implementation

---

## Problem

The current gesture→particle system has three root failures:

1. **Two competing motion systems:** `applyHandForce` adds velocity impulses while the animation loop simultaneously lerps every particle to a natural target position. They fight each other, producing chaotic motion or no visible effect.
2. **Wrong force magnitudes:** `attract` collapses all particles to a single invisible point; `repel` at close range produces force of 480 units/frame, blasting particles off-screen permanently.
3. **Split architecture:** `GestureEngine` emits `{ left, right, bimanual }` and `ParticleCanvas` runs a 200-line switch to interpret it. Two separate mental models for what is one concern.

---

## Gesture Set

### Single hand (1 hand detected)
| Gesture | Trigger |
|---------|---------|
| `pinch` | Thumb + index close (distance < 0.06 normalized) |
| `swipe` | Open hand, fast horizontal movement (vx > 0.8 * 60 world/s) |

### Two hands (2 hands detected) — priority order
| Gesture | Trigger | Priority |
|---------|---------|----------|
| `freeze` | Both fists within 300ms | 1 (highest) |
| `explosion` | Prayer contact → fast separation (vel > 0.3 * 60) | 2 |
| `orbit` | One pinch stable ≥ 500ms + other hand circles | 3 |
| `portal` | Both hands at same height, 10–60 world units apart, open or pinch | 4 |

**Removed gestures:** open/repel, fist/burst, implosion, dual-pinch, point/beam.

---

## Architecture

### 1. GestureEngine — unified output

**File:** `src/lib/gesture-engine.ts`

**Output type:**
```typescript
type UnifiedGesture =
  | 'none' | 'pinch' | 'swipe'
  | 'explosion' | 'orbit' | 'freeze' | 'portal'

interface UnifiedGestureState {
  gesture:     UnifiedGesture
  handCount:   0 | 1 | 2
  swipeSign:   number          // +1 right, -1 left (only meaningful for swipe)
  orbitAnchor: THREE.Vector3   // world pos of pinch hand (only for orbit)
  portalCenter: THREE.Vector3  // midpoint between hands (only for portal)
  portalRadius: number         // half-distance between hands (only for portal)
  phase:       string          // 'idle' | 'contact' | 'blast' | 'sustained' | 'instant'
}
```

**Classification logic:**
```
handCount = 0 → gesture = 'none'
handCount = 1 → classify single-hand (pinch → swipe → none)
handCount = 2 → classify bimanual priority order:
                  freeze → explosion → orbit → portal → none
```

**Smoothing:**
- 5-frame hold: new gesture only commits after 5 consecutive frames
- 5-frame memory: if hand disappears ≤ 5 frames, hold last gesture (prevents MediaPipe miss flicker)
- Bimanual gestures: 3-frame hold (faster response for two-hand triggers)

**Removed from GestureEngine:** `BimanualPattern`, `HandState`, `HandGesture` types (replaced by `UnifiedGestureState`). Internal landmark processing unchanged.

---

### 2. ParticleEngine — gesture modifier system

**File:** `src/lib/particle-engine.ts`

**Core change:** gestures modify `spread`, `core`, `rotSpeed`, `bloom` parameters. The existing single lerp-to-target motion system handles all particle movement. No velocity impulses for continuous gestures.

**Modifier presets:**
```typescript
interface GestureModifier {
  spreadMult: number  // multiplier on currentSpread
  coreMult:   number  // multiplier on currentCore
  rotMult:    number  // multiplier on currentRotSpeed
  bloomAdd:   number  // additive bloom boost
}

const GESTURE_MODIFIERS: Record<UnifiedGesture, GestureModifier> = {
  none:      { spreadMult: 1.0, coreMult: 1.0, rotMult: 1.0, bloomAdd: 0.0 },
  pinch:     { spreadMult: 0.1, coreMult: 0.2, rotMult: 0.5, bloomAdd: 0.3 },
  swipe:     { spreadMult: 1.2, coreMult: 1.0, rotMult: 4.0, bloomAdd: 0.5 },
  freeze:    { spreadMult: 1.0, coreMult: 1.0, rotMult: 0.0, bloomAdd: 0.0 },
  orbit:     { spreadMult: 0.8, coreMult: 0.8, rotMult: 2.0, bloomAdd: 0.4 },
  portal:    { spreadMult: 0.6, coreMult: 0.6, rotMult: 1.5, bloomAdd: 0.6 },
  explosion: { spreadMult: 1.0, coreMult: 1.0, rotMult: 1.0, bloomAdd: 0.0 }, // bloom handled by shockwave() one-shot (spikes to 6.0 for 400ms), not modifier
}
```

**Active modifier lerp (in `_animate`):**
```typescript
// Smooth transition between modifiers (rate 0.05 per frame)
activeMod.spreadMult += (targetMod.spreadMult - activeMod.spreadMult) * 0.05
activeMod.coreMult   += (targetMod.coreMult   - activeMod.coreMult)   * 0.05
activeMod.rotMult    += (targetMod.rotMult    - activeMod.rotMult)    * 0.05
activeMod.bloomAdd   += (targetMod.bloomAdd   - activeMod.bloomAdd)   * 0.05

// Applied to target computation
effectiveSpread = currentSpread * activeMod.spreadMult
effectiveCore   = currentCore   * activeMod.coreMult
effectiveRot    = currentRot    * activeMod.rotMult
bloomPass.strength = currentBloom + activeMod.bloomAdd + smoothAmp * 1.5
```

**One-shot / velocity effects (unchanged physics, called once):**
- `explosion` blast: `shockwave(origin=(0,0,0), radius=80, force=10)` — fires once per phase transition to `'blast'` (detected when previous phase ≠ `'blast'` and current phase = `'blast'`; a boolean guard `_blastFired` is reset when phase leaves `'blast'`)
- `swipe`: `lateralWave(sign, speed)` — 1-frame impulse, affects all particles
- `freeze`: `crystallize(3000)` — existing logic unchanged
- `orbit`: `orbitAnchor(pos, radius)` — existing activeEffects[] logic unchanged
- `portal`: `portalRing(center, radius)` — existing activeEffects[] logic unchanged

**New public API:**
```typescript
export function applyGesture(state: UnifiedGestureState): void
```
Replaces: `setGlobalGesture`, `clearGlobalGesture`, `applyHandForce`, `clearHandForce`, `setGestureModifier`.

**Removed from ParticleEngine:** `setGlobalGesture`, `clearGlobalGesture`, `applyHandForce`, `clearHandForce`, `_globalGesture`, `_globalOrigin`.

---

### 3. ParticleCanvas — thin bridge

**File:** `src/components/ParticleCanvas.svelte`

Reduced to ~40 lines. All gesture logic moves to engine and gesture-engine.

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

<canvas bind:this={canvasEl} style="position:fixed;inset:0;z-index:0;width:100vw;height:100vh;" />
<video bind:this={videoEl} autoplay playsinline muted
  style="position:fixed;top:-9999px;left:-9999px;width:320px;height:240px;" />
```

---

### 4. Types — updated

**File:** `src/lib/types.ts`

Add:
```typescript
export type UnifiedGesture =
  | 'none' | 'pinch' | 'swipe'
  | 'explosion' | 'orbit' | 'freeze' | 'portal'

export interface UnifiedGestureState {
  gesture:      UnifiedGesture
  handCount:    0 | 1 | 2
  swipeSign:    number
  orbitAnchor:  Vector3
  portalCenter: Vector3
  portalRadius: number
  phase:        string
}
```

Remove: `HandGesture`, `BimanualGesture`, `HandState`, `BimanualPattern`, `GestureState`.

**GestureHUD.svelte** adapts to display `UnifiedGestureState`:
- Always: gesture name (PT-BR label) + handCount badge
- `swipe`: show direction arrow (← or →) based on `swipeSign`
- `orbit`: show "âncora ativa" label
- `portal`: show radius value
- `freeze`: show 3s countdown timer
- Non-applicable fields hidden per gesture

---

## Files Changed

| File | Change |
|------|--------|
| `src/lib/types.ts` | Add `UnifiedGesture`, `UnifiedGestureState`; remove old gesture types |
| `src/lib/gesture-engine.ts` | Rewrite: unified output, 5-frame smoothing+memory, priority logic |
| `src/lib/particle-engine.ts` | Add `applyGesture()`, modifier system; remove global gesture API |
| `src/components/ParticleCanvas.svelte` | Reduce to ~40-line bridge |
| `src/components/GestureHUD.svelte` | Adapt display to `UnifiedGestureState` |
| `src/stores/gesture.svelte.ts` | Update store type to `UnifiedGestureState` |

---

## Success Criteria

- `pinch` → particles visibly contract toward center; release → natural expansion back
- `swipe` → visible directional wave sweeping particles
- `explosion` → visible bloom flash + particle burst from center
- `freeze` → particles crystallize to ice blue for 3s
- `orbit` → particles orbit anchor point while one hand holds pinch
- `portal` → particles orbit ring between hands
- No gesture causes particles to disappear or fly off-screen permanently
- Gesture transitions are smooth (no pop/flash between gestures)
- No competing motion systems

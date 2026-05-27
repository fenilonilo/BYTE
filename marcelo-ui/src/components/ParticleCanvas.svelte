<script lang="ts">
  import { onMount, onDestroy } from 'svelte'
  import * as THREE from 'three'
  import * as ParticleEngine from '../lib/particle-engine'
  import * as GestureEngine from '../lib/gesture-engine'
  import { updateGestureState } from '../stores/gesture.svelte'
  import type { GestureState } from '../lib/types'
  import {
    shockwave, vortex, orbitAnchor, crystallize,
    splitField, clearSplitField, portalRing, clearPortal,
    directionalBeam, clearBeam, lateralWave, clearBreath,
    applyHandForce, clearHandForce,
    setGlobalGesture, clearGlobalGesture,
  } from '../lib/particle-engine'

  // Module-level guard: tracks which hands have already fired the fist burst this gesture
  const _fistBurstFired = new Set<'left' | 'right'>()

  // Module-level guard: prevents prayer-explosion shockwave from stacking across frames
  let _blastShockwaveFired = false

  // Gesture smoothing: require N consecutive frames before committing
  const GESTURE_HOLD_FRAMES = 3
  const _leftGestureCount  = new Map<string, number>()
  const _rightGestureCount = new Map<string, number>()
  let _committedLeft  = 'none'
  let _committedRight = 'none'

  function _smoothGesture(
    rawGesture: string,
    side: 'left' | 'right',
  ): string {
    const counter = side === 'left' ? _leftGestureCount : _rightGestureCount

    // Increment count for current gesture, reset others
    const current = counter.get(rawGesture) ?? 0
    counter.clear()
    counter.set(rawGesture, current + 1)

    if ((counter.get(rawGesture) ?? 0) >= GESTURE_HOLD_FRAMES) {
      if (side === 'left') _committedLeft = rawGesture
      else _committedRight = rawGesture
      return rawGesture
    }
    return side === 'left' ? _committedLeft : _committedRight  // return previous committed gesture until new one is stable
  }

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

    // ── Smooth raw gestures ───────────────────────────────────────────────
    const smoothLeft  = _smoothGesture(left.gesture,  'left')
    const smoothRight = _smoothGesture(right.gesture, 'right')

    // ── Bimanual takes full priority ──────────────────────────────────────
    if (bimanual.active && bimanual.pattern) {
      clearGlobalGesture()
      clearHandForce()
      clearBeam()
      clearBreath()

      switch (bimanual.pattern) {
        case 'prayer-explosion':
          if (bimanual.phase === 'blast' && !_blastShockwaveFired) {
            shockwave(new THREE.Vector3(0, 0, 0), 80, 10)
            _blastShockwaveFired = true
            setTimeout(() => { _blastShockwaveFired = false }, 600)
          }
          break
        case 'implosion':
          if (bimanual.phase === 'vortex' || bimanual.phase === 'approach') {
            vortex(new THREE.Vector3(0, 0, 0), 5)
          }
          break
        case 'orbit': {
          const pinchHand = smoothLeft === 'pinch' ? left : right
          orbitAnchor(pinchHand.worldPos, 20)
          // Free hand: directional influence
          const freeGesture = smoothLeft !== 'pinch' ? smoothLeft : smoothRight
          if (freeGesture !== 'none') {
            const freeGlobal = freeGesture === 'open' ? 'repel' : freeGesture === 'fist' ? 'attract' : 'none'
            if (freeGlobal !== 'none') setGlobalGesture(freeGlobal as 'attract' | 'repel')
          }
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

      if (bimanual.pattern !== 'portal') clearPortal()
      if (bimanual.pattern !== 'dual-pinch') clearSplitField()
      return
    }

    // ── Single-hand: clear bimanual leftovers ──────────────────────────────
    clearSplitField()
    clearPortal()

    // ── Map gestures to GLOBAL effects (no cursor positioning) ────────────
    // Priority: left hand takes precedence if both active; swipe/breathe/point
    // are directional so use first active hand

    const activeGestures = [smoothLeft, smoothRight].filter(g => g !== 'none')
    const dominant = activeGestures[0] ?? 'none'

    switch (dominant) {
      case 'pinch':
        // Global attract — all particles collapse toward center
        setGlobalGesture('attract')
        clearBeam()
        clearBreath()
        clearHandForce()
        break
      case 'open':
        // Global repel — all particles explode outward
        setGlobalGesture('repel')
        clearBeam()
        clearBreath()
        clearHandForce()
        break
      case 'breathe':
        setGlobalGesture('breathe')
        clearBeam()
        clearHandForce()
        break
      case 'swipe': {
        // Use whichever hand is swiping
        const swipeHand = smoothLeft === 'swipe' ? left : right
        clearGlobalGesture()
        clearBeam()
        clearBreath()
        clearHandForce()
        lateralWave(new THREE.Vector3(0, 0, 0), Math.sign(swipeHand.velocity.x), Math.max(2, swipeHand.velocity.length() / 60))
        break
      }
      case 'point': {
        const pointHand = smoothLeft === 'point' ? left : right
        clearGlobalGesture()
        clearBreath()
        clearHandForce()
        directionalBeam(
          new THREE.Vector3(0, 0, 0),
          pointHand.velocity.length() > 1
            ? pointHand.velocity.clone().normalize()
            : new THREE.Vector3(0, 1, 0),
        )
        break
      }
      case 'fist':
        // Already handled as one-shot burst in the fist tracking block below
        clearGlobalGesture()
        clearBeam()
        clearBreath()
        clearHandForce()
        break
      default:
        // No active gesture — clear everything
        clearGlobalGesture()
        clearBeam()
        clearBreath()
        clearHandForce()
    }

    // ── Fist one-shot burst (per hand, independent of dominant) ──────────
    for (const [hand, side] of [[left, 'left'], [right, 'right']] as const) {
      const sg = side === 'left' ? smoothLeft : smoothRight
      if (sg !== 'fist') {
        _fistBurstFired.delete(side)
      } else if (!_fistBurstFired.has(side)) {
        shockwave(new THREE.Vector3(0, 0, 0), 80, 8)
        _fistBurstFired.add(side)
      }
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

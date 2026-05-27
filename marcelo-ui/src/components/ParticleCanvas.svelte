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
    directionalBeam, clearBeam, lateralWave, breathePulse, clearBreath,
    applyHandForce, clearHandForce,
  } from '../lib/particle-engine'

  // Module-level guard: tracks which hands have already fired the fist burst this gesture
  const _fistBurstFired = new Set<'left' | 'right'>()

  // Module-level guard: prevents prayer-explosion shockwave from stacking across frames
  let _blastShockwaveFired = false

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
          if (bimanual.phase === 'blast' && !_blastShockwaveFired) {
            const mid = left.worldPos.clone().add(right.worldPos).multiplyScalar(0.5)
            shockwave(mid, 60, 8)
            _blastShockwaveFired = true
            setTimeout(() => { _blastShockwaveFired = false }, 600)
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

      // Clear single-hand persistent effects when bimanual is active
      clearHandForce()
      clearBeam()
      clearBreath()

      // Still apply free-hand unimanual for orbit (free hand)
      if (bimanual.pattern === 'orbit') {
        const freeHand = left.gesture !== 'pinch' ? left : right
        if (freeHand.gesture !== 'none') {
          const mapped = freeHand.gesture === 'fist' ? 'attract'
            : freeHand.gesture === 'open' ? 'repel'
            : 'pinch'
          applyHandForce(freeHand.worldPos, mapped, freeHand.velocity)
        }
      }
      return
    }

    // Single-hand effects (apply both hands independently)
    clearSplitField()
    clearPortal()

    for (const [hand, side] of [[left, 'left'], [right, 'right']] as const) {
      // Reset burst guard when fist gesture ends
      if (hand.gesture !== 'fist') _fistBurstFired.delete(side)
      if (hand.gesture === 'none') continue

      switch (hand.gesture) {
        case 'fist':
          if (!_fistBurstFired.has(side)) {
            shockwave(hand.worldPos, 25, 5)
            _fistBurstFired.add(side)
          }
          break
        case 'pinch':
          applyHandForce(hand.worldPos, 'pinch', hand.velocity)
          break
        case 'open':
          applyHandForce(hand.worldPos, 'repel', hand.velocity)
          break
        case 'point':
          directionalBeam(hand.worldPos, hand.velocity.length() > 1
            ? hand.velocity.clone().normalize()
            : new THREE.Vector3(0, -1, 0))
          break
        case 'swipe':
          lateralWave(hand.worldPos, Math.sign(hand.velocity.x), Math.max(1, hand.velocity.length() / 60))
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

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

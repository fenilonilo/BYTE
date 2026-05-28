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

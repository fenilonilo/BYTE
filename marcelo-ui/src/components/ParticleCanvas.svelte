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

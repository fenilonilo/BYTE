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

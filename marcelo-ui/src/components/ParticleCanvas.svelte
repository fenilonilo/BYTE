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

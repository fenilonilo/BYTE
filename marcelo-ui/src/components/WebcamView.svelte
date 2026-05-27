<script lang="ts">
  import { onMount } from 'svelte'

  let videoEl: HTMLVideoElement
  let visible = $state(false)

  onMount(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false })
      videoEl.srcObject = stream
      visible = true
    } catch {
      // No webcam available — hide silently
    }
  })
</script>

{#if visible}
  <div style="
    position:fixed;
    top:16px;
    right:16px;
    z-index:10;
    width:120px;
    aspect-ratio:4/3;
    border-radius:8px;
    overflow:hidden;
    border:1px solid rgba(255,255,255,0.08);
    background:rgba(6,10,15,0.5);
  ">
    <video
      bind:this={videoEl}
      autoplay
      playsinline
      muted
      style="width:100%;height:100%;object-fit:cover;transform:scaleX(-1);"
    ></video>
  </div>
{/if}

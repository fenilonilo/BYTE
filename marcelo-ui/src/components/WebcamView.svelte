<script lang="ts">
  const PREVIEW_URL = 'http://localhost:8001/preview'
  let failed = $state(false)
</script>

{#if !failed}
  <div style="
    position:fixed;
    top:16px;
    right:16px;
    z-index:10;
    width:160px;
    aspect-ratio:4/3;
    border-radius:8px;
    overflow:hidden;
    border:1px solid rgba(255,255,255,0.08);
    background:rgba(6,10,15,0.5);
  ">
    <img
      src={PREVIEW_URL}
      alt="webcam"
      onerror={() => { failed = true }}
      style="width:100%;height:100%;object-fit:cover;"
    />
  </div>
{/if}

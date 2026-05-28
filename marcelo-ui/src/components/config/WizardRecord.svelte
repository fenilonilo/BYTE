<script lang="ts">
  import { configState, goto } from '../../stores/config.svelte'
  import { startRecording, recordStatus } from '../../lib/config-api'

  let recording = $state(false)
  let remaining = $state(0)

  async function record(): Promise<void> {
    const label = configState.draft.pose.shape.trim()
    if (!label) return
    recording = true
    await startRecording(label, 15)
    const poll = setInterval(async () => {
      const s = await recordStatus()
      remaining = s.remaining
      if (!s.active) {
        clearInterval(poll)
        recording = false
      }
    }, 200)
  }
</script>

<div style="padding:20px;color:#cdd9e5;">
  <h3>1 · Gravar pose</h3>

  <img src="http://localhost:8001/preview" alt="preview"
       style="width:100%;max-width:360px;border-radius:10px;margin:12px 0;border:1px solid #2a3a4a;" />

  <label style="display:block;margin-bottom:8px;">
    Nome da pose
    <input bind:value={configState.draft.pose.shape}
           placeholder="ex: mao_aberta"
           style="display:block;margin-top:4px;padding:6px;width:240px;" />
  </label>

  <button onclick={record} disabled={recording}
          style="padding:8px 16px;border-radius:8px;background:#1f6feb;color:#fff;border:none;">
    {recording ? `Gravando… ${remaining}` : 'Segurar e gravar (15 frames)'}
  </button>

  <div style="margin-top:16px;display:flex;gap:8px;">
    <button onclick={() => goto('list')}>voltar</button>
    <button onclick={() => goto('compose')}>próximo →</button>
  </div>
</div>

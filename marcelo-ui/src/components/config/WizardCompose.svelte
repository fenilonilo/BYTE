<script lang="ts">
  import { onDestroy } from 'svelte'
  import { configState, goto } from '../../stores/config.svelte'
  import { currentGesture, BUILTIN_POSES, MOTIONS } from '../../lib/config-api'

  let detected = $state('none')
  const poll = setInterval(async () => {
    detected = (await currentGesture()).gesture
  }, 250)
  onDestroy(() => clearInterval(poll))
</script>

<div style="padding:20px;color:#cdd9e5;">
  <h3>2 · Compor gesto</h3>

  <label style="display:block;margin:8px 0;">
    Nome do gesto
    <input bind:value={configState.draft.name}
           oninput={() => { configState.draft.id = configState.draft.name.toLowerCase().replace(/\s+/g, '_') }}
           style="display:block;margin-top:4px;padding:6px;width:240px;" />
  </label>

  <label style="display:block;margin:8px 0;">
    Pose
    <input list="poses" bind:value={configState.draft.pose.shape}
           style="display:block;margin-top:4px;padding:6px;width:240px;" />
    <datalist id="poses">
      {#each BUILTIN_POSES as p}<option value={p}></option>{/each}
    </datalist>
  </label>

  <label style="display:block;margin:8px 0;">
    Mãos
    <select bind:value={configState.draft.pose.hands}>
      <option value={1}>1</option>
      <option value={2}>2</option>
    </select>
  </label>

  <label style="display:block;margin:8px 0;">
    Movimento
    <select bind:value={configState.draft.motion.type}>
      {#each MOTIONS as m}<option value={m}>{m}</option>{/each}
    </select>
  </label>

  <p style="margin-top:12px;opacity:0.8;">
    Teste ao vivo — detectado agora:
    <strong style="color:{detected === configState.draft.id ? '#7ee787' : '#cdd9e5'};">{detected}</strong>
  </p>

  <div style="margin-top:16px;display:flex;gap:8px;">
    <button onclick={() => goto('record')}>← voltar</button>
    <button onclick={() => goto('bind')}>próximo →</button>
  </div>
</div>

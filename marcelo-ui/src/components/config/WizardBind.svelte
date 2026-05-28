<script lang="ts">
  import { configState, goto, refreshList } from '../../stores/config.svelte'
  import { saveGesture, EFFECTS, ACTIONS } from '../../lib/config-api'

  let modelParam = $state('gemini')
  let projectParam = $state('')

  async function save(): Promise<void> {
    const d = configState.draft
    if (d.binding.action === 'swap_model') d.binding.action_params = { model: modelParam }
    else if (d.binding.action === 'open_project') d.binding.action_params = { project: projectParam }
    else d.binding.action_params = {}
    if (!d.id) d.id = d.name.toLowerCase().replace(/\s+/g, '_')
    await saveGesture(d)
    await refreshList()
    goto('list')
  }
</script>

<div style="padding:20px;color:#cdd9e5;">
  <h3>3 · Ligar (efeito + ação)</h3>

  <label style="display:block;margin:8px 0;">
    Efeito
    <select bind:value={configState.draft.binding.effect}>
      {#each EFFECTS as e}<option value={e}>{e}</option>{/each}
    </select>
  </label>

  <label style="display:block;margin:8px 0;">
    Ação
    <select bind:value={configState.draft.binding.action}>
      {#each ACTIONS as a}<option value={a === 'none' ? null : a}>{a}</option>{/each}
    </select>
  </label>

  {#if configState.draft.binding.action === 'swap_model'}
    <label style="display:block;margin:8px 0;">
      Modelo
      <select bind:value={modelParam}>
        <option value="groq">groq</option>
        <option value="gemini">gemini</option>
      </select>
    </label>
  {:else if configState.draft.binding.action === 'open_project'}
    <label style="display:block;margin:8px 0;">
      Projeto
      <input bind:value={projectParam} style="padding:6px;" />
    </label>
  {/if}

  <div style="margin-top:16px;display:flex;gap:8px;">
    <button onclick={() => goto('compose')}>← voltar</button>
    <button onclick={save}
            style="padding:8px 16px;border-radius:8px;background:#238636;color:#fff;border:none;">
      Salvar gesto
    </button>
  </div>
</div>

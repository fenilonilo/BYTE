<script lang="ts">
  import { configState, newGesture, editGesture, refreshList } from '../../stores/config.svelte'
  import { deleteGesture } from '../../lib/config-api'

  async function remove(id: string): Promise<void> {
    await deleteGesture(id)
    await refreshList()
  }
</script>

<div style="padding:20px;color:#cdd9e5;">
  <h2 style="margin-bottom:14px;letter-spacing:2px;">GESTOS</h2>

  {#if configState.items.length === 0}
    <p style="opacity:0.6;">Nenhum gesto configurado.</p>
  {/if}

  {#each configState.items as def (def.id)}
    <div style="display:flex;justify-content:space-between;align-items:center;
                padding:10px 12px;border:1px solid #2a3a4a;border-radius:8px;margin-bottom:8px;">
      <div>
        <strong>{def.name}</strong>
        <span style="opacity:0.6;font-size:12px;">
          → {def.binding.effect}{def.binding.action ? ` + ${def.binding.action}` : ''}
        </span>
      </div>
      <div style="display:flex;gap:8px;">
        <button onclick={() => editGesture(def)}>editar</button>
        <button onclick={() => remove(def.id)}>x</button>
      </div>
    </div>
  {/each}

  <button onclick={newGesture}
          style="margin-top:12px;padding:8px 16px;border-radius:8px;
                 background:#1f6feb;color:#fff;border:none;cursor:pointer;">
    + Novo gesto
  </button>
</div>

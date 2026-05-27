<script lang="ts">
  import { onMount, onDestroy } from 'svelte'
  import { projectsState, startPolling } from '../stores/projects.svelte'
  import type { ProjectItem } from '../lib/types'

  let collapsed = $state(false)
  let expanded  = $state(false)
  let stopPolling: () => void

  const SHOW_LIMIT = 5

  onMount(() => { stopPolling = startPolling() })
  onDestroy(() => stopPolling?.())

  /** Returns 'hoje' | '2d' | '5d' | '3sem' etc. */
  function _relTime(mtime: number): string {
    const diff = (Date.now() / 1000) - mtime
    if (diff < 86_400)           return 'hoje'
    if (diff < 86_400 * 7)       return `${Math.floor(diff / 86_400)}d`
    if (diff < 86_400 * 30)      return `${Math.floor(diff / (86_400 * 7))}sem`
    return `${Math.floor(diff / (86_400 * 30))}m`
  }

  /** Green = today, amber = <7d, grey = older */
  function _dotColor(mtime: number): string {
    const diff = (Date.now() / 1000) - mtime
    if (diff < 86_400)      return '#96ff64'
    if (diff < 86_400 * 7)  return 'rgba(255,200,80,0.8)'
    return 'rgba(255,255,255,0.2)'
  }

  function _dotGlow(mtime: number): string {
    const diff = (Date.now() / 1000) - mtime
    if (diff < 86_400)      return '0 0 5px #96ff64'
    return 'none'
  }

  async function _openProject(item: ProjectItem): Promise<void> {
    // Calls open_dev_environment via the WebSocket / tool — for now POST to a
    // dedicated endpoint. If that endpoint doesn't exist yet, opens in explorer.
    try {
      await fetch('/api/v1/open-project', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: item.path }),
      })
    } catch {
      // Fallback: no-op silently
    }
  }

  let displayed = $derived(
    expanded
      ? projectsState.items
      : projectsState.items.slice(0, SHOW_LIMIT)
  )

  let hiddenCount = $derived(
    Math.max(0, projectsState.items.length - SHOW_LIMIT)
  )
</script>

<div style="
  position:fixed;
  bottom:24px;
  right:24px;
  z-index:20;
  width:220px;
  background:rgba(6,10,15,0.75);
  backdrop-filter:blur(12px);
  border:1px solid rgba(255,255,255,0.07);
  border-radius:12px;
  overflow:hidden;
  transition:max-height 200ms ease;
  max-height:{collapsed ? '48px' : '400px'};
">
  <!-- Header -->
  <div
    onclick={() => collapsed = !collapsed}
    style="
      padding:12px 14px;
      display:flex;align-items:center;justify-content:space-between;
      cursor:pointer;
      border-bottom:1px solid {collapsed ? 'transparent' : 'rgba(255,255,255,0.05)'};
    "
  >
    <span style="font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:2px;color:rgba(150,255,180,0.6);text-transform:uppercase;">
      ◈ projetos
    </span>
    {#if projectsState.loading}
      <span style="font-size:9px;color:rgba(255,255,255,0.2);">…</span>
    {/if}
  </div>

  {#if !collapsed}
    <div style="padding:6px 0;">
      {#each displayed as item (item.path)}
        <div
          onclick={() => _openProject(item)}
          style="
            display:flex;align-items:center;gap:8px;
            padding:6px 14px;cursor:pointer;
            transition:background 100ms;
          "
          onmouseenter={(e) => (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.03)'}
          onmouseleave={(e) => (e.currentTarget as HTMLElement).style.background = 'transparent'}
        >
          <span style="
            width:6px;height:6px;border-radius:50%;flex-shrink:0;
            background:{_dotColor(item.mtime)};
            box-shadow:{_dotGlow(item.mtime)};
          "></span>
          <span style="
            flex:1;font-family:Inter,sans-serif;font-size:12px;
            color:rgba(255,255,255,0.65);
            white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
          ">{item.name}</span>
          <span style="
            font-family:'JetBrains Mono',monospace;font-size:9px;
            color:rgba(255,255,255,0.2);flex-shrink:0;
          ">{_relTime(item.mtime)}</span>
        </div>
      {/each}

      {#if hiddenCount > 0 && !expanded}
        <div
          onclick={() => expanded = true}
          style="
            padding:5px 14px;
            font-family:'JetBrains Mono',monospace;font-size:9px;
            color:rgba(255,255,255,0.2);letter-spacing:1px;cursor:pointer;
          "
        >+ {hiddenCount} projetos…</div>
      {/if}
    </div>
  {/if}
</div>

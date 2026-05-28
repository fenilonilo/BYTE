<script lang="ts">
  import { onDestroy } from 'svelte'
  import { gestureState } from '../stores/gesture.svelte'

  // Freeze countdown
  let freezeCountdown = $state(0)
  let _freezeInterval: ReturnType<typeof setInterval> | null = null

  // Badge visible timer
  let badgeVisible = $state(false)
  let _badgeTimer: ReturnType<typeof setTimeout> | null = null

  const LABELS: Record<string, string> = {
    none:      '',
    pinch:     '👌 PINCH',
    swipe:     '🌊 ONDA',
    explosion: '🙏 EXPLOSÃO',
    orbit:     '🌌 ÓRBITA',
    freeze:    '❄️ CONGELAR',
    portal:    '🔮 PORTAL',
  }

  $effect(() => {
    const g = gestureState.gesture
    if (g === 'none') { badgeVisible = false; return }

    badgeVisible = true
    _badgeTimer && clearTimeout(_badgeTimer)
    _badgeTimer = setTimeout(() => { badgeVisible = false }, 1500)

    // Start freeze countdown
    if (g === 'freeze' && !_freezeInterval) {
      freezeCountdown = 3
      _freezeInterval = setInterval(() => {
        freezeCountdown = Math.max(0, freezeCountdown - 1)
        if (freezeCountdown <= 0) {
          clearInterval(_freezeInterval!)
          _freezeInterval = null
        }
      }, 1000)
    }
    // Reset freeze countdown if gesture changed away from freeze
    if (g !== 'freeze' && _freezeInterval) {
      clearInterval(_freezeInterval)
      _freezeInterval = null
      freezeCountdown = 0
    }
  })

  onDestroy(() => {
    _badgeTimer   && clearTimeout(_badgeTimer)
    _freezeInterval && clearInterval(_freezeInterval)
  })
</script>

<!-- Freeze ice overlay -->
{#if gestureState.gesture === 'freeze'}
  <div style="
    position:fixed;inset:0;z-index:25;pointer-events:none;
    background:rgba(150,220,255,0.04);
    animation:iceIn 400ms ease;
  "></div>
{/if}

<!-- Gesture badge -->
{#if badgeVisible && gestureState.gesture !== 'none'}
  <div style="
    position:fixed;
    top:16px;
    left:50%;
    transform:translateX(-50%);
    z-index:30;
    background:rgba(6,10,15,0.85);
    backdrop-filter:blur(8px);
    border:1px solid rgba(255,255,255,0.1);
    border-radius:20px;
    padding:6px 16px;
    font-family:'JetBrains Mono',monospace;
    font-size:11px;
    letter-spacing:2px;
    color:rgba(255,255,255,0.8);
    pointer-events:none;
    animation:fadeIn 100ms ease;
    display:flex;gap:8px;align-items:center;
  ">
    {LABELS[gestureState.gesture] ?? gestureState.gesture.toUpperCase()}

    {#if gestureState.gesture === 'swipe'}
      <span>{gestureState.params.vector.x >= 0 ? '→' : '←'}</span>
    {/if}

    {#if gestureState.gesture === 'orbit'}
      <span style="opacity:0.6;font-size:9px;">âncora ativa</span>
    {/if}

    {#if gestureState.gesture === 'portal'}
      <span style="opacity:0.6;font-size:9px;">r={Math.round(gestureState.params.radius * 100)}</span>
    {/if}

    {#if gestureState.gesture === 'freeze' && freezeCountdown > 0}
      <span style="opacity:0.6;font-size:9px;">{freezeCountdown}s</span>
    {/if}

    {#if gestureState.hands > 0}
      <span style="
        background:rgba(255,255,255,0.1);border-radius:10px;
        padding:1px 6px;font-size:9px;opacity:0.7;
      ">{gestureState.hands}✋</span>
    {/if}
  </div>
{/if}

<style>
  @keyframes iceIn {
    from { opacity: 0; }
    to   { opacity: 1; }
  }
  @keyframes fadeIn {
    from { opacity: 0; transform: translateX(-50%) translateY(-4px); }
    to   { opacity: 1; transform: translateX(-50%) translateY(0); }
  }
</style>

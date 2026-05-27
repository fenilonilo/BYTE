<script lang="ts">
  import { onDestroy } from 'svelte'
  import { gestureState } from '../stores/gesture.svelte'
  import type { BimanualGesture, HandGesture } from '../lib/types'

  // Freeze ice overlay: tracked via crystallize bimanual
  let frozen = $state(false)
  let freezeTimer: ReturnType<typeof setTimeout> | null = null

  // Badge visible timer
  let badgeText = $state<string | null>(null)
  let badgeTimer: ReturnType<typeof setTimeout> | null = null

  const bimanualLabels: Record<BimanualGesture, string> = {
    'prayer-explosion': '🙏 EXPLOSÃO',
    'implosion':        '🌀 IMPLOSÃO',
    'orbit':            '🌌 ÓRBITA',
    'freeze':           '❄️ CONGELAR',
    'dual-pinch':       '⚡ CAMPO DUPLO',
    'portal':           '🔮 PORTAL',
  }

  const unimanualLabels: Partial<Record<HandGesture, string>> = {
    pinch:   '👌 PINCH',
    fist:    '✊ BURST',
    open:    '🖐 REPELIR',
    point:   '☝️ APONTAR',
    swipe:   '🌊 ONDA',
    breathe: '💫 RESPIRAR',
  }

  $effect(() => {
    const { bimanual, left, right } = gestureState

    if (bimanual.active && bimanual.pattern) {
      _showBadge(bimanualLabels[bimanual.pattern])
      if (bimanual.pattern === 'freeze') {
        frozen = true
        freezeTimer && clearTimeout(freezeTimer)
        freezeTimer = setTimeout(() => { frozen = false }, 3000)
      }
      return
    }

    const activeGesture = left.gesture !== 'none' ? left.gesture : right.gesture
    const label = unimanualLabels[activeGesture]
    if (label) _showBadge(label)
  })

  function _showBadge(text: string): void {
    badgeText = text
    badgeTimer && clearTimeout(badgeTimer)
    badgeTimer = setTimeout(() => { badgeText = null }, 1500)
  }

  onDestroy(() => {
    freezeTimer && clearTimeout(freezeTimer)
    badgeTimer && clearTimeout(badgeTimer)
  })
</script>

<!-- Freeze ice overlay -->
{#if frozen}
  <div style="
    position:fixed;inset:0;z-index:25;pointer-events:none;
    background:rgba(150,220,255,0.04);
    animation:iceIn 400ms ease;
  "></div>
{/if}

<!-- Gesture badge -->
{#if badgeText}
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
  ">
    {badgeText}
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

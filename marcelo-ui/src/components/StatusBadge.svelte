<script lang="ts">
  import type { ParticleState } from '../lib/types'

  let { state }: { state: ParticleState } = $props()

  const labels: Record<ParticleState, string> = {
    idle:      'IDLE',
    listening: 'OUVINDO',
    thinking:  'PENSANDO',
    speaking:  'FALANDO',
  }

  const colors: Record<ParticleState, string> = {
    idle:      'rgba(99,179,255,0.5)',
    listening: 'rgba(150,255,180,0.7)',
    thinking:  'rgba(255,200,80,0.7)',
    speaking:  'rgba(150,80,255,0.7)',
  }
</script>

<span style="
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: {colors[state]};
  display: inline-flex;
  align-items: center;
  gap: 5px;
">
  <span style="
    width:5px;height:5px;border-radius:50%;
    background:{colors[state]};
    box-shadow:0 0 6px {colors[state]};
    flex-shrink:0;
  "></span>
  {labels[state]}
</span>

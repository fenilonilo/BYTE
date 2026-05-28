import type { WireGestureEvent } from '../gesture-types'

export const FORCE_MODE = {
  none: 0, attract: 1, repel: 2, freeze: 3, shockwave: 4,
  vortex: 5, orbit: 6, portal: 7, beam: 8, wave: 9, breathe: 10,
} as const

export type EffectName = keyof typeof FORCE_MODE

// Built-in gesture -> effect map (Phase 5 config overrides this).
export const GESTURE_EFFECT: Record<string, EffectName> = {
  none: 'none',
  pinch: 'attract',
  swipe: 'wave',
  freeze: 'freeze',
  orbit: 'orbit',
  portal: 'portal',
}

// One-shot effects: their strength decays to 0 after firing.
export const ONE_SHOT: ReadonlySet<EffectName> = new Set<EffectName>(['shockwave', 'wave'])

export interface ResolvedForce {
  mode: number
  center: [number, number, number]
  vector: [number, number, number]
  radius: number
  strength: number
  oneShot: boolean
}

// Map normalized [0,1] image coords to world space (centered, scaled).
function toWorld(x: number, y: number, z: number): [number, number, number] {
  const SCALE = 60
  return [(x - 0.5) * SCALE, -(y - 0.5) * SCALE, z * SCALE]
}

export function resolveForce(ev: WireGestureEvent): ResolvedForce {
  const effect = GESTURE_EFFECT[ev.gesture] ?? 'none'
  const mode = FORCE_MODE[effect]
  const center = toWorld(ev.params.center.x || 0.5, ev.params.center.y || 0.5, ev.params.center.z)
  const vector: [number, number, number] = [ev.params.vector.x, -ev.params.vector.y, ev.params.vector.z]
  const radius = Math.max(ev.params.radius * 60, 12)
  const strength = effect === 'none' ? 0 : 1.2
  return { mode, center, vector, radius, strength, oneShot: ONE_SHOT.has(effect) }
}

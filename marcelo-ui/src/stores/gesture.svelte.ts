import type { WireGestureEvent } from '../lib/gesture-types'

export const gestureState = $state<WireGestureEvent>({
  gesture: 'none',
  phase: 'idle',
  hands: 0,
  params: {
    points: [],
    vector: { x: 0, y: 0, z: 0 },
    center: { x: 0, y: 0, z: 0 },
    radius: 0,
    magnitude: 0,
  },
  ts: 0,
})

export function updateGestureState(next: WireGestureEvent): void {
  gestureState.gesture = next.gesture
  gestureState.phase = next.phase
  gestureState.hands = next.hands
  gestureState.params = next.params
  gestureState.ts = next.ts
}

import * as THREE from 'three'
import type { GestureState } from '../lib/types'

export const gestureState = $state<GestureState>({
  left: {
    gesture: 'none',
    worldPos: new THREE.Vector3(),
    velocity: new THREE.Vector3(),
    age: 0,
  },
  right: {
    gesture: 'none',
    worldPos: new THREE.Vector3(),
    velocity: new THREE.Vector3(),
    age: 0,
  },
  bimanual: {
    active: false,
    pattern: null,
    phase: 'idle',
    progress: 0,
  },
})

export function updateGestureState(next: GestureState): void {
  gestureState.left  = next.left
  gestureState.right = next.right
  gestureState.bimanual = next.bimanual
}

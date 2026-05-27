import * as THREE from 'three'
import type { UnifiedGestureState } from '../lib/types'

export const gestureState = $state<UnifiedGestureState>({
  gesture:      'none',
  handCount:    0,
  swipeSign:    0,
  orbitAnchor:  new THREE.Vector3(),
  portalCenter: new THREE.Vector3(),
  portalRadius: 0,
  phase:        'idle',
})

export function updateGestureState(next: UnifiedGestureState): void {
  gestureState.gesture      = next.gesture
  gestureState.handCount    = next.handCount
  gestureState.swipeSign    = next.swipeSign
  gestureState.orbitAnchor  = next.orbitAnchor
  gestureState.portalCenter = next.portalCenter
  gestureState.portalRadius = next.portalRadius
  gestureState.phase        = next.phase
}

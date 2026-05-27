import * as THREE from 'three'
import type { HandGesture, BimanualGesture, HandState, BimanualPattern, GestureState } from './types'

// ─── Config ───────────────────────────────────────────────────────────────────

const PINCH_DIST    = 0.06   // normalized landmark distance
const PRAYER_DIST   = 0.15   // palms touching threshold (normalized)
const PRAYER_VEL    = 0.3    // separation velocity to trigger blast
const IMPLOSION_VEL = 0.3    // max approach velocity
const IMPLOSION_DIST = 0.20  // distance to trigger vortex
const ORBIT_HOLD_MS = 500    // ms pinch must be stable before orbit activates
const FREEZE_WINDOW = 300    // ms both fists must close within

// ─── Module state ─────────────────────────────────────────────────────────────

let camera3D: THREE.PerspectiveCamera | null = null
let _mpCamera: any = null

interface PerHandInternal {
  state: HandState
  gestureStartTime: number
  prevPos: THREE.Vector3
  prevTime: number
  breatheStartTime: number | null
  prevResolvedGesture: HandGesture
}

const _hands: Record<'left' | 'right', PerHandInternal> = {
  left:  _emptyHand(),
  right: _emptyHand(),
}

let _bimanual: BimanualPattern = {
  active: false, pattern: null, phase: 'idle', progress: 0
}

// prayer state
let _prayerPhase: 'none' | 'contact' | 'release' | 'blast' = 'none'

// orbit state
let _orbitAnchorHand: 'left' | 'right' | null = null
let _orbitAnchorSince: number | null = null
let _orbitTotalDelta: number = 0
let _orbitPrevAngle: number | null = null

// freeze
let _lastFistTimes: Record<'left' | 'right', number | null> = { left: null, right: null }
let _freezeExpiresAt: number | null = null

export type GestureCallback = (state: GestureState) => void

let _onGesture: GestureCallback | null = null

// ─── Public API ───────────────────────────────────────────────────────────────

export async function init(
  videoEl: HTMLVideoElement,
  camera: THREE.PerspectiveCamera,
  onGesture: GestureCallback,
): Promise<void> {
  camera3D    = camera
  _onGesture  = onGesture

  await _loadScript('https://cdn.jsdelivr.net/npm/@mediapipe/hands/hands.js')
  await _loadScript('https://cdn.jsdelivr.net/npm/@mediapipe/camera_utils/camera_utils.js')

  const hands = new (window as any).Hands({
    locateFile: (f: string) => `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${f}`,
  })

  hands.setOptions({
    maxNumHands: 2,
    modelComplexity: 1,
    minDetectionConfidence: 0.7,
    minTrackingConfidence: 0.5,
  })

  hands.onResults(_processResults)

  _mpCamera = new (window as any).Camera(videoEl, {
    onFrame: async () => { await hands.send({ image: videoEl }) },
    width: 320,
    height: 240,
  })
  _mpCamera.start()
}

export function dispose(): void {
  _mpCamera?.stop()
  _mpCamera = null
  _onGesture = null
  camera3D = null
}

// ─── Internal result handler ──────────────────────────────────────────────────

function _processResults(results: any): void {
  const now = performance.now()

  // Reset both hands to none
  _hands.left.state.gesture  = 'none'
  _hands.right.state.gesture = 'none'

  const lms  = results.multiHandLandmarks ?? []
  const hand = results.multiHandedness ?? []

  for (let hi = 0; hi < lms.length; hi++) {
    const landmarks = lms[hi]
    // MediaPipe labels: "Left" = user's left (mirrored = right in image) — use as-is
    const side: 'left' | 'right' = (hand[hi]?.label ?? 'Right') === 'Left' ? 'left' : 'right'
    const h = _hands[side]

    const gesture  = _classify(landmarks)
    const worldPos = _landmarkToWorld(landmarks[9])
    const dt       = Math.max((now - h.prevTime) / 1000, 0.001)

    const velocity = new THREE.Vector3(
      (worldPos.x - h.prevPos.x) / dt,
      (worldPos.y - h.prevPos.y) / dt,
      (worldPos.z - h.prevPos.z) / dt,
    )

    // Breathe detection
    if (gesture === 'open') {
      const speed = velocity.length()
      if (speed < 0.15 * 60) { // units/s threshold (world space)
        if (h.breatheStartTime === null) h.breatheStartTime = now
        if (now - h.breatheStartTime > 1000) {
          h.state.gesture = 'breathe'
        } else {
          h.state.gesture = 'open'
        }
      } else {
        h.breatheStartTime = null
        // Swipe detection
        if (Math.abs(velocity.x) > 0.8 * 60) {  // was 1.5 * 60
          h.state.gesture = 'swipe'
        } else {
          h.state.gesture = 'open'
        }
      }
    } else {
      h.breatheStartTime = null
      h.state.gesture = gesture
    }

    h.state.worldPos.copy(worldPos)
    h.state.velocity.copy(velocity)

    // Track age using resolved gesture (handles breathe/swipe divergence from raw gesture)
    const resolvedGesture = h.state.gesture
    if (resolvedGesture !== h.prevResolvedGesture) {
      h.gestureStartTime = now
    }
    h.state.age = now - h.gestureStartTime
    h.prevResolvedGesture = resolvedGesture

    h.prevPos.copy(worldPos)
    h.prevTime = now

    // Freeze: track fist times
    if (gesture === 'fist') {
      if (_lastFistTimes[side] === null) _lastFistTimes[side] = now
    } else {
      _lastFistTimes[side] = null
    }
  }

  _detectBimanual(now)

  if (_onGesture) {
    _onGesture({
      left:     { ..._hands.left.state, worldPos: _hands.left.state.worldPos.clone(), velocity: _hands.left.state.velocity.clone() },
      right:    { ..._hands.right.state, worldPos: _hands.right.state.worldPos.clone(), velocity: _hands.right.state.velocity.clone() },
      bimanual: { ..._bimanual },
    })
  }
}

function _detectBimanual(now: number): void {
  const L = _hands.left.state
  const R = _hands.right.state

  if (L.gesture === 'none' || R.gesture === 'none') {
    _resetBimanual()
    return
  }

  // ── BLAST PROTECTION: prayer-explosion blast persists for its full duration ──
  if (_prayerPhase === 'blast') {
    _bimanual = { active: true, pattern: 'prayer-explosion', phase: 'blast', progress: 1 }
    return
  }

  // ── FREEZE: both fists within window ──────────────────────────────────────
  if (L.gesture === 'fist' && R.gesture === 'fist') {
    const lt = _lastFistTimes.left; const rt = _lastFistTimes.right
    if (lt !== null && rt !== null && Math.abs(lt - rt) < FREEZE_WINDOW) {
      _bimanual = { active: true, pattern: 'freeze', phase: 'instant', progress: 1 }
      _freezeExpiresAt = now + 3000   // match crystallize(3000) duration
      return
    }
  }

  // ── DUAL-PINCH ────────────────────────────────────────────────────────────
  if (L.gesture === 'pinch' && R.gesture === 'pinch') {
    _bimanual = { active: true, pattern: 'dual-pinch', phase: 'sustained', progress: 1 }
    return
  }

  // ── PRAYER-EXPLOSION: both open, palms approaching / contact ─────────────
  if (L.gesture === 'open' && R.gesture === 'open') {
    const dist = L.worldPos.distanceTo(R.worldPos)

    if (dist < PRAYER_DIST * 100) { // convert normalized to world-ish (camera-projected)
      if (_prayerPhase === 'none') {
        _prayerPhase = 'contact'
      } else if (_prayerPhase === 'contact') {
        // Detect release velocity
        const sepVel = L.velocity.clone().sub(R.velocity).length()
        if (sepVel > PRAYER_VEL * 60) {
          _prayerPhase = 'blast'
          _bimanual = { active: true, pattern: 'prayer-explosion', phase: 'blast', progress: 1 }
          setTimeout(() => { _prayerPhase = 'none' }, 500)
          return
        }
      }
      _bimanual = { active: true, pattern: 'prayer-explosion', phase: _prayerPhase, progress: 0.5 }
      return
    } else {
      _prayerPhase = 'none'
    }

    // ── IMPLOSION: both open, approaching slowly ────────────────────────────
    const approachVel = R.worldPos.clone().sub(L.worldPos).normalize()
      .dot(L.velocity.clone().sub(R.velocity)) / 60
    const maxVel = Math.max(L.velocity.length(), R.velocity.length()) / 60
    if (approachVel > 0 && maxVel < IMPLOSION_VEL) {
      const progress = Math.min(1, 1 - dist / 80)
      if (dist < IMPLOSION_DIST * 100) {
        _bimanual = { active: true, pattern: 'implosion', phase: 'vortex', progress: 1 }
      } else {
        _bimanual = { active: true, pattern: 'implosion', phase: 'approach', progress }
      }
      return
    }
  }

  // ── ORBIT: one pinch stable, other hand circling ──────────────────────────
  const pinchSide   = L.gesture === 'pinch' ? 'left' : R.gesture === 'pinch' ? 'right' : null
  const freeSide    = pinchSide === 'left' ? 'right' : pinchSide === 'right' ? 'left' : null

  if (pinchSide && freeSide) {
    if (_orbitAnchorHand !== pinchSide) {
      _orbitAnchorHand  = pinchSide
      _orbitAnchorSince = now
      _orbitTotalDelta  = 0
      _orbitPrevAngle   = null
    }

    if (now - (_orbitAnchorSince ?? now) > ORBIT_HOLD_MS) {
      const anchor = _hands[pinchSide].state.worldPos
      const free   = _hands[freeSide].state.worldPos
      const dx = free.x - anchor.x; const dy = free.y - anchor.y
      const angle = Math.atan2(dy, dx)

      if (_orbitPrevAngle !== null) {
        let delta = angle - _orbitPrevAngle
        // Normalize delta to [-π, π]
        if (delta > Math.PI)  delta -= 2 * Math.PI
        if (delta < -Math.PI) delta += 2 * Math.PI
        _orbitTotalDelta += Math.abs(delta)
      }
      _orbitPrevAngle = angle

      if (_orbitTotalDelta > Math.PI) {  // > 180° total swept
        _bimanual = { active: true, pattern: 'orbit', phase: 'orbit', progress: 1 }
        return
      }
      _bimanual = { active: true, pattern: 'orbit', phase: 'anchor', progress: 0.5 }
      return
    }
  } else {
    _orbitAnchorHand  = null
    _orbitAnchorSince = null
    _orbitTotalDelta  = 0
    _orbitPrevAngle   = null
  }

  // ── PORTAL: fingertips of both hands form a rough ring ───────────────────
  if (
    (L.gesture === 'open' || L.gesture === 'pinch') &&
    (R.gesture === 'open' || R.gesture === 'pinch')
  ) {
    const mid  = L.worldPos.clone().add(R.worldPos).multiplyScalar(0.5)
    const dL   = L.worldPos.distanceTo(mid)
    const yDiff = Math.abs(L.worldPos.y - R.worldPos.y)
    // Portal = hands form a ring of radius 5–30, and both at roughly same height (y diff < 10)
    if (dL > 5 && dL < 30 && yDiff < 10) {
      _bimanual = { active: true, pattern: 'portal', phase: 'sustained', progress: 1 }
      return
    }
  }

  _resetBimanual()
}

function _resetBimanual(): void {
  if (_bimanual.pattern === 'freeze' && _freezeExpiresAt !== null && performance.now() < _freezeExpiresAt) return
  if (_prayerPhase === 'blast') return  // blast duration managed by setTimeout
  _bimanual = { active: false, pattern: null, phase: 'idle', progress: 0 }
  _freezeExpiresAt = null
}

// ─── Landmark helpers ─────────────────────────────────────────────────────────

function _classify(lm: any[]): HandGesture {
  const thumbTip  = lm[4]; const indexTip  = lm[8]
  const middleTip = lm[12]; const ringTip  = lm[16]; const pinkyTip = lm[20]

  if (_dist(thumbTip, indexTip) < PINCH_DIST) return 'pinch'

  const indexCurled  = indexTip.y  > lm[6].y
  const middleCurled = middleTip.y > lm[10].y
  const ringCurled   = ringTip.y   > lm[14].y
  const pinkyCurled  = pinkyTip.y  > lm[18].y

  if (indexCurled && middleCurled && ringCurled && pinkyCurled) return 'fist'

  // Point: only index extended
  if (!indexCurled && middleCurled && ringCurled && pinkyCurled) return 'point'

  const allOpen = !indexCurled && !middleCurled && !ringCurled && !pinkyCurled
  if (allOpen) return 'open'

  return 'none'
}

function _dist(a: {x:number;y:number;z:number}, b: {x:number;y:number;z:number}): number {
  return Math.sqrt((a.x-b.x)**2 + (a.y-b.y)**2 + (a.z-b.z)**2)
}

function _landmarkToWorld(lm: {x:number;y:number;z:number}): THREE.Vector3 {
  if (!camera3D) return new THREE.Vector3()
  const ndcX =  lm.x * 2 - 1
  const ndcY = -lm.y * 2 + 1
  const v = new THREE.Vector3(ndcX, ndcY, 0.5)
  v.unproject(camera3D)
  const dir = v.sub(camera3D.position).normalize()
  const t   = -camera3D.position.z / dir.z
  return camera3D.position.clone().add(dir.multiplyScalar(t))
}

function _loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${src}"]`)) { resolve(); return }
    const s = document.createElement('script')
    s.src = src; s.onload = () => resolve(); s.onerror = reject
    document.head.appendChild(s)
  })
}

function _emptyHand(): PerHandInternal {
  return {
    state: {
      gesture: 'none',
      worldPos: new THREE.Vector3(),
      velocity: new THREE.Vector3(),
      age: 0,
    },
    gestureStartTime: 0,
    prevPos: new THREE.Vector3(),
    prevTime: performance.now(),
    breatheStartTime: null,
    prevResolvedGesture: 'none',
  }
}

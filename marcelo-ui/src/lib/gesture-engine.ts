import * as THREE from 'three'
import type { UnifiedGesture, UnifiedGestureState } from './types'

// ─── Config ───────────────────────────────────────────────────────────────────

const PINCH_DIST    = 0.06   // normalized landmark distance (thumb-index)
const PRAYER_DIST   = 15     // world units: hands "touching" threshold
const PRAYER_VEL    = 18     // world units/s separation velocity → blast
const FREEZE_WINDOW = 300    // ms: both fists must close within this window
const ORBIT_HOLD_MS = 500    // ms: pinch must be stable before orbit activates
const HOLD_FRAMES   = 5      // consecutive frames before single-hand gesture commits
const BIMANUAL_HOLD = 3      // consecutive frames before bimanual gesture commits
const MEMORY_FRAMES = 5      // frames of no-hand before committed gesture resets

// ─── Internal types ───────────────────────────────────────────────────────────

type RawGesture = 'pinch' | 'fist' | 'open' | 'none'

interface PerHandInternal {
  worldPos:          THREE.Vector3
  velocity:          THREE.Vector3
  prevPos:           THREE.Vector3
  prevTime:          number
  fistSince:         number | null   // timestamp when fist first detected
  rawGesture:        RawGesture
  detectedThisFrame: boolean
}

// ─── Module state ─────────────────────────────────────────────────────────────

let camera3D: THREE.PerspectiveCamera | null = null
let _mpCamera: any = null

const _hands: Record<'left' | 'right', PerHandInternal> = {
  left:  _emptyHand(),
  right: _emptyHand(),
}

// Smoothing state
let _candidate: UnifiedGesture    = 'none'
let _candidateCount: number       = 0
let _committed: UnifiedGesture    = 'none'
let _noHandCount: number          = 0

// Prayer / explosion state machine
let _prayerPhase: 'none' | 'contact' | 'blast' = 'none'
let _blastExpiresAt: number | null              = null

// Orbit tracking
let _orbitAnchorHand: 'left' | 'right' | null = null
let _orbitAnchorSince: number | null          = null
let _orbitTotalDelta: number                  = 0
let _orbitPrevAngle: number | null            = null

// Freeze tracking
let _lastFistTimes: Record<'left' | 'right', number | null> = { left: null, right: null }
let _freezeExpiresAt: number | null = null

export type GestureCallback = (state: UnifiedGestureState) => void
let _onGesture: GestureCallback | null = null

// ─── Public API ───────────────────────────────────────────────────────────────

export async function init(
  videoEl: HTMLVideoElement,
  camera: THREE.PerspectiveCamera,
  onGesture: GestureCallback,
): Promise<void> {
  camera3D   = camera
  _onGesture = onGesture

  await _loadScript('https://cdn.jsdelivr.net/npm/@mediapipe/hands/hands.js')
  await _loadScript('https://cdn.jsdelivr.net/npm/@mediapipe/camera_utils/camera_utils.js')

  const hands = new (window as any).Hands({
    locateFile: (f: string) => `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${f}`,
  })

  hands.setOptions({
    maxNumHands:           2,
    modelComplexity:       1,
    minDetectionConfidence: 0.7,
    minTrackingConfidence:  0.5,
  })

  hands.onResults(_processResults)

  _mpCamera = new (window as any).Camera(videoEl, {
    onFrame: async () => { await hands.send({ image: videoEl }) },
    width:  320,
    height: 240,
  })
  _mpCamera.start()
}

export function dispose(): void {
  _mpCamera?.stop()
  _mpCamera     = null
  _onGesture    = null
  camera3D      = null
  _prayerPhase  = 'none'
  _blastExpiresAt = null
  _freezeExpiresAt = null
  _hands.left  = _emptyHand()
  _hands.right = _emptyHand()
}

// ─── Result handler ───────────────────────────────────────────────────────────

function _processResults(results: any): void {
  const now = performance.now()

  // Mark both hands as not-detected this frame
  _hands.left.detectedThisFrame  = false
  _hands.right.detectedThisFrame = false

  const lms  = results.multiHandLandmarks  ?? []
  const meta = results.multiHandedness     ?? []

  for (let hi = 0; hi < lms.length; hi++) {
    const landmarks = lms[hi]
    const side: 'left' | 'right' = (meta[hi]?.label ?? 'Right') === 'Left' ? 'left' : 'right'
    const h = _hands[side]

    const raw     = _classifyRaw(landmarks)
    const worldPos = _landmarkToWorld(landmarks[9])
    const dt       = Math.max((now - h.prevTime) / 1000, 0.001)

    h.velocity.set(
      (worldPos.x - h.prevPos.x) / dt,
      (worldPos.y - h.prevPos.y) / dt,
      (worldPos.z - h.prevPos.z) / dt,
    )
    h.worldPos.copy(worldPos)
    h.rawGesture        = raw
    h.detectedThisFrame = true

    // Track fist onset for freeze detection
    if (raw === 'fist') {
      if (_lastFistTimes[side] === null) _lastFistTimes[side] = now
      if (h.fistSince === null) h.fistSince = now
    } else {
      _lastFistTimes[side] = null
      h.fistSince = null
    }

    h.prevPos.copy(worldPos)
    h.prevTime = now
  }

  const handCount = ((_hands.left.detectedThisFrame ? 1 : 0) + (_hands.right.detectedThisFrame ? 1 : 0)) as 0 | 1 | 2

  const rawGesture = _classifyUnified(handCount, now)
  const smoothed   = _smooth(rawGesture, handCount)

  const state = _buildState(smoothed, handCount, now)

  if (_onGesture) _onGesture(state)
}

// ─── Classification ───────────────────────────────────────────────────────────

function _classifyUnified(handCount: 0 | 1 | 2, now: number): UnifiedGesture {
  if (handCount === 0) return 'none'

  // Expire blast
  if (_blastExpiresAt !== null && now >= _blastExpiresAt) {
    _blastExpiresAt = null
    _prayerPhase    = 'none'
  }

  if (handCount === 2) {
    const L = _hands.left
    const R = _hands.right

    // ── 1. FREEZE: both fists within FREEZE_WINDOW ──────────────────────────
    if (L.rawGesture === 'fist' && R.rawGesture === 'fist') {
      const lt = _lastFistTimes.left; const rt = _lastFistTimes.right
      if (lt !== null && rt !== null && Math.abs(lt - rt) < FREEZE_WINDOW) {
        _freezeExpiresAt = now + 3000
        return 'freeze'
      }
    }

    // Sustain freeze until it expires
    if (_freezeExpiresAt !== null && now < _freezeExpiresAt) return 'freeze'
    if (_freezeExpiresAt !== null && now >= _freezeExpiresAt) _freezeExpiresAt = null

    // ── 2. EXPLOSION: prayer contact → fast separation ───────────────────────
    if (_prayerPhase === 'blast' && _blastExpiresAt !== null) return 'explosion'

    if (L.rawGesture === 'open' && R.rawGesture === 'open') {
      const dist = L.worldPos.distanceTo(R.worldPos)
      if (dist < PRAYER_DIST) {
        if (_prayerPhase === 'none') _prayerPhase = 'contact'
        // Check separation velocity
        const sepVel = L.velocity.clone().sub(R.velocity).length()
        if (_prayerPhase === 'contact' && sepVel > PRAYER_VEL) {
          _prayerPhase    = 'blast'
          _blastExpiresAt = now + 600
          return 'explosion'
        }
        return 'none' // contact phase — no gesture yet
      } else {
        if (_prayerPhase === 'contact') _prayerPhase = 'none'
      }
    } else {
      if (_prayerPhase === 'contact') _prayerPhase = 'none'
    }

    // ── 3. ORBIT: one pinch stable ≥ 500ms + other hand circles ≥ 180° ──────
    const pinchSide = L.rawGesture === 'pinch' ? 'left'
                    : R.rawGesture === 'pinch' ? 'right'
                    : null
    const freeSide  = pinchSide === 'left' ? 'right' : pinchSide === 'right' ? 'left' : null

    if (pinchSide && freeSide) {
      if (_orbitAnchorHand !== pinchSide) {
        _orbitAnchorHand  = pinchSide
        _orbitAnchorSince = now
        _orbitTotalDelta  = 0
        _orbitPrevAngle   = null
      }

      if (now - (_orbitAnchorSince ?? now) >= ORBIT_HOLD_MS) {
        const anchor = _hands[pinchSide].worldPos
        const free   = _hands[freeSide].worldPos
        const dx     = free.x - anchor.x
        const dy     = free.y - anchor.y
        const angle  = Math.atan2(dy, dx)

        if (_orbitPrevAngle !== null) {
          let delta = angle - _orbitPrevAngle
          if (delta >  Math.PI) delta -= 2 * Math.PI
          if (delta < -Math.PI) delta += 2 * Math.PI
          _orbitTotalDelta += Math.abs(delta)
        }
        _orbitPrevAngle = angle

        if (_orbitTotalDelta > Math.PI) return 'orbit'
      }
    } else {
      _orbitAnchorHand  = null
      _orbitAnchorSince = null
      _orbitTotalDelta  = 0
      _orbitPrevAngle   = null
    }

    // ── 4. PORTAL: both hands same height, 15–60 world units apart ───────────
    if (
      (L.rawGesture === 'open' || L.rawGesture === 'pinch') &&
      (R.rawGesture === 'open' || R.rawGesture === 'pinch')
    ) {
      const dist  = L.worldPos.distanceTo(R.worldPos)
      const yDiff = Math.abs(L.worldPos.y - R.worldPos.y)
      if (dist >= 15 && dist <= 60 && yDiff < 10) return 'portal'
    }

    return 'none'
  }

  // ── Single hand ──────────────────────────────────────────────────────────────
  const active = _hands.left.detectedThisFrame ? _hands.left : _hands.right

  if (active.rawGesture === 'pinch') return 'pinch'

  if (active.rawGesture === 'open') {
    // Swipe: horizontal velocity exceeds threshold
    if (Math.abs(active.velocity.x) > PRAYER_VEL) return 'swipe'
  }

  return 'none'
}

function _smooth(raw: UnifiedGesture, handCount: 0 | 1 | 2): UnifiedGesture {
  const holdFrames = handCount === 2 ? BIMANUAL_HOLD : HOLD_FRAMES

  if (handCount === 0) {
    _noHandCount++
    if (_noHandCount > MEMORY_FRAMES) {
      _committed      = 'none'
      _candidate      = 'none'
      _candidateCount = 0
    }
    return _committed
  }

  _noHandCount = 0

  if (raw === _candidate) {
    _candidateCount = Math.min(_candidateCount + 1, holdFrames + 1)
  } else {
    _candidate      = raw
    _candidateCount = 1
  }

  if (_candidateCount >= holdFrames) _committed = raw
  return _committed
}

function _buildState(gesture: UnifiedGesture, handCount: 0 | 1 | 2, now: number): UnifiedGestureState {
  let swipeSign    = 0
  let orbitAnchor  = new THREE.Vector3()
  let portalCenter = new THREE.Vector3()
  let portalRadius = 0
  let phase        = 'idle'

  switch (gesture) {
    case 'swipe': {
      const active = _hands.left.detectedThisFrame ? _hands.left : _hands.right
      swipeSign = Math.sign(active.velocity.x)
      phase     = 'instant'
      break
    }
    case 'explosion':
      phase = _prayerPhase === 'blast' ? 'blast' : 'contact'
      break
    case 'orbit': {
      if (_orbitAnchorHand) orbitAnchor.copy(_hands[_orbitAnchorHand].worldPos)
      phase = 'sustained'
      break
    }
    case 'portal': {
      portalCenter = _hands.left.worldPos.clone().add(_hands.right.worldPos).multiplyScalar(0.5)
      portalRadius = _hands.left.worldPos.distanceTo(_hands.right.worldPos) * 0.5
      phase        = 'sustained'
      break
    }
    case 'freeze':
      phase = 'instant'
      break
    case 'pinch':
      phase = 'sustained'
      break
    default:
      phase = 'idle'
  }

  return { gesture, handCount, swipeSign, orbitAnchor, portalCenter, portalRadius, phase }
}

// ─── Landmark helpers ─────────────────────────────────────────────────────────

function _classifyRaw(lm: any[]): RawGesture {
  const thumbTip  = lm[4]; const indexTip  = lm[8]
  const middleTip = lm[12]; const ringTip  = lm[16]; const pinkyTip = lm[20]

  if (_dist(thumbTip, indexTip) < PINCH_DIST) return 'pinch'

  const indexCurled  = indexTip.y  > lm[6].y
  const middleCurled = middleTip.y > lm[10].y
  const ringCurled   = ringTip.y   > lm[14].y
  const pinkyCurled  = pinkyTip.y  > lm[18].y

  if (indexCurled && middleCurled && ringCurled && pinkyCurled) return 'fist'

  if (!indexCurled && !middleCurled && !ringCurled && !pinkyCurled) return 'open'

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
    worldPos:          new THREE.Vector3(),
    velocity:          new THREE.Vector3(),
    prevPos:           new THREE.Vector3(),
    prevTime:          performance.now(),
    fistSince:         null,
    rawGesture:        'none',
    detectedThisFrame: false,
  }
}

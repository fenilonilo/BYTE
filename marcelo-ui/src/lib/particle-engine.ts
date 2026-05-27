import * as THREE from 'three'
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js'
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js'
import type { ParticleState } from './types'

// ─── Constants ────────────────────────────────────────────────────────────────

const COUNT       = 20_000
const HAND_RADIUS = 25
const MOUSE_RADIUS = 15

const STATE_PARAMS: Record<ParticleState, {
  hue: number; sat: number; bloom: number; rotSpeed: number; spread: number; core: number
}> = {
  idle:      { hue: 0.78, sat: 0.85, bloom: 1.8, rotSpeed: 0.15, spread: 10.4, core: 10 },
  listening: { hue: 0.60, sat: 0.90, bloom: 2.2, rotSpeed: 0.20, spread: 15.0, core: 8  },
  thinking:  { hue: 0.12, sat: 0.95, bloom: 2.5, rotSpeed: 0.50, spread: 18.0, core: 6  },
  speaking:  { hue: 0.35, sat: 0.80, bloom: 3.0, rotSpeed: 0.25, spread: 12.0, core: 9  },
}

// ─── Module-level state ───────────────────────────────────────────────────────

let scene: THREE.Scene
let camera: THREE.PerspectiveCamera
let renderer: THREE.WebGLRenderer
let composer: EffectComposer
let bloomPass: UnrealBloomPass
let instancedMesh: THREE.InstancedMesh
let clock: THREE.Clock

const positions:  THREE.Vector3[] = []
const velocities: THREE.Vector3[] = []
const dummy = new THREE.Object3D()
const color = new THREE.Color()
const target = new THREE.Vector3()

let currentState  = 'idle' as ParticleState
let currentHue    = STATE_PARAMS.idle.hue
let currentSat    = STATE_PARAMS.idle.sat
let currentBloom  = STATE_PARAMS.idle.bloom
let currentRot    = STATE_PARAMS.idle.rotSpeed
let currentSpread = STATE_PARAMS.idle.spread
let currentCore   = STATE_PARAMS.idle.core

let uAmplitude = 0.0
let smoothAmp  = 0.0

// One-shot effects active this frame
interface ActiveEffect {
  type: 'shockwave' | 'vortex' | 'orbit' | 'freeze' | 'split' | 'portal' | 'beam' | 'wave' | 'breathe'
  origin?: THREE.Vector3
  target?: THREE.Vector3
  pointA?: THREE.Vector3
  pointB?: THREE.Vector3
  direction?: THREE.Vector3
  dirSign?: number
  radius?: number
  force?: number
  strength?: number
  speed?: number
  expiresAt?: number   // Date.now() + duration
}

const activeEffects: ActiveEffect[] = []

// Hand state
let handActive   = false
let handPos      = new THREE.Vector3()
let handGesture  = 'none'
let handVelocity = new THREE.Vector3()

// Global gesture state (replaces hand-cursor approach for continuous gestures)
let _globalGesture: 'none' | 'attract' | 'repel' | 'breathe' = 'none'
let _globalOrigin  = new THREE.Vector3()  // center of effect (default scene origin)

let mouseNDC   = new THREE.Vector2(9999, 9999)
let isDragging = false

// Freeze state
let frozenUntil = 0

// ─── Shader material ──────────────────────────────────────────────────────────

const material = new THREE.ShaderMaterial({
  uniforms: {
    uTime:      { value: 0 },
    uAmplitude: { value: 0 },
  },
  vertexShader: `
    varying vec2 vUv;
    varying vec3 vColor;
    void main() {
      vUv = uv;
      vColor = instanceColor;
      gl_Position = projectionMatrix * modelViewMatrix * instanceMatrix * vec4(position, 1.0);
    }
  `,
  fragmentShader: `
    varying vec2 vUv;
    varying vec3 vColor;
    uniform float uTime;
    uniform float uAmplitude;
    float rand(vec2 n) { return fract(sin(dot(n, vec2(12.9898,4.1414))) * 43758.5453); }
    float noise(vec2 p) {
      vec2 ip = floor(p); vec2 u = fract(p); u = u*u*(3.0-2.0*u);
      return mix(
        mix(rand(ip), rand(ip+vec2(1,0)), u.x),
        mix(rand(ip+vec2(0,1)), rand(ip+vec2(1,1)), u.x),
        u.y
      );
    }
    void main() {
      float dist = distance(vUv, vec2(0.5));
      float n = noise(vUv * 5.0 + uTime * 0.5);
      float alpha = (1.0 - smoothstep(0.2, 0.5, dist)) * (0.5 + 0.5 * n);
      if (alpha < 0.1) discard;
      float ca = uAmplitude * 0.003;
      gl_FragColor = vec4(vColor.r + ca, vColor.g, vColor.b - ca, alpha * 0.8);
    }
  `,
  transparent: true,
  depthWrite: false,
  side: THREE.DoubleSide,
  blending: THREE.AdditiveBlending,
})

// ─── Public API ───────────────────────────────────────────────────────────────

export function init(canvas: HTMLCanvasElement): void {
  scene = new THREE.Scene()
  scene.fog = new THREE.FogExp2(0x000000, 0.01)

  camera = new THREE.PerspectiveCamera(60, canvas.clientWidth / canvas.clientHeight, 0.1, 2000)
  camera.position.set(0, 0, 100)

  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' })
  renderer.setSize(canvas.clientWidth, canvas.clientHeight)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))

  composer = new EffectComposer(renderer)
  composer.addPass(new RenderPass(scene, camera))
  bloomPass = new UnrealBloomPass(
    new THREE.Vector2(canvas.clientWidth, canvas.clientHeight),
    1.8, 0.4, 0,
  )
  composer.addPass(bloomPass)

  const geometry = new THREE.PlaneGeometry(0.8, 0.8)
  instancedMesh = new THREE.InstancedMesh(geometry, material, COUNT)
  instancedMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage)
  scene.add(instancedMesh)

  for (let i = 0; i < COUNT; i++) {
    positions.push(new THREE.Vector3(
      (Math.random() - 0.5) * 100,
      (Math.random() - 0.5) * 100,
      (Math.random() - 0.5) * 100,
    ))
    velocities.push(new THREE.Vector3())
    instancedMesh.setColorAt(i, color.setHSL(0.78, 0.85, 0.3))
  }

  clock = new THREE.Clock()

  window.addEventListener('resize', _onResize)
  _animate()
}

export function getCamera(): THREE.PerspectiveCamera { return camera }

export function setState(state: ParticleState): void {
  if (STATE_PARAMS[state]) currentState = state
}

export function setAmplitude(value: number): void {
  uAmplitude = Math.max(0, Math.min(1, value))
}

export function applyHandForce(worldPos: THREE.Vector3, gesture: string, velocity: THREE.Vector3): void {
  handActive   = true
  handPos.copy(worldPos)
  handGesture  = gesture
  handVelocity.copy(velocity)
}

export function clearHandForce(): void {
  handActive  = false
  handGesture = 'none'
}

/** Set a continuous global gesture effect. All particles affected regardless of position. */
export function setGlobalGesture(
  type: 'none' | 'attract' | 'repel' | 'breathe',
  origin?: THREE.Vector3,
): void {
  _globalGesture = type
  if (origin) _globalOrigin.copy(origin)
  else _globalOrigin.set(0, 0, 0)
}

/** Clear the global gesture. */
export function clearGlobalGesture(): void {
  _globalGesture = 'none'
}

export function setMouseNDC(ndcX: number, ndcY: number, dragging: boolean): void {
  mouseNDC.set(ndcX, ndcY)
  isDragging = dragging
}

export function dispose(): void {
  window.removeEventListener('resize', _onResize)
  _globalGesture = 'none'
  renderer.dispose()
}

// ─── New effect methods ───────────────────────────────────────────────────────

/** Radial shockwave from origin — prayer-explosion. Bloom flashes white for 400ms. */
export function shockwave(origin: THREE.Vector3, radius: number, force: number): void {
  activeEffects.push({ type: 'shockwave', origin: origin.clone(), radius, force })
  // Temporary bloom spike
  const saved = currentBloom
  bloomPass.strength = 6.0
  setTimeout(() => { bloomPass.strength = saved }, 400)
}

/** Vortex collapse toward target — implosion. */
export function vortex(targetPos: THREE.Vector3, strength: number): void {
  activeEffects.push({ type: 'vortex', target: targetPos.clone(), strength })
}

/** Orbit anchor — particles orbit around anchor continuously while active. Call clearHandForce() to stop. */
export function orbitAnchor(anchor: THREE.Vector3, radius: number): void {
  // Remove previous orbit
  const idx = activeEffects.findIndex(e => e.type === 'orbit')
  if (idx >= 0) activeEffects.splice(idx, 1)
  activeEffects.push({ type: 'orbit', origin: anchor.clone(), radius })
}

/** Freeze particles in place for durationMs. Color shifts to ice hue. */
export function crystallize(durationMs: number): void {
  frozenUntil = Date.now() + durationMs
  // Shift hue to ice
  currentHue = 0.58
  currentSat = 0.4
}

/** Two gravitational poles — dual-pinch. Replaces existing orbit if any. */
export function splitField(pointA: THREE.Vector3, pointB: THREE.Vector3): void {
  const idx = activeEffects.findIndex(e => e.type === 'split')
  if (idx >= 0) activeEffects.splice(idx, 1)
  activeEffects.push({ type: 'split', pointA: pointA.clone(), pointB: pointB.clone() })
}

/** Clear splitField effect. */
export function clearSplitField(): void {
  const idx = activeEffects.findIndex(e => e.type === 'split')
  if (idx >= 0) activeEffects.splice(idx, 1)
}

/** Portal ring — particles orbit a ring. Active while called each frame. */
export function portalRing(center: THREE.Vector3, ringRadius: number): void {
  const idx = activeEffects.findIndex(e => e.type === 'portal')
  if (idx >= 0) activeEffects.splice(idx, 1)
  activeEffects.push({ type: 'portal', origin: center.clone(), radius: ringRadius })
}

/** Clear portal effect. */
export function clearPortal(): void {
  const idx = activeEffects.findIndex(e => e.type === 'portal')
  if (idx >= 0) activeEffects.splice(idx, 1)
}

/** Directional beam — point gesture. Particles stream toward tip along direction. */
export function directionalBeam(tip: THREE.Vector3, direction: THREE.Vector3): void {
  const idx = activeEffects.findIndex(e => e.type === 'beam')
  if (idx >= 0) activeEffects.splice(idx, 1)
  activeEffects.push({ type: 'beam', origin: tip.clone(), direction: direction.clone().normalize() })
}

/** Clear beam effect. */
export function clearBeam(): void {
  const idx = activeEffects.findIndex(e => e.type === 'beam')
  if (idx >= 0) activeEffects.splice(idx, 1)
}

/** Lateral pressure wave — swipe. One-shot. dirSign: +1 = right, -1 = left. */
export function lateralWave(origin: THREE.Vector3, dirSign: number, speed: number): void {
  activeEffects.push({ type: 'wave', origin: origin.clone(), dirSign, speed })
}

/** Breathe pulse — rhythmic expansion from center while held. */
export function breathePulse(center: THREE.Vector3): void {
  const idx = activeEffects.findIndex(e => e.type === 'breathe')
  if (idx >= 0) activeEffects.splice(idx, 1)
  activeEffects.push({ type: 'breathe', origin: center.clone() })
}

/** Clear breathe effect. */
export function clearBreath(): void {
  const idx = activeEffects.findIndex(e => e.type === 'breathe')
  if (idx >= 0) activeEffects.splice(idx, 1)
}

// ─── Private helpers ──────────────────────────────────────────────────────────

function _onResize(): void {
  camera.aspect = window.innerWidth / window.innerHeight
  camera.updateProjectionMatrix()
  renderer.setSize(window.innerWidth, window.innerHeight)
  composer.setSize(window.innerWidth, window.innerHeight)
}

function _ndcToWorld(ndcX: number, ndcY: number): THREE.Vector3 {
  const v = new THREE.Vector3(ndcX, ndcY, 0.5)
  v.unproject(camera)
  const dir = v.sub(camera.position).normalize()
  const t = -camera.position.z / dir.z
  return camera.position.clone().add(dir.multiplyScalar(t))
}

function _tangent(v: THREE.Vector3): THREE.Vector3 {
  return new THREE.Vector3(-v.z, 0, v.x).normalize()
}

function _animate(): void {
  requestAnimationFrame(_animate)

  const now = Date.now()
  const frozen = now < frozenUntil

  // When freeze expires, restore state hue
  if (frozen === false && frozenUntil > 0 && now >= frozenUntil) {
    frozenUntil = 0
    currentHue = STATE_PARAMS[currentState].hue
    currentSat = STATE_PARAMS[currentState].sat
  }

  const delta = clock.getDelta()
  const time  = clock.getElapsedTime()

  const p = STATE_PARAMS[currentState]
  const lerpRate = 0.02
  if (!frozen) {
    currentHue    += (p.hue      - currentHue)    * lerpRate
    currentSat    += (p.sat      - currentSat)    * lerpRate
    currentBloom  += (p.bloom    - currentBloom)  * lerpRate
    currentRot    += (p.rotSpeed - currentRot)    * lerpRate
    currentSpread += (p.spread   - currentSpread) * lerpRate
    currentCore   += (p.core     - currentCore)   * lerpRate
  }

  smoothAmp += (uAmplitude - smoothAmp) * 0.1
  if (!frozen) bloomPass.strength = currentBloom + smoothAmp * 1.5

  material.uniforms.uTime.value      = time * 0.4
  material.uniforms.uAmplitude.value = smoothAmp

  const t    = time * 1.086
  const rotT = t * currentRot
  const cosR = Math.cos(rotT)
  const sinR = Math.sin(rotT)
  const mouseWorld = _ndcToWorld(mouseNDC.x, mouseNDC.y)

  // Expire one-shot wave effects after 1 frame
  for (let ei = activeEffects.length - 1; ei >= 0; ei--) {
    if (activeEffects[ei].type === 'wave' || activeEffects[ei].type === 'shockwave') {
      activeEffects.splice(ei, 1)
    }
  }

  for (let i = 0; i < COUNT; i++) {
    if (frozen) {
      // Crystallize: freeze pos, shift to ice color
      dummy.position.copy(positions[i])
      dummy.updateMatrix()
      instancedMesh.setMatrixAt(i, dummy.matrix)
      color.setHSL(0.58, 0.4, 0.4 + Math.random() * 0.1)
      instancedMesh.setColorAt(i, color)
      continue
    }

    const n1 = Math.abs((Math.sin(i * 12.9898) * 43758.5453) % 1.0)
    const n2 = Math.abs((Math.sin(i * 78.233)  * 43758.5453) % 1.0)
    const n3 = Math.abs((Math.sin(i * 93.989)  * 43758.5453) % 1.0)

    const radiusDist    = Math.pow(n3, 5.0)
    const currentRadius = currentCore + currentSpread * radiusDist
    const theta = n1 * Math.PI * 2.0
    const phi   = Math.acos((n2 * 2.0) - 1.0)

    let xBase = Math.cos(theta) * Math.sin(phi) * currentRadius
    let yBase = Math.sin(theta) * Math.sin(phi) * currentRadius
    let zBase = Math.cos(phi) * currentRadius

    const motion  = t + (n1 * 15.0)
    const breathe = Math.sin(t * 2.0) * (1.0 - radiusDist) * 0.5
                  + smoothAmp * Math.sin(t * 8.0 + i * 0.01) * 3.0

    xBase += Math.sin(motion + yBase * 0.2) * 0.8 + breathe
    yBase += Math.cos(motion + zBase * 0.2) * 0.8 + breathe
    zBase += Math.sin(motion + xBase * 0.2) * 0.8 + breathe

    const fx = xBase * cosR - zBase * sinR
    const fz = xBase * sinR + zBase * cosR
    target.set(fx, yBase, fz)

    // ── Global gesture (affects all particles from _globalOrigin) ──────────
    if (_globalGesture !== 'none') {
      const fromOrigin = positions[i].clone().sub(_globalOrigin)
      const d = fromOrigin.length() + 0.01  // avoid div-by-zero
      switch (_globalGesture) {
        case 'attract': {
          // Pull toward origin — stronger the farther away
          const pull = Math.min(1.0, d / 40)
          velocities[i].add(fromOrigin.normalize().multiplyScalar(-pull * 2.5 * delta * 60))
          break
        }
        case 'repel': {
          // Push away from origin
          const push = Math.min(1.0, 20 / (d + 5))
          velocities[i].add(fromOrigin.normalize().multiplyScalar(push * 2.0 * delta * 60))
          break
        }
        case 'breathe': {
          // Rhythmic expansion/contraction from origin
          const pulse = Math.sin(time * 2.5) * 1.2
          velocities[i].add(fromOrigin.normalize().multiplyScalar(pulse * delta * 60 * 0.6))
          break
        }
      }
    }

    // ── Hand force (KEEP for legacy mouse drag / beam direction) ─────────────
    if (handActive) {
      const toHand = handPos.clone().sub(positions[i])
      const dist   = toHand.length()
      const inf    = Math.max(0, 1 - dist / HAND_RADIUS) ** 2
      if (inf > 0) {
        switch (handGesture) {
          case 'flow':   velocities[i].add(handVelocity.clone().multiplyScalar(inf * 0.8)); break
          case 'rotate': velocities[i].add(_tangent(toHand).multiplyScalar(inf * 2.0)); break
          case 'attract':velocities[i].add(toHand.normalize().multiplyScalar(inf * 2.0)); break
          case 'explode':velocities[i].add(toHand.normalize().multiplyScalar(-inf * 5.0)); break
          case 'pinch':  velocities[i].add(toHand.multiplyScalar(inf * 3.0)); break
          case 'repel':  velocities[i].add(toHand.normalize().multiplyScalar(-inf * 1.5)); break
        }
      }
    }

    // ── New effects ───────────────────────────────────────────────────────
    for (const fx of activeEffects) {
      switch (fx.type) {
        case 'shockwave': {
          const away = positions[i].clone().sub(fx.origin!)
          const d = away.length()
          if (d < (fx.radius ?? 40)) {
            const inf = (1 - d / (fx.radius ?? 40)) ** 2
            velocities[i].add(away.normalize().multiplyScalar(inf * (fx.force ?? 6)))
          }
          break
        }
        case 'vortex': {
          const toTarget = fx.target!.clone().sub(positions[i])
          const d = toTarget.length()
          const inf = Math.max(0, 1 - d / 60) ** 2
          velocities[i].add(toTarget.normalize().multiplyScalar(inf * (fx.strength ?? 3)))
          velocities[i].add(_tangent(toTarget).multiplyScalar(inf * 1.5))
          break
        }
        case 'orbit': {
          const toAnchor = fx.origin!.clone().sub(positions[i])
          const d = toAnchor.length()
          const orbitR = fx.radius ?? 20
          const pullStr = d > orbitR ? 2.0 : -0.5
          velocities[i].add(toAnchor.normalize().multiplyScalar(pullStr * delta * 60))
          velocities[i].add(_tangent(toAnchor).multiplyScalar(1.8 * delta * 60))
          break
        }
        case 'split': {
          const toA = fx.pointA!.clone().sub(positions[i])
          const toB = fx.pointB!.clone().sub(positions[i])
          const dA  = toA.length(); const dB = toB.length()
          const nearest = dA < dB ? toA : toB
          const inf = Math.max(0, 1 - Math.min(dA, dB) / 35) ** 2
          velocities[i].add(nearest.normalize().multiplyScalar(inf * 2.5))
          break
        }
        case 'portal': {
          const toC = fx.origin!.clone().sub(positions[i])
          const d = toC.length()
          const rr = fx.radius ?? 15
          if (Math.abs(d - rr) < 10) {
            velocities[i].add(_tangent(toC).multiplyScalar(2.0 * delta * 60))
          } else {
            const pull = d > rr ? 1.5 : -0.8
            velocities[i].add(toC.normalize().multiplyScalar(pull * delta * 60))
          }
          break
        }
        case 'beam': {
          const toTip = fx.origin!.clone().sub(positions[i])
          const proj  = toTip.dot(fx.direction!)
          if (proj > 0 && proj < 30) {
            const perp = toTip.clone().sub(fx.direction!.clone().multiplyScalar(proj))
            if (perp.length() < 5) {
              velocities[i].add(fx.direction!.clone().multiplyScalar(1.5 * delta * 60))
            }
          }
          break
        }
        case 'wave': {
          // Full-screen sweep — affects all particles regardless of distance
          velocities[i].x += (fx.dirSign ?? 1) * (fx.speed ?? 4) * delta * 60 * 0.5
          break
        }
        case 'breathe': {
          const fromCenter = positions[i].clone().sub(fx.origin!)
          const d = fromCenter.length()
          const pulse = Math.sin(time * 2.5) * 0.8
          if (d < 30) {
            velocities[i].add(fromCenter.normalize().multiplyScalar(pulse * delta * 60))
          }
          break
        }
      }
    }

    // Mouse force
    const toMouse = mouseWorld.clone().sub(positions[i])
    const mDist   = toMouse.length()
    if (mDist < MOUSE_RADIUS) {
      const mInf     = (1 - mDist / MOUSE_RADIUS) ** 2
      const strength = isDragging ? 3.0 : 0.3
      velocities[i].add(toMouse.normalize().multiplyScalar(-mInf * strength))
    }

    positions[i].add(velocities[i].clone().multiplyScalar(delta))
    velocities[i].multiplyScalar(0.85)

    const speed = velocities[i].length()
    const lerpF = Math.max(0.03, 0.1 - speed * 0.01)
    positions[i].lerp(target, lerpF)

    dummy.position.copy(positions[i])
    dummy.updateMatrix()
    instancedMesh.setMatrixAt(i, dummy.matrix)

    const h = currentHue + (n1 * 0.08)
    const s = currentSat + (n2 * 0.15)
    const l = 0.15 + (1.0 - radiusDist) * 0.45 + smoothAmp * 0.2
    color.setHSL(h, s, l)
    instancedMesh.setColorAt(i, color)
  }

  instancedMesh.instanceMatrix.needsUpdate = true
  if (instancedMesh.instanceColor) instancedMesh.instanceColor.needsUpdate = true
  composer.render()
}

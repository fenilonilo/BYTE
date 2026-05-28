import * as THREE from 'three'
import { GPUComputationRenderer } from 'three/addons/misc/GPUComputationRenderer.js'
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js'
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js'
import {
  positionShader, velocityShader, renderVertexShader, renderFragmentShader,
} from './shaders'
import { resolveForce, FORCE_MODE, type ResolvedForce } from './effects'
import type { WireGestureEvent } from '../gesture-types'

const SIZE = 256 // grid edge -> SIZE*SIZE particles

let activeForce: ResolvedForce | null = null

export function applyGestureEvent(ev: WireGestureEvent): void {
  if (ev.phase === 'end' || ev.gesture === 'none') {
    activeForce = null
    return
  }
  activeForce = resolveForce(ev)
}

type ParticleState = 'idle' | 'listening' | 'thinking' | 'speaking'

const STATE_PARAMS: Record<ParticleState, { hue: number; spread: number; core: number; bloom: number }> = {
  idle:      { hue: 0.78, spread: 18, core: 8, bloom: 1.8 },
  listening: { hue: 0.60, spread: 22, core: 7, bloom: 2.2 },
  thinking:  { hue: 0.12, spread: 26, core: 6, bloom: 2.6 },
  speaking:  { hue: 0.35, spread: 20, core: 8, bloom: 3.0 },
}

let currentState: ParticleState = 'idle'
let bloomPass: UnrealBloomPass
let amplitude = 0
let smoothAmp = 0

export function setState(state: ParticleState): void {
  if (STATE_PARAMS[state]) currentState = state
}

export function setAmplitude(value: number): void {
  amplitude = Math.max(0, Math.min(1, value))
}

let renderer: THREE.WebGLRenderer
let scene: THREE.Scene
let camera: THREE.PerspectiveCamera
let composer: EffectComposer
let gpu: GPUComputationRenderer
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let positionVar: any
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let velocityVar: any
let renderUniforms: Record<string, THREE.IUniform>
let clock: THREE.Clock
let points: THREE.Points

function fillPositionTexture(tex: THREE.DataTexture): void {
  const data = tex.image.data as Float32Array
  for (let i = 0; i < data.length; i += 4) {
    const r = 10 + Math.random() * 6
    const theta = Math.random() * Math.PI * 2
    const phi = Math.acos(Math.random() * 2 - 1)
    data[i] = r * Math.cos(theta) * Math.sin(phi)
    data[i + 1] = r * Math.sin(theta) * Math.sin(phi)
    data[i + 2] = r * Math.cos(phi)
    data[i + 3] = 1
  }
}

function fillVelocityTexture(tex: THREE.DataTexture): void {
  const data = tex.image.data as Float32Array
  for (let i = 0; i < data.length; i += 4) {
    data[i] = data[i + 1] = data[i + 2] = 0
    data[i + 3] = 1
  }
}

export function init(canvas: HTMLCanvasElement): void {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' })
  renderer.setSize(canvas.clientWidth, canvas.clientHeight)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))

  scene = new THREE.Scene()
  scene.fog = new THREE.FogExp2(0x000000, 0.01)
  camera = new THREE.PerspectiveCamera(60, canvas.clientWidth / canvas.clientHeight, 0.1, 2000)
  camera.position.set(0, 0, 70)

  gpu = new GPUComputationRenderer(SIZE, SIZE, renderer)
  const pos0 = gpu.createTexture()
  const vel0 = gpu.createTexture()
  fillPositionTexture(pos0)
  fillVelocityTexture(vel0)

  positionVar = gpu.addVariable('texturePosition', positionShader, pos0)
  velocityVar = gpu.addVariable('textureVelocity', velocityShader, vel0)
  gpu.setVariableDependencies(positionVar, [positionVar, velocityVar])
  gpu.setVariableDependencies(velocityVar, [positionVar, velocityVar])

  positionVar.material.uniforms.uDelta = { value: 0 }
  Object.assign(velocityVar.material.uniforms, {
    uDelta: { value: 0 }, uTime: { value: 0 },
    uSpread: { value: 18 }, uCore: { value: 8 },
    uForceMode: { value: 0 }, uForceCenter: { value: new THREE.Vector3() },
    uForceVector: { value: new THREE.Vector3() }, uForceRadius: { value: 20 },
    uForceStrength: { value: 0 },
  })

  const err = gpu.init()
  if (err !== null) console.error('GPUComputationRenderer init error:', err)

  const count = SIZE * SIZE
  const positions = new Float32Array(count * 3)
  const uvs = new Float32Array(count * 2)
  let p = 0
  let u = 0
  for (let y = 0; y < SIZE; y++) {
    for (let x = 0; x < SIZE; x++) {
      positions[p++] = 0; positions[p++] = 0; positions[p++] = 0
      uvs[u++] = (x + 0.5) / SIZE
      uvs[u++] = (y + 0.5) / SIZE
    }
  }
  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  geo.setAttribute('uv', new THREE.BufferAttribute(uvs, 2))

  renderUniforms = {
    texturePosition: { value: null },
    textureVelocity: { value: null },
    uHue: { value: 0.78 },
  }
  const mat = new THREE.ShaderMaterial({
    uniforms: renderUniforms,
    vertexShader: renderVertexShader,
    fragmentShader: renderFragmentShader,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  })
  points = new THREE.Points(geo, mat)
  points.frustumCulled = false
  scene.add(points)

  composer = new EffectComposer(renderer)
  composer.addPass(new RenderPass(scene, camera))
  bloomPass = new UnrealBloomPass(
    new THREE.Vector2(canvas.clientWidth, canvas.clientHeight), 1.8, 0.4, 0,
  )
  composer.addPass(bloomPass)

  clock = new THREE.Clock()
  window.addEventListener('resize', onResize)
  animate()
}

function onResize(): void {
  camera.aspect = window.innerWidth / window.innerHeight
  camera.updateProjectionMatrix()
  renderer.setSize(window.innerWidth, window.innerHeight)
  composer.setSize(window.innerWidth, window.innerHeight)
}

function animate(): void {
  requestAnimationFrame(animate)
  const delta = Math.min(clock.getDelta(), 0.05)
  const time = clock.getElapsedTime()

  positionVar.material.uniforms.uDelta.value = delta
  velocityVar.material.uniforms.uDelta.value = delta
  velocityVar.material.uniforms.uTime.value = time

  const sp = STATE_PARAMS[currentState]
  const vu = velocityVar.material.uniforms
  vu.uSpread.value += (sp.spread - vu.uSpread.value) * 0.02
  vu.uCore.value += (sp.core - vu.uCore.value) * 0.02
  renderUniforms.uHue.value += (sp.hue - renderUniforms.uHue.value) * 0.02
  smoothAmp += (amplitude - smoothAmp) * 0.1
  bloomPass.strength += (sp.bloom + smoothAmp * 1.5 - bloomPass.strength) * 0.02

  const f = activeForce
  if (f) {
    vu.uForceMode.value = f.mode
    vu.uForceCenter.value.set(f.center[0], f.center[1], f.center[2])
    vu.uForceVector.value.set(f.vector[0], f.vector[1], f.vector[2])
    vu.uForceRadius.value = f.radius
    vu.uForceStrength.value += (f.strength - vu.uForceStrength.value) * 0.2
    if (f.oneShot) {
      f.strength = 0
      if (vu.uForceStrength.value < 0.02) activeForce = null
    }
  } else {
    vu.uForceMode.value = FORCE_MODE.none
    vu.uForceStrength.value += (0 - vu.uForceStrength.value) * 0.2
  }

  gpu.compute()
  renderUniforms.texturePosition.value = gpu.getCurrentRenderTarget(positionVar).texture
  renderUniforms.textureVelocity.value = gpu.getCurrentRenderTarget(velocityVar).texture
  composer.render()
}

export function dispose(): void {
  window.removeEventListener('resize', onResize)
  renderer.dispose()
}

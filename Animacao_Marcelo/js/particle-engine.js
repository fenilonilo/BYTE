// Particle swarm engine — Three.js, state machine, force fields, audio uniforms
import * as THREE from 'https://unpkg.com/three@0.160.0/build/three.module.js';
import { EffectComposer } from 'https://unpkg.com/three@0.160.0/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'https://unpkg.com/three@0.160.0/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'https://unpkg.com/three@0.160.0/examples/jsm/postprocessing/UnrealBloomPass.js';

const COUNT       = 20000;
const HAND_RADIUS = 25;
const MOUSE_RADIUS = 15;

const STATE_PARAMS = {
  idle:      { hue: 0.78, sat: 0.85, bloom: 1.8, rotSpeed: 0.15, spread: 10.4, core: 10 },
  listening: { hue: 0.60, sat: 0.90, bloom: 2.2, rotSpeed: 0.20, spread: 15.0, core: 8  },
  thinking:  { hue: 0.12, sat: 0.95, bloom: 2.5, rotSpeed: 0.50, spread: 18.0, core: 6  },
  speaking:  { hue: 0.35, sat: 0.80, bloom: 3.0, rotSpeed: 0.25, spread: 12.0, core: 9  },
};

let scene, camera, renderer, composer, bloomPass, instancedMesh, clock;
let positions, velocities;
const dummy = new THREE.Object3D();
const color  = new THREE.Color();
const target = new THREE.Vector3();

let currentState  = 'idle';
let currentHue    = STATE_PARAMS.idle.hue;
let currentSat    = STATE_PARAMS.idle.sat;
let currentBloom  = STATE_PARAMS.idle.bloom;
let currentRot    = STATE_PARAMS.idle.rotSpeed;
let currentSpread = STATE_PARAMS.idle.spread;
let currentCore   = STATE_PARAMS.idle.core;

let uAmplitude = 0.0;
let smoothAmp  = 0.0;

let handActive   = false;
let handPos      = new THREE.Vector3();
let handGesture  = 'none';
let handVelocity = new THREE.Vector3();

let mouseNDC   = new THREE.Vector2(9999, 9999);
let isDragging = false;

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
});

export function init(canvas) {
  scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x000000, 0.01);

  camera = new THREE.PerspectiveCamera(60, canvas.clientWidth / canvas.clientHeight, 0.1, 2000);
  camera.position.set(0, 0, 100);

  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
  renderer.setSize(canvas.clientWidth, canvas.clientHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

  composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  bloomPass = new UnrealBloomPass(
    new THREE.Vector2(canvas.clientWidth, canvas.clientHeight),
    1.8, 0.4, 0
  );
  composer.addPass(bloomPass);

  const geometry = new THREE.PlaneGeometry(0.8, 0.8);
  instancedMesh  = new THREE.InstancedMesh(geometry, material, COUNT);
  instancedMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  scene.add(instancedMesh);

  positions  = [];
  velocities = [];
  for (let i = 0; i < COUNT; i++) {
    positions.push(new THREE.Vector3(
      (Math.random() - 0.5) * 100,
      (Math.random() - 0.5) * 100,
      (Math.random() - 0.5) * 100,
    ));
    velocities.push(new THREE.Vector3());
    instancedMesh.setColorAt(i, color.setHSL(0.78, 0.85, 0.3));
  }

  clock = new THREE.Clock();

  window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
    composer.setSize(window.innerWidth, window.innerHeight);
  });

  _animate();
}

export function getCamera() {
  return camera;
}

export function setState(state) {
  if (!STATE_PARAMS[state]) return;
  currentState = state;
}

export function setAmplitude(value) {
  uAmplitude = Math.max(0, Math.min(1, value));
}

export function applyHandForce(worldPos, gesture, velocity) {
  handActive = true;
  handPos.copy(worldPos);
  handGesture  = gesture;
  handVelocity.copy(velocity || new THREE.Vector3());
}

export function clearHandForce() {
  handActive  = false;
  handGesture = 'none';
}

export function setMouseNDC(ndcX, ndcY, dragging) {
  mouseNDC.set(ndcX, ndcY);
  isDragging = dragging;
}

function _ndcToWorld(ndcX, ndcY) {
  const v = new THREE.Vector3(ndcX, ndcY, 0.5);
  v.unproject(camera);
  const dir = v.sub(camera.position).normalize();
  const t   = -camera.position.z / dir.z;
  return camera.position.clone().add(dir.multiplyScalar(t));
}

function _tangent(v) {
  return new THREE.Vector3(-v.z, 0, v.x).normalize();
}

function _animate() {
  requestAnimationFrame(_animate);
  const delta = clock.getDelta();
  const time  = clock.getElapsedTime();

  const p        = STATE_PARAMS[currentState];
  const lerpRate = 0.02;
  currentHue    += (p.hue      - currentHue)    * lerpRate;
  currentSat    += (p.sat      - currentSat)    * lerpRate;
  currentBloom  += (p.bloom    - currentBloom)  * lerpRate;
  currentRot    += (p.rotSpeed - currentRot)    * lerpRate;
  currentSpread += (p.spread   - currentSpread) * lerpRate;
  currentCore   += (p.core     - currentCore)   * lerpRate;

  smoothAmp += (uAmplitude - smoothAmp) * 0.1;
  bloomPass.strength = currentBloom + smoothAmp * 1.5;

  material.uniforms.uTime.value      = time * 0.4;
  material.uniforms.uAmplitude.value = smoothAmp;

  const t    = time * 1.086;
  const rotT = t * currentRot;
  const cosR = Math.cos(rotT);
  const sinR = Math.sin(rotT);

  const mouseWorld = _ndcToWorld(mouseNDC.x, mouseNDC.y);

  for (let i = 0; i < COUNT; i++) {
    const n1 = Math.abs((Math.sin(i * 12.9898) * 43758.5453) % 1.0);
    const n2 = Math.abs((Math.sin(i * 78.233)  * 43758.5453) % 1.0);
    const n3 = Math.abs((Math.sin(i * 93.989)  * 43758.5453) % 1.0);

    const radiusDist    = Math.pow(n3, 5.0);
    const currentRadius = currentCore + currentSpread * radiusDist;

    const theta = n1 * Math.PI * 2.0;
    const phi   = Math.acos((n2 * 2.0) - 1.0);

    let xBase = Math.cos(theta) * Math.sin(phi) * currentRadius;
    let yBase = Math.sin(theta) * Math.sin(phi) * currentRadius;
    let zBase = Math.cos(phi) * currentRadius;

    const motion  = t + (n1 * 15.0);
    const breathe = Math.sin(t * 2.0) * (1.0 - radiusDist) * 0.5
                  + smoothAmp * Math.sin(t * 8.0 + i * 0.01) * 3.0;

    xBase += Math.sin(motion + yBase * 0.2) * 0.8 + breathe;
    yBase += Math.cos(motion + zBase * 0.2) * 0.8 + breathe;
    zBase += Math.sin(motion + xBase * 0.2) * 0.8 + breathe;

    const fx = xBase * cosR - zBase * sinR;
    const fz = xBase * sinR + zBase * cosR;
    target.set(fx, yBase, fz);

    // Hand force
    if (handActive) {
      const toHand = handPos.clone().sub(positions[i]);
      const dist   = toHand.length();
      const inf    = Math.max(0, 1 - dist / HAND_RADIUS) ** 2;

      if (inf > 0) {
        switch (handGesture) {
          case 'flow':
            velocities[i].add(handVelocity.clone().multiplyScalar(inf * 0.8));
            break;
          case 'rotate':
            velocities[i].add(_tangent(toHand).multiplyScalar(inf * 2.0));
            break;
          case 'attract':
            velocities[i].add(toHand.normalize().multiplyScalar(inf * 2.0));
            break;
          case 'explode':
            velocities[i].add(toHand.normalize().multiplyScalar(-inf * 5.0));
            break;
          case 'pinch':
            velocities[i].add(toHand.multiplyScalar(inf * 3.0));
            break;
          case 'repel':
            velocities[i].add(toHand.normalize().multiplyScalar(-inf * 1.5));
            break;
        }
      }
    }

    // Mouse force
    const toMouse = mouseWorld.clone().sub(positions[i]);
    const mDist   = toMouse.length();
    if (mDist < MOUSE_RADIUS) {
      const mInf = (1 - mDist / MOUSE_RADIUS) ** 2;
      const strength = isDragging ? 3.0 : 0.3;
      velocities[i].add(toMouse.normalize().multiplyScalar(-mInf * strength));
    }

    // Apply velocity, damp
    positions[i].add(velocities[i].clone().multiplyScalar(delta));
    velocities[i].multiplyScalar(0.85);

    // Lerp toward swarm target — slower lerp = trail when pushed hard
    const speed = velocities[i].length();
    const lerpF = Math.max(0.03, 0.1 - speed * 0.01);
    positions[i].lerp(target, lerpF);

    dummy.position.copy(positions[i]);
    dummy.updateMatrix();
    instancedMesh.setMatrixAt(i, dummy.matrix);

    const h = currentHue + (n1 * 0.08);
    const s = currentSat + (n2 * 0.15);
    const l = 0.15 + (1.0 - radiusDist) * 0.45 + smoothAmp * 0.2;
    color.setHSL(h, s, l);
    instancedMesh.setColorAt(i, color);
  }

  instancedMesh.instanceMatrix.needsUpdate = true;
  instancedMesh.instanceColor.needsUpdate  = true;
  composer.render();
}

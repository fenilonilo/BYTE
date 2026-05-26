# Marcelo Particle UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fullscreen particle UI where the user speaks or types to the Marcelo AI agent; the Three.js particle swarm reacts via audio amplitude, state machine, and MediaPipe hand gestures.

**Architecture:** Standalone HTML/JS frontend (`Animacao_Marcelo/`) calls two new FastAPI endpoints — `POST /api/v1/tts` (Groq TTS → audio bytes) and `WebSocket /api/v1/ws/chat` (agent response). Four JS modules (`particle-engine`, `audio-analyzer`, `hand-tracker`, `chat-client`) are orchestrated by `marcelo_ui.html`.

**Tech Stack:** Three.js 0.160, MediaPipe Hands (CDN), Web Speech API (STT), Groq TTS (PlayAI), FastAPI WebSocket, Web Audio API AnalyserNode.

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Modify | `app/config.py` | Add `groq_tts_model`, `groq_tts_voice` settings |
| Modify | `main.py` | Add CORSMiddleware, import new routers |
| Create | `app/api/voice.py` | `POST /api/v1/tts` → Groq TTS → audio/mpeg bytes |
| Create | `app/api/ws_chat.py` | `WebSocket /api/v1/ws/chat` → ProcessIncomingMessage → stream text |
| Create | `tests/unit/api/test_voice.py` | Unit tests for /tts endpoint |
| Create | `tests/unit/api/test_ws_chat.py` | Unit tests for /ws/chat WebSocket |
| Create | `Animacao_Marcelo/js/particle-engine.js` | Three.js swarm + state machine + audio uniforms + force fields |
| Create | `Animacao_Marcelo/js/audio-analyzer.js` | Web Audio API analyser → amplitude/freq callbacks |
| Create | `Animacao_Marcelo/js/hand-tracker.js` | MediaPipe Hands → gesture classifier + world-space position |
| Create | `Animacao_Marcelo/js/chat-client.js` | WebSocket + Web Speech API STT + state dispatch |
| Create | `Animacao_Marcelo/marcelo_ui.html` | Entry point — imports modules, UI overlay HTML/CSS |

---

## Task 1: Add TTS Config Settings

**Files:**
- Modify: `app/config.py`

- [ ] **Step 1: Add TTS fields to Settings**

Open `app/config.py` and add two fields after the existing Groq block:

```python
# Groq TTS
groq_tts_model: str = "playai-tts"
groq_tts_voice: str = "Fritz-PlayAI"
```

Final Groq block in `app/config.py`:
```python
# Groq (Llama 3.3 70B — default model)
groq_api_key: str = ""
groq_model_id: str = "llama-3.3-70b-versatile"

# Groq TTS
groq_tts_model: str = "playai-tts"
groq_tts_voice: str = "Fritz-PlayAI"
```

- [ ] **Step 2: Verify pyright still passes**

```bash
pyright app/config.py
```

Expected: `0 errors, 0 warnings`

- [ ] **Step 3: Commit**

```bash
git add app/config.py
git commit -m "chore(config): add groq_tts_model and groq_tts_voice settings"
```

---

## Task 2: Add CORS Middleware to FastAPI

**Files:**
- Modify: `main.py`

CORS is required so the HTML file opened from `file://` can call `localhost` endpoints.

- [ ] **Step 1: Add CORSMiddleware import and config**

Replace the imports block in `main.py` with:

```python
from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import get_evolution_client, get_logger, get_settings
from app.api.router import router
from app.api.webhooks import router as webhook_router
```

After `app = FastAPI(title=settings.app_name, lifespan=lifespan)`, add:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- [ ] **Step 2: Run app and verify it starts**

```bash
uvicorn main:app --reload
```

Expected: `Application startup complete.` with no errors.

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "chore(api): add CORSMiddleware for local HTML file access"
```

---

## Task 3: POST /tts Endpoint

**Files:**
- Create: `app/api/voice.py`
- Create: `tests/unit/api/test_voice.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/api/test_voice.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.mark.unit
def test_tts_returns_audio_bytes() -> None:
    mock_audio = b"FAKE_MP3_BYTES"

    mock_response = MagicMock()
    mock_response.read.return_value = mock_audio

    mock_groq_instance = MagicMock()
    mock_groq_instance.audio.speech.create.return_value = mock_response

    with patch("app.api.voice.groq_sdk.Groq", return_value=mock_groq_instance):
        client = TestClient(app)
        response = client.post("/api/v1/tts", json={"text": "Olá, tudo bem?"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content == mock_audio


@pytest.mark.unit
def test_tts_calls_groq_with_correct_params() -> None:
    mock_response = MagicMock()
    mock_response.read.return_value = b"audio"

    mock_groq_instance = MagicMock()
    mock_groq_instance.audio.speech.create.return_value = mock_response

    with patch("app.api.voice.groq_sdk.Groq", return_value=mock_groq_instance):
        client = TestClient(app)
        client.post("/api/v1/tts", json={"text": "Teste"})

    call_kwargs = mock_groq_instance.audio.speech.create.call_args.kwargs
    assert call_kwargs["input"] == "Teste"
    assert "model" in call_kwargs
    assert "voice" in call_kwargs


@pytest.mark.unit
def test_tts_returns_422_for_empty_text() -> None:
    client = TestClient(app)
    response = client.post("/api/v1/tts", json={"text": ""})
    assert response.status_code == 422


@pytest.mark.unit
def test_tts_returns_422_for_missing_text() -> None:
    client = TestClient(app)
    response = client.post("/api/v1/tts", json={})
    assert response.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/api/test_voice.py -v
```

Expected: `ImportError` or `404` because `app/api/voice.py` doesn't exist yet.

- [ ] **Step 3: Create the TTS endpoint**

Create `app/api/voice.py`:

```python
from __future__ import annotations

import groq as groq_sdk
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, field_validator

from app.api.deps import get_settings

if False:  # TYPE_CHECKING
    from app.config import Settings

router = APIRouter()


class TTSRequestSchema(BaseModel):
    text: str

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be empty")
        return v


@router.post("/tts")
async def text_to_speech(
    body: TTSRequestSchema,
    settings: Settings = Depends(get_settings),
) -> Response:
    client = groq_sdk.Groq(api_key=settings.groq_api_key)
    audio_response = client.audio.speech.create(
        model=settings.groq_tts_model,
        voice=settings.groq_tts_voice,
        input=body.text,
        response_format="mp3",
    )
    return Response(content=audio_response.read(), media_type="audio/mpeg")
```

- [ ] **Step 4: Register the router in main.py**

Add to `main.py` imports:

```python
from app.api.voice import router as voice_router
```

Add after existing `app.include_router` calls:

```python
app.include_router(voice_router, prefix="/api/v1")
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/unit/api/test_voice.py -v
```

Expected: `4 passed`

- [ ] **Step 6: Run ruff + pyright**

```bash
ruff check app/api/voice.py && pyright app/api/voice.py
```

Expected: `0 errors`

- [ ] **Step 7: Commit**

```bash
git add app/api/voice.py tests/unit/api/test_voice.py main.py
git commit -m "feat(api): add POST /tts endpoint using Groq TTS"
```

---

## Task 4: WebSocket /ws/chat Endpoint

**Files:**
- Create: `app/api/ws_chat.py`
- Create: `tests/unit/api/test_ws_chat.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/api/test_ws_chat.py`:

```python
from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.domain.entities import OutgoingMessage
from main import app


def _make_outgoing(text: str) -> OutgoingMessage:
    return OutgoingMessage(
        content=text,
        channel="ui",
        recipient="local",
        model_used="groq",
        routed_from=None,
    )


@pytest.mark.unit
def test_ws_chat_returns_chunk_and_done() -> None:
    mock_use_case = MagicMock()
    mock_use_case.execute = AsyncMock(return_value=_make_outgoing("Olá! Como posso ajudar?"))

    with patch("app.api.ws_chat.ProcessIncomingMessage", return_value=mock_use_case):
        client = TestClient(app)
        with client.websocket_connect("/api/v1/ws/chat") as ws:
            ws.send_json({"message": "oi", "session_id": "test-session"})
            chunk = ws.receive_json()
            done = ws.receive_json()

    assert chunk["type"] == "chunk"
    assert chunk["text"] == "Olá! Como posso ajudar?"
    assert done["type"] == "done"


@pytest.mark.unit
def test_ws_chat_sends_error_on_exception() -> None:
    mock_use_case = MagicMock()
    mock_use_case.execute = AsyncMock(side_effect=RuntimeError("boom"))

    with patch("app.api.ws_chat.ProcessIncomingMessage", return_value=mock_use_case):
        client = TestClient(app)
        with client.websocket_connect("/api/v1/ws/chat") as ws:
            ws.send_json({"message": "oi", "session_id": "test-session"})
            error_msg = ws.receive_json()

    assert error_msg["type"] == "error"
    assert "boom" in error_msg["text"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/api/test_ws_chat.py -v
```

Expected: `ImportError` because `app/api/ws_chat.py` doesn't exist.

- [ ] **Step 3: Create the WebSocket endpoint**

Create `app/api/ws_chat.py`:

```python
from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.api.deps import get_agent, get_logger, get_repo
from app.application.use_cases.process_incoming_message import ProcessIncomingMessage
from app.domain.entities import IncomingMessage

router = APIRouter()


class _ChatPayload(BaseModel):
    message: str
    session_id: str = "default"


@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket) -> None:
    await websocket.accept()
    agent = get_agent()
    repo = get_repo()
    log = get_logger()

    try:
        while True:
            raw = await websocket.receive_json()
            payload = _ChatPayload.model_validate(raw)

            use_case = ProcessIncomingMessage(agent=agent, repo=repo, log=log)
            incoming = IncomingMessage(
                id=str(uuid4()),
                sender="local",
                content=payload.message,
                channel="ui",
                timestamp=datetime.now(tz=UTC),
                conversation_id=payload.session_id,
                model_override=None,
            )

            try:
                outgoing = await use_case.execute(incoming)
                await websocket.send_json({"type": "chunk", "text": outgoing.content})
                await websocket.send_json({"type": "done", "text": ""})
            except Exception as exc:
                await websocket.send_json({"type": "error", "text": str(exc)})

    except WebSocketDisconnect:
        pass
```

- [ ] **Step 4: Register the WebSocket router in main.py**

Add import to `main.py`:

```python
from app.api.ws_chat import router as ws_chat_router
```

Add after existing `app.include_router` calls:

```python
app.include_router(ws_chat_router, prefix="/api/v1")
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/unit/api/test_ws_chat.py -v
```

Expected: `2 passed`

- [ ] **Step 6: Run ruff + pyright**

```bash
ruff check app/api/ws_chat.py && pyright app/api/ws_chat.py
```

Expected: `0 errors`

- [ ] **Step 7: Commit**

```bash
git add app/api/ws_chat.py tests/unit/api/test_ws_chat.py main.py
git commit -m "feat(api): add WebSocket /ws/chat endpoint for UI agent communication"
```

---

## Task 5: particle-engine.js

**Files:**
- Create: `Animacao_Marcelo/js/particle-engine.js`

This module wraps the Three.js logic from `jarvis.html`, adds a 4-state machine, per-particle velocity for force fields, and GLSL uniforms for audio reactivity.

- [ ] **Step 1: Create the directory**

```bash
mkdir -p Animacao_Marcelo/js
```

- [ ] **Step 2: Create particle-engine.js**

Create `Animacao_Marcelo/js/particle-engine.js`:

```javascript
// Particle swarm engine — Three.js, state machine, force fields, audio uniforms
import * as THREE from 'https://unpkg.com/three@0.160.0/build/three.module.js';
import { EffectComposer } from 'https://unpkg.com/three@0.160.0/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'https://unpkg.com/three@0.160.0/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'https://unpkg.com/three@0.160.0/examples/jsm/postprocessing/UnrealBloomPass.js';

const COUNT = 20000;
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
let currentBloom  = STATE_PARAMS.idle.bloom;
let currentRot    = STATE_PARAMS.idle.rotSpeed;
let currentSpread = STATE_PARAMS.idle.spread;
let currentCore   = STATE_PARAMS.idle.core;

let uAmplitude = 0.0;
let smoothAmp  = 0.0;

// Hand force state
let handActive   = false;
let handPos      = new THREE.Vector3();
let handGesture  = 'none';
let handVelocity = new THREE.Vector3();

// Mouse force state
let mouseNDC    = new THREE.Vector2(9999, 9999);
let isDragging  = false;
let dragCluster = [];

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
      return mix(mix(rand(ip),rand(ip+vec2(1,0)),u.x),mix(rand(ip+vec2(0,1)),rand(ip+vec2(1,1)),u.x),u.y);
    }
    void main() {
      float dist = distance(vUv, vec2(0.5));
      float n = noise(vUv * 5.0 + uTime * 0.5);
      float alpha = (1.0 - smoothstep(0.2, 0.5, dist)) * (0.5 + 0.5 * n);
      if (alpha < 0.1) discard;
      // Chromatic aberration at amplitude peak
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
  scene    = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x000000, 0.01);

  camera   = new THREE.PerspectiveCamera(60, canvas.clientWidth / canvas.clientHeight, 0.1, 2000);
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

export function setState(state) {
  if (!STATE_PARAMS[state]) return;
  currentState = state;
}

export function setAmplitude(value) {
  uAmplitude = Math.max(0, Math.min(1, value));
}

export function applyHandForce(worldPos, gesture, velocity) {
  handActive   = true;
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

// Convert NDC mouse to approximate world position at z=0
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

  // Lerp state params
  const p = STATE_PARAMS[currentState];
  const lerpRate = 0.02;
  currentHue    += (p.hue    - currentHue)    * lerpRate;
  currentBloom  += (p.bloom  - currentBloom)  * lerpRate;
  currentRot    += (p.rotSpeed - currentRot)  * lerpRate;
  currentSpread += (p.spread - currentSpread) * lerpRate;
  currentCore   += (p.core   - currentCore)   * lerpRate;

  // Smooth amplitude
  smoothAmp += (uAmplitude - smoothAmp) * 0.1;

  // Update bloom
  bloomPass.strength = currentBloom + smoothAmp * 1.5;

  // Update shader uniforms
  material.uniforms.uTime.value      = time * 0.4;
  material.uniforms.uAmplitude.value = smoothAmp;

  const speed  = 1.086;
  const t      = time * speed;
  const rotT   = t * currentRot;
  const cosR   = Math.cos(rotT);
  const sinR   = Math.sin(rotT);

  // Mouse world pos
  const mouseWorld = _ndcToWorld(mouseNDC.x, mouseNDC.y);

  for (let i = 0; i < COUNT; i++) {
    const n1 = Math.abs((Math.sin(i * 12.9898)  * 43758.5453) % 1.0);
    const n2 = Math.abs((Math.sin(i * 78.233)   * 43758.5453) % 1.0);
    const n3 = Math.abs((Math.sin(i * 93.989)   * 43758.5453) % 1.0);

    const radiusDist   = Math.pow(n3, 5.0);
    const currentRadius = currentCore + currentSpread * radiusDist;

    const theta  = n1 * Math.PI * 2.0;
    const phi    = Math.acos((n2 * 2.0) - 1.0);

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

    // --- Hand force ---
    if (handActive) {
      const toHand = handPos.clone().sub(positions[i]);
      const dist   = toHand.length();
      const inf    = Math.max(0, 1 - dist / HAND_RADIUS) ** 2;

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

    // --- Mouse force ---
    const toMouse = mouseWorld.clone().sub(positions[i]);
    const mDist   = toMouse.length();
    if (mDist < MOUSE_RADIUS) {
      const mInf = (1 - mDist / MOUSE_RADIUS) ** 2;
      if (isDragging) {
        velocities[i].add(toMouse.normalize().multiplyScalar(-mInf * 3.0));
      } else {
        velocities[i].add(toMouse.normalize().multiplyScalar(-mInf * 0.3));
      }
    }

    // Apply velocity and damp
    positions[i].add(velocities[i].clone().multiplyScalar(delta));
    velocities[i].multiplyScalar(0.85);

    // Lerp to swarm target (trail: slower lerp when velocity is high)
    const speed2 = velocities[i].length();
    const lerpF  = Math.max(0.03, 0.1 - speed2 * 0.01);
    positions[i].lerp(target, lerpF);

    dummy.position.copy(positions[i]);
    dummy.updateMatrix();
    instancedMesh.setMatrixAt(i, dummy.matrix);

    const h = currentHue + (n1 * 0.08);
    const s = p.sat + (n2 * 0.15);
    const l = 0.15 + (1.0 - radiusDist) * 0.45 + smoothAmp * 0.2;
    color.setHSL(h, s, l);
    instancedMesh.setColorAt(i, color);
  }

  instancedMesh.instanceMatrix.needsUpdate = true;
  instancedMesh.instanceColor.needsUpdate  = true;
  composer.render();
}
```

- [ ] **Step 3: Open `Animacao_Marcelo/jarvis.html` in browser and verify the original still works (no changes made)**

- [ ] **Step 4: Commit**

```bash
git add Animacao_Marcelo/js/particle-engine.js
git commit -m "feat(ui): add particle-engine.js with state machine, force fields, audio uniforms"
```

---

## Task 6: audio-analyzer.js

**Files:**
- Create: `Animacao_Marcelo/js/audio-analyzer.js`

- [ ] **Step 1: Create audio-analyzer.js**

Create `Animacao_Marcelo/js/audio-analyzer.js`:

```javascript
// Web Audio API analyser — decodes TTS audio bytes and streams amplitude to callback
// Also supports mic stream analysis for listening state

let audioCtx = null;

function _getCtx() {
  if (!audioCtx) audioCtx = new AudioContext();
  return audioCtx;
}

/**
 * Play TTS audio bytes and call onAmplitude(0.0-1.0) each animation frame.
 * Returns a Promise that resolves when playback ends.
 */
export async function playAndAnalyze(arrayBuffer, onAmplitude) {
  const ctx      = _getCtx();
  const decoded  = await ctx.decodeAudioData(arrayBuffer.slice(0));

  const analyser = ctx.createAnalyser();
  analyser.fftSize = 512;
  analyser.smoothingTimeConstant = 0.8;

  const source = ctx.createBufferSource();
  source.buffer = decoded;
  source.connect(analyser);
  analyser.connect(ctx.destination);
  source.start();

  const freqData = new Uint8Array(analyser.frequencyBinCount);
  let rafId;

  return new Promise((resolve) => {
    function tick() {
      analyser.getByteFrequencyData(freqData);
      const avg = freqData.reduce((s, v) => s + v, 0) / freqData.length;
      onAmplitude(avg / 255);
      rafId = requestAnimationFrame(tick);
    }

    source.onended = () => {
      cancelAnimationFrame(rafId);
      onAmplitude(0);
      resolve();
    };

    rafId = requestAnimationFrame(tick);
  });
}

/**
 * Analyze microphone stream. Returns a stop() function.
 * Calls onAmplitude(0.0-1.0) each frame while active.
 */
export function analyzeMicStream(stream, onAmplitude) {
  const ctx      = _getCtx();
  const source   = ctx.createMediaStreamSource(stream);
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 256;
  analyser.smoothingTimeConstant = 0.6;

  source.connect(analyser);

  const freqData = new Uint8Array(analyser.frequencyBinCount);
  let active = true;
  let rafId;

  function tick() {
    if (!active) return;
    analyser.getByteFrequencyData(freqData);
    const avg = freqData.reduce((s, v) => s + v, 0) / freqData.length;
    onAmplitude(avg / 255);
    rafId = requestAnimationFrame(tick);
  }

  rafId = requestAnimationFrame(tick);

  return function stop() {
    active = false;
    cancelAnimationFrame(rafId);
    onAmplitude(0);
    source.disconnect();
  };
}
```

- [ ] **Step 2: Commit**

```bash
git add Animacao_Marcelo/js/audio-analyzer.js
git commit -m "feat(ui): add audio-analyzer.js for TTS and mic amplitude extraction"
```

---

## Task 7: hand-tracker.js

**Files:**
- Create: `Animacao_Marcelo/js/hand-tracker.js`

Loads MediaPipe Hands from CDN. Classifies gestures from 21 landmarks. Converts normalized [0,1] landmark positions to Three.js world-space using camera frustum.

- [ ] **Step 1: Create hand-tracker.js**

Create `Animacao_Marcelo/js/hand-tracker.js`:

```javascript
// MediaPipe Hands gesture tracker
// Loads from CDN, runs on hidden video element

const GESTURE_THRESHOLDS = {
  pinchDist:    0.06,  // normalized thumb-index distance
  fistMaxExt:   0.15,  // max tip-to-wrist distance for curl
  pointMaxOthers: 0.12, // other fingers must be curled for pointer gesture
  explosiveMs:  150,   // max ms for fist→open to count as explode
};

let handsInstance = null;
let lastGesture   = 'none';
let lastFistTime  = null;
let camera3D      = null;  // Three.js camera for world-space projection

let prevPalmPos = { x: 0, y: 0, z: 0 };
let prevTime    = performance.now();

/**
 * @param {HTMLVideoElement} videoEl
 * @param {THREE.PerspectiveCamera} camera — used to unproject landmarks to world space
 * @param {Function} onGesture — called each frame: ({gesture, worldPos, velocity})
 */
export async function init(videoEl, camera, onGesture) {
  camera3D = camera;

  // Dynamically load MediaPipe from CDN
  const script1 = Object.assign(document.createElement('script'), {
    src: 'https://cdn.jsdelivr.net/npm/@mediapipe/hands/hands.js',
  });
  const script2 = Object.assign(document.createElement('script'), {
    src: 'https://cdn.jsdelivr.net/npm/@mediapipe/camera_utils/camera_utils.js',
  });

  document.head.appendChild(script1);
  await new Promise(r => { script1.onload = r; });
  document.head.appendChild(script2);
  await new Promise(r => { script2.onload = r; });

  handsInstance = new window.Hands({
    locateFile: (f) => `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${f}`,
  });

  handsInstance.setOptions({
    maxNumHands: 1,
    modelComplexity: 1,
    minDetectionConfidence: 0.7,
    minTrackingConfidence: 0.5,
  });

  handsInstance.onResults((results) => {
    if (!results.multiHandLandmarks || results.multiHandLandmarks.length === 0) {
      onGesture({ gesture: 'none', worldPos: null, velocity: null });
      lastGesture = 'none';
      return;
    }

    const lm       = results.multiHandLandmarks[0];
    const gesture  = _classify(lm);
    const worldPos = _landmarkToWorld(lm[9]);  // palm center (landmark 9)

    const now    = performance.now();
    const dt     = (now - prevTime) / 1000;
    prevTime     = now;
    const velocity = dt > 0 ? {
      x: (worldPos.x - prevPalmPos.x) / dt,
      y: (worldPos.y - prevPalmPos.y) / dt,
      z: (worldPos.z - prevPalmPos.z) / dt,
    } : { x: 0, y: 0, z: 0 };

    prevPalmPos = { ...worldPos };
    lastGesture = gesture;
    onGesture({ gesture, worldPos, velocity });
  });

  const mpCamera = new window.Camera(videoEl, {
    onFrame: async () => { await handsInstance.send({ image: videoEl }); },
    width: 320,
    height: 240,
  });
  mpCamera.start();
}

function _dist(a, b) {
  return Math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2);
}

function _classify(lm) {
  const wrist     = lm[0];
  const thumbTip  = lm[4];
  const indexTip  = lm[8];
  const middleTip = lm[12];
  const ringTip   = lm[16];
  const pinkyTip  = lm[20];
  const indexMcp  = lm[5];

  // Pinch: thumb-index close
  if (_dist(thumbTip, indexTip) < GESTURE_THRESHOLDS.pinchDist) {
    return 'pinch';
  }

  // Determine curl per finger (tip y > mcp y in image coords = curled)
  const indexCurled  = indexTip.y  > lm[6].y;
  const middleCurled = middleTip.y > lm[10].y;
  const ringCurled   = ringTip.y   > lm[14].y;
  const pinkyCurled  = pinkyTip.y  > lm[18].y;

  // Fist: all curled
  const allCurled = indexCurled && middleCurled && ringCurled && pinkyCurled;
  if (allCurled) {
    if (lastGesture !== 'fist') lastFistTime = performance.now();
    return 'attract';  // fist = attract vortex
  }

  // Explosive open: was fist, now open within threshold
  if (lastGesture === 'attract' && lastFistTime !== null) {
    const elapsed = performance.now() - lastFistTime;
    if (elapsed < GESTURE_THRESHOLDS.explosiveMs) {
      lastFistTime = null;
      return 'explode';
    }
  }

  // Point: only index extended
  if (!indexCurled && middleCurled && ringCurled && pinkyCurled) {
    return 'repel';
  }

  // Wrist rotation: velocity has dominant rotational component
  // (simplified: use gesture 'rotate' when all fingers extended + hand is tilted)
  const allOpen = !indexCurled && !middleCurled && !ringCurled && !pinkyCurled;
  if (allOpen) {
    // Check wrist tilt via landmark 0 vs 9 angle
    const dx = lm[9].x - lm[0].x;
    const dy = lm[9].y - lm[0].y;
    const angle = Math.abs(Math.atan2(dy, dx));
    if (angle < 0.5 || angle > 2.6) {
      return 'rotate';
    }
    return 'flow';
  }

  return 'none';
}

function _landmarkToWorld(lm) {
  // lm is normalized [0,1]. Map to NDC [-1,1] (note Y is flipped in image space)
  const ndcX = (lm.x * 2) - 1;
  const ndcY = -(lm.y * 2) + 1;

  // Use window.THREE because hand-tracker.js is a module — THREE is not imported here,
  // but marcelo_ui.html sets window.THREE before calling init().
  const THREE = window.THREE;
  const v   = new THREE.Vector3(ndcX, ndcY, 0.5);
  v.unproject(camera3D);
  const dir = v.sub(camera3D.position).normalize();
  const t   = -camera3D.position.z / dir.z;
  const wp  = camera3D.position.clone().add(dir.multiplyScalar(t));

  return { x: wp.x, y: wp.y, z: wp.z };
}
```

> **Note:** `THREE` must be available on `window` when this module runs, or import it the same way as particle-engine.js. The `marcelo_ui.html` imports Three.js first via importmap, so `THREE` is available globally after `particle-engine.js` assigns it.

- [ ] **Step 2: Commit**

```bash
git add Animacao_Marcelo/js/hand-tracker.js
git commit -m "feat(ui): add hand-tracker.js with MediaPipe Hands gesture classification"
```

---

## Task 8: chat-client.js

**Files:**
- Create: `Animacao_Marcelo/js/chat-client.js`

Manages WebSocket connection, Web Speech API STT, and fires state change callbacks.

- [ ] **Step 1: Create chat-client.js**

Create `Animacao_Marcelo/js/chat-client.js`:

```javascript
// Chat client — WebSocket to /ws/chat + Web Speech API STT
// Fires callbacks: onState, onTranscript, onResponse, onError

export class ChatClient {
  constructor({ wsUrl, ttsUrl, onState, onTranscript, onResponse, onError }) {
    this._wsUrl      = wsUrl;
    this._ttsUrl     = ttsUrl;
    this._onState    = onState    || (() => {});
    this._onTranscript = onTranscript || (() => {});
    this._onResponse = onResponse || (() => {});
    this._onError    = onError    || (() => {});

    this._ws         = null;
    this._recognition = null;
    this._sessionId  = 'ui-session';
    this._micStream  = null;
    this._micStopFn  = null;
    this._silenceTimer = null;
  }

  connect() {
    this._ws = new WebSocket(this._wsUrl);

    this._ws.onopen = () => {
      this._onState('idle');
    };

    this._ws.onmessage = async (ev) => {
      const msg = JSON.parse(ev.data);

      if (msg.type === 'chunk') {
        this._onResponse(msg.text);
        await this._speakTTS(msg.text);
        this._onState('idle');
      } else if (msg.type === 'error') {
        this._onError(msg.text);
        this._onState('idle');
      }
    };

    this._ws.onerror = (ev) => {
      this._onError('WebSocket error');
    };

    this._ws.onclose = () => {
      // Reconnect after 2s
      setTimeout(() => this.connect(), 2000);
    };
  }

  sendText(text) {
    if (!text.trim()) return;
    this._onTranscript({ role: 'user', text });
    this._onState('thinking');
    this._ws.send(JSON.stringify({ message: text, session_id: this._sessionId }));
  }

  async startMic(onMicAmplitude) {
    if (this._recognition) return;

    try {
      this._micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      this._onError('Microphone permission denied');
      return;
    }

    this._onState('listening');
    if (onMicAmplitude) {
      const { analyzeMicStream } = await import('./audio-analyzer.js');
      this._micStopFn = analyzeMicStream(this._micStream, onMicAmplitude);
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      this._onError('Web Speech API not supported in this browser');
      return;
    }

    this._recognition = new SpeechRecognition();
    this._recognition.lang = 'pt-BR';
    this._recognition.continuous = false;
    this._recognition.interimResults = true;

    this._recognition.onresult = (ev) => {
      const transcript = Array.from(ev.results)
        .map(r => r[0].transcript)
        .join('');

      this._onTranscript({ role: 'interim', text: transcript });

      // Reset silence timer on each result
      clearTimeout(this._silenceTimer);
      this._silenceTimer = setTimeout(() => this.stopMic(), 2000);

      if (ev.results[ev.results.length - 1].isFinal) {
        this.stopMic();
        this.sendText(transcript);
      }
    };

    this._recognition.onerror = () => this.stopMic();
    this._recognition.onend   = () => this.stopMic();
    this._recognition.start();
  }

  stopMic() {
    if (this._micStopFn) { this._micStopFn(); this._micStopFn = null; }
    if (this._recognition) { this._recognition.stop(); this._recognition = null; }
    if (this._micStream)   { this._micStream.getTracks().forEach(t => t.stop()); this._micStream = null; }
    clearTimeout(this._silenceTimer);
  }

  async _speakTTS(text) {
    this._onState('speaking');
    try {
      const res = await fetch(this._ttsUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });

      if (!res.ok) throw new Error(`TTS HTTP ${res.status}`);

      const buffer = await res.arrayBuffer();
      const { playAndAnalyze } = await import('./audio-analyzer.js');
      await playAndAnalyze(buffer, (amp) => {
        // Caller (marcelo_ui.html) can listen via onAmplitudeUpdate
        if (this._onAmplitudeUpdate) this._onAmplitudeUpdate(amp);
      });
    } catch (err) {
      this._onError(`TTS error: ${err.message}`);
    }
  }

  setAmplitudeCallback(fn) {
    this._onAmplitudeUpdate = fn;
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add Animacao_Marcelo/js/chat-client.js
git commit -m "feat(ui): add chat-client.js with WebSocket, STT, TTS orchestration"
```

---

## Task 9: marcelo_ui.html — Assembly

**Files:**
- Create: `Animacao_Marcelo/marcelo_ui.html`

Imports all modules, wires state callbacks, provides UI overlay (transcript, mic button, text input, webcam preview).

- [ ] **Step 1: Create marcelo_ui.html**

Create `Animacao_Marcelo/marcelo_ui.html`:

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Marcelo — Interface</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: #000; overflow: hidden; font-family: 'Segoe UI', system-ui, sans-serif; }

    #canvas { position: fixed; inset: 0; width: 100vw; height: 100vh; }

    #transcript {
      position: fixed; top: 20px; left: 20px;
      max-width: 420px; max-height: 220px; overflow: hidden;
      background: rgba(0,0,0,0.45);
      backdrop-filter: blur(12px);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 12px; padding: 12px 16px;
      display: flex; flex-direction: column; gap: 8px;
    }

    .msg { font-size: 13px; line-height: 1.5; animation: fadeIn 0.3s ease; }
    .msg.user      { color: #a0cfff; }
    .msg.assistant { color: #b8ffcb; }
    .msg.interim   { color: rgba(255,255,255,0.4); font-style: italic; }

    @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; } }

    #webcam-wrap {
      position: fixed; bottom: 80px; left: 20px;
      width: 160px; height: 120px;
      border-radius: 10px; overflow: hidden;
      border: 1px solid rgba(255,255,255,0.12);
      opacity: 0.6;
    }
    #webcam { width: 100%; height: 100%; object-fit: cover; transform: scaleX(-1); }

    #dock {
      position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
      display: flex; align-items: center; gap: 10px;
      background: rgba(0,0,0,0.55); backdrop-filter: blur(16px);
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 32px; padding: 10px 16px;
      width: min(600px, 90vw);
    }

    #text-input {
      flex: 1; background: transparent; border: none; outline: none;
      color: #fff; font-size: 14px; caret-color: #7cf;
    }
    #text-input::placeholder { color: rgba(255,255,255,0.3); }

    .dock-btn {
      background: none; border: none; cursor: pointer;
      color: rgba(255,255,255,0.6); font-size: 18px; padding: 4px 8px;
      border-radius: 8px; transition: color 0.2s, background 0.2s;
    }
    .dock-btn:hover { color: #fff; background: rgba(255,255,255,0.1); }
    .dock-btn.active { color: #f55; }

    #state-badge {
      position: fixed; top: 20px; right: 20px;
      font-size: 11px; text-transform: uppercase; letter-spacing: 1px;
      color: rgba(255,255,255,0.35); padding: 4px 10px;
      border: 1px solid rgba(255,255,255,0.1); border-radius: 20px;
    }
  </style>
</head>
<body>
  <canvas id="canvas"></canvas>

  <div id="transcript"></div>

  <div id="webcam-wrap">
    <video id="webcam" autoplay playsinline muted></video>
  </div>

  <div id="dock">
    <input id="text-input" type="text" placeholder="Fale ou escreva para o Marcelo..." autocomplete="off">
    <button class="dock-btn" id="mic-btn" title="Microfone">🎤</button>
    <button class="dock-btn" id="send-btn" title="Enviar">➤</button>
  </div>

  <div id="state-badge">idle</div>

  <script type="importmap">
  {
    "imports": {
      "three": "https://unpkg.com/three@0.160.0/build/three.module.js"
    }
  }
  </script>

  <script type="module">
    import * as THREE from 'three';
    // Expose THREE globally for hand-tracker.js (needs THREE.Vector3)
    window.THREE = THREE;

    import { init as particleInit, setState, setAmplitude, applyHandForce, clearHandForce, setMouseNDC } from './js/particle-engine.js';
    import { init as handTrackerInit } from './js/hand-tracker.js';
    import { ChatClient } from './js/chat-client.js';

    const WS_URL  = 'ws://localhost:8000/api/v1/ws/chat';
    const TTS_URL = 'http://localhost:8000/api/v1/tts';

    // --- Particle engine ---
    const canvas = document.getElementById('canvas');
    particleInit(canvas);

    // --- Chat client ---
    const client = new ChatClient({
      wsUrl: WS_URL,
      ttsUrl: TTS_URL,
      onState: (s) => {
        setState(s);
        document.getElementById('state-badge').textContent = s;
      },
      onTranscript: ({ role, text }) => addTranscript(role, text),
      onResponse:   (text) => addTranscript('assistant', text),
      onError:      (msg)  => console.error('[Marcelo]', msg),
    });
    client.setAmplitudeCallback((amp) => setAmplitude(amp));
    client.connect();

    // --- Transcript ---
    const MAX_MESSAGES = 3;
    const transcriptEl = document.getElementById('transcript');
    let interimEl = null;

    function addTranscript(role, text) {
      if (role === 'interim') {
        if (!interimEl) {
          interimEl = document.createElement('div');
          interimEl.className = 'msg interim';
          transcriptEl.appendChild(interimEl);
        }
        interimEl.textContent = text;
      } else {
        interimEl = null;
        const div = document.createElement('div');
        div.className = `msg ${role === 'user' ? 'user' : 'assistant'}`;
        div.textContent = (role === 'user' ? 'Você: ' : 'Marcelo: ') + text;
        transcriptEl.appendChild(div);
        // Keep max 3 messages (remove interim + old)
        while (transcriptEl.children.length > MAX_MESSAGES) {
          transcriptEl.removeChild(transcriptEl.firstChild);
        }
      }
    }

    // --- Mic button ---
    const micBtn  = document.getElementById('mic-btn');
    let micActive = false;

    micBtn.addEventListener('click', async () => {
      if (micActive) {
        client.stopMic();
        micActive = false;
        micBtn.classList.remove('active');
      } else {
        micActive = true;
        micBtn.classList.add('active');
        await client.startMic((amp) => setAmplitude(amp));
        micActive = false;
        micBtn.classList.remove('active');
      }
    });

    // --- Send button / Enter key ---
    const textInput = document.getElementById('text-input');
    const sendBtn   = document.getElementById('send-btn');

    function sendText() {
      const text = textInput.value.trim();
      if (!text) return;
      textInput.value = '';
      client.sendText(text);
    }

    sendBtn.addEventListener('click', sendText);
    textInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendText(); }
    });

    // --- Mouse interaction ---
    let mouseDown = false;

    canvas.addEventListener('mousemove', (e) => {
      const ndcX =  (e.clientX / window.innerWidth)  * 2 - 1;
      const ndcY = -(e.clientY / window.innerHeight) * 2 + 1;
      setMouseNDC(ndcX, ndcY, mouseDown);
    });
    canvas.addEventListener('mousedown', () => { mouseDown = true; });
    canvas.addEventListener('mouseup',   () => { mouseDown = false; });

    // --- Hand tracker ---
    const videoEl = document.getElementById('webcam');

    // Request webcam (needed both for display and MediaPipe)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      videoEl.srcObject = stream;

      // Lazy-import THREE inside hand-tracker so it gets window.THREE
      await handTrackerInit(videoEl, window.__particleCamera, ({ gesture, worldPos, velocity }) => {
        if (gesture === 'none' || !worldPos) {
          clearHandForce();
          return;
        }
        const wp  = new THREE.Vector3(worldPos.x, worldPos.y, worldPos.z);
        const vel = new THREE.Vector3(velocity.x, velocity.y, velocity.z);
        applyHandForce(wp, gesture, vel);
      });
    } catch (err) {
      console.warn('Camera unavailable:', err.message);
    }
  </script>
</body>
</html>
```

- [ ] **Step 2: Export camera from particle-engine.js for hand tracker**

In `Animacao_Marcelo/js/particle-engine.js`, add this export after the `camera` declaration:

```javascript
export function getCamera() { return camera; }
```

Update `marcelo_ui.html` import line:

```javascript
import { init as particleInit, setState, setAmplitude, applyHandForce, clearHandForce, setMouseNDC, getCamera } from './js/particle-engine.js';
```

And replace `window.__particleCamera` with `getCamera()`:

```javascript
await handTrackerInit(videoEl, getCamera(), ({ gesture, worldPos, velocity }) => {
```

- [ ] **Step 3: Commit**

```bash
git add Animacao_Marcelo/marcelo_ui.html Animacao_Marcelo/js/particle-engine.js
git commit -m "feat(ui): add marcelo_ui.html — full particle chat interface"
```

---

## Task 10: Integration Test & Smoke Check

- [ ] **Step 1: Start the backend**

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Expected: `Application startup complete.`

- [ ] **Step 2: Test /tts endpoint directly**

```bash
curl -X POST http://localhost:8000/api/v1/tts \
  -H "Content-Type: application/json" \
  -d '{"text":"Olá Marcelo"}' \
  --output test.mp3
```

Expected: `test.mp3` file exists and plays audio.

- [ ] **Step 3: Test WebSocket chat**

```bash
# Install wscat if needed: npm install -g wscat
wscat -c ws://localhost:8000/api/v1/ws/chat
```

Send: `{"message": "Oi Marcelo", "session_id": "test"}`

Expected: receive `{"type":"chunk","text":"..."}` then `{"type":"done","text":""}`.

- [ ] **Step 4: Open the UI**

Open `Animacao_Marcelo/marcelo_ui.html` in Chrome (file:// works since CORS is `*`).

Expected:
- Particle swarm visible in violet/idle state
- Webcam preview appears bottom-left
- Type a message → particles turn amber (thinking) → green (speaking) → violet (idle)
- Voice plays from TTS

- [ ] **Step 5: Test mic input**

Click 🎤, speak "Qual é o seu nome?" in Portuguese.

Expected: interim transcript appears, STT finalizes, state → thinking → speaking, TTS response plays.

- [ ] **Step 6: Test hand gestures**

Place hand in webcam frame. Verify in browser console (add `console.log(gesture)` temporarily in hand-tracker.js):
- Open hand + move → `flow`
- Fist → `attract`
- Point one finger → `repel`

- [ ] **Step 7: Run full test suite**

```bash
pytest -m unit && ruff check . && pyright
```

Expected: all green.

- [ ] **Step 8: Final commit**

```bash
git add -A
git commit -m "feat(ui): marcelo particle UI — integration verified"
```

---

## Troubleshooting Notes

**CORS / file:// issues:** If browser blocks requests, serve the HTML via a local server instead:
```bash
cd Animacao_Marcelo && python -m http.server 3000
```
Then open `http://localhost:3000/marcelo_ui.html`.

**Groq TTS model name:** If `playai-tts` returns 404, check current Groq TTS models at `https://console.groq.com`. Update `groq_tts_model` in `.env` or `config.py`.

**MediaPipe CDN slow load:** First load may take 3-5s while WASM downloads. Subsequent loads use browser cache.

**STT language:** Change `this._recognition.lang = 'pt-BR'` in `chat-client.js` to `'en-US'` if testing in English.

**60fps with 20k particles + MediaPipe:** MediaPipe runs inference on each frame. If FPS drops, reduce `COUNT` in `particle-engine.js` to `10000` or set `modelComplexity: 0` in `hand-tracker.js`.

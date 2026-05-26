# Marcelo Particle UI — Design Spec
_2026-05-26_

## Overview

Standalone HTML/JS interface (`Animacao_Marcelo/marcelo_ui.html`) where the user talks to the Marcelo AI agent via text or voice. The Three.js particle swarm (from `jarvis.html`) reacts in real time: audio-reactive amplitude pulses, state-based color/behavior transitions, and hand-gesture force fields via MediaPipe Hands.

## Architecture

### Frontend

```
Animacao_Marcelo/
├── marcelo_ui.html          # Entry point, UI overlay, module orchestrator
└── js/
    ├── particle-engine.js   # Three.js swarm + state machine + GLSL uniforms
    ├── audio-analyzer.js    # Web Audio API analyser node → amplitude/freq arrays
    ├── hand-tracker.js      # MediaPipe Hands CDN → gesture classification + 3D landmarks
    └── chat-client.js       # WebSocket /ws/chat + Web Speech API STT + state dispatch
```

### Backend (new endpoints)

| File | Endpoint | Method | Purpose |
|---|---|---|---|
| `app/api/voice.py` | `/tts` | POST | Accepts `{text: str}`, calls Groq TTS, returns `audio/mpeg` bytes |
| `app/api/ws_chat.py` | `/ws/chat` | WebSocket | Receives user message, streams RoutingAgnoAgent response as text chunks |

Both wired in `main.py` alongside existing router.

## Particle State Machine

Four states drive color palette, swarm behavior, and bloom intensity:

| State | Trigger | Color | Behavior | Bloom |
|---|---|---|---|---|
| `idle` | Default | Violet (HSL 0.78) | Gentle orbital swarm (current jarvis.html) | 1.8 |
| `listening` | Mic active / recording | Blue (HSL 0.60) | Particles expand outward, pulse with mic amplitude | 2.2 |
| `thinking` | Message sent, awaiting response | Amber (HSL 0.12) | Turbulent chaos, accelerated rotation | 2.5 |
| `speaking` | TTS audio playing | Green-white (HSL 0.35) | Amplitude sync pulse, radial breathing | 3.0 |

State transitions use HSL interpolation over 800ms (`lerp` each frame). Bloom strength transitions linearly.

## Audio Reactivity

```
Groq TTS audio (ArrayBuffer)
  → AudioContext.decodeAudioData()
  → AudioBufferSourceNode → AnalyserNode → destination
  → getByteFrequencyData(frequencyData[256]) each frame
  → uAmplitude uniform (float, 0.0–1.0, smoothed)
  → uFreqBands uniform (vec4, low/mid/high/presence)
```

`uAmplitude` drives:
- Particle scale multiplier (`+30%` at peak)
- Bloom `strength` (`base + uAmplitude * 1.5`)
- Chromatic aberration offset in fragment shader (subtle, max 0.003)
- Trail decay rate (faster decay = sharper trails at loud moments)

## Hand Tracking

MediaPipe Hands loaded from CDN. Runs on hidden `<video>` + `<canvas>` overlay.

### Gesture Classification

| Gesture | Detection | Force Applied |
|---|---|---|
| Open hand + move | All 5 fingers extended, wrist velocity > threshold | Directional flow field in movement direction |
| Wrist rotation | Wrist angle delta > 30°/frame | Rotational torque on particle cluster near hand |
| Fist close | All fingers curled (tip below knuckle) | Attraction vortex centered on palm |
| Fist open (explosive) | Rapid transition fist→open in <150ms | Radial explosion, particles scatter |
| Pinch (thumb+index) | Thumb tip < 30px from index tip | Local compression — particles collapse to pinch point |
| Point (index only) | Only index extended | Directional repulsion cone along finger vector |

Hand landmarks projected from normalized [0,1] → Three.js world space using camera frustum inverse.

Force fields decay with distance (inverse square). Max influence radius: 25 world units.

## Gesture-to-Particle Force

```javascript
// Executed each frame per particle i
const toHand = handWorldPos.clone().sub(positions[i]);
const dist = toHand.length();
const influence = Math.max(0, 1 - dist / HAND_RADIUS) ** 2;

switch (currentGesture) {
  case 'flow':    vel[i].add(handVelocity.clone().multiplyScalar(influence * 0.8)); break;
  case 'rotate':  vel[i].add(tangent(toHand).multiplyScalar(influence * rotSpeed)); break;
  case 'attract': vel[i].add(toHand.normalize().multiplyScalar(influence * 2.0));   break;
  case 'explode': vel[i].add(toHand.normalize().multiplyScalar(-influence * 5.0));  break;
  case 'pinch':   vel[i].add(toHand.multiplyScalar(influence * 3.0));               break;
  case 'repel':   vel[i].add(toHand.normalize().multiplyScalar(-influence * 1.5));  break;
}
```

## Mouse Interaction

- **Hover**: soft repulsion sphere radius 15 units, strength 0.3
- **Click + drag**: grab cluster within 10 units, drag with cursor, release with momentum

## UI Layout

```
┌─────────────────────────────────────────────────────┐
│                  Three.js canvas (fullscreen)        │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │ transcript overlay                           │   │
│  │ semi-transparent, backdrop-blur, top-left    │   │
│  │ last 3 messages (You / Marcelo)              │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
│  [webcam: 160×120, bottom-left, rounded, low opacity]│
│                                                      │
│  ┌─────────────────────────────────────────────┐    │
│  │ [text input]              [🎤 mic] [➤ send] │    │
│  └─────────────────────────────────────────────┘    │
│                 dock — bottom center                 │
└─────────────────────────────────────────────────────┘
```

Mic button: toggle STT recording. Press = start, press again or silence >2s = stop + send.
Send button: submit text input.
Transcript: slides in from top, auto-scrolls, fades oldest entries.

## Visual Polish

- **Depth of field**: particles beyond camera z-threshold render at reduced alpha (emulated in fragment shader via distance fog already present)
- **Bloom**: UnrealBloomPass, dynamic strength via `uAmplitude`
- **Trail effect**: position lerp factor drops from 0.1 to 0.03 when hand pushes particles — slower lerp = visible trail
- **Chromatic aberration**: fragment shader offset `gl_FragColor.r` and `.b` channels ±`uAmplitude * 0.003` in UV space
- **HSL color interpolation**: particle hue/saturation/lightness lerp toward target state values each frame at rate 0.02

## Backend: `/tts` Endpoint

```python
# POST /tts
# Body: {"text": "Olá, tudo bem?"}
# Response: audio/mpeg stream
```

Calls `groq.audio.speech.create(model="playai-tts", voice="Fritz-PlayAI", input=text)`.
Returns raw bytes with `Content-Type: audio/mpeg`.
No caching (single user, low volume).

## Backend: `/ws/chat` WebSocket

```
Client → {"message": "Oi Marcelo", "session_id": "default"}
Server → {"type": "chunk", "text": "Olá! "}  (streaming)
Server → {"type": "chunk", "text": "Como posso "}
Server → {"type": "done", "text": ""}
```

Uses existing `ProcessIncomingMessage` use case + `RoutingAgnoAgent`. Streams chunks as they arrive from the LLM.

## Out of Scope

- Multi-user sessions
- Persistent conversation history in this UI (backend handles memory)
- Mobile / touch support
- Authentication

## Success Criteria

1. User speaks or types → Marcelo responds with voice within 2s of message completion
2. Particles visibly change color and behavior on each state transition
3. Hand in webcam frame repels/attracts particles within 0.5s of gesture change
4. Mouse drag moves particle cluster smoothly
5. Runs at ≥45fps on mid-range GPU with 20k particles + MediaPipe + audio analysis

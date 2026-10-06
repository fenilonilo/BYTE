# Spec 2 — Voice client: wake word + live conversation on the home laptop

Status: draft for review. Builds on Spec 1
(`2026-10-05-personal-agent-chat-live-design.md`, `WS /live` protocol).

## 1. Goal

A daemon on the Ubuntu Server laptop that listens to the local microphone 24/7,
detects the wake word **"Byte"** locally, then opens `WS /live` and relays
microphone audio to the agent and the agent's audio to the loudspeaker.

Success: say "Byte", ask something, hear the answer; return to listening when
the conversation ends. No audio leaves the laptop before the wake word.

## 2. Scope

**In:** `voice/` package, wake-word detection, `/live` client, half-duplex echo
handling, systemd unit, tests of the session logic.

**Out (v1):** barge-in and acoustic echo cancellation, web chat UI (out of scope
for this repository by `CLAUDE.md`; a separate repo may consume `POST /messages`),
proactive notifications, several microphones, wake-word training pipeline beyond a
documented script.

## 3. Constraints and decisions

| Decision | Choice | Why |
|---|---|---|
| Wake word engine | openWakeWord, `onnx` inference | Local, free, cheap on CPU. tflite has no Python 3.12 wheel. |
| Wake word model | Custom "Byte" `.onnx`, trained once by the owner | No pretrained "Byte". `hey_jarvis` stands in during development; swapping is a config path. pt-BR accuracy is unverified until tested on the laptop. |
| Process model | systemd service on the host, **not** Docker | Audio device passthrough in containers adds fragility. The API stays in compose. |
| Server address | `ws://127.0.0.1:8000/api/v1/live` | Same machine; loopback needs no TLS. The bearer token is still required. |
| Echo | Half-duplex: mic muted while the agent speaks | Embedded mic + speaker; AEC on a headless server is fragile. `ponytail:` marker, upgrade to AEC or a headset with hardware AEC. |
| Detector abstraction | Plain function `bytes -> bool` | No second detector in sight (rule 9). |

## 4. Components

```
voice/
├── wake.py      openWakeWord wrapper: feed 80 ms PCM16 16 kHz, return detected bool
├── audio.py     sounddevice: microphone input (16 kHz), speaker output (24 kHz)
├── session.py   state machine + /live protocol; no real audio or sockets imported
└── main.py      env config, wiring, signal handling
```

Dependencies live in an optional extra `voice` in `pyproject.toml`
(`openwakeword`, `sounddevice`, `websockets`, `numpy`; `scipy` arrives with
openWakeWord). The server image does not install it. System packages:
`libportaudio2`; the service user is in the `audio` group.

`session.py` receives its microphone source, speaker sink, WebSocket connector,
detector and monotonic clock by injection, so it is testable without hardware.

## 5. Behavior

```
IDLE ──wake──▶ CONNECTING ──ready──▶ LIVE ──end──▶ IDLE
```

- **IDLE:** microphone frames of 80 ms (1280 samples at 16 kHz) go to the
  detector only. A score above the configured threshold is a wake.
- **CONNECTING:** open the socket with `Authorization: Bearer <token>`, send
  `{"type":"start"}`. Microphone audio captured since the wake is held in a
  bounded buffer (default 5 s; oldest dropped) until `ready`. Connect or handshake
  failure → log the status, return to IDLE.
- **LIVE:** flush the buffer, then stream microphone audio upsampled 16 → 24 kHz
  (`scipy.signal.resample_poly(x, 3, 2)` per frame; `ponytail:` per-frame edge
  artifacts, switch to a stateful resampler if recognition suffers). Play incoming
  binary frames at 24 kHz through the speaker.
- **Half-duplex:** while server audio is arriving or the playback queue is not
  empty, no microphone frames are sent. Sending resumes ~300 ms after the queue
  drains (configurable tail for room echo).
- **`interrupt` event:** clear the playback queue and reply
  `{"type":"played","audio_end_ms":N}` with the milliseconds actually played.
- **End of session:** server closes (60 s idle, 10 min cap, code 4000), or the
  client closes after `BYTE_VOICE_IDLE_SECONDS` (default 8) with no activity after
  `turn_done`. Always return to IDLE and reset the detector's internal buffers.
  There is **no automatic reconnect**; only a new wake word opens a session. A
  close with code 4000 is therefore handled by construction.
- **`error` event or protocol surprise:** close, log the code, return to IDLE.

## 6. Configuration (env, `BYTE_VOICE_` prefix except the token)

`BYTE_API_TOKEN` (required, same variable as the server), `BYTE_VOICE_URL`,
`BYTE_VOICE_WAKE_MODEL` (path to `.onnx`), `BYTE_VOICE_THRESHOLD` (default 0.5),
`BYTE_VOICE_IDLE_SECONDS`, `BYTE_VOICE_INPUT_DEVICE`, `BYTE_VOICE_OUTPUT_DEVICE`,
`BYTE_VOICE_SEGMENT` (default `auto`). The process refuses to start if the token is
shorter than 32 characters or the model file is missing.

## 7. Security and logging

- Token comes from the environment, never from argv, never logged.
- Logs carry state transitions, close codes and durations only. No audio, no
  transcripts, no message content.
- Nothing is sent to the network in IDLE. Audio exists only in memory.
- The service unit runs as an unprivileged user with `Restart=always`.

## 8. Testing

- **Unit (TDD)** for `session.py` with fake microphone, speaker, socket, detector
  and an injected clock; no sleeping, no real audio, no real network. Cases:
  handshake order, buffer flushed on `ready`, buffer bound, microphone muted during
  playback and resumed after the tail, `interrupt` → `played`, idle close,
  server close → IDLE with detector reset, connect failure → IDLE, `error` event.
- **Unit** for the 16 → 24 kHz conversion (length ratio, dtype).
- **Manual on the laptop:** `hey_jarvis` end to end, then the custom "Byte"
  model; record false-trigger and miss rate over a day of ordinary household noise.
- Coverage rules from `CLAUDE.md` apply to `voice/` except `audio.py` and
  `wake.py`, which wrap hardware and a third-party model.

## 9. Open items

- Train the "Byte" model (script and steps shipped under `docs/`); accuracy on
  pt-BR pronunciation unknown until tested.
- Laptop CPU/RAM not yet known; openWakeWord is light, but verify on the device.
- Barge-in/AEC, after a headset or USB speakerphone replaces the built-in audio.

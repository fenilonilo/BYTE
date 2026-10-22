# Byte

A personal assistant backend for one person, running headless in Docker on a home
server. It controls lights, an air conditioner and music, manages a calendar and tracks
monthly expenses, through two modes:

- **chat** — `POST /api/v1/messages`: a text message in, a text reply out.
- **live** — `WS /api/v1/live`: a spoken conversation; the agent runs tools while it talks.

One agent holds every tool. Every outside resource (the model provider, the smart
home, the calendar, the expense sheet, storage) is an adapter behind a port. The
live client is a custom ESP32-S3, but the protocol is plain WebSocket: any client works.

No GUI beyond the optional `web/` control panel, no computer vision, no chat-channel adapters, no multi-user support.

## Run

```bash
cp .env.example .env        # fill BYTE_API_TOKEN (32+ chars) and BYTE_OPENAI_API_KEY
docker compose up --build
```

API on `http://127.0.0.1:8000/api/v1`, interactive docs at `/docs`. Compose binds to
loopback only.

### Web panel (optional, off by default)

Set `BYTE_WEB=true` in `.env` (works with docker compose), or run locally with
`python main.py --web [--host H --port P]`. Open `http://127.0.0.1:8000/` and enter
`BYTE_API_TOKEN`. It drives the same adapters as chat: real devices when configured, in-memory
fakes otherwise (the boot log says which).

### Real devices

Each group runs against an in-memory fake until you configure the real thing, and the
boot log says which adapter is active (`adapters.selected`).

| Group | Adapter | Configure in `.env` |
|---|---|---|
| Lights | Tuya, over the LAN (`tinytuya`) | `BYTE_TUYA_LIGHTS`: JSON of name → `device_id`, `address`, `local_key`, `version` |
| Air conditioner | LG ThinQ | `BYTE_THINQ_ACCESS_SECRET` (personal access token), `BYTE_THINQ_COUNTRY` |
| Music | Spotify (Premium) | `BYTE_SPOTIFY_CLIENT_ID`, `BYTE_SPOTIFY_REFRESH_TOKEN` (get it with `python scripts/spotify_login.py`), `BYTE_SPOTIFY_DEVICE` |

### Expose it on the LAN (for the ESP32)

Only together with TLS, because the bearer token would otherwise travel in cleartext.

```bash
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=byte" \
  -keyout certs/byte.key -out certs/byte.crt \
  -addext "subjectAltName=IP:192.168.0.10"          # the server's LAN IP
```

Give the server a fixed DHCP reservation for that IP, pin `certs/byte.crt` in the
firmware, then set in `.env`:

```
BYTE_PUBLISH_HOST=192.168.0.10
BYTE_TLS_CERT=/certs/byte.crt
BYTE_TLS_KEY=/certs/byte.key
```

## Chat

```bash
curl -X POST http://127.0.0.1:8000/api/v1/messages \
  -H "authorization: Bearer $BYTE_API_TOKEN" -H 'content-type: application/json' \
  -d '{"content": "apaga o dentista de amanhã"}'
```

```json
{
  "id": "…",
  "role": "assistant",
  "content": "Apagar o evento evt-1. Posso apagar?",
  "conversation_id": "…",
  "pending_confirmation": { "summary": "Apagar o evento evt-1" }
}
```

Send `conversation_id` on later calls to continue the conversation. `segment`
(`home`, `music`, `agenda`, `finance`) is an optional filter over the tools; omitted or
`auto` means all of them; an unknown segment returns `404`.

Sensitive actions (deleting a calendar event, recording an expense, switching the air
conditioner on or off) never run on the first request: the reply carries the exact action in
`pending_confirmation`, and only the user's very next message, if it is a clear
"sim", executes it.

## Live protocol

`WS /api/v1/live` with `Authorization: Bearer <token>` on the upgrade request.

| Direction | Frame | Meaning |
|---|---|---|
| client → server | JSON `{"type":"start","segment"?,"conversation_id"?}` | first frame |
| server → client | JSON `{"type":"ready","conversation_id","audio":{"format":"pcm16","rate":24000,"channels":1}}` | provider session is open; start streaming |
| both | binary | PCM16 mono 24 kHz audio |
| server → client | JSON `transcript`, `turn_done`, `interrupt`, `error {code}`, `closed {reason}` | events |
| client → server | JSON `{"type":"played","audio_end_ms":N}` | after `interrupt`: how much of the reply was actually played |

Firmware requirements: upsample 16 → 24 kHz, echo cancellation (or mute the mic
while playing), buffer microphone audio until `ready`, pin the server certificate,
and do not auto-reconnect after close code `4000` (another client took over).
One live session at a time; a session ends after 60 s without speech or 10 minutes.

Try it without hardware:

```bash
python scripts/live_probe.py question.wav reply.wav --token "$BYTE_API_TOKEN"
```

## Develop

```bash
pip install -e ".[api,openai,thinq,tuya,spotify,voice,dev]"
# openWakeWord: --no-deps because its tflite-runtime dependency has no Python 3.12+ wheel
# and is not needed with onnx
pip install --no-deps openwakeword
pip install onnxruntime tqdm scikit-learn requests
python -c "import openwakeword; openwakeword.utils.download_models()"
ruff check . && pyright && pytest
pytest -m integration        # hits the real OpenAI API (needs BYTE_OPENAI_API_KEY)
```

Regenerate the locked dependencies used by the Docker image:

```bash
uv pip compile pyproject.toml --extra api --extra gemini --extra openai --extra thinq \
  --extra tuya --extra spotify --extra google --extra tts \
  --python-version 3.12 --python-platform x86_64-manylinux_2_28 -o requirements.lock
```

## Reminders, alarms and Google Calendar

Byte speaks first: "me lembra amanhã às 9 de pagar a luz", "alarme às 6h30". The voice
daemon keeps `WS /api/v1/ws/notifications` open (no model, no tokens); at the time the
server sends speech made by a local Piper voice, the device plays it and acks. An alarm
repeats until you say the wake word. Google Calendar events are announced 10 minutes before.

```bash
# voice (~60 MB), read by the server through BYTE_PIPER_MODEL
python -m piper.download_voices pt_BR-faber-medium --download-dir models
# Google Calendar: create a "Desktop app" OAuth client, enable the Calendar API, set the
# consent screen to "In production" (in "Testing" the token dies after 7 days), then:
python scripts/google_login.py   # prints BYTE_GOOGLE_REFRESH_TOKEN
```

Reminders are kept in `data/reminders.json` (a compose volume) and survive restarts; one
missed while the device was off is spoken when it reconnects.

## Status

Chat and live are built end to end. Lights (Tuya), the air conditioner (ThinQ), music
(Spotify) and the calendar (Google) have real adapters; the expenses are still **in memory**,
so the whole flow (tools, confirmation, barge-in) also runs with no device at all. Not built
yet: the Google Sheets adapter, Postgres persistence (history is in memory and lost on
restart) and the Gemini Live adapter.

See `CLAUDE.md` for the rules, `docs/ARCHITECTURE.md` for the decisions and
`docs/superpowers/specs/` for the design.

# Byte

A personal assistant backend for one person, running headless in Docker on a home
server. It controls lights, an air conditioner and music, manages a calendar and tracks
monthly expenses, through two modes:

- **chat** — `POST /api/v1/messages`: a text message in, a text reply out.
- **live** — `WS /api/v1/live`: a spoken conversation; the agent runs tools while it talks.

One agent holds every tool. Every outside resource (the model provider, the smart
home, the calendar, the expense sheet, storage) is an adapter behind a port. The
live client is a custom ESP32-S3, but the protocol is plain WebSocket: any client works.

No GUI beyond the `frontend/` control panel, no computer vision, no chat-channel adapters, no multi-user support.

## Layout

```
frontend/   the web panel: static HTML/CSS/JS, no build step (tests: node --test frontend/tests/*.test.mjs)
backend/    the API (FastAPI), voice/ client, tests, migrations, scripts, Dockerfile
deploy/     Caddyfile, systemd unit for the voice client
docker-compose.yml, .env   at the root
```

Python commands below (`python scripts/...`, `pytest`) run from `backend/`.

## Run (home server)

```bash
cp .env.example .env        # fill BYTE_API_TOKEN (32+ chars), BYTE_OPENAI_API_KEY, BYTE_DB_PASSWORD
docker compose up --build
```

Three services: `caddy` (HTTPS, serves the panel, proxies `/api/*` with WebSockets), `api`
(plain HTTP, host loopback `127.0.0.1:8000` for the voice client on the same machine) and `db`.
Open `https://byte.local/` (or `https://localhost/` with `BYTE_SITE=localhost`) and enter
`BYTE_API_TOKEN`. Caddy proxies only `/api/*`; FastAPI's interactive docs stay at
`http://127.0.0.1:8000/docs` on the server.

### Open it to the house (phones, ESP32)

Give the server a fixed DHCP reservation, then in `.env`:

```
BYTE_PUBLISH_HOST=192.168.0.10   # the server's LAN IP; Caddy listens there on 443 and 80
BYTE_SITE=byte.local             # the name devices use (mDNS via Avahi, or a router DNS entry)
```

Caddy signs `BYTE_SITE` with its own CA (`tls internal`). Export the root once and install
it on each phone (Android: Settings → Security → Install certificate → CA; a native app must
bundle or pin it), and pin it in the ESP32 firmware:

```bash
docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./byte-root.crt
```

The `caddy-data` volume holds that CA: deleting it means every device trusts a new root.
Wider exposure later is a `BYTE_SITE` with a real domain and `tls internal` removed from
`deploy/Caddyfile` (public certificate). The API port itself stays on loopback.

### Web panel on the Windows PC (dev, Lynus)

```bash
cd backend
python main.py --web [--host H --port P]   # serves ../frontend at /
```

Open `http://127.0.0.1:8000/`. Lynus and the project terminal live only here: they need
`claude` and the `pty` extra, which the Linux image does not have. `BYTE_TLS_CERT` /
`BYTE_TLS_KEY` give this uvicorn its own TLS if you need it.

Moving from the old layout: `.env` stays at the root; move local `data/` and
`models/pt_BR-*` into `backend/`.

### Real devices

Each group runs against an in-memory fake until you configure the real thing, and the
boot log says which adapter is active (`adapters.selected`).

| Group | Adapter | Configure in `.env` |
|---|---|---|
| Lights | Tuya, over the LAN (`tinytuya`) | `BYTE_TUYA_LIGHTS`: JSON of name → `device_id`, `address`, `local_key`, `version` |
| Air conditioner | LG ThinQ | `BYTE_THINQ_ACCESS_SECRET` (personal access token), `BYTE_THINQ_COUNTRY` |
| Music | Spotify (Premium) | `BYTE_SPOTIFY_CLIENT_ID`, `BYTE_SPOTIFY_REFRESH_TOKEN` (get it with `python scripts/spotify_login.py`), `BYTE_SPOTIFY_DEVICE` |

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
cd backend
pip install -e ".[api,openai,thinq,tuya,spotify,voice,dev]"
# openWakeWord: --no-deps because its tflite-runtime dependency has no Python 3.12+ wheel
# and is not needed with onnx
pip install --no-deps openwakeword
pip install onnxruntime tqdm scikit-learn requests
python -c "import openwakeword; openwakeword.utils.download_models()"
ruff check . && pyright && pytest
node --test ../frontend/tests/*.test.mjs
pytest -m integration        # hits the real OpenAI API (needs BYTE_OPENAI_API_KEY)
```

Regenerate the locked dependencies used by the Docker image:

```bash
uv pip compile pyproject.toml --extra api --extra gemini --extra openai --extra thinq \
  --extra tuya --extra spotify --extra google --extra weather --extra tts --extra db --extra embed \
  --python-version 3.12 --python-platform x86_64-manylinux_2_28 -o requirements.lock
```

## Projects: knowledge and terminal (Spec 4)

Byte knows your programming projects and opens them for coding in the panel.

- **Ask** (chat or voice): "o que o Sistema_Perfil usa de banco?" — answered from the projects'
  `CLAUDE.md` through a local vector index (`search_projects`). Only the project names go in
  every prompt; content is fetched when a question needs it.
- **Open** (panel only, typed or spoken): "abre o FinFlow" — the panel's terminal becomes a real
  terminal running a new `claude` in that folder. "fecha o projeto" goes back to Byte's log.
  One project at a time; reloading the tab keeps the session.

Setup on the Windows machine that holds the projects (Byte under uvicorn):

```bash
pip install -e ".[api,gemini,db,embed,pty]"
# .env
BYTE_PROJECTS={"Byte":{"path":"D:/Projetos/Byte/BYTE"},"FinFlow":{"path":"D:/Projetos/FinFlow"}}
BYTE_DB_PASSWORD=<long random>
BYTE_DATABASE_URL=postgresql+asyncpg://byte:<same password>@127.0.0.1:5432/byte
docker compose up -d db      # pgvector, loopback only; Byte runs the migrations at boot
cd backend && python main.py --web
```

- Each project's `docs` defaults to `["CLAUDE.md"]`; add more relative `.md` paths to index
  them. The index refreshes every 5 minutes by content hash (`BYTE_KNOWLEDGE_SCAN_SECONDS`).
- The embedding model (`paraphrase-multilingual-MiniLM-L12-v2`, ~220 MB, CPU) downloads once
  into `data/models`. Without `BYTE_DATABASE_URL` the index lives in memory and is rebuilt at boot.
- A server that cannot see the folders keeps answering from the last index; the terminal tools
  only exist where `claude` is on `PATH` and the `pty` extra is installed (not in the Docker image).
- The `claude` child process gets no `BYTE_*` variable, no provider key and no marker of a
  parent Claude Code session.

## Reminders, alarms and Google Calendar

Byte speaks first: "me lembra amanhã às 9 de pagar a luz", "alarme às 6h30". The voice
daemon keeps `WS /api/v1/ws/notifications` open (no model, no tokens); at the time the
server sends speech made by a local Piper voice, the device plays it and acks. An alarm
repeats until you say the wake word. Google Calendar events are announced 10 minutes before.

```bash
# voice (~60 MB), read by the server through BYTE_PIPER_MODEL
python -m piper.download_voices pt_BR-faber-medium --download-dir backend/models
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

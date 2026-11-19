# Spec 7 — Front/back split and self-hosting on the LAN

## Intent

Byte moves to an old laptop that acts as a home server. Other devices in the house (the owner's
phone, a future phone app, a future ESP32-S3 speaker) reach it over the LAN. Until the ESP32
exists, the server laptop itself is the "Alexa": `voice/` runs on it with its own mic and speaker.

The repository is split so the two halves are obvious: `frontend/` (the static panel) and
`backend/` (the API and everything Python). A reverse proxy in front owns HTTPS, so the backend
becomes API-only and later exposure is a config change, not a code change.

## Goals

- `frontend/` and `backend/` as top-level folders; `docker compose up` from the root brings up
  the whole server.
- HTTPS on the LAN with no manual certificate work beyond trusting one root CA per device.
- Phone (browser now, native app later) and ESP32 reach the same API over the LAN.
- `voice/` on the server reaches the API on loopback, no TLS needed.
- Exposure beyond the LAN later = change the proxy's site address. The owner decides when.

## Non-goals

- The phone app itself (later project). This spec only keeps the door open: same origin, no CORS.
- Silent tool actions (lights/AC/music with a beep instead of speech) — **next spec**.
- Continuous voice with barge-in on the laptop (PipeWire `echo-cancel` + stop muting the mic in
  `voice/`) — **spec after that**.
- Lynus and the project terminal on the server. They stay on the owner's Windows PC, started only
  when the owner asks. On the Linux server they are already off (no `claude`, no winpty →
  `get_project_session()` returns `None`); nothing to add.

## Anti-goals

- Any change to the panel's JavaScript to make it work behind the proxy.
- A second copy of TLS logic: the server deployment does TLS in one place (the proxy).
- Breaking the Windows dev flow (`python main.py --web`, Lynus panel on the PC).

## Approaches

| | Approach | Trade-off |
|---|---|---|
| A | Move folders only; the backend keeps serving the panel and doing TLS in uvicorn | Smallest diff; certificates and future exposure stay manual and inside Python |
| **B** | **Caddy in front: serves `frontend/`, proxies `/api` to the backend, owns HTTPS** | **One more container; HTTPS automatic (`tls internal`), exposure later is one line, no JS change** |
| C | Frontend hosted independently, backend URL configurable, CORS | Only useful if the panel lives on another host; it does not |

**Picked: B** (owner, 2026-11-18). Reason: LAN HTTPS without hand-made certs, a native phone app
later needs no CORS (native clients don't enforce it), and future exposure is the owner's switch.

## Layout

```
frontend/              ← was web/ (index.html, *.js, style.css, vendor/, models/)
frontend/tests/        ← was tests/web/*.test.mjs (node --test)
backend/
  app/ main.py alembic.ini migrations/ tests/ scripts/ voice/ models/
  pyproject.toml requirements.lock Dockerfile .dockerignore
deploy/
  Caddyfile
  byte-voice.service   (paths updated to /opt/byte/backend)
docker-compose.yml     (root)
.env.example           (root, next to compose)
.pre-commit-config.yaml, CLAUDE.md, README.md, docs/  (root)
```

`voice/` stays inside `backend/`: it imports `app.*` (logger, `ConfigError`,
`MIN_TOKEN_LENGTH`) and shares the venv. Pulling it out is work for when the ESP32 replaces it.
*(builder's call, recorded)*

## Compose

```
caddy  → ${BYTE_PUBLISH_HOST:-127.0.0.1}:443  (and :80 → redirect)
         serves /srv/frontend (bind mount ./frontend, read-only)
         reverse_proxy /api/* → api:8000   (WebSockets pass through as-is)
api    → 127.0.0.1:8000 on the host, for voice/ on the same machine; BYTE_WEB unset
db     → 127.0.0.1:5432 (unchanged)
```

- Caddy site address from env `BYTE_SITE` (default `byte.local`, mDNS name of the laptop via
  Avahi). `tls internal`: Caddy's own CA; its root lives in the `caddy-data` volume and is
  installed once on each phone. The ESP32 pins it.
- Future exposure: set `BYTE_SITE` to a real domain and drop `tls internal` → Let's Encrypt.
  Owner's decision; no code involved.
- The API container no longer does TLS: Dockerfile `CMD` drops the `--ssl-*` branch, compose drops
  the `certs` mount. `main.py`'s `BYTE_TLS_CERT/KEY` support stays for the Windows PC.
- `BYTE_CLAUDE_HOOK_URL` and Lynus settings are irrelevant on the server and stay as they are.

## Backend changes

- `main.py`: `WEB_DIR` points to `../frontend` (resolved from `backend/main.py`) so
  `python main.py --web` on the PC still serves the panel. `mount_web` unchanged.
- No API, auth or route change. Bearer token on every route as today; Caddy forwards the
  `Authorization` header and the WebSocket subprotocol untouched.
- Uvicorn behind a proxy: `--proxy-headers --forwarded-allow-ips=*` inside the container so logs
  see the real client IP. *(builder's call)*

## Tooling

- `pyproject.toml` moves to `backend/`; ruff, pyright, pytest run from `backend/`.
- `.pre-commit-config.yaml` stays at root; hooks scoped to `^backend/` and run with
  `backend/` as the working dir (pyright: `entry: bash -c "cd backend && pyright"`); the large-file
  exclude becomes `^frontend/models/`.
- Node tests: `node --test frontend/tests/`. Import paths inside the `.mjs` files fixed.
- CI/README/CLAUDE.md commands updated to the new paths.

## Verification

- `cd backend && ruff check . && pyright && pytest` green, same test count as before the move.
- `node --test frontend/tests/` green.
- `docker compose up --build` on the PC: `https://byte.local/` (or `https://127.0.0.1/` with
  `BYTE_SITE=127.0.0.1`) loads the panel, login with token works, chat round-trip works,
  `/api/v1/ws/panel` connects through Caddy.
- `curl http://127.0.0.1:8000/api/v1/health` from the host works (voice path).

## Order and merge

`fix/resilient-devices` (commit `1ac65aa`, Gemini Live fix touching `app/adapters/gemini/`,
`run_live_session.py`, `web/live.js`) is not in `main`. Merge it first, rebase this branch, then
do the move as one `git mv` commit so rename detection keeps history and later merges.

## Left to the builder

- Exact Caddyfile syntax and the redirect on :80.
- Whether `models/ei_byte.onnx` duplicates between `frontend/models/` and `backend/models/` stay
  as two copies (they do today) — yes, keep both; different consumers.

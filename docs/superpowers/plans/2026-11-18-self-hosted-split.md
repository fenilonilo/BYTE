# Front/back split and LAN self-hosting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the repo into `frontend/` and `backend/` and serve both from the home server behind Caddy (HTTPS on the LAN), with the API also on host loopback for `voice/`.

**Architecture:** Pure `git mv` move first (no behavior change, same test count). Then compose gains a `caddy` service that serves `frontend/` and proxies `/api/*` to `api:8000`; the API container drops TLS. Docs last.

**Tech Stack:** Python 3.12 / FastAPI / uvicorn, Docker Compose, Caddy 2 (`caddy:2.8-alpine`), node `--test`.

**Spec:** `docs/superpowers/specs/2026-11-18-self-hosted-split-design.md`

## Global Constraints

- Panel JavaScript does not change behavior; only test import paths move.
- Default bind stays loopback: `${BYTE_PUBLISH_HOST:-127.0.0.1}` for Caddy, `127.0.0.1:8000` for the API, `127.0.0.1:5432` for the db.
- Caddy site address from `BYTE_SITE`, default `byte.local`, `tls internal`.
- Windows dev flow keeps working: from `backend/`, `python main.py --web` serves `../frontend`.
- `.env` stays at the repo root (compose reads it there); Python settings read `../.env` then `.env`.
- English for code, comments, docs, commits. Conventional Commits.

## Review Focus

1. WebSockets through Caddy (`/api/v1/live`, `/ws/panel`, `/ws/notifications`, `/ws/terminal`) keep the `bearer, <token>` subprotocol and upgrade — expect a connected socket, not 400/502. (Task 2 smoke step.)
2. `Authorization` header reaches the API untouched — expect 401 without token, 200 with. (Task 2 smoke step.)
3. Panel files served by Caddy carry `Cache-Control: no-cache` like `_RevalidatedFiles` did — a stale `style.css` with a new `index.html` must not happen. (Task 2 Caddyfile + curl check.)
4. Owner's existing local state after the move: `.env` at root still read when running from `backend/`; `data/reminders.json` and `models/pt_BR-*` now expected under `backend/`. (Task 1 settings test + README note.)
5. `.gitignore` patterns with a slash are root-anchored: `models/pt_BR-*` must become `backend/models/pt_BR-*` or the Piper voice gets committed. (Task 1 `git status` check.)

---

### Task 0: Bring in the Gemini Live fix (owner decision)

`fix/resilient-devices` (`1ac65aa`) touches `app/adapters/gemini/live_events.py`, `app/application/use_cases/run_live_session.py`, `web/live.js`. Owner merges it into `main` (or tells the executor to). Then:

- [ ] **Step 1:** `git fetch && git rebase origin/main` on this branch. Expected: clean rebase.
- [ ] **Step 2:** `pytest -q` → all pass (peer reported 724).

---

### Task 1: Move to `frontend/` and `backend/`

**Files:**
- Move (`git mv`): `web/` → `frontend/`; `tests/web/` → `frontend/tests/`; `app/ main.py alembic.ini migrations/ tests/ scripts/ voice/ models/ pyproject.toml requirements.lock Dockerfile .dockerignore` → `backend/`
- Modify: `backend/main.py` (`WEB_DIR`), `backend/app/config.py:99`, `backend/voice/config.py:27`, `frontend/tests/*.mjs` imports, `.pre-commit-config.yaml`, `.gitignore`
- Test: `backend/tests/unit/test_config.py` (or the existing settings test file — append there)

**Interfaces:**
- Produces: `backend/` is the Python project root (cwd for ruff/pyright/pytest/uvicorn). `frontend/` is a static dir with `index.html` at its top.

- [ ] **Step 1: Move with `git mv` only, commit nothing else in this step.** One commit keeps rename detection: `refactor: split repo into frontend/ and backend/`.
- [ ] **Step 2: Fix paths**
  - `backend/main.py`: `WEB_DIR = Path(__file__).resolve().parent.parent / "frontend"`.
  - `frontend/tests/*.mjs`: `'../../web/x.js'` → `'../x.js'`.
  - `app/config.py` and `voice/config.py`: `env_file=("../.env", ".env")` (later wins; root `.env` is the shared one).
  - `.pre-commit-config.yaml`: large-file exclude `^frontend/models/`; ruff hooks `files: ^backend/` with `args: [--config, backend/pyproject.toml, ...]`; pyright `entry: bash -c "cd backend && pyright"`.
  - `.gitignore`: `models/pt_BR-*` → `backend/models/pt_BR-*`.
  - `app/adapters/postgres/migrate.py` `parents[3]` still resolves to `backend/` — no change, verify.
- [ ] **Step 3: Write the failing test** `test_settings_read_root_env_file`: in `tmp_path`, write `tmp_path/".env"` with `BYTE_API_TOKEN=` + 40×`a`, `chdir` to `tmp_path/"backend"`, `Settings()` (without `_env_file=None`) → `api_token.get_secret_value() == "a"*40`. Mirror one for `VoiceSettings` with `BYTE_VOICE_WAKE_MODEL=hey_jarvis`.
- [ ] **Step 4:** `cd backend && pytest -q` → same count as Task 0 Step 2 plus the 2 new tests; `ruff check . && pyright` clean.
- [ ] **Step 5:** `node --test frontend/tests/` → all pass.
- [ ] **Step 6:** From `backend/`: `python main.py --web` boots, `curl -s http://127.0.0.1:8000/` returns the panel HTML. `git status` clean (no Piper model, no `data/` tracked).
- [ ] **Step 7: Commit** `fix: repoint paths after the frontend/backend split`.

---

### Task 2: Caddy in front, API without TLS

**Files:**
- Create: `deploy/Caddyfile`
- Modify: `docker-compose.yml` (root), `backend/Dockerfile`, `.env.example` (root)

**Interfaces:**
- Consumes: `backend/` build context, `frontend/` static dir from Task 1.
- Produces: services `caddy`, `api`, `db`; env `BYTE_SITE`.

- [ ] **Step 1: `deploy/Caddyfile`**

```
{$BYTE_SITE:byte.local} {
	tls internal
	encode gzip
	handle /api/* {
		reverse_proxy api:8000
	}
	handle {
		root * /srv/frontend
		header Cache-Control no-cache
		file_server
	}
}
```

- [ ] **Step 2: `backend/Dockerfile`** — `COPY web ./web` removed; `CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--proxy-headers", "--forwarded-allow-ips=*"]`; healthcheck plain `http://localhost:8000/api/v1/health`.
- [ ] **Step 3: `docker-compose.yml`**
  - `api`: `build: ./backend`, `env_file: .env`, ports `"127.0.0.1:8000:8000"`, volumes `./backend/models:/app/models:ro` + `byte-data:/app/data`; `certs` mount removed; `BYTE_WEB` not set.
  - `caddy`: `image: caddy:2.8-alpine`, ports `"${BYTE_PUBLISH_HOST:-127.0.0.1}:443:443"` and `:80:80`, volumes `./deploy/Caddyfile:/etc/caddy/Caddyfile:ro`, `./frontend:/srv/frontend:ro`, `caddy-data:/data`, `caddy-config:/config`; `environment: BYTE_SITE: ${BYTE_SITE:-byte.local}`; `depends_on: api`.
  - `db` unchanged. Volumes add `caddy-data`, `caddy-config`.
- [ ] **Step 4: `.env.example`** — add `BYTE_SITE=` (LAN name, default `byte.local`; a real domain later turns on Let's Encrypt after removing `tls internal`). LAN block: `BYTE_PUBLISH_HOST` now binds Caddy; `BYTE_TLS_CERT/KEY` documented as Windows-PC-only (uvicorn).
- [ ] **Step 5: Smoke** with `BYTE_SITE=localhost` in `.env`, `docker compose up --build -d`:
  - `curl -sk https://localhost/api/v1/health` → 200.
  - `curl -sk -o /dev/null -w '%{http_code}' -X POST https://localhost/api/v1/messages -d '{}'` → 401.
  - `curl -skI https://localhost/style.css` → contains `cache-control: no-cache`.
  - `curl -s http://127.0.0.1:8000/api/v1/health` → 200 (voice path).
  - Browser `https://localhost/`: log in with token, send a chat message, panel weather pushes over `/ws/panel` (devtools: socket 101, stays open).
- [ ] **Step 6: Commit** `feat(deploy): serve the panel and proxy the API through Caddy`.

---

### Task 3: Docs and voice service paths

**Files:**
- Modify: `README.md`, `CLAUDE.md`, `docs/VOICE.md`, `deploy/byte-voice.service`, `docs/web-api-contract.md` (only if it names `web/`)

- [ ] **Step 1:** `byte-voice.service`: `WorkingDirectory=/opt/byte/backend`, `ExecStart=/opt/byte/backend/.venv/bin/python -m voice.main`; `BYTE_VOICE_URL` default (`ws://127.0.0.1:8000/api/v1/live`) still right — note it in `docs/VOICE.md` and update install paths there.
- [ ] **Step 2:** `README.md`: layout section; dev commands under `cd backend`; replace the openssl/`certs/` LAN section with: set `BYTE_PUBLISH_HOST=<LAN IP>` + `BYTE_SITE`, export Caddy's root (`docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt .`), install it on each phone, ESP32 pins it. Note that local `data/` and `models/pt_BR-*` move to `backend/`.
- [ ] **Step 3:** `CLAUDE.md`: architecture tree under `backend/`, web panel path `frontend/`, Docker section (Caddy owns TLS, API loopback), Safety/Network rule rewritten to the new setup ("LAN through Caddy with HTTPS; wider exposure is the owner's call"), tooling commands from `backend/`, Current state row "Front/back split + Caddy (Spec 7) | done".
- [ ] **Step 4:** `grep -rn "web/" README.md CLAUDE.md docs/*.md deploy` → no stale `web/` path left (specs/plans under `docs/superpowers/` are historical, leave them).
- [ ] **Step 5: Commit** `docs: describe the frontend/backend layout and Caddy deployment`.

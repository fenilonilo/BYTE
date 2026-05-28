# Marcelo

Personal AI assistant — hexagonal architecture, multi-channel (WhatsApp), gesture-controlled UI.

## Prerequisites

- Python 3.12+
- Node.js 20+ (for frontend)
- `uv` or `pip` for Python deps
- `.env` file with required variables (see `app/config.py`)

## Services overview

| Service | Port | Description |
|---|---|---|
| Backend API | `8000` | FastAPI — REST + WebSocket |
| Gesture CV | `8001` | MediaPipe pose detection service |
| Frontend UI | `5173` | Svelte 5 + Vite dev server |

## 1. Python environment

```powershell
# Create and activate venv
python -m venv .venv
.venv\Scripts\Activate.ps1

# Install all optional deps
pip install -e ".[api,llm,db,vision,dev]"
```

With `uv`:
```powershell
uv sync --all-extras
```

## 2. Backend API (port 8000)

```powershell
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

- API docs: http://localhost:8000/docs
- WebSocket chat: `ws://localhost:8000/ws/chat`
- WebSocket gesture: `ws://localhost:8000/ws/gesture`

> **Note:** On first start, the backend tries to register a WhatsApp webhook via Evolution API. If the gateway is not running, it silently skips and continues.

## 3. Gesture CV service (port 8001)

Separate process — must run alongside the backend when using gesture control.

```powershell
python gesture_service/main.py
```

Endpoints:
- `GET /current` — current detected pose
- `POST /record/start` / `/record/stop` — capture session for gesture config
- `POST /reload` — reload gesture bindings from disk

## 4. Frontend (port 5173)

```powershell
cd marcelo-ui
npm install        # first time only
npm run dev
```

UI: http://localhost:5173

Vite proxies `/ws` → `ws://localhost:8000`, so backend must be running.

## 5. Quality checks

```powershell
ruff check . && ruff format .   # lint + format
pyright                          # type check (strict)
pytest                           # tests + coverage (≥80% required)
pre-commit run --all-files       # all gates at once
```

## Environment variables

All vars use `MARCELO_` prefix. Minimum required to boot:

```env
MARCELO_APP_NAME=Marcelo
MARCELO_WEBHOOK_BASE_URL=http://your-public-url-or-ngrok
# LLM keys (at least one)
GROQ_API_KEY=...
ANTHROPIC_API_KEY=...
GOOGLE_API_KEY=...
```

See `app/config.py` for full list with defaults.

## Typical dev startup sequence

1. Activate venv
2. Start backend: `uvicorn main:app --reload`
3. Start gesture service: `python gesture_service/main.py`
4. Start frontend: `cd marcelo-ui && npm run dev`
5. Open http://localhost:5173

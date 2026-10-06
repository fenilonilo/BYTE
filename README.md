# Byte

A personal assistant backend for one person, running headless in Docker on a home
server. It controls lights, an air conditioner and music, manages a calendar and tracks
monthly expenses. Chat today (`POST /api/v1/messages`); a live spoken mode comes next.

One agent holds every tool. Every outside resource (the model provider, the smart
home, the calendar, the expense sheet, storage) is an adapter behind a port.

No GUI, no computer vision, no chat-channel adapters, no multi-user support.

## Run

```bash
cp .env.example .env        # fill BYTE_API_TOKEN (32+ chars) and BYTE_OPENAI_API_KEY
docker compose up --build
```

API on `http://127.0.0.1:8000/api/v1`, interactive docs at `/docs`. Compose binds to
loopback only.

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

## Develop

```bash
pip install -e ".[api,openai,thinq,tuya,spotify,dev]"
ruff check . && pyright && pytest
pytest -m integration        # hits the real OpenAI API (needs BYTE_OPENAI_API_KEY)
```

## Status

Chat is built end to end. Lights (Tuya), the air conditioner (ThinQ) and music (Spotify)
have real adapters; the calendar and the expenses are still **in memory**, so the whole
flow (tools, confirmation) also runs with no device at all. Not built yet: live voice, the
Google Calendar and Google Sheets adapters, Postgres persistence (history is in memory
and lost on restart) and the reminder scheduler.

See `CLAUDE.md` for the rules, `docs/ARCHITECTURE.md` for the decisions and
`docs/superpowers/specs/` for the design.

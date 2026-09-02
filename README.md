# Byte

A JARVIS-style personal voice assistant, running headless in Docker on a home
server. It controls smart-home devices, manages a calendar, and tracks monthly
expenses — spoken to, not clicked.

The intended client is a custom **ESP32-S3** device: wake word detected on the
device, audio streamed to this server, answer spoken back. Any other
application can use the same HTTP API.

No GUI, no computer vision, no chat-channel adapters. HTTP is the only
interface.

## Segments

| Segment | Owns | Talks to |
|---|---|---|
| `home` | Lights, plugs, sensors, scenes | Tuya Cloud API |
| `agenda` | Events, appointments, reminders | Google Calendar |
| `finance` | Monthly expenses, bills, spend totals | Google Sheets |

Name a segment to reach its agent directly. Omit it and the routing agent picks
one from what you said — that is the voice path.

## Run

```bash
cp .env.example .env
docker compose up --build
```

API on `http://127.0.0.1:8000/api/v1`. Interactive docs at `/docs`.

## Use

```bash
curl -X POST http://127.0.0.1:8000/api/v1/messages \
  -H 'content-type: application/json' \
  -d '{"content": "apaga a luz da sala", "segment": "home"}'
```

```json
{
  "id": "…",
  "role": "assistant",
  "content": "[stub:home] apaga a luz da sala",
  "conversation_id": "…"
}
```

Pass `conversation_id` on later calls to continue the same conversation. An
unknown `segment` returns `404`.

## Develop

```bash
pip install -e ".[api,dev]"
ruff check . && pyright && pytest
```

## Status

The skeleton is complete and green: hexagonal layout, segment registry, direct
routing, Docker. Agents are still `StubAgent` (echo).

Not built yet: the Agno adapter and Team routing, Postgres, the Tuya / Google
Calendar / Google Sheets adapters, the voice pipeline, the reminder scheduler,
and **API authentication**.

> Byte controls physical devices and reads financial data, and it has no
> authentication yet. That is why compose binds to `127.0.0.1`. Do not expose it
> until auth exists.

See `CLAUDE.md` for the rules, `docs/ARCHITECTURE.md` for the decisions.

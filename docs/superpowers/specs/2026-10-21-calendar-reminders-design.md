# Spec 3 — Google Calendar, reminders and alarms

Status: approved by the owner in conversation (2026-10-21); the owner delegated every open
decision ("tome as melhores decisões"). Calls made without the owner are marked *(my call)*.

## Intent

Byte speaks first. The owner says "me lembra amanhã às 9 de pagar a luz" or "alarme às 6h30"
and, at that moment, the voice device says it out loud. Appointments in Google Calendar,
including ones created from the phone, are announced 10 minutes before they start.

**Hard constraint from the owner: spend the fewest model tokens possible.** The model is used
only to understand the request (one short tool call). Scheduling, firing, speech and stopping
an alarm are plain code and local models — zero tokens.

## Goals

1. `create_event` / `list_events` / `delete_event` work against the owner's real Google
   Calendar (the tools already exist; only the adapter is missing).
2. Reminders (`lembrete`, spoken once) and alarms (`alarme`, beep + speech repeating until
   stopped), created by voice or chat, fired at the wall-clock time.
3. A spoken warning 10 minutes before each Google Calendar event.
4. A reminder due while the device is off or disconnected is spoken as soon as it reconnects,
   even late. Nothing is silently dropped — except calendar warnings, which expire at the
   event's start *(my call: "em 10 minutos, dentista" three hours late is noise)*.
5. The model knows the current local date and time (today it does not).

## Non-goals

- Snooze, recurring reminders, editing a reminder (cancel + create covers it).
- Reminders delivered to chat or the web panel. Only the voice device speaks them.
- Postgres. Reminders live in a JSON file until the Postgres spec.
- Google Sheets (expenses) — later.

## Anti-goals

- A model call when a reminder fires, or to stop an alarm.
- A reminder lost because the device was offline or the server restarted.
- An alarm that only stops on a model-recognised word ("para") — that would open a paid
  live session. It stops on the local wake word "Ei Byte".

## Design

### Current time in the prompt

`Settings.timezone` (default `America/Sao_Paulo`, validated with `zoneinfo`; `tzdata` becomes a
core dependency because the slim image and Windows ship no tz database). Chat and live append
one short line to the system prompt: `Agora: 2026-10-21 14:32, quarta-feira.` Live computes it
at session start (sessions last ≤ 10 min). Both use cases receive an injected wall clock.
Naive datetimes from the model are read in the configured timezone.

### Google Calendar adapter (`app/adapters/google/google_calendar.py`)

- REST over `aiohttp` (already used by Spotify), not `google-api-python-client` (sync, heavy).
- OAuth refresh token from env, like Spotify: `BYTE_GOOGLE_CLIENT_ID`,
  `BYTE_GOOGLE_CLIENT_SECRET`, `BYTE_GOOGLE_REFRESH_TOKEN`, `BYTE_GOOGLE_CALENDAR_ID`
  (default `primary`). Scope `calendar.events`. `scripts/google_login.py` runs the one-time
  loopback consent and prints the refresh token. The OAuth app must be set to *In production*
  (unverified is fine for one user) — in *Testing* Google expires refresh tokens after 7 days.
- Idempotency: the event id sent to Google is `sha256(key)` in hex (hex ⊂ base32hex, which
  Google accepts as a client-chosen id). A 409 on insert means "already created" → fetch it.
- `list_events(day)` asks for that day in the configured timezone, single events expanded,
  ordered by start. Errors become `CalendarError(DomainError)`; 404 → `EventNotFoundError`.
- `get_calendar()` picks it when the three Google settings are set, else in-memory (same rule
  as the other device groups). The real adapter must pass `CalendarPortContract`
  (integration marker).

### Reminders — domain and storage

- `app/domain/reminders.py`: `ReminderKind` (`lembrete`, `alarme`) and
  `Reminder(id, text, at, kind, expires_at: datetime | None)`, pure functions for "due" and
  "expired", and `calendar_warnings(events, lead)` that maps events to reminders with id
  `cal-<event id>-<start>`, `at = start - 10 min`, `expires_at = start`.
- `ReminderStorePort` (`add`, `remove`, `all`). Adapter `JsonReminderStore`: the whole list in
  one JSON file, rewritten atomically (temp file + `os.replace`) on every change.
  `BYTE_REMINDERS_PATH` (default `data/reminders.json`); compose mounts `./data`.
  *(my call: one file adapter, tests use `tmp_path`; Postgres replaces it behind the port.)*

### Tools (segment `agenda`)

- `create_reminder(text, at, kind)` — `at` ISO 8601; rejects a time in the past; id derived
  from the idempotency key. No confirmation.
- `list_reminders()` — user reminders only (not calendar warnings), short one-line format.
- `cancel_reminder(id)` — no confirmation *(my call: a cancel is cheap to undo and a
  confirmation round costs tokens; `delete_event` keeps its confirmation)*.

Tool descriptions and results stay one line — tokens.

### Firing — `ReminderHub` (application, singleton via `lru_cache`)

Holds the current listener (the device connection) and the ids already sent on it.

- `tick(now)`: drop expired reminders; push each due, unsent reminder to the listener; no
  listener → nothing happens, the reminder waits in the store.
- `ack(id)`: the device has played it (reminder) or the owner stopped it (alarm) → remove.
  Reminders sent but never acked are pushed again on the next connection.
- `sync_calendar(now)`: list today's and tomorrow's events, upsert their warnings, remove
  `cal-` warnings whose event disappeared or moved.

A background task started in the FastAPI lifespan calls `tick` every 5 s and `sync_calendar`
every 5 min, logging and surviving any error *(ponytail: polling; sleep-until-next-due if the
5 s granularity ever matters)*. Google is still the source of truth: warnings are recomputed
from it, never trusted as cached data.

### Speech — `SpeechPort` + Piper

- `SpeechPort.synthesize(text) -> bytes`: PCM16 mono 24 kHz, opaque to `application/`.
- `PiperSpeech` adapter (`piper-tts`, CPU, ~60 MB voice `pt_BR-faber-medium`), run in a
  thread, resampled 22.05 → 24 kHz inside the adapter. `BYTE_PIPER_MODEL` points at the
  `.onnx`; compose mounts `./models` read-only. Unset → `SilentSpeech` (empty audio: the
  device still beeps) and the boot log says so.
- Synthesis runs on the server so the future ESP32 only plays audio.

### Protocol — `WS /api/v1/ws/notifications`

Same auth as `/live` (bearer header or `["bearer", token]` subprotocol). One listener; a new
connection replaces the old one (close code 4000).

- server → device: `{"type":"reminder","id":"…","kind":"lembrete"|"alarme"}` then one binary
  frame with the speech PCM (may be empty). No text on the wire — the device does not need it.
- device → server: `{"type":"ack","id":"…"}`.
- Keep-alive is the WebSocket ping of the libraries. No model involved: zero tokens.

### Voice client (`voice/`)

- `voice/notifications.py`: keeps the link open, reconnects every 5 s on failure.
- Plays a reminder (two-tone chime + speech) only while `VoiceSession` is idle; queues
  otherwise. Ack after it finishes playing.
- Alarm: beep + speech, pause, repeat, until the wake word is heard; then ack. The wake word
  while ringing stops the alarm and does **not** open a live session. Safety cap: rings at
  most 5 minutes, then stops and acks *(my call)*.
- Beeps are generated with numpy; no audio assets.

## Build order

1. Timezone setting + current time in chat/live prompts.
2. Domain reminders + `ReminderStorePort` + `JsonReminderStore` (+ contract tests).
3. Reminder tools + registry wiring.
4. `SpeechPort`, `SilentSpeech`, `PiperSpeech`.
5. `ReminderHub` + scheduler task + `WS /ws/notifications`.
6. Voice client notifications + alarm stop on wake word.
7. Google Calendar adapter + `scripts/google_login.py`.
8. `.env.example`, compose volumes, Dockerfile, README/CLAUDE.md current state, lock file.

Every step: TDD for the application/domain logic, `ruff check`, `pyright`, `pytest` green.

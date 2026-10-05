# Byte — Personal agent: chat + live, tools as adapters (Spec 1)

Status: **DRAFT v3 — reviewer rounds 1-2 applied; awaiting owner review.** Not approved. No implementation before approval.
Date: 2026-10-05 · Branch: `feat/agno-team-routing` (to be renamed) · Author: Claude + owner

## 0. Intent (agreed with owner)

One personal assistant for **one person**. Two ways in:

- **chat** — a text message in, a text reply out (`POST /messages`).
- **live** — a spoken conversation over a WebSocket where the agent executes tools mid-conversation.

Every integration with an outside resource (LLM provider, smart home, calendar, spreadsheet, storage) is an **adapter** behind a **port**. No SDK type crosses a port.

Scope of Spec 1: foundation + chat + live, with **tools backed by in-memory adapters** (real adapters, fake world). Tuya / Google Calendar / Google Sheets / Postgres are later specs and are swaps of adapters, not rewrites.

Success criteria:

1. Same tool set, same confirmation rules, in chat and in live.
2. A tool marked `requires_confirmation` can never run unless **the very next user utterance after the request is affirmative** (enforced in code, not prompt).
3. Swapping OpenAI for another provider touches one adapter package only.
4. `ruff`, `pyright --strict`, `pytest` green; the findings of the project report (A1-A6, M1-M9) closed or explicitly deferred (§4).

### Decisions taken

| # | Decision | Why |
|---|---|---|
| D1 | Provider: **OpenAI** for chat and live; live model `gpt-realtime-2.1-mini`. Gemini Live is the planned second `LiveSessionPort` adapter. | Owner choice. Flagship realtime audio is $32/$64 per 1M tokens vs $10/$20 for mini (confirmed by reviewer on OpenAI's pricing page). Gemini Live figures ($3/$12) come from ai.google.dev pricing, checked by the author only. At personal scale the gap is $10-40/month, so quality (tool-call reliability, pt-BR, latency) decides — settled by an A/B day, not assumed. |
| D2 | **Drop Agno, Team and `Registry[AgentPort]`.** One agent, all tools, own ~80-line tool loop. | Single user + ~10-15 tools: routing hop is pure latency; Agno cannot do speech-to-speech, so live would bypass it and tools would be defined twice. Reverses ADR-010. Real loss: cross-provider fallback. The OpenAI SDK's default retries (2) cover 429/5xx; accepted. Reviewer agrees. |
| D3 | `segment` becomes an optional **tool filter**; omitted or `auto` = all tools; unknown segment still **404**. | Keeps the direct-call use case at one line of code. |
| D4 | Live client contract: a plain WebSocket protocol; **ESP32-S3 is one client**, a terminal script is another. Repo ships no GUI. | Owner choice; keeps the "no frontend" rule intact. |
| D5 | Tools execute **server-side**. The provider only chooses which tool to call. | Credentials live here; provider never holds them. |
| D6 | **LAN exposure with TLS** (see §3 Deployment). **Approved by owner 2026-10-05**: it relaxes the "127.0.0.1 only" rule, which CLAUDE.md allows only in a change that also adds authentication — this change does. | The ESP32 cannot reach a loopback-bound server; plain `ws://` would send the bearer token in cleartext. |
| D7 | Audio is **opaque `bytes`** to `application/`: relayed, never decoded or transformed. | Needed for `RunLiveSession` to live in `application/`; requires amending the CLAUDE.md audio rule (§4 step 7). |

## 1. Layers and ports

```
domain/       Message, Conversation, ToolSpec, ToolCall, PendingAction, LiveEvent,
              is_affirmative(text)                                                (dataclasses + pure fns, stdlib only)
ports/        ChatModelPort   complete(messages, tools) -> ModelTurn   (text | tool_calls)
              LiveSessionPort open(instructions, tools) -> LiveSession
                              LiveSession: send_audio(bytes), events(), send_tool_results(list), interrupt(audio_end_ms), close()
              HomePort / CalendarPort / ExpensesPort    what a tool needs from the world
              ConversationStorePort   get(id), append(id, messages)  (atomic append; `get` and `append` both count as use for LRU;
                                      `append` on an unknown or evicted id creates the conversation)
              LoggerPort
application/  Registry[T]          existing generic registry, reused for tools (name -> Tool); optional segment filter
              Tool (ABC)           spec: ToolSpec ; execute(args) -> str       (application code, NOT a port)
              ToolRunner           allowlist, timeout + shield, confirmation, output truncation
              PendingActionStore   one pending action per conversation; on_user_utterance(conv_id, text); injectable monotonic clock
              ProcessChatMessage   text -> model/tool loop -> reply
              RunLiveSession       WS bytes <-> LiveSessionPort, dispatches tool calls to ToolRunner
adapters/     openai/  (chat + realtime)    memory/  (Home, Calendar, Expenses, Store)    structlog/
api/          POST /messages   WS /live   GET /health   bearer-token dependency
```

Rules carried over from CLAUDE.md: `domain` stdlib only, ports are `ABC`, one use case per file, async I/O, strict typing, `LoggerPort` instead of `print`.

- Tools are **application code**; they call ports, never SDKs. Implementations of `Tool` live in `application/tools/`.
- A home tool takes a **device name**; the adapter validates it against the known device list. The model never supplies a raw device or spreadsheet id.
- **Lifetimes**: `PendingActionStore`, the conversation store and the tool `Registry` are singletons built once via `lru_cache` in `api/deps.py` (hard rule 8). Use cases are built per request and hold no state. Creating the pending store per request would make confirmation impossible.
- **Atomic `append(conversation_id, messages)`** on the store replaces the per-conversation lock of v1: chat and live both append whole turns, so no lost update (A4) and no lock to forget in live.
- **Clocks are injected**: `PendingActionStore` and `RunLiveSession` receive `now: Callable[[], float]` (monotonic). The 60 s expiry, the 2 s transcript wait and the "during playback" window are tested without sleeping.
- Removed: `agno`, `groq`, `google-genai` dependencies, `AgnoAgent`, `AgentPort`, `AgentRegistry` wiring, Team routing, `tests/unit/adapters/test_model_tiers.py`.

## 2. Tool loop and confirmation

Loop (chat):

```
msgs = last 20 messages of the conversation + new user message
repeat up to 6 steps:
    turn = model.complete(msgs, registry tools, parallel_tool_calls=False)
    no tool_calls -> store.append(...) ; return turn.text
    tool_calls    -> ToolRunner.run(each) -> append results to msgs
exceeded 6 steps -> AgentError (502)
```

- `ToolRunner` limits: 10 s per tool, output truncated to 2,000 chars, 30 s for the whole chat request (exceeding it raises `AgentError`, mapped to 502).
- Tool execution is wrapped in `asyncio.shield`: a dropped socket or request cancellation does not abort a physical action halfway. On the 10 s timeout the model receives `estado desconhecido: verifique o dispositivo` — never "success" or "failure" — and the real outcome is logged when the shielded task finishes. `ToolRunner` keeps **strong references** to shielded tasks in a set (the event loop only holds weak ones), logs the outcome in a done-callback, and the FastAPI lifespan drains the set on shutdown. Because the model may re-request after "estado desconhecido", mutating tools take the pending action's id as an **idempotency key** (e.g. `write_expense` never writes the same id twice).
- A tool failure does **not** fail the turn: unknown tool, tool outside the segment filter, or tool error is returned to the model as text (`erro: ...`) so it can explain.
- Tool results are not persisted in history (only user/assistant text), which is why confirmation must not depend on a model-visible id (below).

### Confirmation (closes A6) — v2

- `ToolSpec.requires_confirmation` marks sensitive tools: unlock door, turn off something running, delete calendar event, write an expense.
- Calling such a tool does **not** execute it. `ToolRunner` stores a `PendingAction(tool, frozen args, summary, created_at, expires_at=+60 s)` in `PendingActionStore`, **keyed by `conversation_id`, at most one per conversation** (a new request replaces the old one). It returns `needs_confirmation` to the model.
- The **summary is generated by code** from the frozen args (not by the model). In chat it is also returned in the HTTP response (`pending_confirmation.summary`, additive optional field, API stays v1) so the user sees the exact action even if the model paraphrases.
- Execution happens only via the built-in tool `confirm_action()` — **no arguments**, so there is no id to guess, replay or smuggle across conversations. It is registered **whatever the segment filter**. With nothing pending (or already dropped) it returns `erro: nada para confirmar`. It runs iff, atomically (pop before execute, so two parallel calls cannot both run):
  1. a pending action exists for this conversation and has not expired (60 s, injectable monotonic clock), and
  2. it is **armed**, i.e. this is the **very next user utterance** after the request. Both use cases call `PendingActionStore.on_user_utterance(conv_id, text)` for every user utterance: the first one after creation arms the pending action (and records its text); any later one **drops** it. Turn order, not timestamps, so "unlock the door? / what time is it? / want the AC on? / yes" cannot unlock the door, and
  3. the armed utterance satisfies `is_affirmative(text)`. The matcher is pure and unit-tested: lowercase, strip accents and punctuation, **whole words only** (never substrings: "assim" must not match "sim"), accept only utterances of **5 words or fewer** (long TV dialogue never qualifies), and the **deny list wins**: não/nao, nem, nunca, negativo, cancela, para/pare/parar, espera, deixa, esquece, depois ("pode deixar", "pode esquecer", "nem pensar" are denials).
- Same rules in chat (the utterance is the next `POST /messages` body; while a pending action exists the loop prepends a system line with its summary so the model knows to call `confirm_action`) and in live (the transcript, below).
- **Live specifics**: input transcription is enabled; `confirm_action` waits up to 2 s for `input_audio_transcription.completed` of the committing item. Commits that **start while assistant audio is playing** (echo, TV) are ignored for confirmation, and commits produced by `idle_timeout`/`timeout_triggered` never count. If no transcript arrives in time, the action is not confirmed.
- False negatives (unusual phrasing) cost one repeat; false positives are what the matcher is built to avoid. Pending actions live in memory: a restart drops them (fails safe).
- Residual risk, stated plainly: a spoken "sim" from a TV or another person in the room still counts. Speaker verification is out of scope; the 60 s expiry, the next-utterance-only rule and the code-generated summary limit the window. In **live** the user hears the model's wording, not the code-generated summary: the summary is placed in the `needs_confirmation` output with an instruction to read it word for word, so protection there depends on the model complying. The chat API returns the summary verbatim.

## 3. Live protocol, auth, deployment, config

### Deployment (D6 — approved by owner)

- Default compose stays bound to `127.0.0.1` (chat from the server itself). A documented env var `BYTE_PUBLISH_HOST=<LAN IP>` opts in to LAN exposure for the ESP32; never `0.0.0.0` on a host with a public interface.
- **TLS (`wss://`)**: uvicorn serves with `--ssl-keyfile/--ssl-certfile`; self-signed certificate whose fingerprint (or CA) is **pinned in the ESP32 firmware**. Cert generation is a documented one-time command, not a new container. The certificate's **SAN must include the server's LAN IP**, so the server gets a fixed DHCP reservation. The firmware pins it via `cert_pem`, never uses `skip_cert_common_name_check`, and needs SNTP for the validity check (or the certificate gets a long validity). `esp_websocket_client` can send the `Authorization` header over `wss` (confirmed in Espressif docs).
- `BYTE_API_TOKEN` must be **at least 32 characters**; the app refuses to boot otherwise.

### Auth

- `Authorization: Bearer <token>` on the upgrade request (ESP32 can set headers). Compared with `hmac.compare_digest`. Failure -> 401 on `/messages`, close code 1008 on the socket. Never a query-string token. The same dependency guards both.

### Protocol — `WS /api/v1/live`

- **Handshake**: first client frame is JSON `{"type":"start","conversation_id"?,"segment"?}`. The server opens the provider session first and sends `{"type":"ready","conversation_id","audio":{"format":"pcm16","rate":24000,"channels":1}}` **only after the provider's `session.updated`**. The firmware buffers microphone audio captured between the wake word and `ready` (bounded buffer; firmware concern).
- **Audio**: binary frames both ways, PCM16 mono little-endian, **24 kHz** (the only rate the provider's `audio/pcm` accepts). The microphone runs at 16 kHz for the wake-word engine, so the **firmware upsamples 16 -> 24 kHz (2:3)** — decided now. G.711 (`pcmu`/`pcma`, 8 kHz) is the documented alternative if the upsampler proves too heavy. The server never resamples.
- **Echo (firmware requirement)**: use ESP-SR acoustic echo cancellation (AFE AEC) or mute the microphone while playing. Without it, server VAD hears the assistant and barges in on itself, cutting most replies short. The session also sets `input_audio_noise_reduction: far_field`.
- **Provider session config, set explicitly** (docs disagree on the default): `server_vad` via `BYTE_LIVE_VAD` (A/B against `semantic_vad`), input transcription on (`gpt-4o-mini-transcribe`, billed separately, roughly $0.003/min), realtime `truncation.retention_ratio` set to bound re-billed context.
- **Server -> client JSON events**: `transcript {role, text, final}`, `interrupt`, `turn_done`, `error {code}`.
- **Barge-in**: on the provider's `speech_started` the server sends `interrupt`; the client stops playback and replies `{"type":"played","audio_end_ms":N}`; the server calls `conversation.item.truncate(audio_end_ms)` so the model's memory matches what was actually heard. Downstream audio is **paced** (bounded queue, ~real-time) because the provider sends faster than real time; WebSocket `max_size` is capped.
- **Tool calls**: one `response.done` can contain several calls. `RunLiveSession` runs them **sequentially** (physical actions), sends all outputs through `send_tool_results(list)`, then sends **exactly one `response.create`** — deferred while another response is active (barge-in).
- **Session lifecycle**: ends on client close, 60 s idle, or a 10-min hard cap (provider's own limit is 60 min). A **new connection replaces the old one** (old gets close code 4000): after a Wi-Fi drop the half-open socket must not lock the user out. Clients **must not auto-reconnect after close code 4000**, or two clients would keep evicting each other.
- **Live history**: no stored history is loaded into a live session in Spec 1 (cold start each time; cost stays bounded). Transcripts **are** saved at turn end via `append`, so a later chat message can continue the conversation.

### Config and limits

- All settings `BYTE_`-prefixed, including keys (removes the alias inconsistency): `BYTE_API_TOKEN`, `BYTE_OPENAI_API_KEY`, `BYTE_CHAT_MODEL`, `BYTE_LIVE_MODEL`, `BYTE_LIVE_VAD`, `BYTE_PUBLISH_HOST`, timeouts and caps. Validated at boot in the FastAPI lifespan (fail fast, closes M1). `log_level` applied; JSON logs when stdout is not a TTY (M3).
- Input limits on `POST /messages`: `content` 1-4,000 chars; `conversation_id` matches `^[A-Za-z0-9_-]{1,64}$` (A3).
- Logs never contain tool arguments, transcripts or message content; only ids, tool names, durations, status.

## 4. Errors, bounds, testing, migration

### Errors

- Domain errors: `AgentError` (model or loop failure), `LiveSessionError`, `ConfigError` (boot only). Adapters wrap provider exceptions and keep `__cause__`.
- HTTP mapping lives in the router layer: auth 401, validation 422, unknown segment 404, `AgentError` 502, any other `DomainError` 500 with a generic body. No raw 500s.
- Logging records exception **type and the provider's HTTP status**, never content (closes M6).
- Live: failure -> `error {code}` event (`model_unavailable`, `session_limit`, `internal`) then close. A mutating tool that already ran cannot be rolled back, so tools are written **idempotent** and the shield/timeout rules of §2 apply.
- No cross-provider fallback in Spec 1 (D2). Closes M8 by removal.

### Bounds (closes A5)

- Chat context sent to the model: **last 20 messages**. Live: no stored history (§3).
- In-memory store: **max 50 conversations**, least-recently-used evicted. History is lost on restart; Postgres is a later spec.
- Pending confirmations: dropped on expiry or restart.
- Two concurrent chat requests on the same conversation may interleave their turns (atomic append prevents loss, not ordering). `# ponytail:` acceptable for one owner.

### Testing

TDD for: `Registry`+`Tool` wiring, `ToolRunner` (confirmation matrix: no pending, expired, confirm in same request, non-affirmative utterance, negation, replaced pending, parallel `confirm_action` runs once, other conversation, shield on cancel, timeout -> "estado desconhecido"), `is_affirmative`, `ProcessChatMessage` loop, `RunLiveSession` (multi-call `response.done` -> one `response.create`, deferred while active, echo-commit ignored, transcript timeout), auth dependency, router (including WebSocket via `TestClient`: replace-on-reconnect, `ready` only after `session.updated`), settings boot validation (token length).

- `is_affirmative` table-driven test, each case explicit: "sim", "pode", "confirmo", "manda ver" pass; "assim", "pode deixar", "pode esquecer", "nem pensar", "espera", "não, cancela", a 12-word TV sentence containing "sim" fail.
- Confirmation matrix additions: pending survives only until the next utterance ("unlock? / what time? / AC? / yes" does not unlock); `confirm_action` with nothing pending -> `erro: nada para confirmar`; `confirm_action` present under every segment filter; shielded task survives cancellation and is drained at shutdown; idempotency key stops a double write after "estado desconhecido".
- Store: LRU counts both `get` and `append`; `append` on an unknown or evicted id creates the conversation.
- All time-dependent tests use the injected clock; none sleeps.
- Test doubles: `ScriptedChatModel` and `ScriptedLiveSession` under `tests/fakes/`.
- **Port contract suites**: one per port (`HomePort`, `CalendarPort`, `ExpensesPort`, `ConversationStorePort`) run against every adapter, including negative cases (unknown device -> `DomainError`). In-memory passes now; Tuya/Google must pass the same suite later (integration marker). This keeps the fakes honest.
- OpenAI adapters: integration tests against the real API, marked `integration`+`slow`, **excluded from default `pytest`** via `addopts`.
- Coverage floor stays 80%; omit list shrinks to `adapters/openai/**` only.
- Manual check: `scripts/live_probe.py` (dev extra) sends a WAV to `/live` and writes the reply WAV.

### Migration order (input for the plan)

1. Remove Agno / groq / google-genai, `AgentPort`, Team wiring, `test_model_tiers`; add domain types and ports.
2. In-memory adapters (Home, Calendar, Expenses, Store with atomic append) + tools + contract suites.
3. `Registry[Tool]`, `ToolRunner`, `PendingActionStore`, `is_affirmative`.
4. `ChatModelPort` OpenAI adapter + `ProcessChatMessage`.
5. Auth, input limits, lifespan boot validation, JSON logs, global error handling.
6. `LiveSessionPort` OpenAI Realtime adapter + `RunLiveSession` + `/live`.
7. Hygiene and docs: Dockerfile non-root + locked dependencies + TLS flags, `BYTE_PUBLISH_HOST` in compose, untrack `.idea/` and `.claude/settings.local.json`, drop the unused `db` extra, rewrite README, fix the `pip install` dev command, and **amend CLAUDE.md** (authorized by owner 2026-10-05; applied ahead of the code so the rules match the target): Voice pipeline (audio is opaque bytes relayed by `application/`; STT/TTS ports replaced by the realtime session port), Segments/Routing/Team/Agno sections, "API has no authentication" safety block, API table, Current state, new ADR superseding ADR-010. Until then CLAUDE.md is stale and must not be used to judge this implementation.

`POST /messages` keeps its request shape and adds one optional response field, so the path stays `/api/v1`.

### Findings from the project report: where each one lands

| Finding | Closed by |
|---|---|
| A1 no auth | §3 token + TLS |
| A2 foreign conversation ids | single owner + token |
| A3 unbounded input | §3 limits |
| A4 race on conversation | §1 atomic `append` |
| A5 unbounded history/store | §4 bounds |
| A6 confirmation only in prompt | §2 code-enforced, affirmative-utterance gate |
| M1 lazy build, fails at first request | §3 lifespan validation |
| M2 four sources of truth for segments | agents/tiers/roles removed |
| M3 `log_level` unused, console logs | §3 |
| M4 no timeouts | §2 |
| M5 segment frozen at creation | segment is only a per-request tool filter |
| M6 lost error cause | §4 errors |
| M7 telemetry | Agno removed; OpenAI adapter sends none |
| M8 silent downgrade | no fallback chain in Spec 1 |
| M9 env mutation | provider key passed to the adapter, not exported |
| Docker/repo/doc hygiene | migration step 7 |

### Explicitly deferred

Postgres persistence, Tuya / Google adapters, Gemini Live adapter, speaker verification, scheduler and proactive pushes (`/ws/notifications`), cross-provider fallback.

## Review log

### Round 1 — independent Opus reviewer, sections 0-3 (+4 as written)

Verdicts: §1 approve with changes, §2 rework (small), §3 approve with changes. D2, D5 and the 10-min cap endorsed.

| Severity | Finding | Resolution |
|---|---|---|
| BLOCKER | Loopback bind unreachable from ESP32; plain `ws://` leaks the token | D6 + §3 Deployment: opt-in LAN bind, TLS with pinned cert, token >= 32 chars. **Needs owner sign-off.** |
| HIGH | `action_id` flow breaks in chat (tool results not persisted); guessable/replayable id; double execution | §2 v2: one pending per conversation, argument-free `confirm_action()`, atomic pop |
| HIGH | Live "new user turn" satisfied by noise/echo/TV; injection + cough unlocks door | §2 v2: input transcription + `is_affirmative` gate, ignore commits during playback and idle-timeout commits. Promoted from "ponytail upgrade" to required |
| HIGH | Audio in `application/` contradicts CLAUDE.md; CLAUDE.md stale | D7 + migration step 7 (amend CLAUDE.md with owner approval; not edited now) |
| MEDIUM | Lifetimes of pending store / locks unspecified; live skipped the lock | §1 lifetimes + atomic `append` |
| MEDIUM | Single-session lockout after Wi-Fi drop | §3: new connection replaces old (close 4000) |
| MEDIUM | Words after wake word lost during provider connect | §3: `ready` after `session.updated`, firmware buffers |
| MEDIUM | 16 kHz mic vs 24 kHz provider: "no resampling" unworkable | §3: firmware upsamples 2:3; G.711 documented fallback |
| MEDIUM | Multi-call `response.done`; `response.create` is client-sent | §3 tool calls: sequential, `send_tool_results(list)`, one deferred `response.create` |
| MEDIUM | Barge-in needs `conversation.item.truncate`; provider sends faster than real time | §3: `played` message, paced downstream queue, `max_size` cap |
| MEDIUM | Cancellation could abort a physical action; timeout ambiguity | §2: `asyncio.shield`, "estado desconhecido" on timeout |
| MEDIUM | No history cap; live history unspecified | §3/§4: last 20 messages in chat, none in live, `retention_ratio` |
| MEDIUM | VAD default ambiguous in docs | §3: set explicitly, configurable |
| LOW | Summary by code + in API response; `parallel_tool_calls=false`; no arg/transcript logging; 404 kept; reuse `Registry[T]`; `Tool` is not a port; contract tests incl. negatives | all applied (§1-§4) |
| Unverified | Gemini price ratio; provider ack deadline (none found) | Gemini figures sourced by author; no ack rule assumed |

### Round 2 — same reviewer, spec v2

Verdict: **approve with changes** overall (§1 approve; §2, §3, §4 approve with changes). Round-1 fixes closed their holes; two needed tightening. Gemini price, `gpt-4o-mini-transcribe` price and ESP32 `wss` header support were confirmed against official docs.

| Severity | Finding | Resolution |
|---|---|---|
| HIGH | Pending action survived turns that did not confirm it ("unlock? / time? / AC? / yes" unlocks the door) | §2: armed by the next utterance only, dropped by any later one (`on_user_utterance`); turn order replaces timestamp rule |
| HIGH | `is_affirmative` under-specified (substring "assim", "pode deixar", "nem pensar", TV dialogue) | §2 matcher rules + table-driven tests (§4) |
| MEDIUM | No echo cancellation -> assistant barges in on itself | §3 firmware requirement (AEC or mute) + `far_field` noise reduction |
| MEDIUM | Live user never hears the code-generated summary | §2: summary in tool output with verbatim instruction; residual risk restated |
| MEDIUM | No injectable clock | §1: `now` injected into `PendingActionStore` and `RunLiveSession` |
| MEDIUM | Shielded tasks can be GC'd; re-request can double-execute | §2: strong-ref set, done-callback, lifespan drain, idempotency key |
| LOW | `confirm_action` with nothing pending; must survive segment filter; chat system line with pending summary; LRU semantics; no auto-reconnect on 4000; TLS SAN/DHCP/SNTP/`cert_pem`; 30 s chat timeout result | all applied (§2-§4) |
| Contradiction | §2 timestamp rule vs. turn-order requirement | resolved by turn-order rule |
| No issue | "Last 20 messages" cannot split tool call from result (tool messages are not persisted) | none needed |

### Owner decisions

- 2026-10-05: **D6 approved** (LAN exposure with TLS, token >= 32 chars, opt-in bind).
- 2026-10-05: **CLAUDE.md rewrite authorized** (migration step 7 text is applied now; see CLAUDE.md).

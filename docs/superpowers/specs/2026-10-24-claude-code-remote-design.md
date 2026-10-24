# Spec 5 — Byte drives Claude Code (prompts and permission answers)

Status: draft, written on 2026-10-24 without a brainstorm (the owner asked for the spec
directly). Every decision not taken from Spec 4 or `CLAUDE.md` is marked *(my call)*.

## Intent

Spec 4 put one `claude` process, owned by the server, in the panel's terminal. The owner still
has to sit at the panel to use it. Spec 5 lets the owner work with that session **from
anywhere Byte hears them**: by voice through the ESP32 or the laptop voice client, or by
chat.

- "Ei Byte, manda o Claude rodar os testes" → Byte types the prompt into the open session.
- Claude Code asks for permission ("rodar `pytest`?") → Byte says it out loud on the device
  and the owner answers "libera" or "nega". The panel shows the same request with buttons.
- Claude finishes a turn that Byte started → Byte says "Claude terminou no FinFlow". "O que
  ele disse?" → Byte reads back a short version of Claude's last message.

**Owner's standing constraint: spend the fewest model tokens possible.** Claude's output
reaches Byte's model only when the owner asks for it, through one tool, capped. Spoken
notices are templates rendered by Piper. They never call the model, the same rule as
reminders.

## Goals

1. `send_to_claude(text)` types a prompt into the open project's `claude` session.
2. Claude Code's permission requests reach Byte through Claude Code's **documented hooks**
   (`PermissionRequest`), not by scraping the terminal. Byte answers allow or deny for one
   request at a time.
3. Byte speaks a pending request on the notification device. The owner answers by voice,
   chat or panel buttons. Allowing goes through the existing confirmation rules.
4. `claude_status()` reports what the session is doing: idle, working, or waiting on a
   request (with the request's description). It also returns Claude's last message, capped.
5. A turn Byte started ends with a spoken "Claude terminou no <projeto>".

## Non-goals

- Opening or closing a project from anywhere but the panel. Spec 4's `panel_only` rule
  stays: the owner opens the project at the panel, then can walk away. *(my call; lifting
  it later is a one-flag change on two tools)*
- Answering "always allow" (`updatedPermissions`). Byte allows **once**. Standing rules are
  set by the owner in the terminal or in Claude Code's settings.
- Answering Claude's multiple-choice questions (`AskUserQuestion`) and MCP elicitation
  dialogs. Byte only says "Claude tem uma pergunta no <projeto>, responda no painel".
- Byte working on its own: picking tasks, chaining prompts, or deciding anything without
  the owner's words. Every prompt and every allow starts from an owner utterance or click.
- Several sessions or several projects at once.
- The POSIX PTY / home-server move: this still runs where Spec 4's terminal runs (Windows,
  uvicorn).
- Streaming Claude's output to the device, or reading whole transcripts aloud.

## Anti-goals

- **Byte approving anything by itself.** No auto-allow lists in Byte, no default allow on
  timeout, no allow decided by the model alone.
- An allow that came from the prompt instead of code. The model asks; `ToolRunner` decides.
- Answering the wrong request: an allow that was confirmed for request A must never reach
  request B.
- Scraping the TUI to find dialogs, or typing "1⏎" into a dialog to answer it.
- Byte's owner token or provider keys reaching the `claude` process (Spec 4's env filter
  stays; the new hook token is separate and scoped, below).
- Prompt text, commands, file paths or Claude's output in logs.
- Touching `~/.claude/settings.json` or the project's `.claude/` files. The hooks exist
  only in the process Byte launches.
- A prompt sent by Byte running with no permission gate (see **Launch**).

## Design

### Verify first (spike, throwaway)

The Claude Code docs leave five behaviours unclear. A throwaway spike with a logging hook
on the installed `claude` (2.1.310) settles them before anything is built:

1. `--settings <file>` hooks run **alongside** the owner's user hooks (caveman and
   ponytail SessionStart hooks must keep working).
2. `PermissionRequest` accepts a `type: "http"` handler. If it doesn't, use a `command`
   handler running a ~20-line stdlib Python script that POSTs stdin to the same URL.
3. Is the terminal dialog shown **while** the hook is still pending, or only after it
   returns? This changes the panel UX (below), not the bridge.
4. Text typed into the TUI mid-turn is queued and submitted when the turn ends.
   Bracketed paste (`ESC[200~ … ESC[201~` then `\r`) submits multi-line text as one prompt.
5. `PermissionRequest` fires for `AskUserQuestion`, or doesn't.

The spike's answers go back into this document before planning.

### Launch

`ProjectSession.open` starts `claude` with two extra flags:

- `--settings <data/claude-hooks.json>`: Byte's hooks, regenerated at every open.
- `--permission-mode default`: a session Byte can prompt must ask before acting, even if
  the owner's global settings default to `bypassPermissions` or `acceptEdits`. The owner's
  own allow rules still apply; that is their choice. *(my call)*

The child also gets `BYTE_BRIDGE_TOKEN`, added **after** Spec 4's env filter: 32 random
bytes, new at every open, valid only for the current session. Its only power is posting
hook events for that session. The owner's token never reaches the child.

### Hooks (`data/claude-hooks.json`, generated)

All hooks are `type: "http"` and POST to `BYTE_CLAUDE_HOOK_URL` (default
`http://127.0.0.1:8000/api/v1/claude/hooks`) with
`Authorization: Bearer $BYTE_BRIDGE_TOKEN` (listed in `allowedEnvVars`).

| Event | Why | Timeout |
|---|---|---|
| `PermissionRequest` | the request to answer; the HTTP response carries the decision | `approval_seconds + 10` |
| `UserPromptSubmit` | session → `working` | 5 s |
| `Stop` | session → `idle`; keep `last_assistant_message` | 5 s |
| `Notification` (`elicitation_dialog`) | "Claude tem uma pergunta" notice | 5 s |

If Byte is down or slow, the hook errors out. Claude Code treats that as non-blocking and
shows its normal dialog: the owner answers in the terminal, the same as today. Fail open to
the owner, never to "allow".

### Route `POST /api/v1/claude/hooks`

- Auth: bearer equals the current session's bridge token (`hmac.compare_digest`). The
  owner token is **not** accepted here, and the bridge token is accepted nowhere else. No
  open session → 401. This is the one route that does not take the owner token. It still
  requires a bearer, and the bridge token never leaves the machine. *(my call)*
- Body: Claude Code's hook JSON; the router dispatches on `hook_event_name`. A Pydantic
  schema keeps only the fields Byte uses: `tool_name`, `tool_input`,
  `last_assistant_message`, `notification_type`.
- `PermissionRequest` is a long request. It returns either
  `{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"allow"}}}`
  or `...{"behavior":"deny","message":"Negado pelo dono via Byte."}`, or `{}` (no
  decision → normal dialog) after `approval_seconds` (default 300).
- Other events return `{}` at once.

### Domain (`app/domain/claude.py`)

- `ClaudeRequest(id, tool_name, description, created_at)`, frozen dataclass. `id` is
  generated by Byte (Claude Code sends no request id).
- `describe_request(tool_name, tool_input) -> str`: a short pt-BR line, pure, TDD. Shapes:
  - `Bash`: `rodar: <description>`, from `tool_input.description` when present, otherwise
    the first 80 characters of the command.
  - `Edit` / `Write` / `MultiEdit`: `editar <basename>` / `criar <basename>`.
  - `WebFetch`: `abrir <host>`.
  - MCP and anything else: `usar <tool_name>`.
  - Capped at 120 characters. Built to be spoken: no newlines, no markdown.
- `ClaudeState`: `closed | idle | working | waiting`.

### `ClaudeBridge` (`app/application/claude_bridge.py`)

Singleton through `deps.py`, next to `ProjectSession`. Owns the session's coordination
state, not the process:

- The bridge token for the current session. `ProjectSession` asks for a fresh one on open
  and revokes it on close or exit (a small seam between the two; builder's choice).
- A FIFO of pending `ClaudeRequest`s, each paired with an `asyncio.Future[bool | None]`.
  The **head** is "the" request; answers always go to the head. *(my call: Claude asks one
  at a time in practice; the queue only keeps a second one from overwriting the first)*
- `state`, `last_message` (capped at 4,000 characters when stored), and
  `byte_started_turn: bool`.
- `submit(request) -> bool | None`: called by the route; enqueue, announce, await with the
  timeout, dequeue. Timeout or session close → `None`.
- `answer(request_id, allow)`: resolves that future only if `request_id` is still the head.
  Otherwise it raises `StaleClaudeRequestError(DomainError)` → "o pedido mudou".
- `prompt(text)`: no open session → `NoOpenProjectError`. Otherwise
  `ProjectSession.write(ESC[200~ + text + ESC[201~ + \r)`, and set
  `byte_started_turn = True`.
- On `Stop`: `state = idle`, store `last_message`. If `byte_started_turn`, push the "Claude
  terminou no <projeto>" notice and reset the flag.
- On close or exit: every pending future resolves `None`, the queue empties, `state =
  closed`.

### Spoken notices

The notices go through the existing `/ws/notifications` push (Piper audio + ack), with a
new `kind: "claude"`. They are **transient**: they are not written to `ReminderStorePort`.
A notice that was never delivered is dropped when its request is answered or expires. A
stale "Claude pede permissão" spoken after the fact would be wrong. *(my call; how the push
reuses `ReminderHub` / `ReminderListener` is the builder's choice)*

| When | Text |
|---|---|
| request at head, unanswered after `speak_delay_seconds` (default 10) | `Claude pede permissão no <projeto>: <description>. Libero?` |
| `Stop` after a turn Byte started | `Claude terminou no <projeto>.` |
| `elicitation_dialog`, or an `AskUserQuestion` request | `Claude tem uma pergunta no <projeto>. Responda no painel.` |

The 10 s delay lets the owner answer at the panel first. A request answered within the
delay is never spoken. *(my call)*

### Tools (segment `projects`, **not** panel-only)

| Tool | Confirmation | Returns |
|---|---|---|
| `send_to_claude(text)` | none | `enviado ao Claude no <projeto>` / `nenhum projeto aberto` |
| `claude_status()` | none (read) | `<projeto>: <estado>[; pedido: <description>][; última resposta: <≤1,500 chars>]` |
| `allow_claude()` | **`requires_confirmation`** | `liberado` / `nenhum pedido pendente` / `o pedido mudou` |
| `deny_claude()` | none | `negado` / `nenhum pedido pendente` |

- `send_to_claude` takes no confirmation: Claude Code's own permission gate (forced to
  `default` at launch) is the guard on what the prompt can do. `text` is 1–2,000
  characters. The model passes the owner's instruction; it does not write a task of its
  own. The tool description says so. *(my call)*
- `allow_claude` takes no arguments. When `ToolRunner` stores the pending action, it binds
  the head request's `id`, and the confirmation summary is the request's description
  (`Liberar o Claude: rodar testes do backend?`). On confirm, `answer(id, True)`. If the
  head changed in between → `o pedido mudou`, nothing allowed. Voice flow: "libera" →
  Byte: "Liberar o Claude: rodar testes do backend?" → "sim" → allowed. The owner hears
  exactly what they allow, even if the notice was minutes ago. *(my call: one extra word
  per allow, in exchange for reusing the confirmation matrix as is)*
- `deny_claude` runs at once: denying is never the dangerous direction.
- Prompt line: when a request is pending at prompt-build time, add one line, `Claude
  aguarda permissão no <projeto>: <description>.`, so a cold live session started by "Ei
  Byte, libera" knows what "libera" refers to. Nothing otherwise. *(my call)*

### Panel

- `/ws/terminal` `state` message gains `"claude": {"state": "...", "request":
  {"id","description"} | null}`. It is pushed on every bridge change. The panel shows a
  banner over the terminal with **Permitir** / **Negar**.
- `POST /api/v1/claude/answer` `{"id": str, "allow": bool}` → `answer(id, allow)`. 409 when
  `id` is not the head. The banner shows the description before the click, so the click is
  the decision. No second confirmation step on the panel. *(my call; this differs from
  `DELETE /agenda`'s two-step, because here the summary is on screen before the owner acts)*
- If the spike shows the terminal dialog is **not** displayed while the hook waits, the
  banner is the only way to answer at the panel, and must be visible. If it **is**
  displayed, the owner may answer either place. A terminal answer makes Claude Code drop the
  hook. Byte sees the next event (`UserPromptSubmit`/`Stop`, or the HTTP request closing),
  dequeues the request and clears the banner.
- Contract added to `docs/web-api-contract.md`.

### Configuration

`BYTE_CLAUDE_HOOK_URL`, `BYTE_CLAUDE_APPROVAL_SECONDS` (default 300, 30–1,800),
`BYTE_CLAUDE_SPEAK_DELAY_SECONDS` (default 10, 0–120). The feature is on whenever Spec 4's
terminal is on. No new extras, no new dependencies, no compose change.

### Logging

`claude.prompt_sent`, `claude.request` (`request_id`, `tool_name`, `project`),
`claude.answered` (`request_id`, `decision`, `via`: voice | chat | panel | timeout | terminal,
`waited_ms`), `claude.turn_done`. `tool_name` here is Claude Code's tool name (`Bash`,
`Edit`), not its input. Never `text`, `tool_input`, `description` or `last_assistant_message`.

## Testing

- TDD: `describe_request` (each shape, cap, missing fields), `ClaudeBridge` (FIFO head,
  answer to the head only, stale id, timeout → `None`, close resolves all, `Stop` notice
  only when Byte started the turn, speak delay cancelled by an early answer, bracketed-paste
  bytes), the four tools, `allow_claude` bound to the request id across confirmation (the
  request changes → refused), the hook route (bridge token only, owner token rejected, no
  session → 401, each event, long-poll returns the decision, `{}` on timeout),
  `/claude/answer` 409, the prompt line, settings validation. All with the injected clock
  and a fake `ProjectTerminalPort`. No sleeps.
- One `integration` + `slow` test: real `claude` in a PTY with the generated settings file,
  a harmless prompt that makes Claude ask for a `Bash` permission, answered by the bridge.
  It needs a logged-in `claude`, so it never runs by default.

## Left to the builder

- How `ClaudeBridge` and `ProjectSession` share the session lifecycle (token, exit).
- How the transient notice reuses `ReminderHub`'s listener.
- How the bound request id is carried in the pending action (`ToolRunner` already stores
  arguments; an internal field filled by the tool at request time is fine).
- Whether `settings.json` goes inline in `--settings` or in a file (file is safer with
  Windows quoting).

## Order

1. Spike (above), answers written back here.
2. Domain + `ClaudeBridge` + hook route + launch flags (testable with the fake terminal).
3. Tools, `allow_claude` binding, prompt line.
4. Spoken notices (`kind: "claude"`).
5. Panel banner, `/claude/answer`, contract doc.

# Spec 5 — Lynus: an autonomous agent that drives Claude Code

Status: approved by the owner on 2026-10-24. The first draft had Byte relay prompts and the
owner approve every permission by voice. The owner replaced it with Lynus. Their rule: **Lynus
approves anything on its own and works on its own.** Decisions not stated by the owner are
marked *(my call)*.

## Intent

The owner hands a programming task to an agent and walks away. That agent drives Claude Code
in the project until the task is done.

1. In the panel, the owner switches the chat to **Lynus**.
2. **Byte** asks which project and for a short description of the task, then hands over.
3. **Lynus** opens the project (a fresh `claude` in the panel terminal). It reads what it
   needs (`CLAUDE.md`, specs, plans) and talks with the owner in the chat to deepen the task.
4. When the task is clear, Lynus **takes over**. It writes the prompts for Claude, approves
   every permission request on its own, reads each of Claude's replies, and checks them
   against the project's specs and plans. It answers Claude's questions and steers until the
   task is done. Then it reports back.

The owner can still type in the chat (Lynus reads it at its next step) or stop Lynus at any
time. The terminal stays visible in the panel throughout.

Lynus runs on **Google's strongest coding model** that the owner's key reaches
(`gemini-3.1-pro-preview`, configurable), separate from Byte's cheap chat model.

## Goals

1. A second agent, Lynus, with its own model, prompt, tools and transcript. It is not a
   sub-agent of Byte: Byte only hands it a project and a task.
2. Claude Code's hooks report every permission request and every turn end to the server.
   While Lynus is working, every request is **allowed by code at once** (owner's rule).
3. Lynus reads Claude's last message at every turn end, can read any file in the project to
   check the work, and replies with the next prompt or with "done".
4. Panel: a Byte | Lynus switch on the chat, Lynus's conversation and progress pushed live,
   and a stop button.
5. Byte gets `start_lynus(project, task)` (panel only) and `lynus_status()`.

## Non-goals

- Byte relaying prompts or permission answers by voice (the first draft). Lynus replaces it.
- Several Lynus tasks or several projects at once. A new task replaces the current one.
- Starting Lynus anywhere but the panel. Lynus's conversation lives in the panel's chat.
  Byte can report on it by voice (`lynus_status`). *(my call)*
- Spoken notices when Lynus finishes. *(my call: the panel shows it; add one later through
  `ReminderHub` if wanted)*
- Lynus editing files itself, running commands itself, or reaching outside the project.
  Claude Code does the work; Lynus reads and steers.
- Persisting Lynus's transcript across restarts.

## Anti-goals

- Lynus stopping to ask the owner before each Claude action. That breaks the owner's rule.
- Byte's owner token or provider keys reaching the `claude` process (Spec 4's env filter
  stays). The new bridge token can only post hook events for the current session.
- Lynus reading files outside the project folder (absolute paths and `..` are refused).
- Prompts, file contents, Claude's output or Lynus's messages in logs.
- Scraping the TUI to find dialogs, or typing into a dialog to answer it.
- Touching `~/.claude/settings.json` or the project's `.claude/`. Hooks are injected only
  into the process Byte launches.

## Safety, as the owner set it

By the owner's rule, Lynus approves anything Claude Code asks: shell commands, edits,
network access, as the owner's Windows user, in that project's folder and wherever a command
reaches. What bounds it:

- It only runs after the owner explicitly starts it in the panel, for one named project.
- Stop button and `POST /lynus/stop`. Stopping drops autopilot at once and interrupts
  Claude's turn (`Esc`).
- A turn budget (`BYTE_LYNUS_MAX_TURNS`, default 40 prompts) and a per-turn timeout
  (`BYTE_LYNUS_TURN_MINUTES`, default 30). Hitting either stops Lynus and says so.
- Approvals are logged (`claude.allowed`, Claude Code's tool name only).
- Byte's secrets are not in the child's environment.

## Spike results (2026-10-24, `claude` 2.1.310, ConPTY)

1. Hooks passed with `--settings <file>` run **alongside** the owner's user hooks (Orca,
   caveman, ponytail).
2. `type: "http"` hooks work for `PermissionRequest` and `Stop`. The
   `$BYTE_BRIDGE_TOKEN` header, interpolated from the child's environment, arrived on every
   call. Holding a `PermissionRequest` response and then answering `allow` ran the command.
   `Stop` carries `last_assistant_message`.
3. The terminal dialog is shown **while** the hook is pending. A terminal answer wins at
   once, and the late hook reply is ignored.
4. A prompt typed mid-turn is accepted immediately. A bracketed paste
   (`ESC[200~ … ESC[201~`, then `\r` a moment later) becomes **one** prompt, newlines kept.
5. `PermissionRequest` fires for `AskUserQuestion` too. Replying `{}` leaves the question
   in the terminal.
6. The owner's global `defaultMode` is `"auto"`. Lynus's sessions start with
   `--permission-mode default`, so every request goes through the hook. Otherwise the auto
   classifier could block an action that Lynus is supposed to approve.

## Design

### Claude bridge (`app/application/claude_bridge.py`)

A singleton (`deps.py`). It knows the current `claude` session's hook token and turns hook
events into something Lynus can wait on.

- `begin() -> str`: a fresh token (`secrets.token_urlsafe(32)`). `end()` revokes it and
  wakes anyone waiting on a turn (the session is gone).
- `authorized(token) -> bool`: `hmac.compare_digest` against the current token.
- `pilot: Callable[[str], Awaitable[str]] | None`. Set while Lynus works; it is Lynus's
  answer to an `AskUserQuestion`.
- `hook(event) -> dict`:
  - `PermissionRequest` with no pilot → `{}`. The owner answers in the terminal, as in
    Spec 4.
  - `PermissionRequest` with a pilot, any tool but `AskUserQuestion` → `allow`. Logged as
    `claude.allowed`.
  - `PermissionRequest` with a pilot, `AskUserQuestion` → `deny` with the message
    `Resposta do dono (via Lynus): <answer>`, where the answer comes from `pilot(question
    JSON)`. *(my call: it answers through the denial message, because the `updatedInput`
    shape for answers is undocumented; Claude reads the message and goes on)*
  - `Stop` → `last_assistant_message` goes into a queue that `next_turn()` reads.
  - Anything else → `{}`.
- `next_turn(timeout) -> str | None`: the next turn's final message. `None` on timeout or
  when the session ended. `clear()` drops stale turn ends before a new prompt.
- `settings() -> dict`: the hooks JSON for `--settings`. `PermissionRequest` (matcher `*`,
  timeout 120 s, long enough for a pilot answer) and `Stop` (5 s). Both are `type: "http"`
  to `BYTE_CLAUDE_HOOK_URL`, with `Authorization: Bearer $BYTE_BRIDGE_TOKEN` in
  `allowedEnvVars`. The file is written to `data/claude-hooks.json` at boot.

### Project session changes (Spec 4)

`ProjectSession` takes an optional bridge.

- `open(name, extra_args=())`: argv = command + `--settings <hooks file>` + `extra_args`.
  The env gets `BYTE_BRIDGE_TOKEN = bridge.begin()`, added **after** the secret filter.
- Stop or exit → `bridge.end()`.
- `open_project` (the owner at the panel) passes nothing extra, so the owner's own
  permission mode applies. Lynus passes `--permission-mode default`.

### Route `POST /api/v1/claude/hooks`

The bearer must be the bridge token, never the owner token. The owner token is refused here
and the bridge token is refused everywhere else. Body: Claude Code's hook JSON. Response:
whatever `bridge.hook` returns. Not under the owner's auth because the `claude` process must
never hold the owner token. It is still bearer-protected, loopback, and scoped to one session.

### Lynus (`app/application/lynus.py`)

A singleton. Owns the phase, the transcript sent to the model, the notes the panel shows, and
the worker task.

Phases (`app/domain/lynus.py`): `off → briefing → working → done | stopped | failed`.

- **Folder trust (found in the end-to-end run):** a folder Claude Code has not trusted opens
  on its trust dialog, whose default answer is "No, exit". Lynus's first `Enter` picked it and
  `claude` quit. Before opening, `start` reads `~/.claude.json` (read only) and refuses an
  untrusted folder with an instruction: open it in the panel and pick "Yes, I trust this
  folder". If the file cannot be read or is in another format, it goes ahead. Lynus never
  types into dialogs.
- `start(project, task)`: stops any current task, opens the project (fresh `claude` with
  `--permission-mode default`), sets `briefing`, and schedules Lynus's first message. That
  is one model call with the project's `CLAUDE.md` excerpt (capped at 6,000 chars), the
  owner's task, and the tools `read_file` and `begin_work`. Lynus asks the owner what is
  still unclear, briefly.
- `say(text)`: an owner message.
  - In `briefing`: one model turn (`read_file`, `begin_work`). A text reply becomes a note
    for the owner.
  - In `working`: it goes into the transcript as `Mensagem do dono: …`. Lynus answers at
    once and may call `send_to_claude` (a prompt mid-turn is accepted, spike 4).
  - In any other phase it is refused (409).
- `begin_work(brief)` (a model tool): `working`, `bridge.pilot = answer_question`, and the
  worker starts.
- Worker loop:
  1. `bridge.clear()`, type the prompt (bracketed paste, then `\r` after
     `BYTE_LYNUS_PASTE_DELAY` = 0.3 s), turns += 1.
  2. `last = await bridge.next_turn(turn_timeout)`. `None` → `failed` ("o Claude não
     terminou o turno" or "sessão do Claude encerrada").
  3. Model turn with `Claude terminou o turno. Última mensagem: <last, capped 8,000>` and
     the tools `read_file`, `send_to_claude`, `finish`. `send_to_claude(text)` → back to 1.
     `finish(summary)` → `done`. Neither → one nudge, then `failed`.
  4. turns > max → `stopped` ("limite de turnos").
- `stop()`: cancel the worker, clear the pilot, `stopped`, write `ESC` to the terminal.
- Model calls are serialized (one lock). Text the model writes in any phase becomes a note.
- Transcript compaction *(my call)*: the system prompt and the brief always stay. When the
  transcript passes 40 messages, it is cut back to the last 30, starting at a plain user
  message so call/response pairs stay intact.
- Tools (Lynus's own, no `ToolRunner`: nothing in Lynus's world asks for confirmation, by
  rule):
  - `read_file(path)`: relative to the project folder, `..`/absolute refused, ≤ 20,000
    chars, `DocumentSourcePort.read`.
  - `begin_work(brief)` (briefing only), `send_to_claude(text)` and `finish(summary)`
    (working only).
- Gemini's Google Search stays on (it comes with the adapter), so Lynus can look things up.
- The prompt is in pt-BR: Lynus is a senior engineer and Claude's tech lead. It checks
  claims against files (specs in `docs/superpowers/specs`, plans in
  `docs/superpowers/plans`) and asks Claude for evidence (tests run, output). It never
  accepts "done" without tests, and it approves the designs and plans Claude presents when
  they match the task.
- Panel listener: `attach/detach` like `WeatherDisplay`. Every note or phase change calls
  `changed()`.

### Byte's tools (segment `projects`)

- `start_lynus(project, task)`, `panel_only`. Its description tells Byte to ask for the
  project and a short task description first, if the owner has not given them. It returns
  `Lynus assumiu <projeto>; a conversa continua com ele no chat.`
- `lynus_status()`: `<fase> em <projeto>: <última nota do Lynus, ≤ 400 chars>`.

### API

- `GET /api/v1/lynus` → `{phase, project, task, notes: [{role: "owner"|"lynus"|"claude"|"system", text, at}]}`.
  `claude` notes are the prompts Lynus sent. Last 200 notes.
- `POST /api/v1/lynus/messages {content}` (1–4,000 chars) → 202. 409 outside
  briefing/working.
- `POST /api/v1/lynus/stop` → `{phase}`.
- `WS /ws/panel` also pushes `{"type":"lynus"}`. The panel reads the truth from
  `GET /lynus`, the same pattern as the weather.
- All under the owner token. Lynus is absent (503) when there is no project terminal or no
  Gemini key.

### Panel

- A `Byte | Lynus` switch over the chat.
  - **Lynus**, when Lynus is off: the panel sends Byte `Quero passar uma tarefa para o
    Lynus.` Byte asks for the project and the task, then calls `start_lynus`. The push
    arrives and the chat becomes Lynus's.
  - **Lynus**, when Lynus is active: shows Lynus's conversation; the input posts to
    `/lynus/messages`.
  - **Byte**: back to Byte's conversation. Lynus keeps working.
- Lynus's view: the phase chip (`conversando`, `trabalhando · turno n`, `concluído`,
  `parado`, `falhou`), notes (owner / Lynus / prompts sent to Claude, the last in mono), and
  `Parar` while active.
- Contract in `docs/web-api-contract.md`.

### Configuration

`BYTE_LYNUS_MODEL` (`gemini-3.1-pro-preview`), `BYTE_LYNUS_THINKING` (`low|medium|high`,
default `medium`), `BYTE_LYNUS_MAX_TURNS` (40), `BYTE_LYNUS_TURN_MINUTES` (30),
`BYTE_CLAUDE_HOOK_URL` (`http://127.0.0.1:8000/api/v1/claude/hooks`). Lynus needs
`BYTE_GEMINI_API_KEY`, whatever Byte's provider is. Without it, Lynus is off and logged.

### Logging

`lynus.started` (project), `lynus.phase` (phase, turns), `lynus.prompt_sent` (turn),
`claude.allowed` (tool_name), `claude.turn_done`. Never prompt text, notes, file contents or
Claude's messages.

## Testing

- TDD: `is_inside` path check; `ClaudeBridge` (token rotate/refuse, no pilot → `{}`, pilot
  → allow, `AskUserQuestion` → deny with the pilot's answer, `Stop` → `next_turn`,
  timeout and `end()` → `None`, `clear()`); `ProjectSession` passes `--settings`, extra
  args and token env, and ends the bridge on stop and exit; Lynus with `ScriptedChatModel`
  and `FakeTerminal` (start → briefing note; `begin_work` → working + pilot + bracketed
  prompt; turn end → `send_to_claude` → second prompt; `finish` → done; no tool twice →
  failed; budget → stopped; timeout → failed; `stop()` → `Esc` + pilot cleared; owner
  message while working; `read_file` refuses `..`; compaction keeps pairs); the hook route
  (bridge token only, owner token refused); the Lynus routes (409, 202, stop); Byte's two
  tools.
- Manual check: the panel switch, a real task end to end on a scratch project.

## Order

1. Domain + bridge + session changes + hook route.
2. Lynus + its tools + Byte's tools + routes + deps/lifespan.
3. Panel.

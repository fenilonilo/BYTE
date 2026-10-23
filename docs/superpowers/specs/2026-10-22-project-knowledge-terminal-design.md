# Spec 4 — Project knowledge (vector store + RAG) and project terminal

Status: draft, brainstormed with the owner on 2026-10-22. Calls made without the owner are
marked *(my call)*.

## Intent

Byte knows the owner's personal programming projects and opens them for coding.

- The owner asks "o que o Sistema_Perfil usa de banco?" by chat or voice; Byte answers from
  the projects' `CLAUDE.md` files, retrieved from a vector store (RAG).
- In the **web panel only** — typed in its chat or spoken through its voice mode — the owner
  says "abre o FinFlow"; the panel's terminal pane becomes
  a real terminal running `claude` (Claude Code) in that project's folder. "Fecha o projeto"
  ends it and the pane goes back to Byte's activity log.

Why a vector store for five files: the owner will add more and more important documents
later. The store and the indexer are built to grow; today they index five files.

Why the index lives in the database: Byte will later move to a home server that has no access
to `D:\Projetos`. It must keep answering questions from the last indexed version there.

**Owner's standing constraint: spend the fewest model tokens possible.** Project content
reaches the model only through a tool the model calls when the question is about a project.

## Goals

1. A vector store (Postgres 16 + pgvector) holding chunks of registered documents with
   embeddings from a **local** model (owner's decision: no embedding API).
2. Self-feeding index: a background loop re-indexes a document when it changes on disk,
   adds new ones, removes deleted ones. Nothing is removed when the folders are unreachable.
3. `search_projects` tool: RAG over the index, available in chat and voice.
4. The model always knows the project names (one prompt line), nothing more.
5. `open_project` / `close_project` tools, web panel only: a real PTY running `claude` in the
   project folder, streamed to the panel. One project at a time; opening another closes the
   current one (owner's decision).

## Registered projects

Five, chosen by the owner. The folder is the one that holds `CLAUDE.md`; `claude` starts there.

| Name | Folder |
|---|---|
| `API_Financeira` | `D:\Projetos\API_Financeira` |
| `App_Easy_Finance` | `D:\Projetos\App_Easy_Finance\easy_finance` |
| `Byte` | `D:\Projetos\Byte\BYTE` (`Byte\killifish` excluded) |
| `FinFlow` | `D:\Projetos\FinFlow` |
| `Sistema_Perfil` | `D:\Projetos\Sistema_Perfil` |

## Non-goals

- **Byte driving Claude Code on its own** (sending prompts, approving permission requests while
  the owner is away). That is Spec 5, brainstormed separately. This spec only has to leave the
  `claude` process owned by the server so Spec 5 can attach to it.
- Opening a project from the ESP32 or any client other than the web panel.
- A free shell in the browser. Only `claude`, only in a registered folder.
- Several projects open at once, tabs in the terminal.
- Indexing source code, PDFs or anything but Markdown files listed in the config.
- Moving the conversation store to Postgres (stays in memory; later spec).
- Making Claude Code start in caveman/ponytail mode: the owner's global SessionStart hooks
  already do it for every `claude` session. Nothing to build.

## Anti-goals

- The model naming a path, a folder or a command. It names a registered project, nothing else.
- Byte's secrets reaching the `claude` process (its environment is filtered, below).
- Losing the index because the server cannot see the files.
- Project text in logs, or the whole of every `CLAUDE.md` pushed into every prompt.
- Closing the browser tab killing the `claude` session.

## Design

### Configuration (`app/config.py`)

- `BYTE_PROJECTS`: JSON map `name → {"path": str, "docs": [str]}`. `docs` are paths relative
  to `path`, default `["CLAUDE.md"]`. Adding a document to the knowledge base = adding a path
  here *(my call: explicit list, no globbing, so the blast radius stays known)*. Names match
  `^[A-Za-z0-9_-]{1,64}$`. Empty map = feature off (no tools registered, no loop).
- `BYTE_DATABASE_URL` (`postgresql+asyncpg://…`). Unset → in-memory knowledge store (rebuilt
  from disk at boot), same "real when configured, in-memory otherwise" rule as the devices.
- `BYTE_EMBEDDING_MODEL` (default below), `BYTE_KNOWLEDGE_SCAN_SECONDS` (default 300),
  `BYTE_CLAUDE_COMMAND` (default `claude`; resolved with `shutil.which` at boot when projects
  are configured, warn — not fail — if missing).
- `open_project`/`close_project` and `/ws/terminal` exist only when projects are configured,
  the `pty` extra imports and `claude` resolves; otherwise they are not registered and the model
  never sees them. `search_projects` needs only the store and the embedder, so it works on the
  home server without the files *(my call)*. The Docker image carries neither `pywinpty` nor
  `claude`: the terminal is a Windows/uvicorn feature until the POSIX adapter and Spec 5.

### Domain (`app/domain/knowledge.py`)

- `DocumentRef(project, rel_path)`, `Chunk(ref, ordinal, heading, text)`,
  `SearchHit(chunk, score)`.
- `split_markdown(text, max_chars) -> tuple[Chunk-like, ...]`: split on Markdown headings,
  keep the heading path ("Safety and security › Network") with each chunk, split long sections
  on paragraph boundaries under `max_chars` (≈1,200) *(my call)*. Pure, TDD.
- `content_hash(text)` — sha256, used to skip unchanged documents.

### Ports

- `EmbedderPort.embed(texts: Sequence[str]) -> tuple[tuple[float, ...], ...]` and
  `dimensions`. Async (CPU work runs off the event loop in the adapter).
- `KnowledgeStorePort`: `document_hash(ref) -> str | None`, `replace_document(ref, hash,
  chunks, vectors)` (atomic: old chunks out, new in, one transaction), `remove_document(ref)`,
  `documents() -> refs`, `search(vector, k, project: str | None) -> tuple[SearchHit, ...]`.
- `DocumentSourcePort.read(path) -> str | None` and `reachable(root) -> bool`. Local
  filesystem adapter today; the home server later gets the same adapter once files are there.
- `ProjectTerminalPort` (one PTY process): `start(cwd, argv, env, cols, rows)`,
  `write(bytes)`, `resize(cols, rows)`, `read() -> bytes` (async, empty on exit), `stop()`
  (kills the whole process tree), `alive`. Two implementations in sight: Windows ConPTY via
  `pywinpty` now, POSIX `pty` on the Linux server later.

### Adapters

- `adapters/postgres/`: SQLAlchemy asyncio + asyncpg + `pgvector`. Tables `documents(project,
  rel_path, hash, model, indexed_at, PK(project, rel_path))` and `chunks(project, rel_path,
  ordinal, heading, text, embedding vector)` — untyped `vector`, no index *(my call: a few
  hundred rows need none, and a model with another dimension needs no migration)*. Cosine distance. Alembic migration creates `CREATE EXTENSION vector`. Vendor
  errors → `KnowledgeError(DomainError)`.
- `adapters/memory/in_memory_knowledge.py`: same port, brute-force cosine. Unit tests and the
  no-database mode.
- `adapters/fastembed/`: `fastembed` (ONNX on CPU). Default model
  `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384 dims, multilingual,
  ~220 MB, downloaded once into a cache folder under `data/`) *(my call; any multilingual model
  ≤ ~500 MB that fastembed supports is acceptable)*. Each document row stores the model name; a
  document embedded by another model counts as changed and is re-embedded on the next scan, and
  `search` only compares vectors of the current model.
- A deterministic fake embedder under `tests/fakes/` (hash → vector) for unit tests.
- `adapters/pty/`: `WinPtyTerminal` (pywinpty). POSIX version not written now.
- Port contract suites for `KnowledgeStorePort` (memory + Postgres via testcontainers,
  integration marker) and `DocumentSourcePort`.

### Indexer (`app/application/knowledge_indexer.py`)

A loop in the lifespan, like `ReminderHub`: at boot and every `scan_seconds`, for each project
and each listed doc:

- project folder unreachable → skip the project, keep its index untouched;
- file readable, hash unchanged → nothing (zero embedding work);
- file readable, hash changed or new → split, embed, `replace_document`;
- folder reachable but file missing → `remove_document`.
- Documents in the store that are no longer in the config → removed.

Logs ids, counts and durations only. A failure on one document is logged and retried next
scan; it never stops the loop.

### Tools (segment `projects`)

- `search_projects(query, project?)` — embeds the query, top 4 hits (optionally one project),
  returns `[Projeto › heading] text` blocks capped at 2,000 characters total, `ToolRunner`'s output limit *(my call)*.
  Unknown project → error string listing the valid names. Read-only, no confirmation.
- `open_project(project)` — panel only (below). Closes the current session if any, starts a
  **new** `claude` session (plain `claude`, no `--continue`; owner's decision) in the project
  folder, returns `aberto: <name>`. No confirmation: the owner is in front of the panel and
  asked for it *(my call)*.
- `close_project()` — stops the session, returns `fechado` or `nenhum projeto aberto`.

The system prompt gets one line: `Projetos: API_Financeira, App_Easy_Finance, Byte, FinFlow,
Sistema_Perfil.` (from config).

**Panel only, chat and voice, enforced in code:** the panel identifies itself — `POST
/messages` gains an optional `client` field and the `/live` start message an optional
`"client"` key; the panel sends `"panel"`, everything else (ESP32, scripts) omits it
(default `"api"`). `ToolSpec` gains `panel_only: bool = False`; `open_project` and
`close_project` set it. A request or live session not marked `panel` is neither offered these
tools nor allowed to run them — `ToolRunner` refuses, not just the prompt. This is a routing
rule, not a security boundary: every client holds the same owner token *(my call)*. The
`client` field is additive, so `/api/v1` stays compatible.

### Project session (`app/application/project_session.py`)

Singleton through `deps.py`. Owns the one `ProjectTerminalPort`, the current project name, a
scrollback ring buffer (~256 KB of raw output) and the set of attached sockets.

- `open(name)`: stop the current process, start `claude` with `cwd = project.path`.
- **Environment:** the child gets the server's environment minus every `BYTE_*` variable and
  the provider keys (`OPENAI_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`). Byte's token must
  never be readable by the process it spawned.
- Output is read continuously into the scrollback and fanned out to attached sockets; nobody
  attached → still read (the process must not block on a full pipe).
- Process exits by itself (owner typed `/exit`) → session becomes closed, sockets notified.
- Server shutdown → process tree stopped.
- Never logs terminal input or output.

### WebSocket `WS /api/v1/ws/terminal`

Bearer auth like the other sockets (header or `["bearer", token]` subprotocol). One panel at a
time; a new connection replaces the old (close 4000), same rule as `/live`.

- Server → panel text: `{"type":"state","project":"FinFlow"|null}` on connect and on every
  open/close/exit. Binary frames: terminal output. On connect with an open project, the
  scrollback is replayed first.
- Panel → server: binary frames = keystrokes; text `{"type":"resize","cols":n,"rows":n}`.
  Input with no open project is dropped.

The panel stays connected to this socket while it is open, so it switches views when the
`state` message arrives — the chat response shape does not change.

### Web panel

- xterm.js (+ fit addon) vendored under `web/vendor/` at a pinned version *(my call: no CDN,
  the panel works offline on the LAN)*.
- The panel sends `client: "panel"` on chat and on the live start message.
- The terminal pane shows the activity log (today's terminal) when no project is open and the
  xterm view when one is, with the project name in the pane header. Existing log commands keep
  working in log view.
- Contract added to `docs/web-api-contract.md`.

### Compose and dependencies

- `docker-compose.yml` gains `db` (`pgvector/pgvector:pg16`, `127.0.0.1:5432`, named volume,
  password from `.env`). Byte's own container gets `BYTE_DATABASE_URL` pointing at `db`.
  Today the owner runs Byte with `uvicorn` on Windows and only `db` in Docker.
- Extras: `db` (sqlalchemy[asyncio], asyncpg, pgvector, alembic), `embed` (fastembed),
  `pty` (pywinpty, Windows marker). Locked like the others.
- `.env.example` gets the new names, empty.

### Security notes

- The PTY socket is code execution on the owner's machine as the owner. It inherits every
  existing guard: bearer token, loopback by default, TLS required for LAN. No new exposure.
- The model can only pick one of five names; the command and folder come from config.
- Claude Code's own permission prompts are untouched; the owner answers them in the terminal.

## Testing

- TDD: `split_markdown`, `content_hash`, the indexer matrix (unreachable / unchanged /
  changed / new / missing / dropped from config / one document failing), `search_projects`
  formatting and cap, `open_project`/`close_project`, `ProjectSession` (replace on open,
  env filtering, exit → state, scrollback replay, fan-out) with a fake `ProjectTerminalPort`,
  `ToolRunner` refusing `panel_only` tools for non-panel chat and live callers, `/ws/terminal` auth and replacement, settings
  validation for `BYTE_PROJECTS`.
- Contract suites as above; Postgres and the real embedder and PTY are `integration` + `slow`.

## Left to the builder

- Exact chunk size, overlap (none is fine), top-k.
- Whether `KnowledgeIndexer` and `ReminderHub` share a loop helper.
- Scrollback size, PTY default size, xterm theme matching the panel.
- How the `client` marker is threaded into `ProcessChatMessage`, `RunLiveSession` and
  `ToolRunner`.

## Order

1. Domain + ports + in-memory adapters + fake embedder + indexer + `search_projects` + prompt
   line (fully testable, no Postgres).
2. Postgres adapter, Alembic, compose `db`, fastembed adapter.
3. `ProjectSession`, PTY adapter, `/ws/terminal`, `open_project`/`close_project`, `client`
   marker and `panel_only`.
4. Panel: xterm view, state switching.

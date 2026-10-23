# Project Knowledge + Project Terminal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Byte answers questions about five registered projects from a local-embedding vector
store, and opens/closes a real `claude` terminal for one project at a time in the web panel.

**Architecture:** New domain (`projects`, `knowledge`), four ports (`EmbedderPort`,
`KnowledgeStorePort`, `DocumentSourcePort`, `ProjectTerminalPort`), a `KnowledgeIndexer` loop and
a `ProjectSession` singleton in `application/`, three tools in segment `projects`, a `panel`
client marker threaded through chat/live/`ToolRunner`, `WS /api/v1/ws/terminal`, and an xterm.js
view in the panel.

**Tech Stack:** Python 3.14 venv (project floor 3.12), FastAPI, SQLAlchemy asyncio + asyncpg +
pgvector + Alembic, fastembed (ONNX CPU), pywinpty (ConPTY), xterm.js vendored.

**Spec:** `docs/superpowers/specs/2026-10-22-project-knowledge-terminal-design.md`

## Global Constraints

- Hexagonal rules from `CLAUDE.md`: domain stdlib-only frozen slotted dataclasses; ports are
  `ABC` + `@abstractmethod`; vendor types (SQLAlchemy, asyncpg, fastembed, winpty) only inside
  their adapter package; vendor errors wrapped in a `DomainError` subclass keeping `__cause__`.
- `pyright --strict`, `ruff check`, `pytest` (coverage ≥ 80 %) green after every task.
- Never log document text, queries, chunk text, terminal input or output. Ids, counts, durations.
- Project names match `^[A-Za-z0-9_-]{1,64}$`. The model names a project, never a path.
- Tool output ≤ 2,000 chars (`ToolRunner` cuts there); `search_projects` caps itself at 2,000.
- Defaults: scan every 300 s; embedding model
  `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`; chunk `max_chars` 1,200;
  top-k 4; scrollback 262,144 bytes; PTY 120×30.
- Child env drops every `BYTE_*` key and `OPENAI_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`.
- `open_project` starts plain `claude` (no `--continue`); no confirmation on open/close.
- Commits: Conventional Commits, ending with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. A `CLAUDE.md` with no headings, or text before the first heading → still indexed (one or
   more chunks, heading `""`). Test in Task 1.
2. Folder reachable, file temporarily unreadable/locked (editor saving) → `read` returns `None`
   only when the file is missing; an `OSError` other than "not found" leaves the index alone
   and logs. Test in Task 3.
3. `claude` exits on its own (`/exit`, crash) while no panel is attached → session becomes
   closed, next attach gets `{"type":"state","project":null}`. Test in Task 7.
4. Owner opens the same project that is already open → a fresh session replaces it (spec:
   always new). Test in Task 7.
5. Keystrokes or resize arriving with no open project, or resize with absurd sizes
   (0, 10,000) → dropped / clamped to 2..500, never an exception that kills the socket.
   Test in Task 9.

---

### Task 1: Domain — projects, chunks, config

**Files:**
- Create: `app/domain/projects.py`, `app/domain/knowledge.py`
- Modify: `app/domain/exceptions.py`, `app/config.py`
- Test: `tests/unit/domain/test_knowledge.py`, `tests/unit/test_config_projects.py`

**Interfaces:**
- Produces:
  - `Project(name: str, path: str, docs: tuple[str, ...])` (frozen, slots).
  - `DocumentRef(project: str, rel_path: str)`; `Chunk(ref: DocumentRef, ordinal: int,
    heading: str, text: str)`; `SearchHit(chunk: Chunk, score: float)`.
  - `split_markdown(ref: DocumentRef, text: str, max_chars: int = 1200) -> tuple[Chunk, ...]`
  - `content_hash(text: str) -> str` (sha256 hex).
  - Exceptions: `KnowledgeError(DomainError)`, `ProjectError(DomainError)`,
    `UnknownProjectError(ProjectError)`; `failure_reason` maps `UnknownProjectError` to
    `"validation"`.
  - Settings: `ProjectSettings(path: str, docs: list[str] = ["CLAUDE.md"])`;
    `Settings.projects: dict[str, ProjectSettings] = {}` (env `BYTE_PROJECTS`, JSON),
    `database_url: SecretStr | None = None`, `embedding_model: str` (default above),
    `embedding_cache: str = "data/models"`, `knowledge_scan_seconds: float = 300`,
    `claude_command: str = "claude"`. Validator: every project name matches the pattern;
    every `docs` entry is relative and has no `..` part.
  - `Settings.project_list() -> tuple[Project, ...]` sorted by name.

- [ ] **Step 1: Write the failing tests**

```python
def test_split_keeps_heading_path():
    text = "# Byte\nintro\n## Safety\n### Network\nloopback only\n"
    chunks = split_markdown(REF, text)
    assert [c.heading for c in chunks] == ["Byte", "Byte › Safety › Network"]
    assert chunks[-1].text.strip() == "loopback only"
    assert [c.ordinal for c in chunks] == [0, 1]

def test_split_text_without_headings_is_one_chunk():
    assert [(c.heading, c.text) for c in split_markdown(REF, "só texto")] == [("", "só texto")]

def test_split_long_section_on_paragraphs_under_limit():
    text = "# A\n" + "\n\n".join(["x" * 500] * 5)
    chunks = split_markdown(REF, text, max_chars=1200)
    assert len(chunks) == 3 and all(len(c.text) <= 1200 for c in chunks)

def test_split_skips_empty_sections():
    assert [c.heading for c in split_markdown(REF, "# A\n\n# B\ntexto")] == ["B"]

def test_content_hash_is_stable_sha256():
    assert content_hash("a") == hashlib.sha256(b"a").hexdigest()

def test_projects_parse_from_json_env(monkeypatch):  # BYTE_PROJECTS='{"FinFlow":{"path":"D:/P/FinFlow"}}'
    assert settings.project_list() == (Project("FinFlow", "D:/P/FinFlow", ("CLAUDE.md",)),)

@pytest.mark.parametrize("bad", ['{"a b":{"path":"x"}}', '{"A":{"path":"x","docs":["../e.md"]}}',
                                 '{"A":{"path":"x","docs":["C:/abs.md"]}}'])
def test_bad_projects_refuse_boot(bad, monkeypatch): ...  # load_settings raises ConfigError
```

A paragraph longer than `max_chars` on its own is hard-cut at `max_chars`.

- [ ] **Step 2: Run, verify FAIL** — `pytest tests/unit/domain/test_knowledge.py tests/unit/test_config_projects.py -v` → ImportError.
- [ ] **Step 3: Implement** the types, `split_markdown`, `content_hash`, exceptions, settings.
- [ ] **Step 4: Run, verify PASS**, then `ruff check . && pyright`.
- [ ] **Step 5: Commit** `feat(knowledge): project and chunk domain, project settings`

---

### Task 2: Knowledge ports, in-memory store, local source, fake embedder, contracts

**Files:**
- Create: `app/ports/embedder.py`, `app/ports/knowledge.py`, `app/ports/documents.py`,
  `app/adapters/memory/in_memory_knowledge.py`, `app/adapters/files/local_documents.py`,
  `tests/fakes/embedder.py`, `tests/contracts/knowledge_store_contract.py`,
  `tests/contracts/document_source_contract.py`
- Test: `tests/unit/adapters/test_in_memory_knowledge.py`, `tests/unit/adapters/test_local_documents.py`

**Interfaces:**
- Consumes: Task 1 types.
- Produces:
  - `EmbedderPort`: `model: str` (abstract property);
    `async embed(texts: Sequence[str]) -> tuple[tuple[float, ...], ...]`.
  - `KnowledgeStorePort`:
    - `async digest(ref: DocumentRef, model: str) -> str | None` — stored hash only if that
      document was embedded with `model`, else `None`.
    - `async replace_document(ref, digest: str, model: str, chunks: Sequence[Chunk],
      vectors: Sequence[Sequence[float]]) -> None` — atomic.
    - `async remove_document(ref) -> None` (unknown ref: no-op).
    - `async documents() -> tuple[DocumentRef, ...]`.
    - `async search(vector: Sequence[float], model: str, k: int, project: str | None)
      -> tuple[SearchHit, ...]` — cosine similarity, best first, only `model`'s vectors.
  - `DocumentSourcePort`: `async reachable(root: str) -> bool`;
    `async read(path: str) -> str | None` (`None` = file does not exist; other `OSError` →
    `KnowledgeError`). UTF-8, BOM stripped.
  - `FakeEmbedder(model="fake", dims=16)`: deterministic vector from sha256 of the text,
    normalised; same text → same vector. Counts calls in `calls: int`.
  - `InMemoryKnowledge()`; `LocalDocuments()` (`asyncio.to_thread` + `pathlib`).

- [ ] **Step 1: Write the contract suites** (ABC with `make()`, pattern of
  `tests/contracts/reminder_store_contract.py`):
  `test_replace_then_digest`, `test_digest_none_for_other_model`,
  `test_replace_swaps_old_chunks` (2 chunks then 1 → search finds only the new one),
  `test_remove_document`, `test_remove_unknown_is_noop`, `test_documents_lists_refs`,
  `test_search_orders_by_similarity`, `test_search_filters_project`,
  `test_search_ignores_other_model`, `test_search_empty_store`.
  Source contract: `test_read_existing_utf8_with_bom`, `test_read_missing_is_none`,
  `test_reachable_true_for_dir_false_for_missing`.
- [ ] **Step 2: Wire both suites** to the in-memory store and `LocalDocuments` (`tmp_path`);
  run → FAIL.
- [ ] **Step 3: Implement** ports, adapters, fake.
- [ ] **Step 4: Run PASS**, ruff, pyright.
- [ ] **Step 5: Commit** `feat(knowledge): ports, in-memory store and local document source`

---

### Task 3: KnowledgeIndexer

**Files:**
- Create: `app/application/knowledge_indexer.py`
- Test: `tests/unit/application/test_knowledge_indexer.py`

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces:
  - `KnowledgeIndexer(projects: Sequence[Project], source: DocumentSourcePort,
    embedder: EmbedderPort, store: KnowledgeStorePort, log: LoggerPort)` with
    `async scan() -> None`.
  - `async run_indexer(indexer: KnowledgeIndexer, every: float, log: LoggerPort, *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None` — scan at once, then
    every `every` s; an exception from `scan` is logged (`knowledge.scan_failed`, error type)
    and the loop goes on.

Doc path = `Path(project.path) / rel_path` as a string. Per-document failures are logged
(`knowledge.doc_failed`, project, rel_path, error type) and do not stop the scan.

- [ ] **Step 1: Failing tests** (fake embedder, in-memory store, a dict-backed fake source):
  - `test_new_doc_is_indexed` → `store.documents() == (REF,)`, search finds it.
  - `test_unchanged_doc_is_not_reembedded` → second `scan()` leaves `embedder.calls` equal.
  - `test_changed_doc_is_reindexed`.
  - `test_unreachable_project_keeps_index` → remove root from fake; `documents()` unchanged.
  - `test_missing_file_in_reachable_project_is_removed`.
  - `test_doc_dropped_from_config_is_removed` (store holds a ref no project lists).
  - `test_model_change_reembeds` (new `FakeEmbedder(model="other")`).
  - `test_one_failing_doc_does_not_stop_others` (source raises `KnowledgeError` for one).
  - `test_read_error_keeps_index` (Review Focus 2: `KnowledgeError` on a reachable project's
    already indexed doc → still in `documents()`).
  - `test_run_indexer_survives_scan_error` (scan raises once, fake sleep stops after 2 loops).
- [ ] **Step 2: Run FAIL.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run PASS**, ruff, pyright.
- [ ] **Step 5: Commit** `feat(knowledge): self-feeding indexer`

---

### Task 4: `search_projects` tool and the projects prompt line

**Files:**
- Create: `app/application/tools/projects.py`
- Modify: `app/application/prompts.py`, `app/application/tools/catalog.py`,
  `app/application/use_cases/process_chat_message.py`,
  `app/application/use_cases/run_live_session.py`
- Test: `tests/unit/application/tools/test_projects.py`, `tests/unit/application/test_prompts.py`,
  use-case tests (one assertion each that the line is in the prompt)

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces:
  - `SearchProjects(store: KnowledgeStorePort, embedder: EmbedderPort, names: Sequence[str])`,
    spec `search_projects`, segment `"projects"`, params `query` (required), `project`
    (optional).
  - `projects_line(names: Sequence[str]) -> str` → `"Projetos: A, B."`; `""` for no names.
  - `ProcessChatMessage(..., projects: Sequence[str] = ())` and `RunLiveSession(...,
    projects: Sequence[str] = ())`: the line is appended after `now_line` when non-empty.
  - `build_tool_registry(..., knowledge: tuple[KnowledgeStorePort, EmbedderPort,
    Sequence[str]] | None = None, session: ProjectSession | None = None)` — `session` is
    added in Task 7; this task adds `knowledge` only.

Output format: one block per hit `[<project> › <heading>] <text>`, blocks joined by `\n`,
stopping before a block would push the total over 2,000 chars (at least the first block,
truncated). No hits → `"nada encontrado nos projetos"`. Unknown `project` →
`UnknownProjectError("projeto desconhecido; válidos: A, B")`.

- [ ] **Step 1: Failing tests**: `test_search_returns_tagged_blocks`,
  `test_search_filters_by_project`, `test_search_unknown_project_lists_valid_names`,
  `test_search_caps_at_2000_chars`, `test_search_no_hits`, `test_projects_line`,
  `test_projects_line_empty`, chat + live prompt contains `"Projetos: FinFlow."`.
- [ ] **Step 2–4:** FAIL → implement → PASS, ruff, pyright.
- [ ] **Step 5: Commit** `feat(knowledge): search_projects tool and project names in the prompt`

---

### Task 5: Panel-only tools — `client` marker through chat, live and ToolRunner

**Files:**
- Modify: `app/domain/tools.py`, `app/application/tool_runner.py`,
  `app/application/use_cases/process_chat_message.py`,
  `app/application/use_cases/run_live_session.py`, `app/api/schemas.py`, `app/api/router.py`,
  `app/api/live.py`
- Test: `tests/unit/application/test_tool_runner.py`, `tests/unit/api/test_router.py`,
  `tests/unit/api/test_live.py`, use-case tests

**Interfaces:**
- Produces:
  - `ToolSpec.panel_only: bool = False`.
  - `ToolRunner.specs(segment, *, panel: bool = False)` omits `panel_only` specs unless
    `panel`; `ToolRunner.run(call, conversation_id, segment, *, panel: bool = False)` returns
    `"erro: ferramenta disponível só no painel"` for a `panel_only` tool when not `panel`.
  - `ProcessChatMessage.execute(conversation_id, text, segment, *, panel: bool = False)`;
    `RunLiveSession.execute(transport, conversation_id, segment, *, panel: bool = False)`
    (passed down to `LiveRun` and every `runner.run`).
  - `IncomingMessageSchema.client: Literal["panel", "api"] = "api"`;
    `LiveStartSchema.client: Literal["panel", "api"] = "api"`. Routers pass
    `panel=body.client == "panel"`.

- [ ] **Step 1: Failing tests**: `test_panel_only_hidden_from_non_panel_specs`,
  `test_panel_only_listed_for_panel`, `test_panel_only_refused_when_not_panel`,
  `test_panel_only_runs_for_panel`, router `test_client_panel_reaches_use_case` (fake use case
  records `panel`), live `test_start_client_panel` and `test_start_unknown_client_rejected`
  (`bad_start`).
- [ ] **Step 2–4:** FAIL → implement → PASS (whole suite: defaults keep old callers green).
- [ ] **Step 5: Commit** `feat(api): panel client marker and panel-only tools`

---

### Task 6: Postgres store, Alembic, compose `db`; fastembed embedder

**Files:**
- Create: `app/adapters/postgres/__init__.py`, `app/adapters/postgres/knowledge_store.py`,
  `app/adapters/postgres/migrate.py`, `alembic.ini`, `migrations/env.py`,
  `migrations/script.py.mako`, `migrations/versions/0001_knowledge.py`,
  `app/adapters/fastembed/__init__.py`, `app/adapters/fastembed/embedder.py`
- Modify: `pyproject.toml` (extras `db = ["sqlalchemy[asyncio]>=2.0", "asyncpg>=0.30",
  "pgvector>=0.3", "alembic>=1.13"]`, `embed = ["fastembed>=0.7"]`; dev adds
  `testcontainers[postgres]>=4.8`, plus `db` and `embed` packages), `docker-compose.yml`,
  `.env.example`
- Test: `tests/integration/test_postgres_knowledge.py`, `tests/integration/test_fastembed.py`,
  `tests/unit/adapters/test_fastembed_errors.py`

**Interfaces:**
- Produces:
  - `PostgresKnowledge(url: str)` — implements `KnowledgeStorePort`; tables `documents(project,
    rel_path, digest, model, indexed_at, PK(project, rel_path))`, `chunks(project, rel_path,
    ordinal, heading, text, embedding vector)` (untyped `vector`, FK on delete cascade, no
    index). Cosine via `embedding <=> :v`, filtered by `documents.model`. SQLAlchemy/asyncpg
    errors → `KnowledgeError`. `async aclose()`.
  - `upgrade(url: str) -> None` in `migrate.py`: runs `alembic upgrade head` (sync, call it
    with `asyncio.to_thread`). Migration 0001: `CREATE EXTENSION IF NOT EXISTS vector` + both
    tables.
  - `FastEmbedder(model: str, cache_dir: str)` — loads lazily on first `embed`, runs in
    `asyncio.to_thread`; vendor errors → `KnowledgeError`. Before coding, check
    `TextEmbedding.list_supported_models()` contains the default model; if not, pick the
    closest supported multilingual model ≤ 500 MB and update the settings default + spec.
  - Compose: service `db` `pgvector/pgvector:pg16`, `127.0.0.1:5432:5432`, env
    `POSTGRES_DB=byte`, `POSTGRES_USER=byte`, `POSTGRES_PASSWORD=${BYTE_DB_PASSWORD}`, volume
    `byte-db`, healthcheck `pg_isready`; `api` `depends_on: db (healthy)`.
    `.env.example` gains `BYTE_DATABASE_URL=`, `BYTE_DB_PASSWORD=`, `BYTE_PROJECTS=`.

- [ ] **Step 1:** Integration test class wiring `KnowledgeStoreContract` to a testcontainers
  pgvector (`pgvector/pgvector:pg16`), running `upgrade` first; marked `integration`, `slow`.
  fastembed integration: Portuguese sentence closer to its paraphrase than to an unrelated one.
  Unit: `test_fastembed_wraps_vendor_errors` (monkeypatched loader raising) → `KnowledgeError`.
- [ ] **Step 2:** `pip install -e .[db,embed,dev]`; run unit FAIL.
- [ ] **Step 3:** Implement adapters, migration, compose, extras.
- [ ] **Step 4:** `pytest` PASS; `pytest -m integration tests/integration/test_postgres_knowledge.py
  tests/integration/test_fastembed.py` PASS (Docker running); ruff; pyright.
  Add `app/adapters/postgres/**` and `app/adapters/fastembed/**` to coverage `omit`, like the
  OpenAI adapters (integration-only).
- [ ] **Step 5: Commit** `feat(knowledge): postgres vector store and local fastembed embedder`

---

### Task 7: ProjectSession and `open_project` / `close_project`

**Files:**
- Create: `app/ports/terminal.py`, `app/application/project_session.py`,
  `tests/fakes/terminal.py`
- Modify: `app/application/tools/projects.py`, `app/application/tools/catalog.py`
- Test: `tests/unit/application/test_project_session.py`,
  `tests/unit/application/tools/test_projects.py`

**Interfaces:**
- Produces:
  - `ProjectTerminalPort`: `async start(cwd: str, argv: Sequence[str], env: Mapping[str, str],
    cols: int, rows: int) -> None`, `async write(data: bytes) -> None`, `async resize(cols,
    rows) -> None`, `async read() -> bytes` (`b""` once the process ended), `async stop() ->
    None` (whole tree; idempotent), `alive: bool`. Raise `ProjectError` on spawn failure.
  - `TerminalListener(ABC)`: `async state(project: str | None) -> None`,
    `async output(data: bytes) -> None`. Must not raise.
  - `child_env(environ: Mapping[str, str]) -> dict[str, str]` (module function).
  - `ProjectSession(terminal: ProjectTerminalPort, projects: Sequence[Project],
    command: Sequence[str], environ: Mapping[str, str], log: LoggerPort, *,
    scrollback: int = 262144)`:
    `async open(name) -> None` (`UnknownProjectError`), `async close() -> bool`,
    `current: str | None`, `async attach(listener)` (sends state, then scrollback if open),
    `detach(listener)`, `async write(data)`, `async resize(cols, rows)`, `async aclose()`.
    A reader task pumps `read()` into scrollback (bytes ring, oldest dropped) and listeners;
    on `b""` it clears `current` and sends `state(None)`.
    Logs `project.opened` / `project.closed` / `project.exited` with the name only.
  - Tools: `OpenProject(session, names)` (`open_project`, param `project`, `panel_only=True`,
    returns `"aberto: <name>"`), `CloseProject(session)` (`close_project`, `panel_only=True`,
    `"fechado"` / `"nenhum projeto aberto"`), segment `"projects"`.
  - `build_tool_registry(..., session: ProjectSession | None = None)`.
  - `FakeTerminal`: records `started` (cwd, argv, env), `written`, `sizes`; `feed(bytes)` and
    `exit()` drive `read()`.

- [ ] **Step 1: Failing tests**:
  `test_open_starts_command_in_project_folder`, `test_open_filters_secrets_from_env`
  (`BYTE_API_TOKEN`, `OPENAI_API_KEY` absent; `PATH` present),
  `test_open_other_project_stops_current`, `test_open_same_project_starts_fresh`
  (Review Focus 4: `stop` then `start` again), `test_open_unknown_project_raises`,
  `test_close_returns_false_when_nothing_open`, `test_output_fans_out_and_fills_scrollback`,
  `test_scrollback_drops_oldest_beyond_limit`, `test_attach_replays_state_then_scrollback`,
  `test_process_exit_clears_current_and_notifies` (Review Focus 3: no listener attached at
  exit; a later attach gets `state(None)`), `test_write_without_open_project_is_dropped`,
  `test_aclose_stops_terminal`; tool tests for both tools' strings and `panel_only`.
- [ ] **Step 2–4:** FAIL → implement → PASS, ruff, pyright.
- [ ] **Step 5: Commit** `feat(projects): project session and open/close tools`

---

### Task 8: Windows PTY adapter

**Files:**
- Create: `app/adapters/pty/__init__.py`, `app/adapters/pty/winpty_terminal.py`
- Modify: `pyproject.toml` (extra `pty = ["pywinpty>=2.0; sys_platform == 'win32'"]`; dev adds
  it), coverage `omit` adds `app/adapters/pty/**`
- Test: `tests/integration/test_winpty_terminal.py` (`integration`, `slow`, skipped off Windows)

**Interfaces:**
- Produces: `WinPtyTerminal()` implementing `ProjectTerminalPort` with
  `winpty.PtyProcess.spawn(argv, cwd=, env=, dimensions=(rows, cols))`; blocking reads in
  `asyncio.to_thread`, text encoded UTF-8; `stop` kills the process tree
  (`taskkill /PID <pid> /T /F` via `asyncio.create_subprocess_exec`, then `close`).
  Vendor errors → `ProjectError`.

- [ ] **Step 1:** Integration test: start `cmd /c echo byte-ok` → read until `b""`, output
  contains `byte-ok`; start `cmd` (stays open), `stop()`, `alive is False`.
- [ ] **Step 2–4:** implement; `pytest -m integration tests/integration/test_winpty_terminal.py`
  PASS; ruff; pyright.
- [ ] **Step 5: Commit** `feat(projects): windows pty adapter`

---

### Task 9: Wiring — deps, lifespan, `WS /api/v1/ws/terminal`

**Files:**
- Create: `app/api/terminal.py`
- Modify: `app/api/deps.py`, `main.py`, `docs/web-api-contract.md`
- Test: `tests/unit/api/test_terminal.py`, `tests/unit/api/test_deps.py`, `tests/unit/test_main.py`

**Interfaces:**
- Consumes: everything above.
- Produces (`deps.py`, all `lru_cache`):
  - `get_embedder() -> EmbedderPort` (`FastEmbedder`, lazy import; extra missing →
    `ConfigError` only when projects are configured).
  - `get_knowledge() -> KnowledgeStorePort` (`PostgresKnowledge` when `database_url`, else
    `InMemoryKnowledge`).
  - `get_indexer() -> KnowledgeIndexer | None` (`None` without projects).
  - `get_project_session() -> ProjectSession | None` — `None` unless projects are configured,
    `shutil.which(settings.claude_command)` resolves and `app.adapters.pty` imports
    (otherwise log `projects.terminal_unavailable` with the reason, once).
  - `get_terminal_slot() -> LiveSlot`.
  - `get_tools()` passes `knowledge=(get_knowledge(), get_embedder(), names)` when projects
    exist and `session=get_project_session()`; `get_process_chat` / `get_run_live_session`
    pass `projects=names`.
- Lifespan: when `database_url` → `await asyncio.to_thread(upgrade, url)` before anything
  else; start `run_indexer` task when an indexer exists; on shutdown cancel it, `await
  session.aclose()`, `await knowledge.aclose()` if it has one. Log `adapters.selected` gains
  `knowledge` and `terminal`.
- `WS /ws/terminal` (`app/api/terminal.py`): `accept_authorized`; 4404-style close (`1008`)
  when `get_project_session()` is `None`; `slot.claim` (old socket closed 4000); a
  `TerminalListener` that sends `{"type":"state","project":...}` as text and output as binary;
  `session.attach`; loop: binary → `session.write`; text JSON `{"type":"resize","cols","rows"}`
  → clamp each to 2..500 → `session.resize`; anything else ignored; `finally` detach +
  release. Contract section added to `docs/web-api-contract.md`.

- [ ] **Step 1: Failing tests** (TestClient websocket, `ProjectSession` over `FakeTerminal`
  injected via `app.dependency_overrides`): `test_terminal_requires_token`,
  `test_terminal_sends_state_on_connect`, `test_terminal_replays_scrollback`,
  `test_terminal_binary_is_written`, `test_terminal_resize_clamped` (0 → 2, 10000 → 500),
  `test_terminal_garbage_text_ignored`, `test_terminal_input_without_project_dropped`,
  `test_second_terminal_replaces_first` (4000), `test_terminal_closed_when_unavailable`;
  deps: `test_session_none_without_claude` (monkeypatched `shutil.which`),
  `test_knowledge_memory_without_database_url`.
- [ ] **Step 2–4:** FAIL → implement → PASS, ruff, pyright.
- [ ] **Step 5: Commit** `feat(api): project terminal websocket and knowledge wiring`

---

### Task 10: Web panel — xterm view and `client: "panel"`

**Files:**
- Create: `web/vendor/xterm/xterm.js`, `web/vendor/xterm/xterm.css`,
  `web/vendor/xterm/addon-fit.js` (pinned `@xterm/xterm@5.5.0`, `@xterm/addon-fit@0.10.0`,
  downloaded from jsdelivr, license header kept), `web/project-term.js`
- Modify: `web/index.html` (`#pane-term` gets a `#term-xterm` container, hidden by default;
  title shows the project), `web/app.js`, `web/api.js` (`chat` body adds `client: 'panel'`),
  `web/live.js` (start message adds `client: 'panel'`), `web/style.css`
- Test: `tests/web/project-term.test.mjs` (node test, like `time.test.mjs`, for the pure
  state-to-view function)

**Interfaces:**
- Produces: `web/project-term.js` exports `connectProjectTerm({ token, el, onState })` that
  opens `/api/v1/ws/terminal` with the `["bearer", token]` subprotocol, writes binary frames
  to an xterm `Terminal`, sends keystrokes (`onData` → UTF-8 bytes) and fit-addon resizes,
  reconnects with backoff (1 s → 30 s) while the panel is unlocked; and
  `paneView(project) -> { mode: 'log'|'xterm', title: string }` (`null` → log,
  `"byte@casa: ~"`; name → xterm, `"byte@casa: ~/<name>"`).
- `app.js`: on `onState`, switch `#term-out`/`#term-form` vs `#term-xterm` and the title;
  log `projeto aberto: <name>` / `projeto fechado` in the activity log.

- [ ] **Step 1:** Failing node test for `paneView`; run `node --test tests/web` → FAIL.
- [ ] **Step 2:** Implement; `node --test tests/web` PASS.
- [ ] **Step 3:** Manual check with `python main.py --web` and `BYTE_PROJECTS` set: chat
  "abre o FinFlow" → xterm shows `claude` in `D:\Projetos\FinFlow`; reload tab → same
  session, scrollback back; "fecha o projeto" → log view; panel voice "abre o Byte" works;
  a `/live` start without `client` cannot open (tool absent).
- [ ] **Step 4: Commit** `feat(web): project terminal view in the panel`

---

### Task 11: Docs, lock, final gate

**Files:**
- Modify: `CLAUDE.md` (segment table row `projects`; API table row `WS /ws/terminal`;
  Persistence: Postgres now holds the knowledge index; Current state row "Project knowledge +
  terminal (Spec 4) — done"), `README.md` (pip-compile command adds `--extra db --extra
  embed`; how to set `BYTE_PROJECTS`, start `docker compose up db`), `requirements.lock`
  (regenerate with the README command), `Dockerfile` only if the new extras need system libs.
- [ ] **Step 1:** Update docs; regenerate lock with `uv pip compile …`.
- [ ] **Step 2:** `ruff check . && ruff format --check . && pyright && pytest` — all green.
- [ ] **Step 3: Commit** `docs: document project knowledge and terminal (Spec 4)`

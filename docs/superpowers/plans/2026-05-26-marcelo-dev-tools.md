# Marcelo Dev Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar ao agente Marcelo ferramentas de filesystem e ambiente de desenvolvimento — CRUD em `~/Desktop/marcelo/`, abertura de PyCharm + terminal com `claude`, e envio de prompts reformatados via SendKeys após aprovação do usuário.

**Architecture:** Hexagonal — ShellPort (ABC) + WindowsShellAdapter; dois Agno Toolkits (FilesystemToolkit, DeveloperToolkit) injetados no GroqAgnoAgent; ws_chat.py estendido para o fluxo preview→approve; UI recebe card de preview com botões.

**Tech Stack:** Python 3.12, Agno 2.6.5 (Toolkit), PowerShell WScript.Shell, pathlib, subprocess, FastAPI WebSocket, Vanilla JS

---

## File Map

| Ação | Arquivo |
|---|---|
| CREATE | `app/ports/shell.py` |
| CREATE | `app/adapters/shell/__init__.py` |
| CREATE | `app/adapters/shell/windows_shell_adapter.py` |
| CREATE | `app/adapters/tools/__init__.py` |
| CREATE | `app/adapters/tools/filesystem_tool.py` |
| CREATE | `app/adapters/tools/developer_tool.py` |
| CREATE | `tests/unit/adapters/tools/__init__.py` |
| CREATE | `tests/unit/adapters/tools/test_filesystem_tool.py` |
| CREATE | `tests/unit/adapters/tools/test_developer_tool.py` |
| MODIFY | `app/config.py` |
| MODIFY | `app/api/deps.py` |
| MODIFY | `app/api/ws_chat.py` |
| MODIFY | `app/adapters/agent/groq_agno_agent.py` |
| MODIFY | `Animacao_Marcelo/marcelo_ui.html` |
| MODIFY | `Animacao_Marcelo/js/chat-client.js` |

---

## Task 1: Config fields

**Files:**
- Modify: `app/config.py`

- [ ] **Step 1: Add workspace_path and pycharm_path to Settings**

```python
# app/config.py — add after groq_tts_voice field
    # Developer tools
    workspace_path: str = ""  # resolved at runtime to ~/Desktop/marcelo if empty
    pycharm_path: str = r"C:\Users\fenil\AppData\Local\Programs\PyCharm 2025.2.0.1\bin\pycharm.bat"
```

- [ ] **Step 2: Verify pyright passes**

```bash
pyright app/config.py
```
Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
git add app/config.py
git commit -m "feat(config): add workspace_path and pycharm_path settings"
```

---

## Task 2: ShellPort + WindowsShellAdapter

**Files:**
- Create: `app/ports/shell.py`
- Create: `app/adapters/shell/__init__.py`
- Create: `app/adapters/shell/windows_shell_adapter.py`
- Test: `tests/unit/adapters/test_shell.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/adapters/test_shell.py
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.shell.windows_shell_adapter import WindowsShellAdapter


def test_run_returns_stdout() -> None:
    adapter = WindowsShellAdapter()
    result = adapter.run(["echo", "hello"])
    assert "hello" in result


def test_run_with_cwd(tmp_path) -> None:
    adapter = WindowsShellAdapter()
    result = adapter.run(["pwd"], cwd=str(tmp_path))
    # just verify it doesn't raise
    assert isinstance(result, str)


def test_send_to_window_calls_powershell() -> None:
    adapter = WindowsShellAdapter()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        adapter.send_to_window("my-title", "hello world")
        call_args = mock_run.call_args
        script = call_args[0][0]
        assert "my-title" in " ".join(script)
        assert "hello world" in " ".join(script)


def test_send_to_window_retries_on_failure() -> None:
    adapter = WindowsShellAdapter()
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="AppActivate returned false"),
            MagicMock(returncode=0, stdout="", stderr=""),
        ]
        # Should not raise — retries once
        adapter.send_to_window("my-title", "hello")
        assert mock_run.call_count == 2
```

- [ ] **Step 2: Run to confirm fail**

```bash
pytest tests/unit/adapters/test_shell.py -v
```
Expected: `ModuleNotFoundError: app.adapters.shell.windows_shell_adapter`

- [ ] **Step 3: Create ShellPort**

```python
# app/ports/shell.py
from __future__ import annotations

from abc import ABC, abstractmethod


class ShellPort(ABC):
    @abstractmethod
    def run(self, command: list[str], cwd: str | None = None) -> str: ...

    @abstractmethod
    def send_to_window(self, window_title: str, text: str) -> None: ...
```

- [ ] **Step 4: Create __init__.py**

```python
# app/adapters/shell/__init__.py
```
(empty file)

- [ ] **Step 5: Create WindowsShellAdapter**

```python
# app/adapters/shell/windows_shell_adapter.py
from __future__ import annotations

import subprocess
import time

from app.ports.shell import ShellPort


class WindowsShellAdapter(ShellPort):
    def run(self, command: list[str], cwd: str | None = None) -> str:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout + result.stderr

    def send_to_window(self, window_title: str, text: str) -> None:
        # Escape special SendKeys chars: +^%~{}[]
        escaped = (
            text.replace("{", "{{")
                .replace("}", "}}")
                .replace("+", "{+}")
                .replace("^", "{^}")
                .replace("%", "{%}")
                .replace("~", "{~}")
                .replace("(", "{(}")
                .replace(")", "{)}")
        )
        ps_script = (
            f"$wsh = New-Object -ComObject WScript.Shell; "
            f"$result = $wsh.AppActivate('{window_title}'); "
            f"if (-not $result) {{ exit 1 }}; "
            f"Start-Sleep -Milliseconds 300; "
            f"$wsh.SendKeys('{escaped}'); "
            f"$wsh.SendKeys('{{ENTER}}')"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            # Retry once after short delay
            time.sleep(0.5)
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"send_to_window failed for title '{window_title}': {result.stderr}"
                )
```

- [ ] **Step 6: Run tests**

```bash
pytest tests/unit/adapters/test_shell.py -v
```
Expected: 4 PASSED

- [ ] **Step 7: Commit**

```bash
git add app/ports/shell.py app/adapters/shell/ tests/unit/adapters/test_shell.py
git commit -m "feat(shell): add ShellPort + WindowsShellAdapter with SendKeys support"
```

---

## Task 3: FilesystemToolkit

**Files:**
- Create: `app/adapters/tools/__init__.py`
- Create: `app/adapters/tools/filesystem_tool.py`
- Test: `tests/unit/adapters/tools/test_filesystem_tool.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/adapters/tools/test_filesystem_tool.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.adapters.tools.filesystem_tool import FilesystemToolkit


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def toolkit(workspace: Path) -> FilesystemToolkit:
    return FilesystemToolkit(workspace_root=workspace)


def test_create_and_read_file(toolkit: FilesystemToolkit, workspace: Path) -> None:
    result = json.loads(toolkit.create_file("hello.txt", "world"))
    assert result["ok"] is True
    assert (workspace / "hello.txt").read_text() == "world"
    content = toolkit.read_file("hello.txt")
    assert content == "world"


def test_write_file_overwrites(toolkit: FilesystemToolkit, workspace: Path) -> None:
    toolkit.create_file("f.txt", "v1")
    toolkit.write_file("f.txt", "v2")
    assert (workspace / "f.txt").read_text() == "v2"


def test_delete_file(toolkit: FilesystemToolkit, workspace: Path) -> None:
    toolkit.create_file("del.txt", "bye")
    result = json.loads(toolkit.delete_file("del.txt"))
    assert result["ok"] is True
    assert not (workspace / "del.txt").exists()


def test_create_folder(toolkit: FilesystemToolkit, workspace: Path) -> None:
    result = json.loads(toolkit.create_folder("subdir"))
    assert result["ok"] is True
    assert (workspace / "subdir").is_dir()


def test_delete_folder(toolkit: FilesystemToolkit, workspace: Path) -> None:
    (workspace / "todel").mkdir()
    (workspace / "todel" / "f.txt").write_text("x")
    result = json.loads(toolkit.delete_folder("todel"))
    assert result["ok"] is True
    assert not (workspace / "todel").exists()


def test_list_files(toolkit: FilesystemToolkit, workspace: Path) -> None:
    toolkit.create_file("a.txt", "")
    toolkit.create_folder("subdir")
    result = json.loads(toolkit.list_files())
    names = [e["name"] for e in result]
    assert "a.txt" in names
    assert "subdir" in names


def test_path_traversal_blocked(toolkit: FilesystemToolkit) -> None:
    result = json.loads(toolkit.read_file("../../etc/passwd"))
    assert "error" in result


def test_create_file_creates_intermediate_dirs(toolkit: FilesystemToolkit, workspace: Path) -> None:
    toolkit.create_file("deep/nested/file.txt", "content")
    assert (workspace / "deep" / "nested" / "file.txt").exists()
```

- [ ] **Step 2: Run to confirm fail**

```bash
pytest tests/unit/adapters/tools/test_filesystem_tool.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create __init__ files**

```python
# app/adapters/tools/__init__.py
# tests/unit/adapters/tools/__init__.py
```
(both empty)

- [ ] **Step 4: Implement FilesystemToolkit**

```python
# app/adapters/tools/filesystem_tool.py
from __future__ import annotations

import json
import shutil
from pathlib import Path

from agno.tools import Toolkit


class FilesystemToolkit(Toolkit):
    def __init__(self, workspace_root: Path | None = None) -> None:
        super().__init__(name="filesystem")
        if workspace_root is None:
            workspace_root = Path.home() / "Desktop" / "marcelo"
        workspace_root.mkdir(parents=True, exist_ok=True)
        self._root = workspace_root.resolve()
        self.register(self.list_files)
        self.register(self.read_file)
        self.register(self.create_file)
        self.register(self.write_file)
        self.register(self.delete_file)
        self.register(self.create_folder)
        self.register(self.delete_folder)

    def _resolve(self, rel_path: str) -> Path | None:
        target = (self._root / rel_path).resolve()
        if not str(target).startswith(str(self._root)):
            return None
        return target

    def list_files(self, path: str = "") -> str:
        """List files and folders in the workspace (1 level deep)."""
        target = self._resolve(path) if path else self._root
        if target is None:
            return json.dumps({"error": "path traversal detected"})
        if not target.exists():
            return json.dumps({"error": f"path not found: {path}"})
        entries = [
            {"name": p.name, "type": "dir" if p.is_dir() else "file"}
            for p in sorted(target.iterdir())
        ]
        return json.dumps(entries)

    def read_file(self, path: str) -> str:
        """Read and return the content of a file in the workspace."""
        target = self._resolve(path)
        if target is None:
            return json.dumps({"error": "path traversal detected"})
        if not target.exists():
            return json.dumps({"error": f"file not found: {path}"})
        return target.read_text(encoding="utf-8")

    def create_file(self, path: str, content: str) -> str:
        """Create a new file with content. Creates intermediate directories."""
        target = self._resolve(path)
        if target is None:
            return json.dumps({"error": "path traversal detected"})
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return json.dumps({"ok": True, "path": str(target)})

    def write_file(self, path: str, content: str) -> str:
        """Overwrite an existing file with new content."""
        target = self._resolve(path)
        if target is None:
            return json.dumps({"error": "path traversal detected"})
        target.write_text(content, encoding="utf-8")
        return json.dumps({"ok": True})

    def delete_file(self, path: str) -> str:
        """Delete a file from the workspace."""
        target = self._resolve(path)
        if target is None:
            return json.dumps({"error": "path traversal detected"})
        if not target.exists():
            return json.dumps({"error": f"file not found: {path}"})
        target.unlink()
        return json.dumps({"ok": True})

    def create_folder(self, path: str) -> str:
        """Create a folder in the workspace."""
        target = self._resolve(path)
        if target is None:
            return json.dumps({"error": "path traversal detected"})
        target.mkdir(parents=True, exist_ok=True)
        return json.dumps({"ok": True, "path": str(target)})

    def delete_folder(self, path: str) -> str:
        """Delete a folder and all its contents from the workspace."""
        target = self._resolve(path)
        if target is None:
            return json.dumps({"error": "path traversal detected"})
        if not target.exists():
            return json.dumps({"error": f"folder not found: {path}"})
        shutil.rmtree(target)
        return json.dumps({"ok": True})
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/unit/adapters/tools/test_filesystem_tool.py -v
```
Expected: 9 PASSED

- [ ] **Step 6: Commit**

```bash
git add app/adapters/tools/ tests/unit/adapters/tools/
git commit -m "feat(tools): add FilesystemToolkit with CRUD and path traversal protection"
```

---

## Task 4: DeveloperToolkit

**Files:**
- Create: `app/adapters/tools/developer_tool.py`
- Test: `tests/unit/adapters/tools/test_developer_tool.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/adapters/tools/test_developer_tool.py
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.tools.developer_tool import DeveloperToolkit


@pytest.fixture
def shell() -> MagicMock:
    return MagicMock()


@pytest.fixture
def pycharm_path(tmp_path: Path) -> Path:
    p = tmp_path / "pycharm.bat"
    p.write_text("")
    return p


@pytest.fixture
def toolkit(shell: MagicMock, tmp_path: Path, pycharm_path: Path) -> DeveloperToolkit:
    workspace = tmp_path / "marcelo"
    workspace.mkdir()
    return DeveloperToolkit(
        shell=shell,
        workspace_root=workspace,
        pycharm_path=str(pycharm_path),
    )


def test_open_dev_environment_creates_folder(
    toolkit: DeveloperToolkit, tmp_path: Path
) -> None:
    result = json.loads(toolkit.open_dev_environment("myproject"))
    assert result["ok"] is True
    assert (tmp_path / "marcelo" / "myproject").is_dir()


def test_open_dev_environment_calls_pycharm(
    toolkit: DeveloperToolkit, shell: MagicMock
) -> None:
    toolkit.open_dev_environment("myproject")
    calls = [str(c) for c in shell.run.call_args_list]
    assert any("myproject" in c for c in calls)


def test_open_dev_environment_sets_active_project(
    toolkit: DeveloperToolkit,
) -> None:
    toolkit.open_dev_environment("jarvis")
    assert toolkit.active_project == "jarvis"
    assert toolkit.claude_window_title == "marcelo-claude-jarvis"


def test_send_to_claude_no_project_returns_error(
    toolkit: DeveloperToolkit,
) -> None:
    result = json.loads(toolkit.send_to_claude("hello"))
    assert "error" in result


def test_send_to_claude_calls_send_to_window(
    toolkit: DeveloperToolkit, shell: MagicMock
) -> None:
    toolkit.open_dev_environment("jarvis")
    result = json.loads(toolkit.send_to_claude("## Task\nDo something"))
    assert result["ok"] is True
    shell.send_to_window.assert_called_once_with(
        "marcelo-claude-jarvis", "## Task\nDo something"
    )


def test_open_dev_environment_existing_folder_ok(
    toolkit: DeveloperToolkit, tmp_path: Path
) -> None:
    (tmp_path / "marcelo" / "existing").mkdir()
    result = json.loads(toolkit.open_dev_environment("existing"))
    assert result["ok"] is True
```

- [ ] **Step 2: Run to confirm fail**

```bash
pytest tests/unit/adapters/tools/test_developer_tool.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement DeveloperToolkit**

```python
# app/adapters/tools/developer_tool.py
from __future__ import annotations

import json
from pathlib import Path

from agno.tools import Toolkit

from app.ports.shell import ShellPort


class DeveloperToolkit(Toolkit):
    def __init__(
        self,
        shell: ShellPort,
        workspace_root: Path | None = None,
        pycharm_path: str = "",
    ) -> None:
        super().__init__(name="developer")
        if workspace_root is None:
            workspace_root = Path.home() / "Desktop" / "marcelo"
        workspace_root.mkdir(parents=True, exist_ok=True)
        self._root = workspace_root.resolve()
        self._shell = shell
        self._pycharm_path = pycharm_path
        self.active_project: str | None = None
        self.claude_window_title: str | None = None
        self.register(self.open_dev_environment)
        self.register(self.send_to_claude)

    def open_dev_environment(self, project_name: str) -> str:
        """Open PyCharm and a terminal with claude for the given project name.
        Creates ~/Desktop/marcelo/<project_name>/ if it does not exist.
        """
        project_path = self._root / project_name
        project_path.mkdir(parents=True, exist_ok=True)

        path_str = str(project_path)
        window_title = f"marcelo-claude-{project_name}"

        # Open PyCharm (non-blocking)
        if self._pycharm_path:
            try:
                self._shell.run(
                    ["powershell", "-NoProfile", "-Command",
                     f"Start-Process '{self._pycharm_path}' -ArgumentList '{path_str}'"],
                )
            except Exception:
                pass  # PyCharm failure is non-fatal

        # Open Windows Terminal with claude
        self._shell.run(
            ["powershell", "-NoProfile", "-Command",
             f"Start-Process 'wt' -ArgumentList \"-d '{path_str}' --title '{window_title}' pwsh -NoExit -Command claude\""],
        )

        self.active_project = project_name
        self.claude_window_title = window_title

        return json.dumps({
            "ok": True,
            "project": project_name,
            "path": path_str,
            "window_title": window_title,
        })

    def send_to_claude(self, prompt: str) -> str:
        """Send an approved prompt to the active claude terminal via SendKeys."""
        if not self.active_project or not self.claude_window_title:
            return json.dumps({
                "error": "No active project. Ask the user to say 'cria o projeto X' first."
            })
        try:
            self._shell.send_to_window(self.claude_window_title, prompt)
            return json.dumps({"ok": True})
        except RuntimeError as exc:
            return json.dumps({"error": str(exc)})
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/unit/adapters/tools/test_developer_tool.py -v
```
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/adapters/tools/developer_tool.py tests/unit/adapters/tools/test_developer_tool.py
git commit -m "feat(tools): add DeveloperToolkit — open_dev_environment + send_to_claude"
```

---

## Task 5: Wiring — deps.py + config + GroqAgnoAgent

**Files:**
- Modify: `app/api/deps.py`
- Modify: `app/adapters/agent/groq_agno_agent.py`

- [ ] **Step 1: Add get_shell, get_filesystem_tool, get_developer_tool to deps.py**

```python
# app/api/deps.py — add these imports at the top
from app.adapters.shell.windows_shell_adapter import WindowsShellAdapter
from app.adapters.tools.filesystem_tool import FilesystemToolkit
from app.adapters.tools.developer_tool import DeveloperToolkit
```

Add these functions before `get_agent()`:

```python
@lru_cache
def get_shell() -> WindowsShellAdapter:
    return WindowsShellAdapter()


@lru_cache
def get_filesystem_tool() -> FilesystemToolkit:
    settings = get_settings()
    root = Path(settings.workspace_path) if settings.workspace_path else None
    return FilesystemToolkit(workspace_root=root)


@lru_cache
def get_developer_tool() -> DeveloperToolkit:
    settings = get_settings()
    root = Path(settings.workspace_path) if settings.workspace_path else None
    return DeveloperToolkit(
        shell=get_shell(),
        workspace_root=root,
        pycharm_path=settings.pycharm_path,
    )
```

Add `from pathlib import Path` to imports.

- [ ] **Step 2: Update get_agent to pass tools**

```python
@lru_cache
def get_agent() -> AgentPort:
    settings = get_settings()
    fs_tool = get_filesystem_tool()
    dev_tool = get_developer_tool()
    return RoutingAgnoAgent(
        groq_agent=GroqAgnoAgent(settings, tools=[fs_tool, dev_tool]),
        gemini_agent=GeminiAgnoAgent(settings),
    )
```

- [ ] **Step 3: Update GroqAgnoAgent to accept tools**

```python
# app/adapters/agent/groq_agno_agent.py
# Change __init__ signature and Agent construction:

from agno.tools import Toolkit  # add import

class GroqAgnoAgent(AgentPort):
    def __init__(self, settings: Settings, tools: list[Toolkit] | None = None) -> None:
        self._model_id = settings.groq_model_id
        agno_db_url = settings.database_url.replace("+asyncpg", "+psycopg")
        db = PostgresDb(db_url=agno_db_url)
        self._agent = Agent(
            model=Groq(id=self._model_id),
            db=db,
            tools=tools or [],
            add_history_to_context=True,
            add_datetime_to_context=settings.agno_add_datetime,
            add_location_to_context=settings.agno_add_location,
            output_schema=GroqOutputSchema,
            instructions=[_SYSTEM_PROMPT],
        )
```

- [ ] **Step 4: Update _SYSTEM_PROMPT to handle dev mode**

Replace the existing `_SYSTEM_PROMPT` in `groq_agno_agent.py`:

```python
_SYSTEM_PROMPT = """Você é Marcelo, assistente pessoal de inteligência artificial.
Personalidade: direto, inteligente, levemente informal, confiante sem ser arrogante.
Fale sempre em português brasileiro, de forma natural como numa conversa real.
Respostas curtas a médias — não faça listas desnecessárias, não seja verboso.
Lembre-se do histórico da conversa e mantenha continuidade natural.

Você tem acesso a ferramentas:
- filesystem: criar, ler, editar, deletar arquivos e pastas em ~/Desktop/marcelo/
- developer: abrir ambiente de desenvolvimento (PyCharm + terminal com claude), enviar prompts ao claude

Quando o usuário disser "cria o projeto X" ou "codar X" ou "abrir projeto X":
  → chame open_dev_environment(project_name="X")

Quando o modo desenvolvimento está ativo (open_dev_environment já foi chamado) e o usuário descrever uma tarefa de código:
  → reformate o pedido no seguinte formato e responda APENAS com o prompt formatado:

## Task
[descrição clara e objetiva da tarefa]

## Requisitos
- [item específico e acionável]
- [item específico e acionável]

## Contexto
Projeto: [nome] | Workspace: ~/Desktop/marcelo/[nome]/

## Constraints
[arquitetura, stack, estilo — se mencionados pelo usuário; omitir se não mencionado]

Antes de responder, classifique internamente a complexidade:
- Se a tarefa exige raciocínio profundo multi-etapas, matemática avançada, geração de código complexo ou análise estruturada longa: defina complexity='complex' e content=[]. NÃO responda.
- Caso contrário: complexity='simple' e preencha content com sua resposta completa."""
```

- [ ] **Step 5: Verify pyright**

```bash
pyright app/api/deps.py app/adapters/agent/groq_agno_agent.py
```
Expected: 0 errors (ignore existing `model_override` warning)

- [ ] **Step 6: Commit**

```bash
git add app/api/deps.py app/adapters/agent/groq_agno_agent.py
git commit -m "feat(agent): wire FilesystemToolkit + DeveloperToolkit into GroqAgnoAgent"
```

---

## Task 6: ws_chat.py — preview flow

**Files:**
- Modify: `app/api/ws_chat.py`

- [ ] **Step 1: Rewrite ws_chat to handle preview/approve/cancel**

```python
# app/api/ws_chat.py
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.api.deps import get_agent, get_developer_tool, get_logger, get_repo
from app.application.use_cases.process_incoming_message import ProcessIncomingMessage
from app.domain.entities import IncomingMessage

router = APIRouter()

_PREVIEW_MARKER = "## Task"


class _ChatPayload(BaseModel):
    message: str
    session_id: str = "default"


@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket) -> None:
    await websocket.accept()
    agent = get_agent()
    repo = get_repo()
    log = get_logger()
    dev_tool = get_developer_tool()

    pending_prompt: str | None = None

    try:
        while True:
            raw = await websocket.receive_json()
            msg_type = raw.get("type", "message")

            # ── Approve pending preview ─────────────────────────────────
            if msg_type == "approve_send":
                if pending_prompt and dev_tool.active_project:
                    result = dev_tool.send_to_claude(pending_prompt)
                    pending_prompt = None
                    await websocket.send_json({
                        "type": "chunk",
                        "text": "Prompt enviado ao Claude Code! Veja o terminal.",
                    })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "text": "Nenhum prompt pendente ou projeto ativo.",
                    })
                continue

            # ── Cancel pending preview ──────────────────────────────────
            if msg_type == "cancel_send":
                pending_prompt = None
                await websocket.send_json({"type": "chunk", "text": "Cancelado."})
                continue

            # ── Normal chat message ─────────────────────────────────────
            payload = _ChatPayload.model_validate(raw)

            use_case = ProcessIncomingMessage(agent=agent, repo=repo, log=log)
            incoming = IncomingMessage(
                id=str(uuid4()),
                sender="local",
                content=payload.message,
                channel="ui",
                timestamp=datetime.now(tz=UTC),
                conversation_id=payload.session_id,
                model_override=None,
            )

            try:
                outgoing = await use_case.execute(incoming)
                response_text = outgoing.content

                # Detect reformatted dev prompt → send as preview
                if (
                    dev_tool.active_project
                    and response_text.strip().startswith(_PREVIEW_MARKER)
                ):
                    pending_prompt = response_text
                    await websocket.send_json({
                        "type": "preview",
                        "prompt": response_text,
                        "project": dev_tool.active_project,
                    })
                else:
                    await websocket.send_json({"type": "chunk", "text": response_text})

                await websocket.send_json({"type": "done", "text": ""})

            except Exception as exc:
                await websocket.send_json({"type": "error", "text": str(exc)})

    except WebSocketDisconnect:
        pass
```

- [ ] **Step 2: Verify pyright**

```bash
pyright app/api/ws_chat.py
```
Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
git add app/api/ws_chat.py
git commit -m "feat(ws): add preview/approve_send/cancel_send flow for Claude Code bridge"
```

---

## Task 7: UI — preview card

**Files:**
- Modify: `Animacao_Marcelo/marcelo_ui.html`
- Modify: `Animacao_Marcelo/js/chat-client.js`

- [ ] **Step 1: Add preview card CSS to marcelo_ui.html**

Add inside the `<style>` block, after `.msg.interim` rule:

```css
    /* ── Preview card ── */
    #preview-card {
      display: none;
      background: rgba(0, 20, 40, 0.75);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid rgba(100, 200, 255, 0.25);
      border-radius: 14px;
      padding: 14px 16px;
      margin-top: 8px;
      pointer-events: auto;
    }
    #preview-card.visible { display: block; }
    #preview-header {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 1.5px;
      color: rgba(100, 200, 255, 0.7);
      margin-bottom: 8px;
    }
    #preview-body {
      font-size: 12px;
      line-height: 1.6;
      color: rgba(255, 255, 255, 0.85);
      white-space: pre-wrap;
      word-break: break-word;
      max-height: 260px;
      overflow-y: auto;
      scrollbar-width: none;
      margin-bottom: 12px;
    }
    #preview-body::-webkit-scrollbar { display: none; }
    #preview-actions {
      display: flex;
      gap: 10px;
    }
    .preview-btn {
      flex: 1;
      padding: 7px 0;
      border: none;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: opacity 0.2s;
    }
    .preview-btn:hover { opacity: 0.8; }
    #btn-approve { background: rgba(50, 200, 100, 0.85); color: #fff; }
    #btn-cancel  { background: rgba(200, 60, 60, 0.7);  color: #fff; }
```

- [ ] **Step 2: Add preview card HTML to marcelo_ui.html**

Inside `#transcript` div, add after its opening tag:

```html
    <div id="preview-card">
      <div id="preview-header">📋 Prompt para Claude Code</div>
      <pre id="preview-body"></pre>
      <div id="preview-actions">
        <button class="preview-btn" id="btn-approve">✓ Enviar</button>
        <button class="preview-btn" id="btn-cancel">✗ Cancelar</button>
      </div>
    </div>
```

- [ ] **Step 3: Wire preview card in marcelo_ui.html script**

Add after the `const sendBtn` line in the script block:

```javascript
    const previewCard   = document.getElementById('preview-card');
    const previewBody   = document.getElementById('preview-body');
    const btnApprove    = document.getElementById('btn-approve');
    const btnCancel     = document.getElementById('btn-cancel');

    btnApprove.addEventListener('click', () => {
      client.approvePreview();
      previewCard.classList.remove('visible');
    });

    btnCancel.addEventListener('click', () => {
      client.cancelPreview();
      previewCard.classList.remove('visible');
    });
```

Update the `ChatClient` instantiation — add `onPreview` callback:

```javascript
    const client = new ChatClient({
      wsUrl: WS_URL,
      ttsUrl: TTS_URL,
      onState: (s) => { setState(s); stateBadge.textContent = s; },
      onTranscript: ({ role, text }) => addTranscript(role, text),
      onResponse:   (text)          => addTranscript('assistant', text),
      onError:      (msg)           => console.error('[Marcelo]', msg),
      onPreview: ({ prompt, project }) => {
        previewBody.textContent = prompt;
        previewCard.classList.add('visible');
        transcriptEl.scrollTop = transcriptEl.scrollHeight;
      },
    });
```

- [ ] **Step 4: Add approvePreview/cancelPreview to chat-client.js**

In the `ChatClient` constructor, add:
```javascript
    this._onPreview = options.onPreview || (() => {});
```

In the `connect()` `onmessage` handler, add before the `chunk` check:
```javascript
      if (msg.type === 'preview') {
        this._onPreview({ prompt: msg.prompt, project: msg.project });
        return;
      }
```

Add these two methods to `ChatClient`:
```javascript
  approvePreview() {
    if (this._ws?.readyState === WebSocket.OPEN) {
      this._ws.send(JSON.stringify({ type: 'approve_send', session_id: this._sessionId }));
    }
  }

  cancelPreview() {
    if (this._ws?.readyState === WebSocket.OPEN) {
      this._ws.send(JSON.stringify({ type: 'cancel_send', session_id: this._sessionId }));
    }
  }
```

- [ ] **Step 5: Verify page loads with no console errors**

```bash
# http server should already be running on port 3000
curl -s http://localhost:3000/marcelo_ui.html | grep "preview-card"
```
Expected: line containing `preview-card`

- [ ] **Step 6: Commit**

```bash
git add Animacao_Marcelo/marcelo_ui.html Animacao_Marcelo/js/chat-client.js
git commit -m "feat(ui): add preview card with approve/cancel for Claude Code prompts"
```

---

## Task 8: Create workspace folder + rebuild + smoke test

**Files:** none (runtime setup + docker)

- [ ] **Step 1: Create Desktop workspace folder**

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\Desktop\marcelo"
```

- [ ] **Step 2: Rebuild Docker container**

```bash
cd D:/Projetos/Marcelo && docker compose up -d --build app
```
Expected: `marcelo-app-1 Started`

- [ ] **Step 3: Wait for startup**

```bash
sleep 5 && docker logs marcelo-app-1 --tail 5
```
Expected: `Application startup complete.`

- [ ] **Step 4: Smoke test filesystem tool via chat**

Open http://localhost:3000/marcelo_ui.html, type:

```
lista os arquivos do meu workspace
```

Expected: Marcelo lists files in `~/Desktop/marcelo/` (may be empty initially).

- [ ] **Step 5: Smoke test dev environment via chat**

Type in UI:
```
cria o projeto teste-jarvis
```

Expected:
- `~/Desktop/marcelo/teste-jarvis/` created
- PyCharm opens
- Windows Terminal opens with `claude` running titled `marcelo-claude-teste-jarvis`
- Marcelo responds: "Ambiente pronto!"

- [ ] **Step 6: Smoke test preview flow**

With project active, type:
```
quero uma API REST simples em FastAPI com um endpoint de saúde
```

Expected: preview card appears in UI with `## Task` formatted prompt and [✓ Enviar] [✗ Cancelar] buttons.

- [ ] **Step 7: Approve and verify SendKeys**

Click [✓ Enviar]. Expected: prompt is typed into the Windows Terminal claude session.

- [ ] **Step 8: Final commit**

```bash
git add .
git commit -m "feat(dev-tools): complete dev tools — filesystem, dev environment, claude bridge"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** ShellPort ✓ | WindowsShellAdapter ✓ | FilesystemToolkit (7 ops) ✓ | DeveloperToolkit ✓ | Preview flow ✓ | UI card ✓ | Wiring ✓ | Config ✓
- [x] **Path traversal protection:** Task 3, `_resolve()` validates all paths
- [x] **Error handling:** PyCharm missing → non-fatal; window not found → retry once; no active project → clear error message
- [x] **Type consistency:** `DeveloperToolkit.send_to_claude` used in both test and ws_chat; `ShellPort.send_to_window` signature consistent across port, adapter, and toolkit
- [x] **lru_cache singleton:** `get_developer_tool()` same instance in `get_agent()` and `ws_chat` — `active_project` state shared correctly
- [x] **No placeholders:** all code blocks complete

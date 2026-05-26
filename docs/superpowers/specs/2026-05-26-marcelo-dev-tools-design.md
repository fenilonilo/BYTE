# Marcelo Dev Tools — Design Spec
**Date:** 2026-05-26  
**Status:** Approved  

---

## Overview

Adicionar ao agente Marcelo duas capacidades:
1. **File System Tools** — CRUD de arquivos e pastas no workspace `~/Desktop/marcelo/`
2. **Developer Environment Tool** — comando "codar/criar" que abre PyCharm + Windows Terminal com `claude` e envia prompts reformatados via SendKeys após aprovação do usuário

---

## Arquitetura

Segue a arquitetura hexagonal existente. Nenhuma dependência nova entra no `domain/`.

```
app/
├── ports/
│   └── shell.py                          # ShellPort ABC
├── adapters/
│   ├── shell/
│   │   ├── __init__.py
│   │   └── windows_shell_adapter.py      # subprocess + PowerShell SendKeys
│   └── tools/
│       ├── __init__.py
│       ├── filesystem_tool.py            # Agno Toolkit — CRUD workspace
│       └── developer_tool.py            # Agno Toolkit — env + claude bridge
├── api/
│   ├── deps.py                           # wire tools no Agno agent
│   └── ws_chat.py                        # novo tipo de mensagem: preview + approve
└── config.py                             # workspace_path, pycharm_path
```

---

## Componente 1 — ShellPort

**Arquivo:** `app/ports/shell.py`

```python
class ShellPort(ABC):
    @abstractmethod
    def run(self, command: list[str], cwd: str | None = None) -> str: ...

    @abstractmethod
    def send_to_window(self, window_title: str, text: str) -> None: ...
```

**Adapter:** `app/adapters/shell/windows_shell_adapter.py`
- `run()` → `subprocess.run()` com timeout de 30s, captura stdout+stderr
- `send_to_window()` → PowerShell inline:
  ```powershell
  $wsh = New-Object -ComObject WScript.Shell
  $wsh.AppActivate('TITLE')
  Start-Sleep -Milliseconds 200
  $wsh.SendKeys('TEXT{ENTER}')
  ```

---

## Componente 2 — Filesystem Toolkit

**Arquivo:** `app/adapters/tools/filesystem_tool.py`

Workspace root: `~/Desktop/marcelo/` (resolvido em runtime via `pathlib.Path.home()`).  
**Todos os paths são validados** — path traversal (`../`) levanta `ValueError` antes de qualquer operação.

| Função Agno | Descrição |
|---|---|
| `list_files(path="")` | Lista arquivos e pastas (recursivo 1 nível) |
| `read_file(path)` | Retorna conteúdo UTF-8 do arquivo |
| `create_file(path, content)` | Cria arquivo (cria dirs intermediários) |
| `write_file(path, content)` | Sobrescreve arquivo existente |
| `delete_file(path)` | Remove arquivo |
| `create_folder(path)` | Cria pasta |
| `delete_folder(path)` | Remove pasta recursivamente |

Retorno: string JSON `{"ok": true}` ou `{"error": "mensagem"}` — Agno repassa ao LLM.

---

## Componente 3 — Developer Toolkit

**Arquivo:** `app/adapters/tools/developer_tool.py`

### `open_dev_environment(project_name: str) -> str`

1. Cria `~/Desktop/marcelo/<project_name>/` se não existir
2. Abre PyCharm: `pycharm.bat <path>` (path de `settings.pycharm_path`)
3. Abre Windows Terminal com claude:
   ```
   wt -d <path> --title "marcelo-claude-<project>" pwsh -NoExit -Command "claude"
   ```
4. Salva `active_project` e `claude_window_title` em memória do adapter
5. Retorna confirmação ao Marcelo

### `send_to_claude(prompt: str) -> str`

- Usa `ShellPort.send_to_window(claude_window_title, prompt)`
- Só executa se `active_project` estiver definido
- Retorna `{"ok": true}` ou erro

---

## Componente 4 — Preview Flow (UI + WS)

### WebSocket — novos tipos de mensagem

**Backend → Frontend:**
```json
{"type": "preview", "prompt": "## Task\n...", "project": "jarvis"}
```

**Frontend → Backend (aprovação):**
```json
{"type": "approve_send", "session_id": "ui-session"}
```

**Frontend → Backend (cancelar):**
```json
{"type": "cancel_send", "session_id": "ui-session"}
```

### UI — card de preview

Card especial no transcript (canto superior esquerdo, abaixo das msgs normais):

```
┌─────────────────────────────────────────┐
│ 📋 Prompt para Claude Code              │
│                                         │
│ ## Task                                 │
│ [texto reformatado pelo Marcelo]        │
│                                         │
│ ## Requisitos                           │
│ - item 1                                │
│ - item 2                                │
│                                         │
│ ## Contexto                             │
│ Projeto: jarvis                         │
│                                         │
│    [✓ Enviar]        [✗ Cancelar]       │
└─────────────────────────────────────────┘
```

Botões têm `pointer-events: auto` (transcript em geral é `none`).  
Aprovação: envia `approve_send` via WS → backend chama `send_to_claude()`.

---

## Componente 5 — Prompt Reformatter

Quando `active_project` está definido, Marcelo usa system prompt adicional por sessão:

```
Modo desenvolvimento ativo. Projeto: <project_name>.
Quando o usuário descrever uma tarefa de código, reformate em:

## Task
[descrição clara e objetiva]

## Requisitos
- [item específico e acionável]

## Contexto
Projeto: <project_name> | Workspace: ~/Desktop/marcelo/<project_name>/

## Constraints
[arquitetura, stack, estilo — se mencionados]

Responda APENAS com o prompt formatado, sem texto adicional.
Após reformatar, defina type="preview" no output.
```

---

## Configuração

**`app/config.py` — novos campos:**
```python
workspace_path: str = ""        # default: ~/Desktop/marcelo (resolved at runtime)
pycharm_path: str = r"C:\Users\fenil\AppData\Local\Programs\PyCharm 2025.2.0.1\bin\pycharm.bat"
```

---

## Wiring — `app/api/deps.py`

```python
@lru_cache
def get_shell() -> ShellPort:
    return WindowsShellAdapter()

@lru_cache  
def get_filesystem_tool() -> FilesystemToolkit:
    return FilesystemToolkit()

@lru_cache
def get_developer_tool() -> DeveloperToolkit:
    return DeveloperToolkit(shell=get_shell(), settings=get_settings())
```

Agno agent recebe `tools=[get_filesystem_tool(), get_developer_tool()]`.

---

## Fluxo End-to-End

```
User: "cria o projeto jarvis"
  ↓
Marcelo detecta intenção → chama open_dev_environment("jarvis")
  ↓
~/Desktop/marcelo/jarvis/ criada
PyCharm abre na pasta
Windows Terminal abre: claude roda em ~/Desktop/marcelo/jarvis/
active_project = "jarvis", claude_window_title = "marcelo-claude-jarvis"
  ↓
Marcelo: "Ambiente pronto! Pode descrever o que quer desenvolver."

User: "quero uma API de autenticação JWT em FastAPI"
  ↓
Marcelo reformata → WS envia {type:"preview", prompt:"## Task\n..."}
  ↓
UI mostra card com [✓ Enviar] [✗ Cancelar]
  ↓
User aprova → {type:"approve_send"}
  ↓
Backend: PowerShell SendKeys → prompt digitado no terminal claude
Claude processa e responde na janela do terminal
```

---

## Tratamento de Erros

| Cenário | Comportamento |
|---|---|
| PyCharm não encontrado | Erro claro: "PyCharm não encontrado em `<path>`. Verifique `pycharm_path` no .env" |
| Window title não encontrado no SendKeys | Retry 1x após 500ms, depois erro ao usuário |
| Path traversal detectado | ValueError imediato, não executa |
| `active_project` não definido e user pede send | Marcelo instrui: "Primeiro diga 'cria o projeto X'" |
| Pasta já existe | Abre ambiente normalmente sem recriar |

---

## O que não entra neste ciclo

- Leitura de output do claude de volta pro Marcelo (claude responde no terminal, Marcelo não lê)
- Múltiplos projetos abertos simultaneamente (um `active_project` por vez)
- Suporte a outros IDEs além do PyCharm
- Suporte a macOS/Linux (SendKeys é Windows-only)

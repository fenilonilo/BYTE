from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

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

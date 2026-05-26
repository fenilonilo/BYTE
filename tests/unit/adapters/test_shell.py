from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.adapters.shell.windows_shell_adapter import WindowsShellAdapter


def test_run_returns_stdout() -> None:
    adapter = WindowsShellAdapter()
    result = adapter.run(["echo", "hello"])
    assert "hello" in result


def test_run_with_cwd(tmp_path) -> None:
    adapter = WindowsShellAdapter()
    result = adapter.run(["pwd"], cwd=str(tmp_path))
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
        adapter.send_to_window("my-title", "hello")
        assert mock_run.call_count == 2

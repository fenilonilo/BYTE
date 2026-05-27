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

        if self._pycharm_path:
            try:
                self._shell.run(
                    ["powershell", "-NoProfile", "-Command",
                     f"Start-Process '{self._pycharm_path}' -ArgumentList '{path_str}'"],
                )
            except Exception:
                pass

        self._shell.run(
            ["powershell", "-NoProfile", "-Command",
             f"Start-Process 'wt' -ArgumentList @('-d', '\"{path_str}\"', '--title', '\"{window_title}\"', 'powershell', '-NoExit', '-Command', 'claude')"],
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

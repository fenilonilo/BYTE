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

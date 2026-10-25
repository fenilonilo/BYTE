from __future__ import annotations

import asyncio
import hmac
import json
import secrets
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

    from app.ports.logger import LoggerPort

TOKEN_ENV = "BYTE_BRIDGE_TOKEN"  # noqa: S105 - the variable's name, not a secret
QUESTION_TOOL = "AskUserQuestion"
PERMISSION_TIMEOUT = 120  # long enough for the pilot to answer one of Claude's questions
HOOK_TIMEOUT = 5


def _decision(behavior: str, **extra: str) -> dict[str, object]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {"behavior": behavior, **extra},
        }
    }


class ClaudeBridge:
    """Claude Code's hooks for the one `claude` the server runs, turned into turn ends and
    permission answers. With a pilot (Lynus at work) every request is allowed: owner's rule."""

    def __init__(self, hook_url: str, log: LoggerPort) -> None:
        self._url = hook_url
        self._log = log
        self._token: str | None = None
        self._turns: asyncio.Queue[str | None] = asyncio.Queue()
        self.pilot: Callable[[str], Awaitable[str]] | None = None

    def begin(self) -> str:
        """A new session: a fresh token, and nothing left over from the old one."""
        self._token = secrets.token_urlsafe(32)
        self.clear()
        return self._token

    def end(self) -> None:
        self._token = None
        self._turns.put_nowait(None)  # whoever waits on a turn: the session is gone

    def authorized(self, token: str) -> bool:
        current = self._token
        return current is not None and hmac.compare_digest(token.encode(), current.encode())

    def clear(self) -> None:
        while not self._turns.empty():
            self._turns.get_nowait()

    async def next_turn(self, within: float) -> str | None:
        """Claude's final message of the next turn; None on timeout or when the session ended."""
        try:
            return await asyncio.wait_for(self._turns.get(), within)
        except TimeoutError:
            return None

    async def hook(self, event: Mapping[str, object]) -> dict[str, object]:
        name = event.get("hook_event_name")
        if name == "Stop":
            text = event.get("last_assistant_message")
            self._turns.put_nowait(text if isinstance(text, str) else "")
            self._log.info("claude.turn_done")
            return {}
        pilot = self.pilot
        if name != "PermissionRequest" or pilot is None:
            return {}
        tool = str(event.get("tool_name", ""))
        if tool == QUESTION_TOOL:
            answer = await pilot(json.dumps(event.get("tool_input", {}), ensure_ascii=False))
            return _decision("deny", message=f"Resposta do dono (via Lynus): {answer}")
        self._log.info("claude.allowed", tool_name=tool)
        return _decision("allow")

    def settings(self) -> dict[str, object]:
        """The `--settings` JSON that points the session's hooks at this server."""

        def http(timeout: int) -> dict[str, object]:
            return {
                "type": "http",
                "url": self._url,
                "timeout": timeout,
                "headers": {"Authorization": f"Bearer ${TOKEN_ENV}"},
                "allowedEnvVars": [TOKEN_ENV],
            }

        return {
            "hooks": {
                "PermissionRequest": [{"matcher": "*", "hooks": [http(PERMISSION_TIMEOUT)]}],
                "Stop": [{"hooks": [http(HOOK_TIMEOUT)]}],
            }
        }

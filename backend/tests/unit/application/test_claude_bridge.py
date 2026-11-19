from __future__ import annotations

import asyncio
import json

import pytest

from app.application.claude_bridge import ClaudeBridge
from tests.fakes.logger import RecordingLogger

URL = "http://127.0.0.1:8000/api/v1/claude/hooks"


def make() -> tuple[ClaudeBridge, RecordingLogger]:
    log = RecordingLogger()
    return ClaudeBridge(URL, log), log


def permission(tool: str, tool_input: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "hook_event_name": "PermissionRequest",
        "tool_name": tool,
        "tool_input": tool_input or {},
    }


def stop(text: str) -> dict[str, object]:
    return {"hook_event_name": "Stop", "last_assistant_message": text}


async def answer(question: str) -> str:
    return f"azul ({json.loads(question)['questions'][0]['question']})"


@pytest.mark.unit
def test_token_is_fresh_per_session_and_revoked_on_end() -> None:
    bridge, _ = make()
    first = bridge.begin()
    second = bridge.begin()
    assert len(second) >= 32
    assert first != second
    assert not bridge.authorized(first)
    assert bridge.authorized(second)
    bridge.end()
    assert not bridge.authorized(second)


@pytest.mark.unit
def test_nothing_is_authorized_without_a_session() -> None:
    bridge, _ = make()
    assert not bridge.authorized("")
    assert not bridge.authorized("anything")


@pytest.mark.unit
async def test_permission_without_pilot_leaves_the_dialog_to_the_owner() -> None:
    bridge, _ = make()
    assert await bridge.hook(permission("Bash")) == {}


@pytest.mark.unit
async def test_pilot_allows_anything_at_once() -> None:
    bridge, log = make()
    bridge.pilot = answer
    reply = await bridge.hook(permission("Bash", {"command": "rm -rf build"}))
    assert reply == {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {"behavior": "allow"},
        }
    }
    assert ("info", "claude.allowed", {"tool_name": "Bash"}) in log.events
    assert "rm -rf" not in repr(log.events)


@pytest.mark.unit
async def test_pilot_answers_claude_questions_through_the_denial() -> None:
    bridge, _ = make()
    bridge.pilot = answer
    question: dict[str, object] = {
        "questions": [{"question": "Cor?", "options": [{"label": "azul"}]}]
    }
    reply = await bridge.hook(permission("AskUserQuestion", question))
    assert reply == {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {
                "behavior": "deny",
                "message": "Resposta do dono (via Lynus): azul (Cor?)",
            },
        }
    }


@pytest.mark.unit
async def test_stop_hands_the_last_message_to_the_next_turn() -> None:
    bridge, _ = make()
    bridge.begin()
    assert await bridge.hook(stop("DONE")) == {}
    assert await bridge.next_turn(1.0) == "DONE"


@pytest.mark.unit
async def test_next_turn_times_out_with_none() -> None:
    bridge, _ = make()
    bridge.begin()
    assert await bridge.next_turn(0.01) is None


@pytest.mark.unit
async def test_end_wakes_a_waiting_turn_with_none() -> None:
    bridge, _ = make()
    bridge.begin()
    waiting = asyncio.create_task(bridge.next_turn(5.0))
    await asyncio.sleep(0)
    bridge.end()
    assert await waiting is None


@pytest.mark.unit
async def test_clear_drops_stale_turn_ends() -> None:
    bridge, _ = make()
    bridge.begin()
    await bridge.hook(stop("old"))
    bridge.clear()
    await bridge.hook(stop("new"))
    assert await bridge.next_turn(1.0) == "new"


@pytest.mark.unit
async def test_other_events_are_ignored() -> None:
    bridge, _ = make()
    assert await bridge.hook({"hook_event_name": "Notification"}) == {}
    assert await bridge.hook({}) == {}


@pytest.mark.unit
def test_settings_point_every_hook_at_byte_with_the_session_token() -> None:
    bridge, _ = make()

    def http(timeout: int) -> dict[str, object]:
        return {
            "type": "http",
            "url": URL,
            "timeout": timeout,
            "headers": {"Authorization": "Bearer $BYTE_BRIDGE_TOKEN"},
            "allowedEnvVars": ["BYTE_BRIDGE_TOKEN"],
        }

    assert bridge.settings() == {
        "hooks": {
            "PermissionRequest": [{"matcher": "*", "hooks": [http(120)]}],
            "Stop": [{"hooks": [http(5)]}],
        }
    }

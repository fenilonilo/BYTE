from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import deps
from app.api.lynus import router
from app.application.claude_bridge import ClaudeBridge
from app.application.lynus import Lynus, LynusLimits
from app.application.project_session import ProjectSession
from app.domain.model import ModelTurn
from app.domain.projects import Project
from tests.fakes.chat_model import ScriptedChatModel
from tests.fakes.clock import wall
from tests.fakes.logger import RecordingLogger
from tests.fakes.terminal import FakeTerminal
from tests.fakes.world import TOKEN, make_settings
from tests.unit.application.test_lynus import Docs

if TYPE_CHECKING:
    from collections.abc import Callable

pytestmark = pytest.mark.unit

P = "/api/v1"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
PROJECT = Project("Byte", "D:/P/Byte", ("CLAUDE.md",))


def _provide(value: object) -> Callable[[], object]:
    return lambda: value


class Env:
    def __init__(self, *, with_lynus: bool = True) -> None:
        log = RecordingLogger()
        self.bridge = ClaudeBridge("http://x/hooks", log)
        self.session = ProjectSession(
            FakeTerminal(), [PROJECT], ["claude"], {}, log, bridge=(self.bridge, "h.json")
        )
        self.lynus = Lynus(
            ScriptedChatModel([ModelTurn(text="Qual o escopo?"), ModelTurn(text="Ok.")]),
            self.session,
            self.bridge,
            Docs(),
            [PROJECT],
            log=log,
            clock=wall,
            limits=LynusLimits(paste_delay=0),
        )
        app = FastAPI()
        app.include_router(router, prefix=P)
        overrides: dict[Callable[..., object], object] = {
            deps.get_settings: make_settings(),
            deps.get_claude_bridge: self.bridge,
            deps.get_lynus: self.lynus if with_lynus else None,
        }
        for dep, value in overrides.items():
            app.dependency_overrides[dep] = _provide(value)
        self.client = TestClient(app)


def hook(env: Env, token: str, event: dict[str, object]) -> int:
    res = env.client.post(
        P + "/claude/hooks", json=event, headers={"Authorization": f"Bearer {token}"}
    )
    return res.status_code


def test_hook_accepts_only_the_session_token() -> None:
    env = Env()
    event: dict[str, object] = {"hook_event_name": "Stop", "last_assistant_message": "ok", "x": 1}
    assert hook(env, "nope", event) == 401
    token = env.bridge.begin()
    assert hook(env, TOKEN, event) == 401  # the owner token is no good here
    assert hook(env, token, event) == 200
    assert env.client.post(P + "/claude/hooks", json=event).status_code == 401


def test_hook_returns_the_bridge_decision() -> None:
    env = Env()
    token = env.bridge.begin()

    async def pilot(_: str) -> str:
        return "a"

    env.bridge.pilot = pilot
    res = env.client.post(
        P + "/claude/hooks",
        json={"hook_event_name": "PermissionRequest", "tool_name": "Bash", "tool_input": {}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.json()["hookSpecificOutput"]["decision"] == {"behavior": "allow"}


def test_lynus_routes_need_the_owner_token() -> None:
    env = Env()
    assert env.client.get(P + "/lynus").status_code == 401
    assert env.client.post(P + "/lynus/stop").status_code == 401


def test_view_message_and_stop() -> None:
    env = Env()
    body = env.client.get(P + "/lynus", headers=AUTH).json()
    assert body == {"phase": "off", "project": None, "task": "", "turns": 0, "notes": []}
    res = env.client.post(P + "/lynus/messages", json={"content": "oi"}, headers=AUTH)
    assert res.status_code == 409

    async def started() -> None:
        await env.lynus.start("Byte", "logs")
        for _ in range(50):
            await asyncio.sleep(0)

    with env.client as client:  # the app's loop: Lynus's tasks must live on it
        client.portal.call(started)  # pyright: ignore[reportOptionalMemberAccess]
        view = client.get(P + "/lynus", headers=AUTH).json()
        assert view["phase"] == "briefing"
        assert [n["role"] for n in view["notes"]] == ["system", "owner", "lynus"]
        res = client.post(P + "/lynus/messages", json={"content": "só backend"}, headers=AUTH)
        assert res.status_code == 202
        assert client.post(P + "/lynus/stop", headers=AUTH).json() == {"phase": "stopped"}
        client.portal.call(env.lynus.aclose)  # pyright: ignore[reportOptionalMemberAccess]
        client.portal.call(env.session.aclose)  # pyright: ignore[reportOptionalMemberAccess]


def test_message_content_is_bounded() -> None:
    env = Env()
    res = env.client.post(P + "/lynus/messages", json={"content": ""}, headers=AUTH)
    assert res.status_code == 422


def test_without_lynus_routes_answer_503() -> None:
    env = Env(with_lynus=False)
    assert env.client.get(P + "/lynus", headers=AUTH).status_code == 503

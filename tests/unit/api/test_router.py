from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_agents, get_repo, get_settings
from app.api.router import router
from app.application.registry import Registry
from app.domain.exceptions import AgentError
from app.ports.agent import AgentPort

if TYPE_CHECKING:
    from app.domain.entities import Conversation


class FailingAgent(AgentPort):
    async def run(self, message: str, conversation: Conversation) -> str:
        raise AgentError("upstream is down")


class FakeAgent(AgentPort):
    def __init__(self, segment: str) -> None:
        self._segment = segment

    async def run(self, message: str, conversation: Conversation) -> str:
        return f"[{self._segment}] {message} ({len(conversation.messages)} msgs)"


@pytest.fixture
def client() -> TestClient:
    get_settings.cache_clear()
    get_agents.cache_clear()
    get_repo.cache_clear()
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    agents: Registry[AgentPort] = Registry()
    for segment in ("home", "agenda", "finance", "auto"):
        agents.register(segment, FakeAgent(segment))
    agents.register("broken", FailingAgent())
    app.dependency_overrides[get_agents] = lambda: agents

    return TestClient(app)


@pytest.mark.unit
def test_health(client: TestClient) -> None:
    assert client.get("/api/v1/health").json() == {"status": "ok"}


@pytest.mark.unit
def test_known_segment_returns_reply(client: TestClient) -> None:
    res = client.post("/api/v1/messages", json={"content": "oi", "segment": "home"})
    assert res.status_code == 200
    body = res.json()
    assert body["role"] == "assistant"
    assert "home" in body["content"]
    assert body["conversation_id"]


@pytest.mark.unit
def test_omitted_segment_routes_to_auto(client: TestClient) -> None:
    res = client.post("/api/v1/messages", json={"content": "apaga a luz"})
    assert res.status_code == 200
    assert "[auto]" in res.json()["content"]


@pytest.mark.unit
def test_unknown_segment_returns_404(client: TestClient) -> None:
    res = client.post("/api/v1/messages", json={"content": "oi", "segment": "nope"})
    assert res.status_code == 404


@pytest.mark.unit
def test_conversation_id_is_echoed_back(client: TestClient) -> None:
    res = client.post(
        "/api/v1/messages",
        json={"content": "oi", "segment": "home", "conversation_id": "conv-1"},
    )
    assert res.json()["conversation_id"] == "conv-1"


@pytest.mark.unit
def test_agent_failure_returns_502(client: TestClient) -> None:
    res = client.post("/api/v1/messages", json={"content": "oi", "segment": "broken"})
    assert res.status_code == 502

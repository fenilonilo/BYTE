from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_process_chat, get_runner, get_settings
from app.api.errors import install_error_handlers
from app.api.router import router
from app.domain.exceptions import AgentError, UnknownLightDeviceError
from tests.fakes.world import TOKEN, World, make_settings, text_turn, tool_turn

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.domain.model import ModelTurn

AUTH = {"Authorization": f"Bearer {TOKEN}"}
URL = "/api/v1/messages"


class ExplodingChat:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def execute(
        self, conversation_id: str, text: str, segment: str | None, *, panel: bool = False
    ) -> object:
        raise self._error


class PanelRecorder:
    def __init__(self, chat: object) -> None:
        self.chat = chat
        self.panel: list[bool] = []

    async def execute(
        self, conversation_id: str, text: str, segment: str | None, *, panel: bool = False
    ) -> object:
        self.panel.append(panel)
        return await self.chat.execute(conversation_id, text, segment)  # type: ignore[attr-defined]


def make_client(turns: Sequence[ModelTurn] = ()) -> tuple[TestClient, World]:
    world = World(turns)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    install_error_handlers(app)
    app.dependency_overrides[get_settings] = make_settings
    app.dependency_overrides[get_process_chat] = lambda: world.chat
    app.dependency_overrides[get_runner] = lambda: world.runner
    return TestClient(app), world


@pytest.mark.unit
def test_health_needs_no_token() -> None:
    client, _ = make_client()
    assert client.get("/api/v1/health").json() == {"status": "ok"}


@pytest.mark.unit
@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer wrong"}, {"Authorization": TOKEN}, {"Authorization": "Basic x"}],
)
def test_messages_require_the_bearer_token(headers: dict[str, str]) -> None:
    client, world = make_client([text_turn("não deveria rodar")])
    res = client.post(URL, json={"content": "oi"}, headers=headers)
    assert res.status_code == 401
    assert world.model.calls == []


@pytest.mark.unit
def test_reply_shape_and_generated_conversation_id() -> None:
    client, _ = make_client([text_turn("Oi!")])
    res = client.post(URL, json={"content": "olá"}, headers=AUTH)
    assert res.status_code == 200
    body = res.json()
    assert body["role"] == "assistant"
    assert body["content"] == "Oi!"
    assert body["conversation_id"]
    assert body["pending_confirmation"] is None


@pytest.mark.unit
def test_the_same_conversation_id_continues_the_history() -> None:
    client, world = make_client([text_turn("um"), text_turn("dois")])
    body = {"content": "oi", "conversation_id": "conv-1"}
    first = client.post(URL, json=body, headers=AUTH).json()
    client.post(URL, json=body, headers=AUTH)
    assert first["conversation_id"] == "conv-1"
    second_call_messages, _ = world.model.calls[1]
    assert [m.role for m in second_call_messages] == ["system", "user", "assistant", "user"]


@pytest.mark.unit
@pytest.mark.parametrize("segment", ["home", "HOME", "auto", " Agenda "])
def test_known_segments_and_auto_are_accepted(segment: str) -> None:
    client, _ = make_client([text_turn("ok")])
    res = client.post(URL, json={"content": "oi", "segment": segment}, headers=AUTH)
    assert res.status_code == 200


@pytest.mark.unit
def test_unknown_segment_is_404_and_never_falls_back() -> None:
    client, world = make_client([text_turn("não deveria rodar")])
    res = client.post(URL, json={"content": "oi", "segment": "nope"}, headers=AUTH)
    assert res.status_code == 404
    assert world.model.calls == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"content": ""},
        {"content": "    "},
        {"content": "x" * 4001},
        {"content": "oi", "conversation_id": "../etc/passwd"},
        {"content": "oi", "conversation_id": "a" * 65},
    ],
)
def test_invalid_payloads_are_422(payload: dict[str, str]) -> None:
    client, world = make_client([text_turn("não deveria rodar")])
    res = client.post(URL, json=payload, headers=AUTH)
    assert res.status_code == 422
    assert world.model.calls == []


@pytest.mark.unit
def test_content_at_the_limit_is_accepted() -> None:
    client, _ = make_client([text_turn("ok")])
    res = client.post(URL, json={"content": "x" * 4000}, headers=AUTH)
    assert res.status_code == 200


@pytest.mark.unit
def test_pending_confirmation_summary_is_returned_verbatim() -> None:
    client, _ = make_client(
        [
            tool_turn("delete_event", '{"event_id": "evt-1"}'),
            text_turn("Quer que eu desligue?"),
        ]
    )
    res = client.post(URL, json={"content": "apaga o dentista"}, headers=AUTH)
    assert res.json()["pending_confirmation"] == {"summary": "Apagar o evento evt-1"}


@pytest.mark.unit
def test_agent_error_is_502_without_leaking_the_cause() -> None:
    client, _ = make_client()
    exploding = ExplodingChat(AgentError("secret upstream detail"))
    client.app.dependency_overrides[get_process_chat] = lambda: exploding  # type: ignore[attr-defined]
    res = client.post(URL, json={"content": "oi"}, headers=AUTH)
    assert res.status_code == 502
    assert res.json() == {"detail": "Agent failed to produce a reply"}


@pytest.mark.unit
def test_other_domain_errors_are_a_generic_500() -> None:
    client, _ = make_client()
    exploding = ExplodingChat(UnknownLightDeviceError("cofre"))
    client.app.dependency_overrides[get_process_chat] = lambda: exploding  # type: ignore[attr-defined]
    res = client.post(URL, json={"content": "oi"}, headers=AUTH)
    assert res.status_code == 500
    assert res.json() == {"detail": "Internal error"}


@pytest.mark.unit
@pytest.mark.parametrize(("client_field", "panel"), [({"client": "panel"}, True), ({}, False)])
def test_client_panel_reaches_use_case(client_field: dict[str, str], panel: bool) -> None:
    client, world = make_client([text_turn("ok")])
    recorder = PanelRecorder(world.chat)
    client.app.dependency_overrides[get_process_chat] = lambda: recorder  # type: ignore[attr-defined]
    res = client.post(URL, json={"content": "oi", **client_field}, headers=AUTH)
    assert res.status_code == 200
    assert recorder.panel == [panel]


@pytest.mark.unit
def test_unknown_client_is_422() -> None:
    client, _ = make_client()
    res = client.post(URL, json={"content": "oi", "client": "esp32"}, headers=AUTH)
    assert res.status_code == 422

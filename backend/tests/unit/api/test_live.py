from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.deps import get_live_slot, get_run_live_session, get_runner, get_settings
from app.api.live import router as live_router
from app.api.live_slot import LiveSlot
from app.application.tool import Tool
from app.application.tools.args import object_schema
from app.domain.exceptions import LiveSessionError
from app.domain.live import (
    AssistantAudio,
    AssistantTranscript,
    ResponseDone,
    UserSpeechStarted,
)
from app.domain.tools import ToolSpec
from tests.fakes.live import LiveWorld
from tests.fakes.world import TOKEN, make_settings

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from fastapi import WebSocket
    from starlette.testclient import WebSocketTestSession

URL = "/api/v1/live"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class TrackingSlot(LiveSlot):
    """Counts released connections, so a test can wait for the server side to finish cleaning
    up (the Starlette test client cancels the app right after the client disconnects)."""

    def __init__(self) -> None:
        super().__init__()
        self.releases = 0

    def release(self, websocket: WebSocket) -> None:
        super().release(websocket)
        self.releases += 1


def make_client(world: LiveWorld) -> tuple[TestClient, TrackingSlot]:
    app = FastAPI()
    app.include_router(live_router, prefix="/api/v1")
    slot = TrackingSlot()
    app.dependency_overrides[get_settings] = make_settings
    app.dependency_overrides[get_runner] = lambda: world.runner
    app.dependency_overrides[get_run_live_session] = lambda: world.run
    app.dependency_overrides[get_live_slot] = lambda: slot
    return TestClient(app), slot


def until(predicate: Callable[[], bool], within: float = 2.0) -> None:
    deadline = time.monotonic() + within
    while not predicate():
        assert time.monotonic() < deadline, "condition not reached in time"
        time.sleep(0.01)


def leave(ws: WebSocketTestSession, slot: TrackingSlot, releases: int = 1) -> None:
    """Disconnect and wait until the server finished cleaning up this connection."""
    ws.close()
    until(lambda: slot.releases >= releases)


def receive_event(ws: WebSocketTestSession, event_type: str) -> dict[str, object]:
    """Skip audio frames and other events until the wanted JSON event shows up."""
    for _ in range(20):
        message = ws.receive()
        text = message.get("text")
        if text is not None:
            event: dict[str, object] = json.loads(text)
            if event.get("type") == event_type:
                return event
    raise AssertionError(f"no {event_type!r} event received")


def start(ws: WebSocketTestSession, **extra: object) -> dict[str, object]:
    ws.send_json({"type": "start", **extra})
    return receive_event(ws, "ready")


@pytest.mark.unit
@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Bearer nope"}, {"Authorization": TOKEN}]
)
def test_the_socket_requires_the_bearer_token(headers: dict[str, str]) -> None:
    client, _ = make_client(LiveWorld())
    with pytest.raises(WebSocketDisconnect) as info, client.websocket_connect(URL, headers=headers):
        pass
    assert info.value.code == 1008


@pytest.mark.unit
def test_a_browser_authenticates_through_the_subprotocol_and_gets_only_bearer_back() -> None:
    client, slot = make_client(LiveWorld())
    with client.websocket_connect(URL, subprotocols=["bearer", TOKEN]) as ws:
        start(ws)
        accepted = ws.accepted_subprotocol
        leave(ws, slot)
    assert accepted == "bearer"


@pytest.mark.unit
@pytest.mark.parametrize(
    "subprotocols",
    [["bearer", "nope"], ["bearer"], [TOKEN], [TOKEN, "bearer"], ["bearer", TOKEN, "x"]],
)
def test_a_bad_subprotocol_token_closes_the_socket(subprotocols: list[str]) -> None:
    client, _ = make_client(LiveWorld())
    with (
        pytest.raises(WebSocketDisconnect) as info,
        client.websocket_connect(URL, subprotocols=subprotocols),
    ):
        pass
    assert info.value.code == 1008


@pytest.mark.unit
def test_the_header_path_accepts_without_a_subprotocol() -> None:
    client, slot = make_client(LiveWorld())
    with client.websocket_connect(URL, headers=AUTH) as ws:
        start(ws)
        accepted = ws.accepted_subprotocol
        leave(ws, slot)
    assert accepted is None


@pytest.mark.unit
def test_start_then_ready_with_the_audio_contract() -> None:
    world = LiveWorld()
    client, slot = make_client(world)
    with client.websocket_connect(URL, headers=AUTH) as ws:
        ready = start(ws, segment="HOME", conversation_id="conv-1")
        leave(ws, slot)
    assert ready["conversation_id"] == "conv-1"
    assert ready["audio"] == {"format": "pcm16", "rate": 24000, "channels": 1}
    assert world.adapter.opened_with is not None
    assert {t.segment for t in world.adapter.opened_with[1]} == {"home", "*"}


@pytest.mark.unit
def test_audio_and_events_flow_through_the_socket() -> None:
    world = LiveWorld()
    client, slot = make_client(world)
    with client.websocket_connect(URL, headers=AUTH) as ws:
        start(ws)
        ws.send_bytes(b"\x01\x02")
        until(lambda: world.session.audio_in == [b"\x01\x02"])

        world.session.push(
            AssistantAudio(data=b"\x09\x08", item_id="a1"),
            AssistantTranscript("Pronto."),
            ResponseDone(),
        )
        assert ws.receive_bytes() == b"\x09\x08"
        transcript = receive_event(ws, "transcript")
        assert (transcript["role"], transcript["text"]) == ("assistant", "Pronto.")
        receive_event(ws, "turn_done")
        leave(ws, slot)


@pytest.mark.unit
def test_barge_in_interrupts_the_client_which_reports_what_it_played() -> None:
    world = LiveWorld()
    client, slot = make_client(world)
    with client.websocket_connect(URL, headers=AUTH) as ws:
        start(ws)
        world.session.push(AssistantAudio(data=b"\x01", item_id="a1"), UserSpeechStarted("u1"))
        receive_event(ws, "interrupt")
        ws.send_json({"type": "played", "audio_end_ms": 500})
        until(lambda: world.session.truncations == [("a1", 500)])
        leave(ws, slot)


@pytest.mark.unit
def test_a_bad_first_frame_is_rejected() -> None:
    client, _ = make_client(LiveWorld())
    with client.websocket_connect(URL, headers=AUTH) as ws:
        ws.send_json({"type": "hello"})
        assert ws.receive_json() == {"type": "error", "code": "bad_start"}
        with pytest.raises(WebSocketDisconnect) as info:
            ws.receive_json()
    assert info.value.code == 1008


@pytest.mark.unit
def test_an_unknown_segment_is_rejected_never_defaulted() -> None:
    world = LiveWorld()
    client, _ = make_client(world)
    with client.websocket_connect(URL, headers=AUTH) as ws:
        ws.send_json({"type": "start", "segment": "nope"})
        assert ws.receive_json() == {"type": "error", "code": "bad_segment"}
    assert world.adapter.opened_with is None


@pytest.mark.unit
def test_a_new_connection_replaces_the_old_one_with_close_code_4000() -> None:
    client, slot = make_client(LiveWorld())
    with client.websocket_connect(URL, headers=AUTH) as first:
        start(first)
        with client.websocket_connect(URL, headers=AUTH) as second:
            start(second)
            with pytest.raises(WebSocketDisconnect) as info:
                first.receive_json()
            leave(second, slot)
        leave(first, slot, releases=2)  # the test client only disconnects `first` when told to
    assert info.value.code == 4000


@pytest.mark.unit
def test_an_oversized_audio_frame_closes_the_socket() -> None:
    client, slot = make_client(LiveWorld())
    with client.websocket_connect(URL, headers=AUTH) as ws:
        start(ws)
        ws.send_bytes(b"x" * 70_000)
        with pytest.raises(WebSocketDisconnect) as info:
            ws.receive_json()
        until(lambda: slot.releases >= 1)
    assert info.value.code == 1009


@pytest.mark.unit
def test_provider_unavailable_is_reported_before_closing() -> None:
    world = LiveWorld(open_error=LiveSessionError("down"))
    client, slot = make_client(world)
    with client.websocket_connect(URL, headers=AUTH) as ws:
        ws.send_json({"type": "start"})
        assert ws.receive_json() == {"type": "error", "code": "model_unavailable"}
        until(lambda: slot.releases >= 1)


@pytest.mark.unit
def test_garbage_frames_are_ignored_and_the_session_survives() -> None:
    world = LiveWorld()
    client, slot = make_client(world)
    with client.websocket_connect(URL, headers=AUTH) as ws:
        start(ws)
        ws.send_text("{not json")
        ws.send_text("[1, 2]")
        ws.send_bytes(b"\x07")
        until(lambda: world.session.audio_in == [b"\x07"])
        leave(ws, slot)


@pytest.mark.unit
def test_closing_an_already_gone_client_still_releases_the_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def gone(self: object, code: int = 1000, reason: str | None = None) -> None:
        raise WebSocketDisconnect(code=1006)  # what Starlette raises when the peer vanished

    client, slot = make_client(LiveWorld())
    with client.websocket_connect(URL, headers=AUTH) as ws:
        start(ws)
        monkeypatch.setattr("starlette.websockets.WebSocket.close", gone)
        leave(ws, slot)


class PanelOnly(Tool):
    spec = ToolSpec("open_project", "d", object_schema({}), "projects", panel_only=True)

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        return "ok"


@pytest.mark.unit
@pytest.mark.parametrize(("extra", "offered"), [({"client": "panel"}, True), ({}, False)])
def test_start_client_decides_panel_only_tools(extra: dict[str, str], offered: bool) -> None:
    world = LiveWorld(extra_tools=[PanelOnly()])
    client, slot = make_client(world)
    with client.websocket_connect(URL, headers=AUTH) as ws:
        start(ws, **extra)
        leave(ws, slot)
    assert world.adapter.opened_with is not None
    assert ("open_project" in {t.name for t in world.adapter.opened_with[1]}) is offered


@pytest.mark.unit
def test_start_unknown_client_rejected() -> None:
    client, _ = make_client(LiveWorld())
    with client.websocket_connect(URL, headers=AUTH) as ws:
        ws.send_json({"type": "start", "client": "esp32"})
        assert ws.receive_json() == {"type": "error", "code": "bad_start"}

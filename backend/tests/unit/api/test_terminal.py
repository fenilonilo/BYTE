from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.deps import get_project_session, get_settings, get_terminal_slot
from app.api.live_slot import LiveSlot
from app.api.terminal import router
from app.application.project_session import ProjectSession
from app.domain.projects import Project
from tests.fakes.logger import RecordingLogger
from tests.fakes.terminal import FakeTerminal
from tests.fakes.world import TOKEN, make_settings

if TYPE_CHECKING:
    from collections.abc import Iterator

    from starlette.testclient import WebSocketTestSession

URL = "/api/v1/ws/terminal"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class Setup:
    def __init__(self, available: bool = True) -> None:
        self.terminal = FakeTerminal()
        self.session = ProjectSession(
            self.terminal,
            [Project("Byte", "D:/P/Byte", ("CLAUDE.md",))],
            ["claude"],
            {},
            RecordingLogger(),
        )
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        slot = LiveSlot()
        app.dependency_overrides[get_settings] = make_settings
        app.dependency_overrides[get_project_session] = lambda: self.session if available else None
        app.dependency_overrides[get_terminal_slot] = lambda: slot
        self.client = TestClient(app)

    def call(self, fn: object, *args: object) -> object:
        return self.client.portal.call(fn, *args)  # type: ignore[arg-type, union-attr]

    def open(self, name: str = "Byte") -> None:
        self.call(self.session.open, name)


@pytest.fixture
def setup() -> Iterator[Setup]:
    s = Setup()
    with s.client:  # one portal (event loop) shared by the test and the app
        yield s


def connect(s: Setup) -> WebSocketTestSession:
    return s.client.websocket_connect(URL, headers=AUTH)


@pytest.mark.unit
def test_terminal_requires_token(setup: Setup) -> None:
    with pytest.raises(WebSocketDisconnect), setup.client.websocket_connect(URL) as ws:
        ws.receive_json()


@pytest.mark.unit
def test_terminal_sends_state_on_connect(setup: Setup) -> None:
    with connect(setup) as ws:
        assert ws.receive_json() == {"type": "state", "project": None}


@pytest.mark.unit
def test_terminal_replays_scrollback(setup: Setup) -> None:
    setup.open()
    setup.call(setup.terminal.feed, b"hello")
    with connect(setup) as ws:
        assert ws.receive_json() == {"type": "state", "project": "Byte"}
        assert ws.receive_bytes() == b"hello"


@pytest.mark.unit
def test_terminal_streams_open_and_output(setup: Setup) -> None:
    with connect(setup) as ws:
        ws.receive_json()
        setup.open()
        assert ws.receive_json() == {"type": "state", "project": "Byte"}
        setup.call(setup.terminal.feed, b"out")
        assert ws.receive_bytes() == b"out"


@pytest.mark.unit
def test_terminal_binary_is_written(setup: Setup) -> None:
    setup.open()
    with connect(setup) as ws:
        ws.receive_json()
        ws.send_bytes(b"ls\r")
        ws.send_json({"type": "ping"})  # anything after it proves the bytes were handled
        ws.send_bytes(b"")
    assert setup.terminal.written[0] == b"ls\r"


@pytest.mark.unit
@pytest.mark.parametrize(("cols", "rows", "want"), [(0, 0, (2, 2)), (10000, 10000, (500, 500))])
def test_terminal_resize_clamped(setup: Setup, cols: int, rows: int, want: tuple[int, int]) -> None:
    setup.open()
    with connect(setup) as ws:
        ws.receive_json()
        ws.send_json({"type": "resize", "cols": cols, "rows": rows})
        ws.send_json({"type": "resize", "cols": 81, "rows": 25})
    assert want in setup.terminal.sizes
    assert setup.terminal.sizes[-1] == (81, 25)


@pytest.mark.unit
def test_terminal_garbage_text_ignored(setup: Setup) -> None:
    setup.open()
    with connect(setup) as ws:
        ws.receive_json()
        for junk in ("not json", "[]", '{"type":"resize","cols":"x","rows":2}', '{"type":"x"}'):
            ws.send_text(junk)
        ws.send_bytes(b"still alive")
    assert setup.terminal.written == [b"still alive"]


@pytest.mark.unit
def test_terminal_input_without_project_dropped(setup: Setup) -> None:
    with connect(setup) as ws:
        ws.receive_json()
        ws.send_bytes(b"x")
        ws.send_json({"type": "resize", "cols": 80, "rows": 24})
    assert setup.terminal.written == []


@pytest.mark.unit
def test_second_terminal_replaces_first(setup: Setup) -> None:
    with connect(setup) as first:
        first.receive_json()
        with connect(setup) as second:
            second.receive_json()
            with pytest.raises(WebSocketDisconnect) as info:
                first.receive_json()
            assert info.value.code == 4000


@pytest.mark.unit
def test_terminal_closed_when_unavailable() -> None:
    s = Setup(available=False)
    with s.client, pytest.raises(WebSocketDisconnect) as info, connect(s) as ws:
        ws.receive_json()
    assert info.value.code == 1008

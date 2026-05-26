from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.domain.entities import OutgoingMessage
from main import app


def _make_outgoing(text: str) -> OutgoingMessage:
    return OutgoingMessage(
        content=text,
        channel="ui",
        recipient="local",
        model_used="groq",
        routed_from=None,
    )


@pytest.mark.unit
def test_ws_chat_returns_chunk_and_done() -> None:
    mock_use_case = MagicMock()
    mock_use_case.execute = AsyncMock(return_value=_make_outgoing("Olá! Como posso ajudar?"))

    with patch("app.api.ws_chat.ProcessIncomingMessage", return_value=mock_use_case):
        client = TestClient(app)
        with client.websocket_connect("/api/v1/ws/chat") as ws:
            ws.send_json({"message": "oi", "session_id": "test-session"})
            chunk = ws.receive_json()
            done = ws.receive_json()

    assert chunk["type"] == "chunk"
    assert chunk["text"] == "Olá! Como posso ajudar?"
    assert done["type"] == "done"


@pytest.mark.unit
def test_ws_chat_sends_error_on_exception() -> None:
    mock_use_case = MagicMock()
    mock_use_case.execute = AsyncMock(side_effect=RuntimeError("boom"))

    with patch("app.api.ws_chat.ProcessIncomingMessage", return_value=mock_use_case):
        client = TestClient(app)
        with client.websocket_connect("/api/v1/ws/chat") as ws:
            ws.send_json({"message": "oi", "session_id": "test-session"})
            error_msg = ws.receive_json()

    assert error_msg["type"] == "error"
    assert "boom" in error_msg["text"]

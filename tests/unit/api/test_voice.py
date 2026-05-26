from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.mark.unit
def test_tts_returns_audio_bytes() -> None:
    mock_audio = b"FAKE_MP3_BYTES"

    mock_response = MagicMock()
    mock_response.read.return_value = mock_audio

    mock_groq_instance = MagicMock()
    mock_groq_instance.audio.speech.create.return_value = mock_response

    with patch("app.api.voice.groq_sdk.Groq", return_value=mock_groq_instance):
        client = TestClient(app)
        response = client.post("/api/v1/tts", json={"text": "Olá, tudo bem?"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content == mock_audio


@pytest.mark.unit
def test_tts_calls_groq_with_correct_params() -> None:
    mock_response = MagicMock()
    mock_response.read.return_value = b"audio"

    mock_groq_instance = MagicMock()
    mock_groq_instance.audio.speech.create.return_value = mock_response

    with patch("app.api.voice.groq_sdk.Groq", return_value=mock_groq_instance):
        client = TestClient(app)
        client.post("/api/v1/tts", json={"text": "Teste"})

    call_kwargs = mock_groq_instance.audio.speech.create.call_args.kwargs
    assert call_kwargs["input"] == "Teste"
    assert "model" in call_kwargs
    assert "voice" in call_kwargs


@pytest.mark.unit
def test_tts_returns_422_for_empty_text() -> None:
    mock_response = MagicMock()
    mock_response.read.return_value = b"audio"
    mock_groq_instance = MagicMock()
    mock_groq_instance.audio.speech.create.return_value = mock_response

    with patch("app.api.voice.groq_sdk.Groq", return_value=mock_groq_instance):
        client = TestClient(app)
        response = client.post("/api/v1/tts", json={"text": ""})

    assert response.status_code == 422


@pytest.mark.unit
def test_tts_returns_422_for_missing_text() -> None:
    client = TestClient(app)
    response = client.post("/api/v1/tts", json={})
    assert response.status_code == 422

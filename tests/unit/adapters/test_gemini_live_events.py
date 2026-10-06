from __future__ import annotations

import pytest
from google.genai import types

from app.adapters.gemini.live_events import GeminiEventMapper
from app.domain.live import (
    AssistantAudio,
    AssistantTranscript,
    LiveError,
    ResponseDone,
    ResponseStarted,
    UserSpeechStarted,
    UserTranscript,
)
from app.domain.tools import ToolCall


def content(**kwargs: object) -> types.LiveServerMessage:
    return types.LiveServerMessage(server_content=types.LiveServerContent(**kwargs))  # type: ignore[arg-type]


def heard(text: str) -> types.LiveServerMessage:
    return content(input_transcription=types.Transcription(text=text))


def said(text: str) -> types.LiveServerMessage:
    return content(output_transcription=types.Transcription(text=text))


def audio(data: bytes) -> types.LiveServerMessage:
    part = types.Part(inline_data=types.Blob(data=data, mime_type="audio/pcm;rate=24000"))
    return content(model_turn=types.Content(parts=[part]))


TURN_COMPLETE = content(turn_complete=True)


@pytest.mark.unit
def test_user_transcript_is_joined_and_released_when_the_model_answers() -> None:
    m = GeminiEventMapper()
    assert m.map(heard("liga a ")) == [UserSpeechStarted(item_id="user-1")]
    assert m.map(heard("luz")) == []
    assert m.map(audio(b"\x01\x02")) == [
        UserTranscript(item_id="user-1", text="liga a luz"),
        ResponseStarted(),
        AssistantAudio(data=b"\x01\x02", item_id="turn-1"),
    ]
    assert m.map(audio(b"\x03")) == [AssistantAudio(data=b"\x03", item_id="turn-1")]


@pytest.mark.unit
def test_turn_complete_saves_the_assistant_transcript_and_ends_the_response() -> None:
    m = GeminiEventMapper()
    m.map(audio(b"\x01"))
    m.map(said("Pronto, "))
    m.map(said("acendi."))
    assert m.map(TURN_COMPLETE) == [AssistantTranscript(text="Pronto, acendi."), ResponseDone()]
    assert m.map(audio(b"\x02"))[0] == ResponseStarted()
    assert m.map(audio(b"\x03")) == [AssistantAudio(data=b"\x03", item_id="turn-2")]


@pytest.mark.unit
def test_tool_call_ends_the_response_with_its_calls_and_remembers_the_names() -> None:
    m = GeminiEventMapper()
    m.map(heard("sim"))
    message = types.LiveServerMessage(
        tool_call=types.LiveServerToolCall(
            function_calls=[
                types.FunctionCall(id="c1", name="set_light", args={"name": "lâmpada", "on": True}),
                types.FunctionCall(id="c2", name="list_lights"),
            ]
        )
    )
    assert m.map(message) == [
        UserTranscript(item_id="user-1", text="sim"),
        ResponseDone(
            calls=(
                ToolCall(
                    id="c1", name="set_light", arguments='{"name": "l\\u00e2mpada", "on": true}'
                ),
                ToolCall(id="c2", name="list_lights", arguments="{}"),
            )
        ),
    ]
    assert m.call_names == {"c1": "set_light", "c2": "list_lights"}
    assert m.map(audio(b"\x01"))[0] == ResponseStarted()  # the answer after the tool result


@pytest.mark.unit
def test_interruption_stands_in_for_speech_started_and_closes_the_response() -> None:
    m = GeminiEventMapper()
    m.map(audio(b"\x01"))
    m.map(said("Vou ligar"))
    assert m.map(content(interrupted=True)) == [
        UserSpeechStarted(item_id="user-1"),
        AssistantTranscript(text="Vou ligar"),
        ResponseDone(),
    ]
    assert m.map(TURN_COMPLETE) == []  # no second ResponseDone for the same response


@pytest.mark.unit
def test_go_away_is_an_error_and_empty_messages_are_ignored() -> None:
    m = GeminiEventMapper()
    away = types.LiveServerMessage(go_away=types.LiveServerGoAway())
    assert m.map(away) == [LiveError(code="go_away")]
    assert m.map(types.LiveServerMessage()) == []
    assert m.map(types.LiveServerMessage(setup_complete=types.LiveServerSetupComplete())) == []

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

import pytest
from openai.types.realtime import (
    ConversationItemInputAudioTranscriptionCompletedEvent,
    InputAudioBufferSpeechStartedEvent,
    RealtimeErrorEvent,
    ResponseAudioDeltaEvent,
    ResponseAudioTranscriptDoneEvent,
    ResponseCreatedEvent,
    ResponseDoneEvent,
    SessionUpdatedEvent,
)

from app.adapters.openai.live_session import build_session_config, map_event
from app.domain.live import (
    AssistantAudio,
    AssistantTranscript,
    LiveError,
    ResponseDone,
    ResponseStarted,
    UserSpeechStarted,
    UserTranscript,
)
from app.domain.tools import ToolCall, ToolSpec

if TYPE_CHECKING:
    from openai.types.realtime import RealtimeServerEvent


def parse(model: type, payload: dict[str, object]) -> RealtimeServerEvent:
    return model.model_validate(payload)  # type: ignore[attr-defined, no-any-return]


@pytest.mark.unit
def test_audio_delta_is_decoded_to_raw_bytes() -> None:
    event = parse(
        ResponseAudioDeltaEvent,
        {
            "type": "response.output_audio.delta",
            "event_id": "e1",
            "response_id": "r1",
            "item_id": "item-1",
            "output_index": 0,
            "content_index": 0,
            "delta": base64.b64encode(b"\x01\x02").decode(),
        },
    )
    assert map_event(event) == AssistantAudio(data=b"\x01\x02", item_id="item-1")


@pytest.mark.unit
def test_speech_started_and_transcripts() -> None:
    started = parse(
        InputAudioBufferSpeechStartedEvent,
        {
            "type": "input_audio_buffer.speech_started",
            "event_id": "e1",
            "item_id": "u1",
            "audio_start_ms": 10,
        },
    )
    transcript = parse(
        ConversationItemInputAudioTranscriptionCompletedEvent,
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "event_id": "e2",
            "item_id": "u1",
            "content_index": 0,
            "transcript": "sim",
            "usage": {"type": "duration", "seconds": 1.0},
        },
    )
    spoken = parse(
        ResponseAudioTranscriptDoneEvent,
        {
            "type": "response.output_audio_transcript.done",
            "event_id": "e3",
            "response_id": "r1",
            "item_id": "a1",
            "output_index": 0,
            "content_index": 0,
            "transcript": "Pronto.",
        },
    )
    assert map_event(started) == UserSpeechStarted(item_id="u1")
    assert map_event(transcript) == UserTranscript(item_id="u1", text="sim")
    assert map_event(spoken) == AssistantTranscript(text="Pronto.")


@pytest.mark.unit
def test_response_created_and_done_with_function_calls() -> None:
    created = parse(
        ResponseCreatedEvent,
        {"type": "response.created", "event_id": "e1", "response": {"id": "r1"}},
    )
    done = parse(
        ResponseDoneEvent,
        {
            "type": "response.done",
            "event_id": "e2",
            "response": {
                "id": "r1",
                "output": [
                    {"type": "message", "role": "assistant", "content": []},
                    {
                        "type": "function_call",
                        "call_id": "call-1",
                        "name": "list_lights",
                        "arguments": "",
                    },
                    {
                        "type": "function_call",
                        "call_id": "call-2",
                        "name": "set_light",
                        "arguments": '{"name": "lampada", "power": true}',
                    },
                ],
            },
        },
    )
    assert map_event(created) == ResponseStarted()
    assert map_event(done) == ResponseDone(
        calls=(
            ToolCall(id="call-1", name="list_lights", arguments="{}"),
            ToolCall(id="call-2", name="set_light", arguments='{"name": "lampada", "power": true}'),
        )
    )


@pytest.mark.unit
def test_response_done_without_output_has_no_calls() -> None:
    done = parse(ResponseDoneEvent, {"type": "response.done", "event_id": "e", "response": {}})
    assert map_event(done) == ResponseDone(calls=())


@pytest.mark.unit
def test_errors_keep_the_code_and_unrelated_events_are_dropped() -> None:
    error = parse(
        RealtimeErrorEvent,
        {
            "type": "error",
            "event_id": "e1",
            "error": {
                "type": "invalid_request_error",
                "code": "rate_limit_exceeded",
                "message": "x",
            },
        },
    )
    no_code = parse(
        RealtimeErrorEvent,
        {"type": "error", "event_id": "e2", "error": {"type": "server_error", "message": "x"}},
    )
    updated = parse(
        SessionUpdatedEvent,
        {"type": "session.updated", "event_id": "e3", "session": {"type": "realtime"}},
    )
    assert map_event(error) == LiveError(code="rate_limit_exceeded")
    assert map_event(no_code) == LiveError(code="server_error")
    assert map_event(updated) is None


@pytest.mark.unit
def test_session_config_sets_everything_explicitly() -> None:
    spec = ToolSpec(
        name="set_light",
        description="Liga.",
        parameters={"type": "object", "properties": {}},
        segment="home",
    )
    config = build_session_config(
        "seja breve",
        [spec],
        vad="semantic_vad",
        transcribe_model="gpt-4o-mini-transcribe",
        retention_ratio=0.8,
    )
    pcm = {"type": "audio/pcm", "rate": 24000}
    expected: dict[str, object] = {
        "type": "realtime",
        "instructions": "seja breve",
        "output_modalities": ["audio"],
        "audio": {
            "input": {
                "format": pcm,
                "noise_reduction": {"type": "far_field"},
                "transcription": {"model": "gpt-4o-mini-transcribe", "language": "pt"},
                "turn_detection": {"type": "semantic_vad"},
            },
            "output": {"format": pcm, "voice": "marin"},
        },
        "tools": [
            {
                "type": "function",
                "name": "set_light",
                "description": "Liga.",
                "parameters": {"type": "object", "properties": {}},
            }
        ],
        "tool_choice": "auto",
        "truncation": {"type": "retention_ratio", "retention_ratio": 0.8},
    }
    assert dict(config) == expected

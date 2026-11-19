from __future__ import annotations

import asyncio
import base64
from contextlib import AsyncExitStack, contextmanager
from typing import TYPE_CHECKING, Literal

from openai import OpenAIError
from websockets.exceptions import WebSocketException

from app.domain.exceptions import LiveSessionError
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
from app.ports.live_session import LiveSession, LiveSessionPort

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Generator, Sequence

    from openai import AsyncOpenAI
    from openai.resources.realtime.realtime import AsyncRealtimeConnection
    from openai.types.realtime import RealtimeServerEvent, RealtimeSessionCreateRequestParam
    from openai.types.realtime.realtime_audio_formats_param import AudioPCM
    from openai.types.realtime.realtime_audio_input_turn_detection_param import (
        SemanticVad,
        ServerVad,
    )

    from app.domain.live import LiveEvent
    from app.domain.tools import ToolResult, ToolSpec

type Vad = Literal["server_vad", "semantic_vad"]

HANDSHAKE_TIMEOUT_SECONDS = 10.0
PCM_24K: AudioPCM = {"type": "audio/pcm", "rate": 24000}
_PROVIDER_ERRORS = (OpenAIError, WebSocketException, OSError)


@contextmanager
def _provider_errors() -> Generator[None]:
    try:
        yield
    except _PROVIDER_ERRORS as exc:
        raise LiveSessionError(f"provider failure: {type(exc).__name__}") from exc


def build_session_config(
    instructions: str,
    tools: Sequence[ToolSpec],
    *,
    vad: Vad,
    transcribe_model: str,
    retention_ratio: float,
) -> RealtimeSessionCreateRequestParam:
    """Everything the docs leave ambiguous is set explicitly: VAD, transcription, audio rate."""
    turn_detection: ServerVad | SemanticVad = (
        {"type": "server_vad"} if vad == "server_vad" else {"type": "semantic_vad"}
    )
    return {
        "type": "realtime",
        "instructions": instructions,
        "output_modalities": ["audio"],
        "audio": {
            "input": {
                "format": PCM_24K,
                "noise_reduction": {"type": "far_field"},
                "transcription": {"model": transcribe_model, "language": "pt"},
                "turn_detection": turn_detection,
            },
            "output": {"format": PCM_24K, "voice": "marin"},
        },
        "tools": [
            {
                "type": "function",
                "name": t.name,
                "description": t.description,
                "parameters": dict(t.parameters),
            }
            for t in tools
        ],
        "tool_choice": "auto",
        "truncation": {"type": "retention_ratio", "retention_ratio": retention_ratio},
    }


def map_event(event: RealtimeServerEvent) -> LiveEvent | None:  # noqa: PLR0911 - one branch per event
    """Provider event -> domain event; everything Byte does not care about maps to None."""
    if event.type == "response.output_audio.delta":
        return AssistantAudio(data=base64.b64decode(event.delta), item_id=event.item_id)
    if event.type == "input_audio_buffer.speech_started":
        return UserSpeechStarted(item_id=event.item_id)
    if event.type == "conversation.item.input_audio_transcription.completed":
        return UserTranscript(item_id=event.item_id, text=event.transcript)
    if event.type == "response.output_audio_transcript.done":
        return AssistantTranscript(text=event.transcript)
    if event.type == "response.created":
        return ResponseStarted()
    if event.type == "response.done":
        calls = tuple(
            ToolCall(id=item.call_id, name=item.name, arguments=item.arguments or "{}")
            for item in event.response.output or ()
            if item.type == "function_call" and item.call_id
        )
        return ResponseDone(calls=calls)
    if event.type == "error":
        return LiveError(code=event.error.code or event.error.type)
    return None


class OpenAILiveSession(LiveSession):
    def __init__(self, connection: AsyncRealtimeConnection, stack: AsyncExitStack) -> None:
        self._conn = connection
        self._stack = stack

    async def send_audio(self, data: bytes) -> None:
        with _provider_errors():
            await self._conn.input_audio_buffer.append(audio=base64.b64encode(data).decode("ascii"))

    async def events(self) -> AsyncIterator[LiveEvent]:
        with _provider_errors():
            async for raw in self._conn:
                if (event := map_event(raw)) is not None:
                    yield event

    async def send_tool_results(self, results: Sequence[ToolResult]) -> None:
        with _provider_errors():
            for result in results:
                await self._conn.conversation.item.create(
                    item={
                        "type": "function_call_output",
                        "call_id": result.call_id,
                        "output": result.output,
                    }
                )

    async def request_response(self) -> None:
        with _provider_errors():
            await self._conn.response.create()

    async def truncate(self, item_id: str, audio_end_ms: int) -> None:
        with _provider_errors():
            await self._conn.conversation.item.truncate(
                item_id=item_id, content_index=0, audio_end_ms=audio_end_ms
            )

    async def close(self) -> None:
        with _provider_errors():
            await self._stack.aclose()


class OpenAILiveSessionAdapter(LiveSessionPort):
    """OpenAI Realtime over WebSocket. The OpenAI SDK never leaves this package."""

    def __init__(
        self,
        client: AsyncOpenAI,
        model: str,
        *,
        vad: Vad = "server_vad",
        transcribe_model: str = "gpt-4o-mini-transcribe",
        retention_ratio: float = 0.8,
    ) -> None:
        self._client = client
        self._model = model
        self._vad: Vad = vad
        self._transcribe_model = transcribe_model
        self._retention_ratio = retention_ratio

    async def open(self, instructions: str, tools: Sequence[ToolSpec]) -> LiveSession:
        config = build_session_config(
            instructions,
            tools,
            vad=self._vad,
            transcribe_model=self._transcribe_model,
            retention_ratio=self._retention_ratio,
        )
        stack = AsyncExitStack()
        try:
            with _provider_errors():
                connection = await stack.enter_async_context(
                    self._client.realtime.connect(model=self._model)
                )
                await connection.session.update(session=config)
                async with asyncio.timeout(HANDSHAKE_TIMEOUT_SECONDS):
                    await self._wait_until_configured(connection)
        except BaseException:
            await stack.aclose()
            raise
        return OpenAILiveSession(connection, stack)

    @staticmethod
    async def _wait_until_configured(connection: AsyncRealtimeConnection) -> None:
        async for event in connection:
            if event.type == "session.updated":
                return
            if event.type == "error":
                raise LiveSessionError(f"provider rejected the session: {event.error.type}")
        raise LiveSessionError("provider closed before the session was configured")

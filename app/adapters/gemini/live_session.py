from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack, contextmanager
from typing import TYPE_CHECKING

from google.genai import errors, types
from websockets.exceptions import WebSocketException

from app.adapters.gemini.chat_model import to_gemini_tools
from app.adapters.gemini.live_events import GeminiEventMapper
from app.domain.exceptions import LiveSessionError
from app.ports.live_session import LiveSession, LiveSessionPort

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Generator, Sequence

    from google import genai
    from google.genai.live import AsyncSession

    from app.domain.live import LiveEvent
    from app.domain.tools import ToolResult, ToolSpec

HANDSHAKE_TIMEOUT_SECONDS = 10.0
AUDIO_IN_MIME = "audio/pcm;rate=24000"  # Gemini resamples to its native 16 kHz itself
LANGUAGE = "pt-BR"
VOCABULARY = ("Byte", "Ei Byte", "apague a luz", "acenda a luz", "lâmpada", "ar-condicionado")
_PROVIDER_ERRORS = (errors.APIError, WebSocketException, OSError)


@contextmanager
def _provider_errors() -> Generator[None]:
    try:
        yield
    except _PROVIDER_ERRORS as exc:
        raise LiveSessionError(f"provider failure: {type(exc).__name__}") from exc


def build_connect_config(
    instructions: str, tools: Sequence[ToolSpec], voice: str
) -> types.LiveConnectConfig:
    return types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        system_instruction=instructions,
        speech_config=types.SpeechConfig(
            language_code=LANGUAGE,
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
            ),
        ),
        # Without a hint the transcriber auto-detects the language and garbles pt-BR, and hears
        # the spoken name "Byte" as "vai" or "baixa".
        input_audio_transcription=types.AudioTranscriptionConfig(
            language_codes=[LANGUAGE], custom_vocabulary=list(VOCABULARY)
        ),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        tools=to_gemini_tools(tools),
    )


class GeminiLiveSession(LiveSession):
    def __init__(self, session: AsyncSession, stack: AsyncExitStack) -> None:
        self._session = session
        self._stack = stack
        self._mapper = GeminiEventMapper()

    async def send_audio(self, data: bytes) -> None:
        with _provider_errors():
            await self._session.send_realtime_input(
                audio=types.Blob(data=data, mime_type=AUDIO_IN_MIME)
            )

    async def events(self) -> AsyncIterator[LiveEvent]:
        with _provider_errors():
            while True:  # receive() stops after every turn_complete
                async for message in self._session.receive():
                    for event in self._mapper.map(message):
                        yield event

    async def send_tool_results(self, results: Sequence[ToolResult]) -> None:
        responses = [
            types.FunctionResponse(
                id=r.call_id,
                name=self._mapper.call_names.pop(r.call_id, ""),
                response={"output": r.output},
            )
            for r in results
        ]
        with _provider_errors():
            await self._session.send_tool_response(function_responses=responses)

    async def request_response(self) -> None:
        """No-op: Gemini continues the turn by itself once the tool response arrives."""

    async def truncate(self, item_id: str, audio_end_ms: int) -> None:
        """No-op: Gemini has no item truncation; it drops the unplayed audio on interruption."""

    async def close(self) -> None:
        with _provider_errors():
            await self._stack.aclose()


class GeminiLiveSessionAdapter(LiveSessionPort):
    """Gemini Live over WebSocket. The google-genai SDK never leaves this package."""

    def __init__(self, client: genai.Client, model: str, *, voice: str = "Kore") -> None:
        self._client = client
        self._model = model
        self._voice = voice

    async def open(self, instructions: str, tools: Sequence[ToolSpec]) -> LiveSession:
        config = build_connect_config(instructions, tools, self._voice)
        stack = AsyncExitStack()
        try:
            with _provider_errors():
                async with asyncio.timeout(HANDSHAKE_TIMEOUT_SECONDS):
                    session = await stack.enter_async_context(
                        self._client.aio.live.connect(model=self._model, config=config)
                    )
        except BaseException:
            await stack.aclose()
            raise
        return GeminiLiveSession(session, stack)

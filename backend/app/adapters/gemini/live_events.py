from __future__ import annotations

import json
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from google.genai.types import FunctionCall, LiveServerMessage

    from app.domain.live import LiveEvent


class GeminiEventMapper:
    """Gemini Live messages -> domain events.

    Gemini has no item ids, no speech-started event and streams transcripts in pieces, so this
    keeps the small state needed to synthesise them. Input transcription arrives independently of
    the answer, often after it started: a piece during an answer belongs to the user's last turn,
    is held until the turn ends, and is never new speech; only `interrupted` (Gemini's own VAD)
    marks speech over an answer.
    """

    def __init__(self) -> None:
        self.call_names: dict[str, str] = {}
        self._turn = 0
        self._user = 0
        self._user_open = False
        self._user_text: list[str] = []
        self._assistant_text: list[str] = []
        self._in_response = False
        self._awaiting_tool = False

    def map(self, message: LiveServerMessage) -> list[LiveEvent]:
        events: list[LiveEvent] = []
        if message.go_away is not None:
            events.append(LiveError(code="go_away"))
        if message.tool_call is not None:
            events += self._flush_user()
            events += self._flush_assistant()
            self._in_response = False
            self._awaiting_tool = True
            calls = tuple(self._tool_call(c) for c in message.tool_call.function_calls or ())
            events.append(ResponseDone(calls=calls))
        if (content := message.server_content) is None:
            return events
        if content.interrupted:
            events += self._flush_user()
            events += self._user_started()
            events += self._flush_assistant()
            events += self._end_response()
        if content.input_transcription and content.input_transcription.text:
            if not self._in_response and not self._awaiting_tool:
                events += self._user_started()
            self._user_text.append(content.input_transcription.text)
            if self._awaiting_tool:  # a confirmation may be waiting on these words
                events += self._flush_user()
        if content.model_turn:
            for part in content.model_turn.parts or ():
                if part.inline_data and part.inline_data.data:
                    events += self._begin_response()
                    item_id = f"turn-{self._turn}"
                    events.append(AssistantAudio(data=part.inline_data.data, item_id=item_id))
        if content.output_transcription and content.output_transcription.text:
            events += self._begin_response()
            self._assistant_text.append(content.output_transcription.text)
        if content.turn_complete:
            self._awaiting_tool = False
            events += self._flush_user()
            events += self._flush_assistant()
            events += self._end_response()
        return events

    def _tool_call(self, call: FunctionCall) -> ToolCall:
        call_id = call.id or ""
        name = call.name or ""
        self.call_names[call_id] = name
        return ToolCall(id=call_id, name=name, arguments=json.dumps(call.args or {}))

    def _begin_response(self) -> list[LiveEvent]:
        if self._in_response:
            return []
        self._in_response = True
        self._awaiting_tool = False
        self._turn += 1
        return [ResponseStarted()]

    def _end_response(self) -> list[LiveEvent]:
        if not self._in_response:
            return []
        self._in_response = False
        return [ResponseDone()]

    def _user_started(self) -> list[LiveEvent]:
        if self._user_open:
            return []
        self._user_open = True
        self._user += 1
        return [UserSpeechStarted(item_id=f"user-{self._user}")]

    def _flush_user(self) -> list[LiveEvent]:
        self._user_open = False
        text = "".join(self._user_text).strip()
        self._user_text.clear()
        return [UserTranscript(item_id=f"user-{self._user}", text=text)] if text else []

    def _flush_assistant(self) -> list[LiveEvent]:
        text = "".join(self._assistant_text).strip()
        self._assistant_text.clear()
        return [AssistantTranscript(text=text)] if text else []

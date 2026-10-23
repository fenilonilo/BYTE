from __future__ import annotations

from typing import TYPE_CHECKING

from app.adapters.memory.in_memory_calendar import InMemoryCalendar
from app.adapters.memory.in_memory_climate import InMemoryClimate
from app.adapters.memory.in_memory_conversation_store import InMemoryConversationStore
from app.adapters.memory.in_memory_expenses import InMemoryExpenses
from app.adapters.memory.in_memory_light import InMemoryLight
from app.adapters.memory.in_memory_music import InMemoryMusic
from app.application.pending_actions import PendingActionStore
from app.application.tool_runner import ToolRunner
from app.application.tools.catalog import build_tool_registry
from app.application.use_cases.process_chat_message import ProcessChatMessage
from app.config import Settings
from app.domain.model import ModelTurn
from app.domain.tools import ToolCall
from tests.fakes.chat_model import ScriptedChatModel
from tests.fakes.clock import FakeClock, wall
from tests.fakes.logger import RecordingLogger

if TYPE_CHECKING:
    from collections.abc import Sequence

TOKEN = "t" * 32


def make_settings() -> Settings:
    return Settings.model_validate({"api_token": TOKEN, "openai_api_key": "sk-test"})


class World:
    """A complete in-memory Byte: scripted model, real use case, runner, tools and store."""

    def __init__(
        self,
        turns: Sequence[ModelTurn],
        *,
        max_steps: int = 6,
        history_limit: int = 20,
        timeout_seconds: float = 30.0,
        projects: Sequence[str] = (),
    ) -> None:
        self.light = InMemoryLight()
        self.calendar = InMemoryCalendar()
        self.store = InMemoryConversationStore()
        self.pending = PendingActionStore(FakeClock())
        self.log = RecordingLogger()
        registry = build_tool_registry(
            self.light, InMemoryClimate(), InMemoryMusic(), self.calendar, InMemoryExpenses()
        )
        self.runner = ToolRunner(registry, self.pending, self.log)
        self.model = ScriptedChatModel(turns)
        self.chat = ProcessChatMessage(
            self.model,
            self.store,
            self.runner,
            self.pending,
            self.log,
            clock=wall,
            max_steps=max_steps,
            history_limit=history_limit,
            timeout_seconds=timeout_seconds,
            projects=projects,
        )


def tool_turn(name: str, arguments: str = "{}", call_id: str = "call-1") -> ModelTurn:
    return ModelTurn(text="", tool_calls=(ToolCall(id=call_id, name=name, arguments=arguments),))


def text_turn(text: str) -> ModelTurn:
    return ModelTurn(text=text)

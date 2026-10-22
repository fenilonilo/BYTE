from __future__ import annotations

import time
from functools import lru_cache
from typing import TYPE_CHECKING

from fastapi import Depends
from openai import AsyncOpenAI

from app.adapters.logging.structlog_logger import StructlogLogger
from app.adapters.memory.in_memory_calendar import InMemoryCalendar
from app.adapters.memory.in_memory_climate import InMemoryClimate
from app.adapters.memory.in_memory_conversation_store import InMemoryConversationStore
from app.adapters.memory.in_memory_expenses import InMemoryExpenses
from app.adapters.memory.in_memory_light import InMemoryLight
from app.adapters.memory.in_memory_music import InMemoryMusic
from app.adapters.openai.chat_model import OpenAIChatModel
from app.adapters.openai.live_session import OpenAILiveSessionAdapter
from app.api.live_slot import LiveSlot
from app.application.music_ducker import MusicDucker
from app.application.pending_actions import PendingActionStore
from app.application.tool_runner import ToolRunner
from app.application.tools.catalog import build_tool_registry
from app.application.tools.music import KnownUris
from app.application.use_cases.process_chat_message import ProcessChatMessage
from app.application.use_cases.run_live_session import LiveLimits, RunLiveSession
from app.config import Settings, load_settings

if TYPE_CHECKING:
    from google import genai

    from app.application.registry import Registry
    from app.application.tool import Tool
    from app.ports.calendar import CalendarPort
    from app.ports.chat_model import ChatModelPort
    from app.ports.climate import ClimatePort
    from app.ports.conversation_store import ConversationStorePort
    from app.ports.expenses import ExpensesPort
    from app.ports.light import LightPort
    from app.ports.live_session import LiveSessionPort
    from app.ports.logger import LoggerPort
    from app.ports.music import MusicPort


@lru_cache
def get_settings() -> Settings:
    return load_settings()


@lru_cache
def get_logger() -> LoggerPort:
    return StructlogLogger()


@lru_cache
def get_store() -> ConversationStorePort:
    return InMemoryConversationStore(get_settings().max_conversations)


@lru_cache
def get_pending() -> PendingActionStore:
    return PendingActionStore(time.monotonic)


# The three device groups pick the real adapter when it is configured and the in-memory one
# otherwise, so the whole service runs without hardware. The lifespan logs which one is active.
# Real adapters are imported lazily: their packages live in optional extras (tuya, thinq, spotify).


@lru_cache
def get_light() -> LightPort:
    lights = get_settings().tuya_lights
    if not lights:
        return InMemoryLight()
    from app.adapters.tuya.tuya_light import (  # noqa: PLC0415 - optional extra
        TuyaLight,
        TuyaLightDevice,
    )

    return TuyaLight(
        {
            name: TuyaLightDevice(s.device_id, s.address, s.local_key.get_secret_value(), s.version)
            for name, s in lights.items()
        }
    )


@lru_cache
def get_climate() -> ClimatePort:
    settings = get_settings()
    if settings.thinq_access_secret is None:
        return InMemoryClimate()
    from app.adapters.thinq.thinq_climate import ThinQClimate  # noqa: PLC0415 - optional extra

    return ThinQClimate(
        settings.thinq_access_secret.get_secret_value(),
        settings.thinq_country,
        settings.thinq_client_id,
    )


@lru_cache
def get_music() -> MusicPort:
    settings = get_settings()
    if settings.spotify_client_id is None or settings.spotify_refresh_token is None:
        return InMemoryMusic()
    from app.adapters.spotify.spotify_music import SpotifyMusic  # noqa: PLC0415 - optional extra

    return SpotifyMusic(
        settings.spotify_client_id,
        settings.spotify_refresh_token.get_secret_value(),
        settings.spotify_device,
    )


@lru_cache
def get_calendar() -> CalendarPort:
    # ponytail: in memory until the Google Calendar adapter exists
    return InMemoryCalendar()


@lru_cache
def get_expenses() -> ExpensesPort:
    # ponytail: in memory until the Google Sheets adapter exists
    return InMemoryExpenses()


@lru_cache
def get_known_uris() -> KnownUris:
    return KnownUris()


@lru_cache
def get_ducker() -> MusicDucker:
    return MusicDucker(get_music(), get_logger(), get_settings().live_duck_percent)


@lru_cache
def get_tools() -> Registry[Tool]:
    return build_tool_registry(
        get_light(),
        get_climate(),
        get_music(),
        get_calendar(),
        get_expenses(),
        known=get_known_uris(),
        on_volume=get_ducker().note_volume,
    )


@lru_cache
def get_runner() -> ToolRunner:
    return ToolRunner(
        get_tools(),
        get_pending(),
        get_logger(),
        tool_timeout=get_settings().tool_timeout_seconds,
    )


@lru_cache
def get_openai() -> AsyncOpenAI:
    settings = get_settings()
    assert settings.openai_api_key is not None  # Settings refuses to boot without it
    return AsyncOpenAI(
        api_key=settings.openai_api_key.get_secret_value(),
        timeout=settings.chat_timeout_seconds,
    )


@lru_cache
def get_gemini() -> genai.Client:
    settings = get_settings()
    assert settings.gemini_api_key is not None  # Settings refuses to boot without it
    from google import genai  # noqa: PLC0415 - optional extra

    return genai.Client(api_key=settings.gemini_api_key.get_secret_value())


@lru_cache
def get_chat_model() -> ChatModelPort:
    settings = get_settings()
    if settings.chat_provider == "gemini":
        from app.adapters.gemini.chat_model import GeminiChatModel  # noqa: PLC0415 - optional extra

        return GeminiChatModel(
            get_gemini(), settings.gemini_chat_model, thinking=settings.gemini_thinking_level
        )
    return OpenAIChatModel(get_openai(), settings.chat_model)


@lru_cache
def get_live_port() -> LiveSessionPort:
    settings = get_settings()
    if settings.live_provider == "gemini":
        from app.adapters.gemini.live_session import (  # noqa: PLC0415 - optional extra
            GeminiLiveSessionAdapter,
        )

        return GeminiLiveSessionAdapter(
            get_gemini(), settings.gemini_live_model, voice=settings.gemini_voice
        )
    return OpenAILiveSessionAdapter(get_openai(), settings.live_model, vad=settings.live_vad)


@lru_cache
def get_live_slot() -> LiveSlot:
    return LiveSlot()


def get_process_chat(
    model: ChatModelPort = Depends(get_chat_model),
    store: ConversationStorePort = Depends(get_store),
    runner: ToolRunner = Depends(get_runner),
    pending: PendingActionStore = Depends(get_pending),
    log: LoggerPort = Depends(get_logger),
    settings: Settings = Depends(get_settings),
) -> ProcessChatMessage:
    return ProcessChatMessage(
        model,
        store,
        runner,
        pending,
        log,
        max_steps=settings.max_steps,
        history_limit=settings.history_limit,
        timeout_seconds=settings.chat_timeout_seconds,
    )


def get_run_live_session(
    live: LiveSessionPort = Depends(get_live_port),
    store: ConversationStorePort = Depends(get_store),
    runner: ToolRunner = Depends(get_runner),
    pending: PendingActionStore = Depends(get_pending),
    log: LoggerPort = Depends(get_logger),
    ducker: MusicDucker = Depends(get_ducker),
    settings: Settings = Depends(get_settings),
) -> RunLiveSession:
    return RunLiveSession(
        live,
        store,
        runner,
        pending,
        log,
        now=time.monotonic,
        ducker=ducker,
        limits=LiveLimits(
            idle_seconds=settings.live_idle_seconds,
            max_seconds=settings.live_max_seconds,
            transcript_wait_seconds=settings.live_transcript_wait_seconds,
        ),
    )

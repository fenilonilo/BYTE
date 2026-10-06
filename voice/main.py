"""Voice daemon: local wake word, then a live conversation over WS /live.

python -m voice.main
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
import sys
import time
from typing import TYPE_CHECKING

import websockets

from app.adapters.logging.structlog_logger import StructlogLogger, configure_logging
from app.domain.exceptions import ConfigError
from voice.audio import Speaker, microphone_frames
from voice.config import load_voice_settings
from voice.session import SessionConfig, VoiceSession
from voice.wake import WakeWord

if TYPE_CHECKING:
    from voice.session import Socket


async def run() -> None:
    settings = load_voice_settings()
    configure_logging(settings.log_level, json=False)  # journald keeps stdout
    headers = {"Authorization": f"Bearer {settings.api_token.get_secret_value()}"}

    async def connect() -> Socket:
        return await websockets.connect(settings.url, additional_headers=headers)

    with Speaker(settings.output_device) as speaker:
        session = VoiceSession(
            detector=WakeWord(settings.wake_model, settings.threshold),
            connect=connect,
            speaker=speaker,
            clock=time.monotonic,
            log=StructlogLogger(),
            config=SessionConfig(segment=settings.segment, idle_seconds=settings.idle_seconds),
        )
        await session.run(microphone_frames(settings.input_device))


def main() -> None:
    # systemd stop: unwind and release audio
    signal.signal(signal.SIGTERM, lambda _signum, _frame: sys.exit(0))
    try:
        with contextlib.suppress(KeyboardInterrupt):
            asyncio.run(run())
    except ConfigError as exc:
        sys.exit(f"config error: {exc}")


if __name__ == "__main__":
    main()

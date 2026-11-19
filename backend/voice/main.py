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
from voice.notifications import Notifier
from voice.session import SessionConfig, VoiceSession
from voice.wake import WakeWord

if TYPE_CHECKING:
    from voice.session import Socket


async def run() -> None:
    settings = load_voice_settings()
    configure_logging(settings.log_level, json=False)  # journald keeps stdout
    headers = {"Authorization": f"Bearer {settings.api_token.get_secret_value()}"}

    # the notifications route sits next to /live under the same prefix
    notify_url = settings.url.rsplit("/", 1)[0] + "/ws/notifications"

    async def connect() -> Socket:
        return await websockets.connect(settings.url, additional_headers=headers)

    async def connect_notify() -> Socket:
        return await websockets.connect(notify_url, additional_headers=headers)

    with Speaker(settings.output_device) as speaker:
        log = StructlogLogger()
        session: VoiceSession | None = None
        notifier = Notifier(
            connect=connect_notify,
            speaker=speaker,
            log=log,
            idle=lambda: session is not None and session.state == "idle",
            clock=time.monotonic,
        )
        session = VoiceSession(
            detector=WakeWord(settings.wake_model, settings.threshold),
            connect=connect,
            speaker=speaker,
            clock=time.monotonic,
            log=log,
            config=SessionConfig(segment=settings.segment, idle_seconds=settings.idle_seconds),
            interrupt=notifier.stop,
        )
        notify = asyncio.create_task(notifier.run())
        try:
            await session.run(microphone_frames(settings.input_device))
        finally:
            notify.cancel()


def main() -> None:
    # systemd stop: unwind and release audio
    signal.signal(signal.SIGTERM, lambda _signum, _frame: sys.exit(0))
    try:
        with contextlib.suppress(KeyboardInterrupt):
            asyncio.run(run())
    except ConfigError as exc:
        sys.exit(f"config error: {exc}")
    except TimeoutError:
        sys.exit("microphone stopped delivering audio")


if __name__ == "__main__":
    main()

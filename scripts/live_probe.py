"""Manual check of /live: send a WAV question, save the spoken reply.

    python scripts/live_probe.py question.wav reply.wav \
        --url wss://192.168.0.10:8000/api/v1/live --token "$BYTE_API_TOKEN" --cafile certs/byte.crt

The WAV must be PCM16, mono, 24 kHz. This is a client of the WebSocket protocol, not a GUI.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import ssl
import wave
from pathlib import Path

import websockets

RATE = 24_000
FRAME_MS = 20
FRAME_BYTES = RATE * 2 * FRAME_MS // 1000
SILENCE_SECONDS = 1.5
REPLY_TIMEOUT_SECONDS = 30


def read_wav(path: Path) -> bytes:
    with wave.open(str(path), "rb") as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, RATE):
            raise SystemExit("question.wav must be PCM16 mono 24000 Hz")
        return wav.readframes(wav.getnframes())


def write_wav(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(pcm)


async def stream_question(ws: websockets.ClientConnection, pcm: bytes) -> None:
    silence = bytes(int(RATE * 2 * SILENCE_SECONDS))  # lets the provider VAD end the turn
    audio = pcm + silence
    for offset in range(0, len(audio), FRAME_BYTES):
        await ws.send(audio[offset : offset + FRAME_BYTES])
        await asyncio.sleep(FRAME_MS / 1000)


async def probe(args: argparse.Namespace) -> None:
    context = ssl.create_default_context(cafile=args.cafile) if args.url.startswith("wss") else None
    headers = {"Authorization": f"Bearer {args.token}"}
    reply = bytearray()
    async with websockets.connect(args.url, additional_headers=headers, ssl=context) as ws:
        await ws.send(json.dumps({"type": "start", "segment": args.segment}))
        sender: asyncio.Task[None] | None = None
        try:
            async with asyncio.timeout(REPLY_TIMEOUT_SECONDS):
                async for message in ws:
                    if isinstance(message, bytes):
                        reply.extend(message)
                        continue
                    event = json.loads(message)
                    print(event)
                    if event["type"] == "ready":
                        sender = asyncio.create_task(stream_question(ws, read_wav(args.question)))
                    elif event["type"] == "error":
                        raise SystemExit(f"server error: {event['code']}")
                    elif event["type"] == "turn_done" and reply:
                        break
        finally:
            if sender is not None:
                sender.cancel()
    write_wav(args.reply, bytes(reply))
    print(f"saved {len(reply)} bytes of audio to {args.reply}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", type=Path)
    parser.add_argument("reply", type=Path)
    parser.add_argument("--url", default="ws://127.0.0.1:8000/api/v1/live")
    parser.add_argument("--token", required=True)
    parser.add_argument("--segment", default="auto")
    parser.add_argument("--cafile", help="pinned self-signed certificate for wss://")
    asyncio.run(probe(parser.parse_args()))


if __name__ == "__main__":
    main()

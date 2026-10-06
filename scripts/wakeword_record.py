"""Record your own voice for the "Ei Byte" wake word.

    python scripts/wakeword_record.py pos <label> [count]   # say the phrase after each high beep
    python scripts/wakeword_record.py neg <label> [seconds] # talk freely; saved as 3 s clips

Writes 16 kHz mono PCM16 WAVs to wakeword_data/real_positive or real_negative.
Needs: pip install sounddevice soundfile scipy numpy
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf
from scipy.signal import resample_poly

NATIVE_RATE = 48_000
RATE = 16_000
CLIP_SECONDS = 2.2
NEG_CLIP_SECONDS = 3
FRAME = RATE // 50
BEEP_TAIL_SECONDS = 0.3
MIN_SPEECH_RMS = 0.008
NOISE_RATIO = 4.0
ACTIVE_RATIO = 0.12
SPAN_FRAMES = 50  # one second either side of the loudest frame
TARGET_PEAK = 0.7
PAD_SECONDS = 0.15
ARG_COUNT = 3  # optional third argument present


_out = sd.OutputStream(samplerate=NATIVE_RATE, channels=1, dtype="float32")


def beep(freq: float, seconds: float = 0.3) -> None:
    """Played through one stream kept open: an idle speaker amp can swallow short sounds."""
    t = np.arange(int(NATIVE_RATE * seconds)) / NATIVE_RATE
    lead = np.zeros(int(NATIVE_RATE * 0.15))
    _out.write(
        (0.4 * np.concatenate([lead, np.sin(2 * np.pi * freq * t)])).astype("float32")[:, None]
    )


def record(seconds: float) -> np.ndarray:
    raw = sd.rec(int(seconds * NATIVE_RATE), samplerate=NATIVE_RATE, channels=1, dtype="float32")
    sd.wait()
    return resample_poly(raw[:, 0], RATE, NATIVE_RATE).astype("float32")


def extract(audio: np.ndarray) -> np.ndarray | None:
    """The spoken burst, peak-normalised; None when there is no clear speech in the clip."""
    audio = audio[int(BEEP_TAIL_SECONDS * RATE) :]  # the end of the beep leaks into the mic
    n = len(audio) // FRAME
    rms = np.sqrt((audio[: n * FRAME].reshape(n, FRAME) ** 2).mean(axis=1))
    peak = float(rms.max())
    if peak < MIN_SPEECH_RMS or peak < NOISE_RATIO * float(np.percentile(rms, 20)):
        return None
    centre = int(rms.argmax())
    window = np.arange(max(centre - SPAN_FRAMES, 0), min(centre + SPAN_FRAMES, n))
    active = window[rms[window] > ACTIVE_RATIO * peak]
    pad = int(PAD_SECONDS * RATE / FRAME)
    clip = audio[max(active[0] - pad, 0) * FRAME : (min(active[-1] + pad, n - 1) + 1) * FRAME]
    return clip / float(np.abs(clip).max()) * TARGET_PEAK


def save(path: Path, audio: np.ndarray) -> None:
    sf.write(path, (np.clip(audio, -1, 1) * 32767).astype("<i2"), RATE, subtype="PCM_16")


def main() -> None:
    _out.start()
    kind, label = sys.argv[1], sys.argv[2]
    if kind not in ("pos", "neg"):
        raise SystemExit("first argument must be pos or neg")
    out = Path("wakeword_data") / f"real_{'positive' if kind == 'pos' else 'negative'}"
    out.mkdir(parents=True, exist_ok=True)
    if kind == "pos":
        count = int(sys.argv[3]) if len(sys.argv) > ARG_COUNT else 20
        for _ in range(3):
            beep(600)
            time.sleep(0.4)
        time.sleep(1.0)
        first = len(list(out.glob(f"{label}_*.wav")))  # never overwrite earlier takes
        good = 0
        for attempt in range(count * 2):
            if good == count:
                break
            beep(1200, 0.3)
            time.sleep(max(_out.latency, 0.0))  # let the beep finish before the mic opens
            clip = extract(record(CLIP_SECONDS))
            if clip is None:
                print(f"#{attempt + 1}: nao ouvi a frase, repete", flush=True)
            else:
                save(out / f"{label}_{first + good:03d}.wav", clip)
                good += 1
                print(f"{good}/{count} ok len={len(clip) / RATE:.2f}s", flush=True)
            time.sleep(0.4)
    else:
        seconds = int(sys.argv[3]) if len(sys.argv) > ARG_COUNT else 90
        for _ in range(3):
            beep(600)
            time.sleep(0.4)
        beep(1200, 0.4)
        audio = record(seconds)
        beep(400, 0.4)
        step = NEG_CLIP_SECONDS * RATE
        for i in range(0, len(audio) - step + 1, step):
            save(out / f"{label}_{i // step:03d}.wav", audio[i : i + step])
        print(f"saved {len(audio) // step} negative clips")
    _out.stop()


if __name__ == "__main__":
    main()

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.adapters.memory.silent_speech import SilentSpeech
from app.adapters.piper.piper_speech import PiperSpeech, resample
from app.domain.exceptions import SpeechError

VOICE = Path("models/pt_BR-faber-medium.onnx")


@pytest.mark.unit
async def test_silent_speech_is_empty() -> None:
    assert await SilentSpeech().synthesize("oi") == b""


@pytest.mark.unit
def test_resample_keeps_duration_at_24k() -> None:
    one_second = np.zeros(22_050, dtype=np.int16).tobytes()
    assert len(resample(one_second, 22_050)) == 24_000 * 2
    assert resample(one_second, 24_000) == one_second
    assert resample(b"", 22_050) == b""


@pytest.mark.unit
def test_missing_voice_raises_speech_error() -> None:
    with pytest.raises(SpeechError):
        PiperSpeech("models/nope.onnx")


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.skipif(not VOICE.is_file(), reason="Piper voice not downloaded")
async def test_piper_speaks_portuguese() -> None:
    pcm = await PiperSpeech(str(VOICE)).synthesize("Lembrete: pagar a conta de luz.")
    assert len(pcm) > 24_000  # more than half a second of audio

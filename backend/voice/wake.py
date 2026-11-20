"""openWakeWord behind the Detector protocol. Model wrapper, verified by hand."""

from __future__ import annotations

from typing import cast

import numpy as np
from openwakeword.model import Model


class WakeWord:
    def __init__(self, model: str, vad_threshold: float = 0.0) -> None:
        # vad_threshold > 0 runs openWakeWord's bundled Silero VAD: no voice, score 0
        self._model = Model(
            wakeword_models=[model], inference_framework="onnx", vad_threshold=vad_threshold
        )

    def __call__(self, frame: bytes) -> float:
        scores = cast("dict[str, float]", self._model.predict(np.frombuffer(frame, dtype=np.int16)))
        return float(max(scores.values(), default=0.0))  # np.float32 would print as a repr

    def reset(self) -> None:
        self._model.reset()

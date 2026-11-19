"""openWakeWord behind the Detector protocol. Model wrapper, verified by hand."""

from __future__ import annotations

from typing import cast

import numpy as np
from openwakeword.model import Model


class WakeWord:
    def __init__(self, model: str, threshold: float) -> None:
        self._model = Model(wakeword_models=[model], inference_framework="onnx")
        self._threshold = threshold

    def __call__(self, frame: bytes) -> bool:
        scores = cast("dict[str, float]", self._model.predict(np.frombuffer(frame, dtype=np.int16)))
        return any(score > self._threshold for score in scores.values())

    def reset(self) -> None:
        self._model.reset()

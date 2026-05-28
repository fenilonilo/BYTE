from __future__ import annotations

import json
from pathlib import Path

Vector = tuple[float, ...]


class PoseStore:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._samples: list[tuple[str, Vector]] = []

    def add_sample(self, label: str, vector: Vector) -> None:
        self._samples.append((label, vector))

    def samples(self) -> list[tuple[str, Vector]]:
        return list(self._samples)

    def labels(self) -> set[str]:
        return {label for label, _ in self._samples}

    def clear(self) -> None:
        self._samples = []

    def load(self) -> None:
        if not self._path.exists():
            self._samples = []
            return
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        self._samples = [(item["label"], tuple(item["vector"])) for item in raw]

    def persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = [{"label": label, "vector": list(vec)} for label, vec in self._samples]
        self._path.write_text(json.dumps(payload), encoding="utf-8")

from __future__ import annotations

from dataclasses import dataclass, field

Vector = tuple[float, ...]


def _dist(a: Vector, b: Vector) -> float:
    n = min(len(a), len(b))
    return sum((a[i] - b[i]) ** 2 for i in range(n)) ** 0.5


@dataclass
class KnnClassifier:
    threshold: float = 0.6
    _templates: list[tuple[str, Vector]] = field(default_factory=list)

    def add(self, label: str, vector: Vector) -> None:
        self._templates.append((label, vector))

    def classify(self, vector: Vector) -> str | None:
        best_label: str | None = None
        best_dist = float("inf")
        for label, tpl in self._templates:
            d = _dist(vector, tpl)
            if d < best_dist:
                best_dist = d
                best_label = label
        if best_label is not None and best_dist <= self.threshold:
            return best_label
        return None

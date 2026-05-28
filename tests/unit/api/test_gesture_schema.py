from __future__ import annotations

from app.api.schemas import GestureEventSchema


def test_schema_parses_and_converts_to_domain() -> None:
    raw = {
        "gesture": "portal",
        "phase": "start",
        "hands": 2,
        "params": {
            "points": [{"x": 0.3, "y": 0.5, "z": 0.0}, {"x": 0.7, "y": 0.5, "z": 0.0}],
            "vector": {"x": 0.0, "y": 0.0, "z": 0.0},
            "center": {"x": 0.5, "y": 0.5, "z": 0.0},
            "radius": 0.2,
            "magnitude": 0.0,
        },
        "ts": 12.0,
    }
    schema = GestureEventSchema.model_validate(raw)
    domain = schema.to_domain()
    assert domain.gesture == "portal"
    assert domain.hands == 2
    assert domain.params.center.x == 0.5
    assert domain.params.radius == 0.2
    assert len(domain.params.points) == 2

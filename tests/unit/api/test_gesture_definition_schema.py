from __future__ import annotations

from app.api.schemas import GestureDefinitionSchema


def test_round_trips_to_domain() -> None:
    raw = {
        "id": "punho_duplo",
        "name": "Punho duplo",
        "pose": {"shape": "fist", "hands": 2},
        "motion": {"type": "hold", "params": {}},
        "binding": {"effect": "freeze", "action": "swap_model", "action_params": {"model": "gemini"}},
    }
    schema = GestureDefinitionSchema.model_validate(raw)
    domain = schema.to_domain()
    assert domain.id == "punho_duplo"
    assert domain.binding.action == "swap_model"
    back = GestureDefinitionSchema.from_domain(domain)
    assert back.pose.shape == "fist"

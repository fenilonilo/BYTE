from __future__ import annotations

import pytest

from app.application.action_dispatcher import ActionDispatcher
from app.application.binding_resolver import StaticBindingResolver
from app.application.registry import Registry
from app.domain.gestures import Binding, GestureEvent, GestureParams
from app.ports.action import ActionPort


class _SpyAction(ActionPort):
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def execute(self, params: dict[str, object]) -> None:
        self.calls.append(params)


def _event(gesture: str, phase: str) -> GestureEvent:
    return GestureEvent(gesture=gesture, phase=phase, hands=2, params=GestureParams(), ts=0.0)


def _dispatcher(spy: _SpyAction) -> ActionDispatcher:
    registry: Registry[ActionPort] = Registry()
    registry.register("swap_model", spy)
    resolver = StaticBindingResolver(
        {
            "freeze": Binding(effect="freeze", action="swap_model", action_params={"model": "gemini"}),
            "swipe": Binding(effect="wave", action=None, action_params={}),
        }
    )
    return ActionDispatcher(registry=registry, resolver=resolver)


@pytest.mark.asyncio
async def test_fires_action_on_instant() -> None:
    spy = _SpyAction()
    d = _dispatcher(spy)
    await d.handle(_event("freeze", "instant"))
    assert spy.calls == [{"model": "gemini"}]


@pytest.mark.asyncio
async def test_fires_on_start_once_not_on_hold() -> None:
    spy = _SpyAction()
    d = _dispatcher(spy)
    await d.handle(_event("freeze", "start"))
    await d.handle(_event("freeze", "hold"))
    assert len(spy.calls) == 1


@pytest.mark.asyncio
async def test_noop_when_binding_has_no_action() -> None:
    spy = _SpyAction()
    d = _dispatcher(spy)
    await d.handle(_event("swipe", "instant"))
    assert spy.calls == []


@pytest.mark.asyncio
async def test_noop_when_no_binding() -> None:
    spy = _SpyAction()
    d = _dispatcher(spy)
    await d.handle(_event("unknown", "instant"))
    assert spy.calls == []

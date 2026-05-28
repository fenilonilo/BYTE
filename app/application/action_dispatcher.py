from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain.exceptions import RegistryKeyError

if TYPE_CHECKING:
    from app.application.registry import Registry
    from app.domain.gestures import GestureEvent
    from app.ports.action import ActionPort
    from app.ports.binding_resolver import BindingResolverPort

_TRIGGER_PHASES = frozenset({"instant", "start"})


class ActionDispatcher:
    def __init__(
        self,
        registry: Registry[ActionPort],
        resolver: BindingResolverPort,
    ) -> None:
        self._registry = registry
        self._resolver = resolver

    async def handle(self, event: GestureEvent) -> None:
        if event.phase not in _TRIGGER_PHASES:
            return
        binding = self._resolver.resolve(event.gesture)
        if binding is None or binding.action is None:
            return
        try:
            action = self._registry.get(binding.action)
        except RegistryKeyError:
            return
        await action.execute(binding.action_params)

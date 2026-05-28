from __future__ import annotations

from typing import TYPE_CHECKING

from app.ports.binding_resolver import BindingResolverPort

if TYPE_CHECKING:
    from app.domain.gestures import Binding


class StaticBindingResolver(BindingResolverPort):
    def __init__(self, bindings: dict[str, Binding]) -> None:
        self._bindings = {k.lower(): v for k, v in bindings.items()}

    def resolve(self, gesture: str) -> Binding | None:
        return self._bindings.get(gesture.lower())

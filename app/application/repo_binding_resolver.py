from __future__ import annotations

from typing import TYPE_CHECKING

from app.ports.binding_resolver import BindingResolverPort

if TYPE_CHECKING:
    from app.domain.gestures import Binding
    from app.ports.gesture_def_repo import GestureDefinitionRepositoryPort


class RepoBindingResolver(BindingResolverPort):
    """Caches gesture->binding in memory; resolve() is sync (called per event).
    Call reload() after any config change."""

    def __init__(self, repo: GestureDefinitionRepositoryPort) -> None:
        self._repo = repo
        self._cache: dict[str, Binding] = {}

    async def reload(self) -> None:
        defs = await self._repo.list_all()
        self._cache = {d.id.lower(): d.binding for d in defs}

    def resolve(self, gesture: str) -> Binding | None:
        return self._cache.get(gesture.lower())

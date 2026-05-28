from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.gestures import Binding


class BindingResolverPort(ABC):
    @abstractmethod
    def resolve(self, gesture: str) -> Binding | None: ...

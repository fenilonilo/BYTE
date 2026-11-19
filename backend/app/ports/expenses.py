from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date

    from app.domain.world import Expense


class ExpensesPort(ABC):
    @abstractmethod
    async def add_expense(
        self, key: str, amount_cents: int, category: str, description: str, day: date
    ) -> Expense:
        """Idempotent: the same `key` never writes a second row."""

    @abstractmethod
    async def list_expenses(self, year: int, month: int) -> tuple[Expense, ...]:
        """The month's rows, oldest first."""

    @abstractmethod
    async def month_total(self, year: int, month: int) -> int:
        """Total in cents."""

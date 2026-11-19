from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain.world import Expense
from app.ports.expenses import ExpensesPort

if TYPE_CHECKING:
    from datetime import date


class InMemoryExpenses(ExpensesPort):
    def __init__(self) -> None:
        self._rows: dict[str, Expense] = {}

    async def add_expense(
        self, key: str, amount_cents: int, category: str, description: str, day: date
    ) -> Expense:
        existing = self._rows.get(key)
        if existing is not None:
            return existing
        expense = Expense(
            key=key,
            amount_cents=amount_cents,
            category=category,
            description=description,
            day=day,
        )
        self._rows[key] = expense
        return expense

    async def list_expenses(self, year: int, month: int) -> tuple[Expense, ...]:
        rows = (e for e in self._rows.values() if (e.day.year, e.day.month) == (year, month))
        return tuple(sorted(rows, key=lambda e: e.day))

    async def month_total(self, year: int, month: int) -> int:
        return sum(
            e.amount_cents
            for e in self._rows.values()
            if (e.day.year, e.day.month) == (year, month)
        )

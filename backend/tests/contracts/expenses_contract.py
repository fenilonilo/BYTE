from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.ports.expenses import ExpensesPort


class ExpensesPortContract(ABC):
    """Every ExpensesPort adapter must pass this. `make()` returns an empty ledger."""

    @abstractmethod
    def make(self) -> ExpensesPort: ...

    async def test_empty_month_totals_zero(self) -> None:
        assert await self.make().month_total(2026, 10) == 0

    async def test_total_sums_only_the_requested_month(self) -> None:
        ledger = self.make()
        await ledger.add_expense("a", 5000, "mercado", "feira", date(2026, 10, 2))
        await ledger.add_expense("b", 2500, "transporte", "uber", date(2026, 10, 9))
        await ledger.add_expense("c", 9999, "mercado", "setembro", date(2026, 9, 30))
        assert await ledger.month_total(2026, 10) == 7500

    async def test_same_key_never_writes_twice(self) -> None:
        ledger = self.make()
        await ledger.add_expense("dup", 5000, "mercado", "feira", date(2026, 10, 2))
        await ledger.add_expense("dup", 5000, "mercado", "feira", date(2026, 10, 2))
        assert await ledger.month_total(2026, 10) == 5000

    async def test_list_returns_only_the_requested_month_oldest_first(self) -> None:
        ledger = self.make()
        await ledger.add_expense("a", 5000, "mercado", "feira", date(2026, 10, 9))
        await ledger.add_expense("b", 2500, "transporte", "uber", date(2026, 10, 2))
        await ledger.add_expense("c", 9999, "mercado", "setembro", date(2026, 9, 30))
        listed = await ledger.list_expenses(2026, 10)
        assert [e.description for e in listed] == ["uber", "feira"]

    async def test_list_of_an_empty_month_is_empty(self) -> None:
        assert await self.make().list_expenses(2026, 10) == ()

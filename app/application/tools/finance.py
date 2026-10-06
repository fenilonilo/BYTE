from __future__ import annotations

from typing import TYPE_CHECKING

from app.application.tool import Tool
from app.application.tools.args import date_arg, int_arg, object_schema, str_arg
from app.domain.exceptions import ToolArgumentError
from app.domain.tools import ToolSpec

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.ports.expenses import ExpensesPort


def brl(cents: int) -> str:
    return f"R$ {cents // 100},{cents % 100:02d}"


class AddExpense(Tool):
    spec = ToolSpec(
        name="add_expense",
        description="Registra um gasto. Exige confirmação do usuário.",
        parameters=object_schema(
            {
                "amount_cents": ("integer", "Valor em centavos, ex.: R$ 50,00 = 5000."),
                "category": ("string", "Categoria, ex.: mercado."),
                "description": ("string", "Descrição curta."),
                "date": ("string", "Dia do gasto no formato AAAA-MM-DD."),
            }
        ),
        segment="finance",
        requires_confirmation=True,
    )

    def __init__(self, expenses: ExpensesPort) -> None:
        self._expenses = expenses

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        amount = int_arg(args, "amount_cents")
        if amount <= 0:
            raise ToolArgumentError("amount_cents deve ser positivo")
        expense = await self._expenses.add_expense(
            key,
            amount,
            str_arg(args, "category"),
            str_arg(args, "description"),
            date_arg(args, "date"),
        )
        return f"Gasto registrado: {brl(expense.amount_cents)} em {expense.category}"

    def summarize(self, args: Mapping[str, object]) -> str:
        return (
            f"Registrar gasto de {brl(int_arg(args, 'amount_cents'))} "
            f"em {str_arg(args, 'category')}: {str_arg(args, 'description')}"
        )


class MonthTotal(Tool):
    spec = ToolSpec(
        name="month_total",
        description="Total gasto em um mês.",
        parameters=object_schema(
            {"year": ("integer", "Ano, ex.: 2026."), "month": ("integer", "Mês de 1 a 12.")}
        ),
        segment="finance",
    )

    def __init__(self, expenses: ExpensesPort) -> None:
        self._expenses = expenses

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        year, month = int_arg(args, "year"), int_arg(args, "month")
        if not 1 <= month <= 12:  # noqa: PLR2004
            raise ToolArgumentError("month deve estar entre 1 e 12")
        total = await self._expenses.month_total(year, month)
        return f"Total de {month:02d}/{year}: {brl(total)}"

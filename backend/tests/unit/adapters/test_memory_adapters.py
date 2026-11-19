from __future__ import annotations

import pytest

from app.adapters.memory.in_memory_calendar import InMemoryCalendar
from app.adapters.memory.in_memory_conversation_store import InMemoryConversationStore
from app.adapters.memory.in_memory_expenses import InMemoryExpenses
from app.adapters.memory.in_memory_weather import GOIANIA, InMemoryWeather
from app.domain.weather import Condition
from tests.contracts.calendar_contract import CalendarPortContract
from tests.contracts.conversation_store_contract import (
    ConversationStorePortContract,
    msg,
)
from tests.contracts.expenses_contract import ExpensesPortContract
from tests.contracts.weather_contract import WeatherPortContract


@pytest.mark.unit
class TestInMemoryCalendar(CalendarPortContract):
    def make(self) -> InMemoryCalendar:
        return InMemoryCalendar()


@pytest.mark.unit
class TestInMemoryExpenses(ExpensesPortContract):
    def make(self) -> InMemoryExpenses:
        return InMemoryExpenses()


@pytest.mark.unit
class TestInMemoryConversationStore(ConversationStorePortContract):
    def make(self) -> InMemoryConversationStore:
        return InMemoryConversationStore()

    async def test_least_recently_used_conversation_is_evicted(self) -> None:
        store = InMemoryConversationStore(max_conversations=2)
        await store.append("a", [msg(1)])
        await store.append("b", [msg(2)])
        await store.recent("a", 20)  # reading counts as use, so "b" is now the oldest
        await store.append("c", [msg(3)])
        assert await store.recent("b", 20) == ()
        assert [m.id for m in await store.recent("a", 20)] == ["m1"]

    async def test_append_to_evicted_id_creates_it_again(self) -> None:
        store = InMemoryConversationStore(max_conversations=1)
        await store.append("a", [msg(1)])
        await store.append("b", [msg(2)])
        await store.append("a", [msg(3)])
        assert [m.id for m in await store.recent("a", 20)] == ["m3"]


@pytest.mark.unit
class TestInMemoryWeather(WeatherPortContract):
    def make(self) -> InMemoryWeather:
        return InMemoryWeather()


@pytest.mark.unit
async def test_in_memory_weather_can_be_raining() -> None:
    current = (await InMemoryWeather(raining=True).forecast(GOIANIA)).current
    assert current.raining is True
    assert current.condition is Condition.RAIN

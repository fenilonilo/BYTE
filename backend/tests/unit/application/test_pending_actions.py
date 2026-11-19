from __future__ import annotations

import pytest

from app.application.pending_actions import (
    NOT_ARMED,
    NOT_CONFIRMED,
    NOTHING_PENDING,
    PendingActionStore,
)
from tests.fakes.clock import FakeClock


def make() -> tuple[PendingActionStore, FakeClock]:
    clock = FakeClock()
    return PendingActionStore(clock, ttl_seconds=60), clock


def create(store: PendingActionStore, conversation_id: str = "c1") -> None:
    store.create(conversation_id, "delete_event", '{"event_id":"evt-1"}', "Apagar", "key-1")


@pytest.mark.unit
def test_nothing_pending() -> None:
    store, _ = make()
    assert store.confirm("c1") == (None, NOTHING_PENDING)


@pytest.mark.unit
def test_confirm_in_the_same_turn_is_refused_and_keeps_the_action() -> None:
    store, _ = make()
    create(store)
    assert store.confirm("c1") == (None, NOT_ARMED)
    assert store.peek("c1") is not None


@pytest.mark.unit
def test_next_affirmative_utterance_confirms_once() -> None:
    store, _ = make()
    create(store)
    store.on_user_utterance("c1", "sim, pode")
    action, reason = store.confirm("c1")
    assert action is not None
    assert action.key == "key-1"
    assert reason == ""
    assert store.confirm("c1") == (None, NOTHING_PENDING)


@pytest.mark.unit
def test_non_affirmative_utterance_consumes_the_action() -> None:
    store, _ = make()
    create(store)
    store.on_user_utterance("c1", "não, cancela")
    assert store.confirm("c1") == (None, NOT_CONFIRMED)
    assert store.peek("c1") is None


@pytest.mark.unit
def test_an_unrelated_utterance_between_request_and_yes_drops_the_action() -> None:
    store, _ = make()
    create(store)
    store.on_user_utterance("c1", "que horas são")
    store.on_user_utterance("c1", "sim")
    assert store.confirm("c1") == (None, NOTHING_PENDING)


@pytest.mark.unit
def test_expires_after_ttl() -> None:
    store, clock = make()
    create(store)
    store.on_user_utterance("c1", "sim")
    clock.advance(60)
    assert store.confirm("c1") == (None, NOTHING_PENDING)


@pytest.mark.unit
def test_pending_actions_are_isolated_per_conversation() -> None:
    store, _ = make()
    create(store, "a")
    store.on_user_utterance("b", "sim")
    assert store.confirm("b") == (None, NOTHING_PENDING)
    assert store.peek("a") is not None


@pytest.mark.unit
def test_a_new_request_replaces_the_old_one() -> None:
    store, _ = make()
    create(store)
    store.create("c1", "delete_event", '{"event_id":"evt-1"}', "Apagar", "key-2")
    store.on_user_utterance("c1", "sim")
    action, _ = store.confirm("c1")
    assert action is not None
    assert action.key == "key-2"


@pytest.mark.unit
def test_drop_removes_the_action_and_is_safe_when_empty() -> None:
    store, _ = make()
    store.drop("c1")
    create(store)
    store.drop("c1")
    assert store.peek("c1") is None

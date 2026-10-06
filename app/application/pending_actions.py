from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from app.domain.affirmation import is_affirmative
from app.domain.tools import PendingAction

if TYPE_CHECKING:
    from collections.abc import Callable

NOTHING_PENDING = "nada para confirmar"
NOT_ARMED = "aguarde a resposta do usuário antes de confirmar"
NOT_CONFIRMED = "o usuário não confirmou"


class PendingActionStore:
    """One pending action per conversation, valid for the very next user utterance only."""

    def __init__(self, now: Callable[[], float], ttl_seconds: float = 60.0) -> None:
        self._now = now
        self._ttl = ttl_seconds
        self._pending: dict[str, PendingAction] = {}

    def create(
        self, conversation_id: str, tool: str, arguments: str, summary: str, key: str
    ) -> PendingAction:
        action = PendingAction(
            tool=tool,
            arguments=arguments,
            summary=summary,
            key=key,
            expires_at=self._now() + self._ttl,
        )
        self._pending[conversation_id] = action
        return action

    def on_user_utterance(self, conversation_id: str, text: str) -> None:
        """Call for every user utterance. The first one after creation arms the action;
        any later one drops it, so an old request can never be confirmed by a later "sim"."""
        action = self.peek(conversation_id)
        if action is None:
            return
        if action.armed:
            del self._pending[conversation_id]
            return
        self._pending[conversation_id] = replace(action, armed=True, armed_text=text)

    def peek(self, conversation_id: str) -> PendingAction | None:
        action = self._pending.get(conversation_id)
        if action is None:
            return None
        if self._now() >= action.expires_at:
            del self._pending[conversation_id]
            return None
        return action

    def confirm(self, conversation_id: str) -> tuple[PendingAction | None, str]:
        """Synchronous, so the check-and-pop is atomic: two parallel calls cannot both win."""
        action = self.peek(conversation_id)
        if action is None:
            return None, NOTHING_PENDING
        if not action.armed:
            return None, NOT_ARMED
        del self._pending[conversation_id]
        if not is_affirmative(action.armed_text):
            return None, NOT_CONFIRMED
        return action, ""

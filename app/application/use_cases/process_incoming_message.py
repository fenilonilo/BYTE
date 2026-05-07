from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from app.domain.entities import Conversation, IncomingMessage, Message, OutgoingMessage

if TYPE_CHECKING:
    from app.ports.agent import AgentPort
    from app.ports.logger import LoggerPort
    from app.ports.repository import RepositoryPort


class ProcessIncomingMessage:
    def __init__(self, agent: AgentPort, repo: RepositoryPort, log: LoggerPort) -> None:
        self._agent = agent
        self._repo = repo
        self._log = log

    async def execute(self, msg: IncomingMessage) -> OutgoingMessage:
        conv_id = msg.conversation_id or str(uuid4())
        conversation = await self._repo.get(conv_id)
        if conversation is None:
            conversation = Conversation(
                id=conv_id,
                messages=(),
                created_at=datetime.now(tz=UTC),
            )

        user_msg = Message(
            id=str(uuid4()),
            role="user",
            content=msg.content,
            timestamp=msg.timestamp,
        )
        conversation = conversation.with_message(user_msg)

        self._log.info("agent.run.start", conversation_id=conv_id)
        response_text = await self._agent.run(
            message=msg.content,
            conversation=conversation,
        )

        assistant_msg = Message(
            id=str(uuid4()),
            role="assistant",
            content=response_text,
            timestamp=datetime.now(tz=UTC),
        )
        conversation = conversation.with_message(assistant_msg)

        await self._repo.save(conversation)
        self._log.info("agent.run.done", conversation_id=conv_id)

        return OutgoingMessage(
            content=response_text,
            channel=msg.channel,
            recipient=msg.sender,
        )

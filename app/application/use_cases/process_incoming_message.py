# app/application/use_cases/process_incoming_message.py
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.domain.entities import Conversation, IncomingMessage, Message, OutgoingMessage
from app.ports.llm import LLMPort
from app.ports.logger import LoggerPort
from app.ports.repository import RepositoryPort


class ProcessIncomingMessage:
    def __init__(self, llm: LLMPort, repo: RepositoryPort, log: LoggerPort) -> None:
        self._llm = llm
        self._repo = repo
        self._log = log

    async def execute(self, msg: IncomingMessage) -> OutgoingMessage:
        conv_id = msg.conversation_id or str(uuid4())
        conversation = await self._repo.get(conv_id)
        if conversation is None:
            conversation = Conversation(
                id=conv_id,
                messages=(),
                created_at=datetime.now(tz=timezone.utc),
            )

        user_msg = Message(
            id=str(uuid4()),
            role="user",
            content=msg.content,
            timestamp=msg.timestamp,
        )
        conversation = conversation.with_message(user_msg)

        self._log.info("llm.complete.start", conversation_id=conv_id)
        response_text = await self._llm.complete(
            prompt=msg.content,
            conversation=conversation,
        )

        assistant_msg = Message(
            id=str(uuid4()),
            role="assistant",
            content=response_text,
            timestamp=datetime.now(tz=timezone.utc),
        )
        conversation = conversation.with_message(assistant_msg)

        await self._repo.save(conversation)
        self._log.info("llm.complete.done", conversation_id=conv_id)

        return OutgoingMessage(
            content=response_text,
            channel=msg.channel,
            recipient=msg.sender,
        )

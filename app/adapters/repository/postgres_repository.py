# app/adapters/repository/postgres_repository.py
from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.adapters.repository.models import ConversationModel, MessageModel
from app.domain.entities import Conversation, Message
from app.ports.repository import RepositoryPort

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


class PostgresRepository(RepositoryPort):
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def save(self, conversation: Conversation) -> None:
        now = datetime.now(tz=UTC)
        async with AsyncSession(self._engine) as session:
            result = await session.execute(
                select(ConversationModel).where(ConversationModel.id == conversation.id)
            )
            conv_model = result.scalar_one_or_none()

            if conv_model is None:
                conv_model = ConversationModel(
                    id=conversation.id,
                    created_at=conversation.created_at,
                    updated_at=now,
                )
                session.add(conv_model)
            else:
                conv_model.updated_at = now

            existing_ids_result = await session.execute(
                select(MessageModel.id).where(
                    MessageModel.conversation_id == conversation.id
                )
            )
            existing_ids = {row[0] for row in existing_ids_result}

            for msg in conversation.messages:
                if msg.id not in existing_ids:
                    session.add(
                        MessageModel(
                            id=msg.id,
                            conversation_id=conversation.id,
                            role=msg.role,
                            content=msg.content,
                            timestamp=msg.timestamp,
                        )
                    )

            await session.commit()

    async def get(self, conversation_id: str) -> Conversation | None:
        async with AsyncSession(self._engine) as session:
            result = await session.execute(
                select(ConversationModel)
                .where(ConversationModel.id == conversation_id)
                .options(selectinload(ConversationModel.messages))
            )
            conv_model = result.scalar_one_or_none()
            if conv_model is None:
                return None

            messages = tuple(
                Message(
                    id=m.id,
                    role=m.role,
                    content=m.content,
                    timestamp=m.timestamp.replace(tzinfo=UTC),
                )
                for m in sorted(conv_model.messages, key=lambda m: m.timestamp)
            )
            return Conversation(
                id=conv_model.id,
                messages=messages,
                created_at=conv_model.created_at.replace(tzinfo=UTC),
            )

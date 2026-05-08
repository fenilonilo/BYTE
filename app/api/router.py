from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from fastapi import APIRouter, Depends

from app.api.deps import get_agent, get_logger, get_repo
from app.api.schemas import IncomingMessageSchema, OutgoingMessageSchema
from app.application.use_cases.process_incoming_message import ProcessIncomingMessage
from app.domain.entities import IncomingMessage

if TYPE_CHECKING:
    from app.ports.agent import AgentPort
    from app.ports.logger import LoggerPort
    from app.ports.repository import RepositoryPort

router = APIRouter()


@router.post("/messages", response_model=OutgoingMessageSchema)
async def receive_message(
    body: IncomingMessageSchema,
    agent: AgentPort = Depends(get_agent),
    repo: RepositoryPort = Depends(get_repo),
    log: LoggerPort = Depends(get_logger),
) -> OutgoingMessageSchema:
    use_case = ProcessIncomingMessage(agent=agent, repo=repo, log=log)
    incoming = IncomingMessage(
        id=str(uuid4()),
        sender=body.sender,
        content=body.content,
        channel=body.channel,
        timestamp=datetime.now(tz=UTC),
        conversation_id=body.conversation_id,
        model_override=body.model_override,
    )
    outgoing = await use_case.execute(incoming)
    return OutgoingMessageSchema(
        content=outgoing.content,
        channel=outgoing.channel,
        recipient=outgoing.recipient,
        model_used=outgoing.model_used,
        routed_from=outgoing.routed_from,
    )

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_agents, get_logger, get_repo
from app.api.schemas import IncomingMessageSchema, MessageSchema
from app.application.use_cases.process_incoming_message import ProcessIncomingMessage
from app.domain.entities import IncomingMessage
from app.domain.exceptions import RegistryKeyError

if TYPE_CHECKING:
    from app.application.registry import Registry
    from app.ports.agent import AgentPort
    from app.ports.logger import LoggerPort
    from app.ports.repository import RepositoryPort

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/messages", response_model=MessageSchema)
async def receive_message(
    body: IncomingMessageSchema,
    agents: Registry[AgentPort] = Depends(get_agents),
    repo: RepositoryPort = Depends(get_repo),
    log: LoggerPort = Depends(get_logger),
) -> MessageSchema:
    try:
        agent = agents.get(body.segment)
    except RegistryKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown segment: {body.segment!r}",
        ) from exc

    conversation_id = body.conversation_id or str(uuid4())
    incoming = IncomingMessage(
        id=str(uuid4()),
        content=body.content,
        segment=body.segment,
        timestamp=datetime.now(tz=UTC),
        conversation_id=conversation_id,
    )
    use_case = ProcessIncomingMessage(agent=agent, repo=repo, log=log)
    reply = await use_case.execute(incoming)
    return MessageSchema(
        id=reply.id,
        role=reply.role,
        content=reply.content,
        conversation_id=conversation_id,
    )

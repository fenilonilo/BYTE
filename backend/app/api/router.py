from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import require_token
from app.api.deps import get_process_chat, get_runner
from app.api.schemas import IncomingMessageSchema, MessageSchema, PendingConfirmationSchema

if TYPE_CHECKING:
    from app.application.tool_runner import ToolRunner
    from app.application.use_cases.process_chat_message import ProcessChatMessage

AUTO = "auto"

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/messages", response_model=MessageSchema, dependencies=[Depends(require_token)])
async def receive_message(
    body: IncomingMessageSchema,
    chat: ProcessChatMessage = Depends(get_process_chat),
    runner: ToolRunner = Depends(get_runner),
) -> MessageSchema:
    segment = body.segment.strip().lower()
    if segment != AUTO and segment not in runner.segments():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown segment: {body.segment!r}"
        )
    conversation_id = body.conversation_id or uuid4().hex
    reply = await chat.execute(
        conversation_id,
        body.content,
        None if segment == AUTO else segment,
        panel=body.client == "panel",
    )
    return MessageSchema(
        id=reply.message.id,
        role=reply.message.role,
        content=reply.message.content,
        conversation_id=conversation_id,
        pending_confirmation=(
            PendingConfirmationSchema(summary=reply.pending_summary)
            if reply.pending_summary
            else None
        ),
    )

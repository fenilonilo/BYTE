from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from fastapi import APIRouter, Depends

from app.api.deps import get_llm, get_logger, get_repo
from app.api.schemas import IncomingMessageSchema, OutgoingMessageSchema
from app.application.use_cases.process_incoming_message import ProcessIncomingMessage
from app.config import Settings
from app.domain.entities import IncomingMessage

if TYPE_CHECKING:
    from app.ports.llm import LLMPort
    from app.ports.logger import LoggerPort
    from app.ports.repository import RepositoryPort

router = APIRouter()

_settings = Settings()


@router.post("/messages", response_model=OutgoingMessageSchema)
async def receive_message(
    body: IncomingMessageSchema,
    llm: LLMPort = Depends(get_llm),
    repo: RepositoryPort = Depends(get_repo),
    log: LoggerPort = Depends(get_logger),
) -> OutgoingMessageSchema:
    use_case = ProcessIncomingMessage(llm=llm, repo=repo, log=log)
    incoming = IncomingMessage(
        id=str(uuid4()),
        sender=body.sender,
        content=body.content,
        channel=body.channel,
        timestamp=datetime.now(tz=UTC),
        conversation_id=body.conversation_id,
    )
    outgoing = await use_case.execute(incoming)
    return OutgoingMessageSchema(
        content=outgoing.content,
        channel=outgoing.channel,
        recipient=outgoing.recipient,
    )


@router.get("/projects")
async def list_projects() -> list[dict]:
    """Return directories in workspace_path sorted by mtime descending."""
    workspace: Path = _settings.workspace_path
    if not workspace.is_dir():
        return []

    entries = []
    with os.scandir(workspace) as it:
        for entry in it:
            if entry.is_dir():
                entries.append({
                    "name": entry.name,
                    "path": str(entry.path),
                    "mtime": entry.stat().st_mtime,
                })

    entries.sort(key=lambda e: e["mtime"], reverse=True)
    return entries

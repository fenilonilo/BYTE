from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.api.deps import get_agent, get_logger, get_repo
from app.application.use_cases.process_incoming_message import ProcessIncomingMessage
from app.domain.entities import IncomingMessage

router = APIRouter()


class _ChatPayload(BaseModel):
    message: str
    session_id: str = "default"


@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket) -> None:
    await websocket.accept()
    agent = get_agent()
    repo = get_repo()
    log = get_logger()

    try:
        while True:
            raw = await websocket.receive_json()
            payload = _ChatPayload.model_validate(raw)

            use_case = ProcessIncomingMessage(agent=agent, repo=repo, log=log)
            incoming = IncomingMessage(
                id=str(uuid4()),
                sender="local",
                content=payload.message,
                channel="ui",
                timestamp=datetime.now(tz=UTC),
                conversation_id=payload.session_id,
                model_override=None,
            )

            try:
                outgoing = await use_case.execute(incoming)
                await websocket.send_json({"type": "chunk", "text": outgoing.content})
                await websocket.send_json({"type": "done", "text": ""})
            except Exception as exc:
                await websocket.send_json({"type": "error", "text": str(exc)})

    except WebSocketDisconnect:
        pass

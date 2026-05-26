from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.api.deps import get_agent, get_developer_tool, get_logger, get_repo
from app.application.use_cases.process_incoming_message import ProcessIncomingMessage
from app.domain.entities import IncomingMessage

router = APIRouter()

_PREVIEW_MARKER = "## Task"


class _ChatPayload(BaseModel):
    message: str
    session_id: str = "default"


@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket) -> None:
    await websocket.accept()
    agent = get_agent()
    repo = get_repo()
    log = get_logger()
    dev_tool = get_developer_tool()

    pending_prompt: str | None = None

    try:
        while True:
            raw = await websocket.receive_json()
            msg_type = raw.get("type", "message")

            if msg_type == "approve_send":
                if pending_prompt and dev_tool.active_project:
                    dev_tool.send_to_claude(pending_prompt)
                    pending_prompt = None
                    await websocket.send_json({
                        "type": "chunk",
                        "text": "Prompt enviado ao Claude Code! Veja o terminal.",
                    })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "text": "Nenhum prompt pendente ou projeto ativo.",
                    })
                await websocket.send_json({"type": "done", "text": ""})
                continue

            if msg_type == "cancel_send":
                pending_prompt = None
                await websocket.send_json({"type": "chunk", "text": "Cancelado."})
                await websocket.send_json({"type": "done", "text": ""})
                continue

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
                response_text = outgoing.content

                if (
                    dev_tool.active_project
                    and response_text.strip().startswith(_PREVIEW_MARKER)
                ):
                    pending_prompt = response_text
                    await websocket.send_json({
                        "type": "preview",
                        "prompt": response_text,
                        "project": dev_tool.active_project,
                    })
                else:
                    await websocket.send_json({"type": "chunk", "text": response_text})

                await websocket.send_json({"type": "done", "text": ""})

            except Exception as exc:
                await websocket.send_json({"type": "error", "text": str(exc)})

    except WebSocketDisconnect:
        pass

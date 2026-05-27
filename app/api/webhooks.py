from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from app.adapters.messaging.evolution_client import EvolutionClient
from app.adapters.messaging.whatsapp_adapter import WhatsappAdapter
from app.api.deps import get_agent, get_logger, get_repo, get_settings
from app.application.use_cases.process_incoming_message import ProcessIncomingMessage
from app.domain.entities import IncomingMessage, OutgoingMessage

if TYPE_CHECKING:
    from app.config import Settings
    from app.ports.agent import AgentPort
    from app.ports.logger import LoggerPort
    from app.ports.repository import RepositoryPort

router = APIRouter(tags=["webhook"])

# In-process cache: group_jid -> approved (bool)
_group_cache: dict[str, bool] = {}


def _build_client(settings: Settings) -> EvolutionClient:
    return EvolutionClient(
        base_url=settings.evolution_api_url,
        api_key=settings.evolution_api_key,
        instance=settings.evolution_instance_name,
    )


def _extract_text(message_obj: dict) -> str:
    return (
        message_obj.get("conversation")
        or (message_obj.get("extendedTextMessage") or {}).get("text")
        or ""
    )


async def _process_and_reply(
    incoming: IncomingMessage,
    group_jid: str,
    settings: Settings,
    agent: AgentPort,
    repo: RepositoryPort,
    log: LoggerPort,
) -> None:
    try:
        use_case = ProcessIncomingMessage(agent=agent, repo=repo, log=log)
        outgoing = await use_case.execute(incoming)

        reply = OutgoingMessage(
            content=outgoing.content,
            channel="whatsapp",
            recipient=group_jid,
            model_used=outgoing.model_used,
            routed_from=outgoing.routed_from,
        )

        adapter = WhatsappAdapter(client=_build_client(settings))
        await adapter.send(reply)
    except Exception as exc:
        log.error("whatsapp.reply.failed", error=str(exc), jid=group_jid)


@router.post("/webhook/whatsapp")
async def whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    agent: AgentPort = Depends(get_agent),
    repo: RepositoryPort = Depends(get_repo),
    log: LoggerPort = Depends(get_logger),
) -> dict:
    payload: dict = await request.json()

    if payload.get("event") != "messages.upsert":
        return {"status": "ignored"}

    data: dict = payload.get("data", {})
    key: dict = data.get("key", {})

    if key.get("fromMe"):
        return {"status": "ignored"}

    remote_jid: str = key.get("remoteJid", "")

    if not remote_jid.endswith("@g.us"):
        return {"status": "ignored"}

    # Resolve group name on first encounter, then cache
    if remote_jid not in _group_cache:
        client = _build_client(settings)
        info = await client.get_group_info(remote_jid)
        name: str = info.get("subject", "")
        approved = name == settings.whatsapp_target_group
        _group_cache[remote_jid] = approved
        log.info("whatsapp.group.resolved", jid=remote_jid, name=name, approved=approved)

    if not _group_cache[remote_jid]:
        return {"status": "ignored"}

    text = _extract_text(data.get("message", {}))
    if not text:
        return {"status": "ignored"}

    sender: str = data.get("pushName") or key.get("participant", "unknown")

    incoming = IncomingMessage(
        id=str(uuid4()),
        sender=sender,
        content=text,
        channel="whatsapp",
        timestamp=datetime.now(tz=UTC),
        conversation_id=remote_jid,
    )

    background_tasks.add_task(
        _process_and_reply,
        incoming,
        remote_jid,
        settings,
        agent,
        repo,
        log,
    )

    return {"status": "ok"}

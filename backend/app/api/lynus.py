from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.api.auth import BEARER, require_token
from app.api.deps import get_claude_bridge, get_lynus
from app.api.schemas import (
    ClaudeHookSchema,
    LynusMessageSchema,
    LynusPhaseSchema,
    LynusViewSchema,
)
from app.domain.exceptions import LynusBusyError

if TYPE_CHECKING:
    from app.application.claude_bridge import ClaudeBridge
    from app.application.lynus import Lynus

router = APIRouter()


@router.post("/claude/hooks")
async def claude_hook(
    body: ClaudeHookSchema,
    authorization: str | None = Header(default=None),
    bridge: ClaudeBridge | None = Depends(get_claude_bridge),
) -> dict[str, object]:
    """Called by the `claude` process the server runs, with its session token, never the
    owner's: that process must not be able to read the owner token."""
    token = (authorization or "").removeprefix(BEARER)
    if bridge is None or not authorization or not bridge.authorized(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return await bridge.hook(body.model_dump(exclude_none=True))


def _required(lynus: Lynus | None) -> Lynus:
    if lynus is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Lynus indisponível: falta o terminal de projetos ou a chave do Gemini.",
        )
    return lynus


@router.get("/lynus", response_model=LynusViewSchema, dependencies=[Depends(require_token)])
async def lynus_view(lynus: Lynus | None = Depends(get_lynus)) -> LynusViewSchema:
    return LynusViewSchema.model_validate(_required(lynus).view())


@router.post(
    "/lynus/messages", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_token)]
)
async def lynus_message(
    body: LynusMessageSchema, lynus: Lynus | None = Depends(get_lynus)
) -> dict[str, str]:
    try:
        await _required(lynus).say(body.content)
    except LynusBusyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"status": "accepted"}


@router.post("/lynus/stop", response_model=LynusPhaseSchema, dependencies=[Depends(require_token)])
async def lynus_stop(lynus: Lynus | None = Depends(get_lynus)) -> LynusPhaseSchema:
    return LynusPhaseSchema(phase=(await _required(lynus).stop()).value)

# app/api/schemas.py
from __future__ import annotations

from pydantic import BaseModel


class IncomingMessageSchema(BaseModel):
    sender: str
    content: str
    channel: str
    conversation_id: str | None = None
    model_override: str | None = None


class OutgoingMessageSchema(BaseModel):
    content: str
    channel: str
    recipient: str
    model_used: str = ""
    routed_from: str | None = None

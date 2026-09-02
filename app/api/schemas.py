from __future__ import annotations

from pydantic import BaseModel


class IncomingMessageSchema(BaseModel):
    content: str
    segment: str
    conversation_id: str | None = None


class MessageSchema(BaseModel):
    id: str
    role: str
    content: str
    conversation_id: str

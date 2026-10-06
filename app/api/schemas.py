from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_CONTENT_CHARS = 4000


class IncomingMessageSchema(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    content: str = Field(min_length=1, max_length=MAX_CONTENT_CHARS)
    segment: str = "auto"
    conversation_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")


class PendingConfirmationSchema(BaseModel):
    summary: str


class MessageSchema(BaseModel):
    id: str
    role: str
    content: str
    conversation_id: str
    pending_confirmation: PendingConfirmationSchema | None = None


class LiveStartSchema(BaseModel):
    """First frame a live client sends."""

    model_config = ConfigDict(str_strip_whitespace=True)

    type: Literal["start"]
    segment: str = "auto"
    conversation_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")

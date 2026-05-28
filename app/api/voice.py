from __future__ import annotations

from typing import TYPE_CHECKING

import groq as groq_sdk
from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, field_validator

from app.api.deps import get_settings

if TYPE_CHECKING:
    from app.config import Settings

router = APIRouter()


class TTSRequestSchema(BaseModel):
    text: str

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be empty")
        return v


@router.post("/tts")
async def text_to_speech(
    body: TTSRequestSchema,
    settings: Settings = Depends(get_settings),
) -> Response:
    client = groq_sdk.Groq(api_key=settings.groq_api_key)
    audio_response = client.audio.speech.create(
        model=settings.groq_tts_model,
        voice=settings.groq_tts_voice,
        input=body.text,
        response_format="wav",
    )
    return Response(content=audio_response.read(), media_type="audio/wav")


@router.post("/stt")
async def speech_to_text(
    audio: UploadFile,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    client = groq_sdk.Groq(api_key=settings.groq_api_key)
    audio_bytes = await audio.read()
    filename = audio.filename or "audio.webm"
    content_type = audio.content_type or "audio/webm"
    transcription = client.audio.transcriptions.create(
        file=(filename, audio_bytes, content_type),
        model=settings.groq_stt_model,
        language="pt",
        response_format="json",
    )
    return {"transcript": transcription.text}

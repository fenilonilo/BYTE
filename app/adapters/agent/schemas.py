from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.domain.entities import AudioBlock, ContentBlock, ImageBlock, TextBlock


class TextBlockSchema(BaseModel):
    type: Literal["text"] = "text"
    text: str = ""


class ImageBlockSchema(BaseModel):
    type: Literal["image"] = "image"
    url: str | None = None
    base64_data: str | None = None
    mime_type: str = "image/jpeg"


class AudioBlockSchema(BaseModel):
    type: Literal["audio"] = "audio"
    url: str | None = None
    base64_data: str | None = None
    mime_type: str = "audio/mpeg"


ContentBlockSchema = Annotated[
    TextBlockSchema | ImageBlockSchema | AudioBlockSchema,
    Field(discriminator="type"),
]


class GroqOutputSchema(BaseModel):
    complexity: Literal["simple", "complex"]
    content: list[ContentBlockSchema] = []
    tools_called: list[str] = []


class GeminiOutputSchema(BaseModel):
    content: list[ContentBlockSchema]
    tools_called: list[str] = []


def map_content_block(
    schema: TextBlockSchema | ImageBlockSchema | AudioBlockSchema,
) -> ContentBlock:
    if isinstance(schema, TextBlockSchema):
        return TextBlock(type=schema.type, text=schema.text)
    if isinstance(schema, ImageBlockSchema):
        return ImageBlock(
            type=schema.type,
            url=schema.url,
            base64_data=schema.base64_data,
            mime_type=schema.mime_type,
        )
    return AudioBlock(
        type=schema.type,
        url=schema.url,
        base64_data=schema.base64_data,
        mime_type=schema.mime_type,
    )

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

HEADING_SEPARATOR = " 203a "  # a single right-pointing angle quote
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True, slots=True)
class DocumentRef:
    project: str
    rel_path: str


@dataclass(frozen=True, slots=True)
class Chunk:
    ref: DocumentRef
    ordinal: int
    heading: str
    text: str


@dataclass(frozen=True, slots=True)
class SearchHit:
    chunk: Chunk
    score: float


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _sections(text: str) -> list[tuple[str, str]]:
    """(heading path, body) per heading; text before the first heading has an empty path."""
    path: list[str] = []
    heading = ""
    body: list[str] = []
    sections: list[tuple[str, str]] = []
    fenced = False
    for line in text.splitlines():
        if _FENCE.match(line):
            fenced = not fenced
        match = None if fenced else _HEADING.match(line)
        if match is None:
            body.append(line)
            continue
        sections.append((heading, "\n".join(body)))
        level = len(match.group(1))
        path = [*path[: level - 1], match.group(2)]
        heading = HEADING_SEPARATOR.join(path)
        body = []
    sections.append((heading, "\n".join(body)))
    return sections


def _pieces(body: str, max_chars: int) -> list[str]:
    """Pack paragraphs into pieces of at most `max_chars`; a longer paragraph is hard-cut."""
    pieces: list[str] = []
    current = ""
    for paragraph in (p.strip() for p in body.split("\n\n")):
        if not paragraph:
            continue
        parts = [paragraph[i : i + max_chars] for i in range(0, len(paragraph), max_chars)]
        for part in parts:
            joined = f"{current}\n\n{part}" if current else part
            if len(joined) <= max_chars:
                current = joined
            else:
                pieces.append(current)
                current = part
    if current:
        pieces.append(current)
    return pieces


def split_markdown(ref: DocumentRef, text: str, max_chars: int = 1200) -> tuple[Chunk, ...]:
    """Chunks along Markdown headings, each carrying its heading path."""
    chunks: list[Chunk] = []
    for heading, body in _sections(text):
        for piece in _pieces(body, max_chars):
            chunks.append(Chunk(ref, len(chunks), heading, piece))
    return tuple(chunks)

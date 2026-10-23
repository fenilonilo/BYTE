from __future__ import annotations

import hashlib

import pytest

from app.domain.knowledge import HEADING_SEPARATOR, DocumentRef, content_hash, split_markdown

REF = DocumentRef("Byte", "CLAUDE.md")


@pytest.mark.unit
def test_split_keeps_heading_path() -> None:
    text = "# Byte\nintro\n## Safety\n### Network\nloopback only\n"
    chunks = split_markdown(REF, text)
    assert [c.heading for c in chunks] == [
        "Byte",
        HEADING_SEPARATOR.join(["Byte", "Safety", "Network"]),
    ]
    assert chunks[-1].text.strip() == "loopback only"
    assert [c.ordinal for c in chunks] == [0, 1]
    assert all(c.ref == REF for c in chunks)


@pytest.mark.unit
def test_split_text_without_headings_is_one_chunk() -> None:
    assert [(c.heading, c.text) for c in split_markdown(REF, "só texto")] == [("", "só texto")]


@pytest.mark.unit
def test_split_text_before_first_heading_is_kept() -> None:
    chunks = split_markdown(REF, "preâmbulo\n# A\ncorpo")
    assert [(c.heading, c.text) for c in chunks] == [("", "preâmbulo"), ("A", "corpo")]


@pytest.mark.unit
def test_split_long_section_on_paragraphs_under_limit() -> None:
    text = "# A\n" + "\n\n".join(["x" * 500] * 5)
    chunks = split_markdown(REF, text, max_chars=1200)
    assert len(chunks) == 3
    assert all(len(c.text) <= 1200 for c in chunks)


@pytest.mark.unit
def test_split_hard_cuts_a_paragraph_longer_than_limit() -> None:
    chunks = split_markdown(REF, "# A\n" + "y" * 2500, max_chars=1000)
    assert [len(c.text) for c in chunks] == [1000, 1000, 500]


@pytest.mark.unit
def test_split_skips_empty_sections() -> None:
    assert [c.heading for c in split_markdown(REF, "# A\n\n# B\ntexto")] == ["B"]


@pytest.mark.unit
def test_split_ignores_hash_inside_code_fence() -> None:
    chunks = split_markdown(REF, "# A\n```\n# not a heading\n```\n")
    assert [c.heading for c in chunks] == ["A"]


@pytest.mark.unit
def test_content_hash_is_stable_sha256() -> None:
    assert content_hash("a") == hashlib.sha256(b"a").hexdigest()


@pytest.mark.unit
def test_heading_separator_is_the_angle_quote() -> None:
    assert HEADING_SEPARATOR == f" {chr(0x203A)} "

from __future__ import annotations

import json

import pytest

from app.adapters.memory.in_memory_knowledge import InMemoryKnowledge
from app.application.project_session import ProjectSession
from app.application.tools.projects import CloseProject, OpenProject, SearchProjects
from app.domain.exceptions import UnknownProjectError
from app.domain.knowledge import HEADING_SEPARATOR as SEP, Chunk, DocumentRef
from app.domain.projects import Project
from tests.fakes.embedder import FakeEmbedder, fake_vector
from tests.fakes.logger import RecordingLogger
from tests.fakes.terminal import FakeTerminal

BYTE = DocumentRef("Byte", "CLAUDE.md")
FIN = DocumentRef("FinFlow", "CLAUDE.md")


async def store_with(*items: tuple[DocumentRef, str, str]) -> InMemoryKnowledge:
    store = InMemoryKnowledge()
    by_ref: dict[DocumentRef, list[tuple[str, str]]] = {}
    for ref, heading, text in items:
        by_ref.setdefault(ref, []).append((heading, text))
    for ref, pairs in by_ref.items():
        chunks = [Chunk(ref, i, h, t) for i, (h, t) in enumerate(pairs)]
        # the query "pergunta" must find these: give every chunk the query's own vector
        vectors = [fake_vector("pergunta") for _ in chunks]
        await store.replace_document(ref, "d", "fake", chunks, vectors)
    return store


def tool(store: InMemoryKnowledge) -> SearchProjects:
    return SearchProjects(store, FakeEmbedder(), ["Byte", "FinFlow"])


@pytest.mark.unit
async def test_search_returns_tagged_blocks() -> None:
    store = await store_with((BYTE, "Safety", "loopback only"))
    out = await tool(store).execute({"query": "pergunta"}, "k")
    assert out == f"[Byte{SEP}Safety] loopback only"


@pytest.mark.unit
async def test_search_tags_chunk_without_heading_with_project_only() -> None:
    store = await store_with((BYTE, "", "intro"))
    assert await tool(store).execute({"query": "pergunta"}, "k") == "[Byte] intro"


@pytest.mark.unit
async def test_search_filters_by_project() -> None:
    store = await store_with((BYTE, "A", "byte"), (FIN, "B", "fin"))
    out = await tool(store).execute({"query": "pergunta", "project": "FinFlow"}, "k")
    assert out == f"[FinFlow{SEP}B] fin"


@pytest.mark.unit
async def test_search_unknown_project_lists_valid_names() -> None:
    store = await store_with((BYTE, "A", "x"))
    with pytest.raises(UnknownProjectError, match="Byte, FinFlow"):
        await tool(store).execute({"query": "pergunta", "project": "Nope"}, "k")


@pytest.mark.unit
async def test_search_caps_at_2000_chars() -> None:
    store = await store_with(*((BYTE, f"h{i}", "z" * 900) for i in range(4)))
    out = await tool(store).execute({"query": "pergunta"}, "k")
    assert len(out) <= 2000
    assert out.count("[Byte") == 2


@pytest.mark.unit
async def test_search_truncates_a_single_huge_hit() -> None:
    store = await store_with((BYTE, "h", "z" * 3000))
    out = await tool(store).execute({"query": "pergunta"}, "k")
    assert len(out) == 2000
    assert out.startswith(f"[Byte{SEP}h] zzz")


@pytest.mark.unit
async def test_search_no_hits() -> None:
    out = await tool(InMemoryKnowledge()).execute({"query": "pergunta"}, "k")
    assert out == "nada encontrado nos projetos"


@pytest.mark.unit
def test_search_spec_is_read_only_in_projects_segment() -> None:
    spec = tool(InMemoryKnowledge()).spec
    assert spec.name == "search_projects"
    assert spec.segment == "projects"
    assert not spec.requires_confirmation
    assert json.loads(json.dumps(spec.parameters))["required"] == ["query"]


def session_tools() -> tuple[OpenProject, CloseProject, FakeTerminal, ProjectSession]:
    terminal = FakeTerminal()
    projects = [Project("Byte", "D:/P/Byte", ("CLAUDE.md",))]
    session = ProjectSession(terminal, projects, ["claude"], {}, RecordingLogger())
    return OpenProject(session), CloseProject(session), terminal, session


@pytest.mark.unit
async def test_open_project_opens_and_reports() -> None:
    open_, _, terminal, session = session_tools()
    assert await open_.execute({"project": "Byte"}, "k") == "aberto: Byte"
    assert terminal.started[0][0] == "D:/P/Byte"
    await session.aclose()


@pytest.mark.unit
async def test_close_project_reports_both_outcomes() -> None:
    open_, close, _, _ = session_tools()
    assert await close.execute({}, "k") == "nenhum projeto aberto"
    await open_.execute({"project": "Byte"}, "k")
    assert await close.execute({}, "k") == "fechado"


@pytest.mark.unit
def test_open_and_close_are_panel_only_without_confirmation() -> None:
    open_, close, _, _ = session_tools()
    for spec in (open_.spec, close.spec):
        assert spec.panel_only
        assert not spec.requires_confirmation
        assert spec.segment == "projects"
    assert (open_.spec.name, close.spec.name) == ("open_project", "close_project")

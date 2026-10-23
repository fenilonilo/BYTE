from __future__ import annotations

from typing import TYPE_CHECKING

from app.application.tool import Tool
from app.application.tools.args import object_schema, opt_str, str_arg
from app.domain.exceptions import UnknownProjectError
from app.domain.knowledge import HEADING_SEPARATOR
from app.domain.tools import ToolSpec

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from app.application.project_session import ProjectSession
    from app.domain.knowledge import SearchHit
    from app.ports.embedder import EmbedderPort
    from app.ports.knowledge import KnowledgeStorePort

SEGMENT = "projects"
TOP_K = 4
MAX_CHARS = 2000


def _known(names: Sequence[str], name: str) -> str:
    if name not in names:
        raise UnknownProjectError(f"projeto desconhecido; válidos: {', '.join(names)}")
    return name


def _block(hit: SearchHit) -> str:
    title = HEADING_SEPARATOR.join(p for p in (hit.chunk.ref.project, hit.chunk.heading) if p)
    return f"[{title}] {hit.chunk.text}"


class SearchProjects(Tool):
    spec = ToolSpec(
        name="search_projects",
        description=(
            "Busca nos documentos dos projetos de programação do usuário (CLAUDE.md e outros). "
            "Use para qualquer pergunta sobre esses projetos."
        ),
        parameters=object_schema(
            {
                "query": ("string", "O que procurar, em poucas palavras."),
                "project": ("string", "Nome de um projeto, para buscar só nele."),
            },
            required=["query"],
        ),
        segment=SEGMENT,
    )

    def __init__(
        self, store: KnowledgeStorePort, embedder: EmbedderPort, names: Sequence[str]
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._names = tuple(names)

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        query = str_arg(args, "query")
        project = opt_str(args, "project")
        if project is not None:
            _known(self._names, project)
        (vector,) = await self._embedder.embed([query])
        hits = await self._store.search(vector, self._embedder.model, TOP_K, project)
        if not hits:
            return "nada encontrado nos projetos"
        out = _block(hits[0])[:MAX_CHARS]
        for hit in hits[1:]:
            joined = f"{out}\n{_block(hit)}"
            if len(joined) > MAX_CHARS:
                break
            out = joined
        return out


class OpenProject(Tool):
    spec = ToolSpec(
        name="open_project",
        description=(
            "Abre um projeto no terminal do painel e inicia uma sessão nova do Claude Code. "
            "Fecha o projeto que estiver aberto."
        ),
        parameters=object_schema({"project": ("string", "Nome do projeto.")}),
        segment=SEGMENT,
        panel_only=True,
    )

    def __init__(self, session: ProjectSession) -> None:
        self._session = session

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        name = str_arg(args, "project")
        await self._session.open(name)
        return f"aberto: {name}"


class CloseProject(Tool):
    spec = ToolSpec(
        name="close_project",
        description="Fecha o projeto aberto no terminal do painel e volta ao terminal do Byte.",
        parameters=object_schema({}),
        segment=SEGMENT,
        panel_only=True,
    )

    def __init__(self, session: ProjectSession) -> None:
        self._session = session

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        return "fechado" if await self._session.close() else "nenhum projeto aberto"

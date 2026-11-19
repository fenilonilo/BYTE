from __future__ import annotations

from typing import TYPE_CHECKING

from app.application.tool import Tool
from app.application.tools.args import object_schema, str_arg
from app.domain.tools import ToolSpec

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.application.lynus import Lynus

SEGMENT = "projects"


class StartLynus(Tool):
    spec = ToolSpec(
        name="start_lynus",
        description=(
            "Passa uma tarefa de programação ao Lynus, o agente que conduz o Claude Code sozinho "
            "num projeto. Antes de chamar, pergunte ao usuário qual projeto e uma breve "
            "descrição da tarefa, se ele ainda não disse os dois."
        ),
        parameters=object_schema(
            {
                "project": ("string", "Nome do projeto."),
                "task": ("string", "Breve descrição da tarefa, nas palavras do usuário."),
            }
        ),
        segment=SEGMENT,
        panel_only=True,
    )

    def __init__(self, lynus: Lynus) -> None:
        self._lynus = lynus

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        project = str_arg(args, "project")
        await self._lynus.start(project, str_arg(args, "task"))
        return f"Lynus assumiu {project}; a conversa continua com ele no chat."


class LynusStatus(Tool):
    spec = ToolSpec(
        name="lynus_status",
        description="Diz o que o Lynus está fazendo na tarefa de programação que recebeu.",
        parameters=object_schema({}),
        segment=SEGMENT,
    )

    def __init__(self, lynus: Lynus) -> None:
        self._lynus = lynus

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        return self._lynus.status()

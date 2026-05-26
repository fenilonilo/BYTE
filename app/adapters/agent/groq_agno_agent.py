from __future__ import annotations

from typing import TYPE_CHECKING

from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.models.groq import Groq
from agno.tools import Toolkit

from app.adapters.agent.schemas import GroqOutputSchema, map_content_block
from app.domain.entities import AgentResponse, TextBlock
from app.ports.agent import AgentPort

if TYPE_CHECKING:
    from app.config import Settings
    from app.domain.entities import Conversation

_SYSTEM_PROMPT = """Você é Marcelo, assistente pessoal de inteligência artificial.
Personalidade: direto, inteligente, levemente informal, confiante sem ser arrogante.
Fale sempre em português brasileiro, de forma natural como numa conversa real.
Respostas curtas a médias — não faça listas desnecessárias, não seja verboso.
Lembre-se do histórico da conversa e mantenha continuidade natural.

Antes de responder, classifique internamente a complexidade:
- Se a tarefa exige raciocínio profundo multi-etapas, matemática avançada, geração de código complexo ou análise estruturada longa: defina complexity='complex' e content=[]. NÃO responda.
- Caso contrário: complexity='simple' e preencha content com sua resposta completa."""

_SYSTEM_PROMPT_WITH_TOOLS = """Você é Marcelo, assistente pessoal de inteligência artificial.
Personalidade: direto, inteligente, levemente informal, confiante sem ser arrogante.
Fale sempre em português brasileiro, de forma natural como numa conversa real.
Respostas curtas a médias — não faça listas desnecessárias, não seja verboso.
Lembre-se do histórico da conversa e mantenha continuidade natural.

Você tem acesso a ferramentas:
- filesystem: criar, ler, editar, deletar arquivos e pastas em ~/Desktop/marcelo/
- developer: abrir ambiente de desenvolvimento (PyCharm + terminal com claude), enviar prompts ao claude

Quando o usuário disser "cria o projeto X" ou "codar X" ou "abrir projeto X":
  → chame open_dev_environment(project_name="X")

Quando open_dev_environment já foi chamado e o usuário descrever uma tarefa de código:
  → reformate o pedido no seguinte formato e responda APENAS com o texto abaixo:

## Task
[descrição clara e objetiva da tarefa]

## Requisitos
- [item específico e acionável]

## Contexto
Projeto: [nome] | Workspace: ~/Desktop/marcelo/[nome]/

## Constraints
[arquitetura, stack, estilo — se mencionados; omitir se não mencionado]"""


class GroqAgnoAgent(AgentPort):
    def __init__(self, settings: Settings, tools: list[Toolkit] | None = None) -> None:
        self._model_id = settings.groq_tools_model_id if tools else settings.groq_model_id
        self._has_tools = bool(tools)
        agno_db_url = settings.database_url.replace("+asyncpg", "+psycopg").split("?")[0]
        db = PostgresDb(db_url=agno_db_url)
        prompt = _SYSTEM_PROMPT_WITH_TOOLS if tools else _SYSTEM_PROMPT
        self._agent = Agent(
            model=Groq(id=self._model_id),
            db=db,
            tools=tools or [],
            add_history_to_context=True,
            add_datetime_to_context=settings.agno_add_datetime,
            add_location_to_context=settings.agno_add_location,
            # Groq does not allow JSON mode + tool calling simultaneously
            output_schema=None if tools else GroqOutputSchema,
            instructions=[prompt],
        )

    @property
    def model_id(self) -> str:
        return f"groq/{self._model_id}"

    async def run(
        self,
        message: str,
        conversation: Conversation,
        model_override: str | None = None,
    ) -> AgentResponse:
        response = await self._agent.arun(message, session_id=conversation.id)
        if response is None or response.content is None:
            return AgentResponse(
                content=(),
                model_used=self.model_id,
                complexity="simple",
                tools_called=(),
                routed_from=None,
            )
        if self._has_tools:
            # Plain text response when tools active (no output_schema)
            text = str(response.content)
            return AgentResponse(
                content=(TextBlock(text=text),),
                model_used=self.model_id,
                complexity="simple",
                tools_called=(),
                routed_from=None,
            )
        output: GroqOutputSchema = response.content  # type: ignore[assignment]
        return AgentResponse(
            content=tuple(map_content_block(b) for b in output.content),
            model_used=self.model_id,
            complexity=output.complexity,
            tools_called=tuple(output.tools_called),
            routed_from=None,
        )

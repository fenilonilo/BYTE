from __future__ import annotations

import os
from typing import TYPE_CHECKING

from agno.agent import Agent
from agno.models.fallback import FallbackConfig
from agno.models.message import Message as AgnoMessage
from agno.models.utils import get_model
from agno.team import Team
from agno.team.mode import TeamMode

from app.domain.exceptions import AgentError
from app.ports.agent import AgentPort

if TYPE_CHECKING:
    from app.config import Settings
    from app.domain.entities import Conversation

SEGMENT_TIERS: dict[str, str] = {
    "home": "fast",
    "agenda": "balanced",
    "finance": "heavy",
}

TIER_FALLBACKS: dict[str, list[str]] = {
    "router": ["balanced", "fast", "heavy"],
    "fast": ["balanced", "router", "heavy"],
    "balanced": ["router", "heavy", "fast"],
    "heavy": ["balanced", "router", "fast"],
}

SEGMENT_ROLES: dict[str, str] = {
    "home": "Controla luzes, tomadas, sensores e cenas da casa.",
    "agenda": "Cuida de eventos, compromissos e lembretes do calendário.",
    "finance": "Acompanha gastos mensais, contas e totais de despesa.",
}

SEGMENT_INSTRUCTIONS: dict[str, list[str]] = {
    "home": [
        "Você cuida da casa: luzes, tomadas, sensores e cenas.",
        "Antes de desligar algo que esteja em uso ou destrancar uma porta, peça confirmação.",
    ],
    "agenda": [
        "Você cuida do calendário: eventos, compromissos e lembretes.",
        "Antes de apagar ou mover um evento existente, peça confirmação.",
    ],
    "finance": [
        "Você cuida das despesas do mês: gastos, contas e totais.",
        "Ao registrar um gasto, repita valor e categoria para o dono confirmar.",
    ],
}

TEAM_INSTRUCTIONS: list[str] = [
    "Você é o Byte, assistente pessoal de voz de uma única casa.",
    "Encaminhe cada pedido para o membro que cuida do assunto e devolva a resposta dele.",
    "Se o pedido não pertencer a nenhum membro, diga isso em uma frase curta.",
]

COMMON_INSTRUCTIONS: list[str] = [
    "Responda em português do Brasil.",
    "Sua resposta será falada em voz alta: use frases curtas, sem markdown, listas ou emojis.",
]


class AgnoAgent(AgentPort):
    """Wraps one Agno Agent or Team. Agno types never leave this module."""

    def __init__(self, runner: Agent | Team) -> None:
        self._runner = runner

    async def run(self, message: str, conversation: Conversation) -> str:
        history = [AgnoMessage(role=m.role, content=m.content) for m in conversation.messages]
        payload = history or [AgnoMessage(role="user", content=message)]
        try:
            output = await self._runner.arun(input=payload, session_id=conversation.id)
        except Exception as exc:
            raise AgentError(f"Agent run failed: {type(exc).__name__}") from exc

        content = output.content
        if not isinstance(content, str) or not content.strip():
            raise AgentError("Agent returned no text content")
        return content


def _tier_models(settings: Settings) -> dict[str, str]:
    return {
        "router": settings.router_model,
        "fast": settings.fast_model,
        "balanced": settings.balanced_model,
        "heavy": settings.heavy_model,
    }


def resolve_models(settings: Settings) -> dict[str, list[str]]:
    """Segment (plus `auto`) -> its model string followed by its fallback chain."""
    tiers = _tier_models(settings)

    def chain(tier: str) -> list[str]:
        ordered = [tiers[tier], *(tiers[t] for t in TIER_FALLBACKS[tier])]
        return list(dict.fromkeys(ordered))

    resolved: dict[str, list[str]] = {"auto": chain("router")}
    for segment in settings.segments:
        tier = SEGMENT_TIERS.get(segment)
        if tier is None:
            raise AgentError(f"No model tier defined for segment {segment!r}")
        resolved[segment] = chain(tier)
    return resolved


def _export_provider_keys(settings: Settings) -> None:
    """Agno reads provider keys off the environment; Settings holds them."""
    keys = {
        "GOOGLE_API_KEY": settings.gemini_api_key,
        "GROQ_API_KEY": settings.groq_api_key,
    }
    for name, secret in keys.items():
        if secret is not None:
            os.environ.setdefault(name, secret.get_secret_value())


def _provider(model: str) -> str:
    return model.split(":", 1)[0]


def fallbacks_for(chain: list[str]) -> FallbackConfig:
    """A 429 means the model is busy but the provider is up; an error may mean it is not."""
    primary, rest = chain[0], chain[1:]
    cross_first = sorted(rest, key=lambda m: _provider(m) == _provider(primary))
    same_first = sorted(rest, key=lambda m: _provider(m) != _provider(primary))
    return FallbackConfig(on_error=list(cross_first), on_rate_limit=list(same_first))


def build_agents(settings: Settings) -> dict[str, AgentPort]:
    """One Agno Agent per segment, plus the routing Team registered under `auto`."""
    _export_provider_keys(settings)
    chains = resolve_models(settings)

    members: list[Agent] = []
    for segment in settings.segments:
        if segment not in SEGMENT_INSTRUCTIONS:
            raise AgentError(f"No instructions defined for segment {segment!r}")
        members.append(
            Agent(
                name=segment,
                role=SEGMENT_ROLES[segment],
                model=get_model(chains[segment][0]),
                fallback_config=fallbacks_for(chains[segment]),
                instructions=SEGMENT_INSTRUCTIONS[segment] + COMMON_INSTRUCTIONS,
            )
        )

    team = Team(
        name="byte",
        mode=TeamMode.route,
        model=get_model(chains["auto"][0]),
        fallback_config=fallbacks_for(chains["auto"]),
        members=list(members),
        instructions=TEAM_INSTRUCTIONS + COMMON_INSTRUCTIONS,
    )

    agents: dict[str, AgentPort] = {
        segment: AgnoAgent(member)
        for segment, member in zip(settings.segments, members, strict=True)
    }
    agents["auto"] = AgnoAgent(team)
    return agents

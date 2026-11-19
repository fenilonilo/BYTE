from __future__ import annotations

import pytest

from app.application.tools.lynus import LynusStatus, StartLynus
from app.domain.lynus import LynusPhase
from app.domain.model import ModelTurn
from tests.unit.application.test_lynus import World, until


@pytest.mark.unit
async def test_start_lynus_hands_over_and_is_panel_only() -> None:
    w = World([ModelTurn(text="Qual o escopo?")])
    tool = StartLynus(w.lynus)
    assert tool.spec.panel_only
    out = await tool.execute({"project": "Byte", "task": "logs"}, "k")
    assert out == "Lynus assumiu Byte; a conversa continua com ele no chat."
    assert w.lynus.view().phase is LynusPhase.BRIEFING
    await until(lambda: bool(w.notes("lynus")))
    assert w.lynus.view().task == "logs"
    await w.close()


@pytest.mark.unit
async def test_lynus_status_reports_phase_and_last_word() -> None:
    w = World([ModelTurn(text="Qual o escopo?")])
    status = LynusStatus(w.lynus)
    assert not status.spec.panel_only
    assert await status.execute({}, "k") == "o Lynus não está com nenhuma tarefa"
    await w.lynus.start("Byte", "logs")
    await until(lambda: bool(w.notes("lynus")))
    assert await status.execute({}, "k") == "briefing em Byte: Qual o escopo?"
    await w.close()

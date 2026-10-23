from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.config import load_settings
from app.domain.exceptions import ConfigError
from app.domain.projects import Project

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BYTE_API_TOKEN", "k" * 32)
    monkeypatch.setenv("BYTE_OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("BYTE_PROJECTS", raising=False)


@pytest.mark.unit
def test_projects_default_to_none() -> None:
    assert load_settings().project_list() == ()


@pytest.mark.unit
def test_projects_parse_from_json_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "BYTE_PROJECTS",
        '{"FinFlow":{"path":"D:/P/FinFlow"},"Byte":{"path":"D:/P/B","docs":["CLAUDE.md","docs/a.md"]}}',
    )
    assert load_settings().project_list() == (
        Project("Byte", "D:/P/B", ("CLAUDE.md", "docs/a.md")),
        Project("FinFlow", "D:/P/FinFlow", ("CLAUDE.md",)),
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad",
    [
        '{"a b":{"path":"x"}}',
        '{"A":{"path":"x","docs":["../e.md"]}}',
        '{"A":{"path":"x","docs":["C:/abs.md"]}}',
        '{"A":{"path":"x","docs":["/abs.md"]}}',
    ],
)
def test_bad_projects_refuse_boot(bad: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BYTE_PROJECTS", bad)
    with pytest.raises(ConfigError):
        load_settings()


@pytest.mark.unit
def test_knowledge_defaults() -> None:
    s = load_settings()
    assert s.database_url is None
    assert s.embedding_model == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    assert s.knowledge_scan_seconds == 300
    assert s.claude_command == "claude"

from __future__ import annotations

import pytest

from app.domain.projects import is_inside


@pytest.mark.unit
@pytest.mark.parametrize(
    "path", ["CLAUDE.md", "docs/superpowers/specs/x.md", "docs\\plans\\y.md", "./a.md"]
)
def test_relative_paths_inside_the_project_pass(path: str) -> None:
    assert is_inside(path)


@pytest.mark.unit
@pytest.mark.parametrize(
    "path", ["", "../x.md", "docs/../../x", "C:\\Windows\\a", "/etc/passwd", "\\\\srv\\s", "D:x"]
)
def test_escapes_and_absolute_paths_are_refused(path: str) -> None:
    assert not is_inside(path)

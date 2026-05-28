from __future__ import annotations

from typing import TYPE_CHECKING

from app.ports.action import ActionPort

if TYPE_CHECKING:
    from app.adapters.tools.developer_tool import DeveloperToolkit


class OpenProjectAction(ActionPort):
    """Open a dev environment for a project named in params['project'].
    Reuses the existing DeveloperToolkit."""

    def __init__(self, dev_tool: DeveloperToolkit) -> None:
        self._dev = dev_tool

    async def execute(self, params: dict[str, object]) -> None:
        project = params.get("project")
        if isinstance(project, str) and project:
            self._dev.open_dev_environment(project)

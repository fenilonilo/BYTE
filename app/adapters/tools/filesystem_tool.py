from __future__ import annotations

import json
import shutil
from pathlib import Path

from agno.tools import Toolkit


class FilesystemToolkit(Toolkit):
    def __init__(self, workspace_root: Path | None = None) -> None:
        super().__init__(name="filesystem")
        if workspace_root is None:
            workspace_root = Path.home() / "Desktop" / "marcelo"
        workspace_root.mkdir(parents=True, exist_ok=True)
        self._root = workspace_root.resolve()
        self.register(self.list_files)
        self.register(self.read_file)
        self.register(self.create_file)
        self.register(self.write_file)
        self.register(self.delete_file)
        self.register(self.create_folder)
        self.register(self.delete_folder)

    def _resolve(self, rel_path: str) -> Path | None:
        target = (self._root / rel_path).resolve()
        if not str(target).startswith(str(self._root)):
            return None
        return target

    def list_files(self, path: str = "") -> str:
        """List files and folders in the workspace (1 level deep)."""
        target = self._resolve(path) if path else self._root
        if target is None:
            return json.dumps({"error": "path traversal detected"})
        if not target.exists():
            return json.dumps({"error": f"path not found: {path}"})
        entries = [
            {"name": p.name, "type": "dir" if p.is_dir() else "file"}
            for p in sorted(target.iterdir())
        ]
        return json.dumps(entries)

    def read_file(self, path: str) -> str:
        """Read and return the content of a file in the workspace."""
        target = self._resolve(path)
        if target is None:
            return json.dumps({"error": "path traversal detected"})
        if not target.exists():
            return json.dumps({"error": f"file not found: {path}"})
        return target.read_text(encoding="utf-8")

    def create_file(self, path: str, content: str) -> str:
        """Create a new file with content. Creates intermediate directories."""
        target = self._resolve(path)
        if target is None:
            return json.dumps({"error": "path traversal detected"})
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return json.dumps({"ok": True, "path": str(target)})

    def write_file(self, path: str, content: str) -> str:
        """Overwrite an existing file with new content."""
        target = self._resolve(path)
        if target is None:
            return json.dumps({"error": "path traversal detected"})
        target.write_text(content, encoding="utf-8")
        return json.dumps({"ok": True})

    def delete_file(self, path: str) -> str:
        """Delete a file from the workspace."""
        target = self._resolve(path)
        if target is None:
            return json.dumps({"error": "path traversal detected"})
        if not target.exists():
            return json.dumps({"error": f"file not found: {path}"})
        target.unlink()
        return json.dumps({"ok": True})

    def create_folder(self, path: str) -> str:
        """Create a folder in the workspace."""
        target = self._resolve(path)
        if target is None:
            return json.dumps({"error": "path traversal detected"})
        target.mkdir(parents=True, exist_ok=True)
        return json.dumps({"ok": True, "path": str(target)})

    def delete_folder(self, path: str) -> str:
        """Delete a folder and all its contents from the workspace."""
        target = self._resolve(path)
        if target is None:
            return json.dumps({"error": "path traversal detected"})
        if not target.exists():
            return json.dumps({"error": f"folder not found: {path}"})
        shutil.rmtree(target)
        return json.dumps({"ok": True})

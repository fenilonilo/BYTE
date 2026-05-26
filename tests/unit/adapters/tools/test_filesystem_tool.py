from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.adapters.tools.filesystem_tool import FilesystemToolkit


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def toolkit(workspace: Path) -> FilesystemToolkit:
    return FilesystemToolkit(workspace_root=workspace)


def test_create_and_read_file(toolkit: FilesystemToolkit, workspace: Path) -> None:
    result = json.loads(toolkit.create_file("hello.txt", "world"))
    assert result["ok"] is True
    assert (workspace / "hello.txt").read_text() == "world"
    content = toolkit.read_file("hello.txt")
    assert content == "world"


def test_write_file_overwrites(toolkit: FilesystemToolkit, workspace: Path) -> None:
    toolkit.create_file("f.txt", "v1")
    toolkit.write_file("f.txt", "v2")
    assert (workspace / "f.txt").read_text() == "v2"


def test_delete_file(toolkit: FilesystemToolkit, workspace: Path) -> None:
    toolkit.create_file("del.txt", "bye")
    result = json.loads(toolkit.delete_file("del.txt"))
    assert result["ok"] is True
    assert not (workspace / "del.txt").exists()


def test_create_folder(toolkit: FilesystemToolkit, workspace: Path) -> None:
    result = json.loads(toolkit.create_folder("subdir"))
    assert result["ok"] is True
    assert (workspace / "subdir").is_dir()


def test_delete_folder(toolkit: FilesystemToolkit, workspace: Path) -> None:
    (workspace / "todel").mkdir()
    (workspace / "todel" / "f.txt").write_text("x")
    result = json.loads(toolkit.delete_folder("todel"))
    assert result["ok"] is True
    assert not (workspace / "todel").exists()


def test_list_files(toolkit: FilesystemToolkit) -> None:
    toolkit.create_file("a.txt", "")
    toolkit.create_folder("subdir")
    result = json.loads(toolkit.list_files())
    names = [e["name"] for e in result]
    assert "a.txt" in names
    assert "subdir" in names


def test_path_traversal_blocked(toolkit: FilesystemToolkit) -> None:
    result = json.loads(toolkit.read_file("../../etc/passwd"))
    assert "error" in result


def test_create_file_creates_intermediate_dirs(toolkit: FilesystemToolkit, workspace: Path) -> None:
    toolkit.create_file("deep/nested/file.txt", "content")
    assert (workspace / "deep" / "nested" / "file.txt").exists()

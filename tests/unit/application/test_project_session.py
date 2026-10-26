from __future__ import annotations

import pytest

from app.application.claude_bridge import ClaudeBridge
from app.application.project_session import ProjectSession, child_env
from app.domain.exceptions import ProjectError, UnknownProjectError
from app.domain.projects import Project
from tests.fakes.logger import RecordingLogger
from tests.fakes.terminal import FakeTerminal, RecordingListener, settle

BYTE = Project("Byte", "D:/P/Byte", ("CLAUDE.md",))
FIN = Project("FinFlow", "D:/P/FinFlow", ("CLAUDE.md",))
ENV = {"PATH": "C:/bin", "BYTE_API_TOKEN": "secret", "OPENAI_API_KEY": "sk", "HOME": "C:/u"}


def make(scrollback: int = 262144) -> tuple[ProjectSession, FakeTerminal, RecordingLogger]:
    terminal = FakeTerminal()
    log = RecordingLogger()
    session = ProjectSession(
        terminal, [BYTE, FIN], ["C:/bin/claude.exe"], ENV, log, scrollback=scrollback
    )
    return session, terminal, log


@pytest.mark.unit
def test_child_env_drops_byte_and_provider_secrets() -> None:
    env = child_env({**ENV, "GEMINI_API_KEY": "g", "GOOGLE_API_KEY": "g", "byte_web": "1"})
    assert env == {"PATH": "C:/bin", "HOME": "C:/u"}


@pytest.mark.unit
async def test_open_starts_command_in_project_folder() -> None:
    session, terminal, log = make()
    await session.open("FinFlow")
    cwd, argv, _ = terminal.started[0]
    assert (cwd, argv) == ("D:/P/FinFlow", ("C:/bin/claude.exe",))
    assert session.current == "FinFlow"
    assert ("info", "project.opened", {"project": "FinFlow"}) in log.events
    await session.aclose()


@pytest.mark.unit
async def test_open_filters_secrets_from_env() -> None:
    session, terminal, _ = make()
    await session.open("Byte")
    env = terminal.started[0][2]
    assert "BYTE_API_TOKEN" not in env
    assert "OPENAI_API_KEY" not in env
    assert env["PATH"] == "C:/bin"
    await session.aclose()


@pytest.mark.unit
async def test_open_other_project_stops_current() -> None:
    session, terminal, _ = make()
    listener = RecordingListener()
    await session.attach(listener)
    await session.open("Byte")
    await session.open("FinFlow")
    await settle()
    assert terminal.stops == 1
    assert [s[0] for s in terminal.started] == ["D:/P/Byte", "D:/P/FinFlow"]
    assert listener.states == [None, "Byte", "FinFlow"]
    assert session.current == "FinFlow"
    await session.aclose()


@pytest.mark.unit
async def test_open_same_project_starts_fresh() -> None:
    session, terminal, _ = make()
    await session.open("Byte")
    terminal.feed(b"old")
    await settle()
    await session.open("Byte")
    assert terminal.stops == 1
    assert len(terminal.started) == 2
    listener = RecordingListener()
    await session.attach(listener)
    assert listener.received == b""  # a new session starts with an empty scrollback
    await session.aclose()


@pytest.mark.unit
async def test_open_unknown_project_raises() -> None:
    session, terminal, _ = make()
    with pytest.raises(UnknownProjectError, match="Byte, FinFlow"):
        await session.open("Nope")
    assert terminal.started == []


@pytest.mark.unit
async def test_close_returns_false_when_nothing_open() -> None:
    session, _, _ = make()
    assert await session.close() is False


@pytest.mark.unit
async def test_close_stops_and_notifies() -> None:
    session, terminal, _ = make()
    listener = RecordingListener()
    await session.open("Byte")
    await session.attach(listener)
    assert await session.close() is True
    await settle()
    assert terminal.stops == 1
    assert session.current is None
    assert listener.states == ["Byte", None]


@pytest.mark.unit
async def test_output_fans_out_and_fills_scrollback() -> None:
    session, terminal, _ = make()
    a, b = RecordingListener(), RecordingListener()
    await session.attach(a)
    await session.attach(b)
    await session.open("Byte")
    terminal.feed(b"hello")
    await settle()
    assert a.received == b.received == b"hello"
    late = RecordingListener()
    await session.attach(late)
    assert late.received == b"hello"
    await session.aclose()


@pytest.mark.unit
async def test_scrollback_drops_oldest_beyond_limit() -> None:
    session, terminal, _ = make(scrollback=5)
    await session.open("Byte")
    terminal.feed(b"abc")
    terminal.feed(b"defg")
    await settle()
    listener = RecordingListener()
    await session.attach(listener)
    assert listener.received == b"cdefg"
    await session.aclose()


@pytest.mark.unit
async def test_attach_replays_state_then_scrollback() -> None:
    session, terminal, _ = make()
    await session.open("Byte")
    terminal.feed(b"x")
    await settle()
    listener = RecordingListener()
    await session.attach(listener)
    assert listener.events == ["state:Byte", "output:x"]
    await session.aclose()


@pytest.mark.unit
async def test_detached_listener_gets_nothing_more() -> None:
    session, terminal, _ = make()
    listener = RecordingListener()
    await session.attach(listener)
    await session.open("Byte")
    session.detach(listener)
    terminal.feed(b"x")
    await settle()
    assert listener.received == b""
    await session.aclose()


@pytest.mark.unit
async def test_process_exit_clears_current_and_notifies() -> None:
    session, terminal, log = make()
    await session.open("Byte")
    terminal.exit()  # nobody attached when claude exits
    await settle()
    assert session.current is None
    assert "project.exited" in log.names()
    listener = RecordingListener()
    await session.attach(listener)
    assert listener.events == ["state:None"]


@pytest.mark.unit
async def test_write_and_resize_reach_the_open_terminal() -> None:
    session, terminal, _ = make()
    await session.open("Byte")
    await session.write(b"ls\r")
    await session.resize(100, 40)
    assert terminal.written == [b"ls\r"]
    assert terminal.sizes[-1] == (100, 40)
    await session.aclose()


@pytest.mark.unit
async def test_write_without_open_project_is_dropped() -> None:
    session, terminal, _ = make()
    await session.write(b"x")
    await session.resize(80, 24)
    assert terminal.written == []
    assert terminal.sizes == []


@pytest.mark.unit
async def test_reopen_uses_last_size() -> None:
    session, terminal, _ = make()
    await session.open("Byte")
    await session.resize(100, 40)
    await session.open("FinFlow")
    assert terminal.sizes[-1] == (100, 40)
    await session.aclose()


@pytest.mark.unit
async def test_aclose_stops_terminal() -> None:
    session, terminal, _ = make()
    await session.open("Byte")
    await session.aclose()
    assert terminal.stops == 1
    assert session.current is None


@pytest.mark.unit
def test_child_env_drops_the_parent_claude_session_markers() -> None:
    parent = {
        "CLAUDECODE": "1",
        "CLAUDE_PID": "42",
        "CLAUDE_CODE_CHILD_SESSION": "1",
        "CLAUDE_CODE_ENTRYPOINT": "cli",
        "CLAUDE_CODE_SESSION_ID": "s",
        "CLAUDE_CODE_MESSAGING_TOKEN": "t",
        "CLAUDE_CODE_USE_BEDROCK": "1",  # owner config: must survive
    }
    assert child_env({**ENV, **parent}) == {
        "PATH": "C:/bin",
        "HOME": "C:/u",
        "CLAUDE_CODE_USE_BEDROCK": "1",
    }


class BrokenStart(FakeTerminal):
    async def start(self, *args: object, **kwargs: object) -> None:
        raise ProjectError("spawn failed")


class BrokenStop(FakeTerminal):
    async def stop(self) -> None:
        await super().stop()
        raise ProjectError("kill failed")


@pytest.mark.unit
async def test_failed_start_tells_the_panel_nothing_is_open() -> None:
    terminal = BrokenStart()
    session = ProjectSession(terminal, [BYTE], ["claude"], {}, RecordingLogger())
    listener = RecordingListener()
    await session.attach(listener)
    with pytest.raises(ProjectError):
        await session.open("Byte")
    assert session.current is None
    assert listener.states == [None, None]


@pytest.mark.unit
async def test_failed_stop_still_resets_the_session() -> None:
    terminal = BrokenStop()
    session = ProjectSession(terminal, [BYTE], ["claude"], {}, RecordingLogger())
    listener = RecordingListener()
    await session.attach(listener)
    await session.open("Byte")
    with pytest.raises(ProjectError):
        await session.close()
    assert session.current is None
    assert listener.states[-1] is None


def make_bridged() -> tuple[ProjectSession, FakeTerminal, ClaudeBridge]:
    terminal = FakeTerminal()
    log = RecordingLogger()
    bridge = ClaudeBridge("http://127.0.0.1:8000/api/v1/claude/hooks", log)
    session = ProjectSession(
        terminal,
        [BYTE, FIN],
        ["C:/bin/claude.exe"],
        ENV,
        log,
        bridge=(bridge, "D:/data/claude-hooks.json"),
    )
    return session, terminal, bridge


@pytest.mark.unit
async def test_bridged_open_passes_hooks_extra_args_and_a_session_token() -> None:
    session, terminal, bridge = make_bridged()
    await session.open("Byte", ("--permission-mode", "default"))
    _, argv, env = terminal.started[0]
    assert argv == (
        "C:/bin/claude.exe",
        "--settings",
        "D:/data/claude-hooks.json",
        "--permission-mode",
        "default",
    )
    assert bridge.authorized(env["BYTE_BRIDGE_TOKEN"])
    assert "BYTE_API_TOKEN" not in env
    await session.aclose()
    assert not bridge.authorized(env["BYTE_BRIDGE_TOKEN"])


@pytest.mark.unit
async def test_reopening_rotates_the_bridge_token() -> None:
    session, terminal, bridge = make_bridged()
    await session.open("Byte")
    await session.open("FinFlow")
    old, new = (started[2]["BYTE_BRIDGE_TOKEN"] for started in terminal.started)
    assert not bridge.authorized(old)
    assert bridge.authorized(new)
    await session.aclose()


@pytest.mark.unit
async def test_process_exit_ends_the_bridge_session() -> None:
    session, terminal, bridge = make_bridged()
    await session.open("Byte")
    token = terminal.started[0][2]["BYTE_BRIDGE_TOKEN"]
    terminal.exit()
    await settle()
    assert not bridge.authorized(token)
    assert await bridge.next_turn(0.01) is None


@pytest.mark.unit
async def test_unbridged_open_ignores_extra_args_only_for_the_hooks() -> None:
    session, terminal, _ = make()
    await session.open("Byte", ("--permission-mode", "default"))
    _, argv, env = terminal.started[0]
    assert argv == ("C:/bin/claude.exe", "--permission-mode", "default")
    assert "BYTE_BRIDGE_TOKEN" not in env
    await session.aclose()

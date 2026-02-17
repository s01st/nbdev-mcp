"""CLI behavior tests for nbdev_mcp.mcp callback forwarding."""

from __future__ import annotations

from pathlib import Path

import nbdev_mcp.mcp as mcp_module


class DummyContext:
    """Small context object matching Typer's invoked_subcommand attribute."""

    def __init__(self, invoked_subcommand: str | None):
        self.invoked_subcommand = invoked_subcommand


def test_callback_passes_transport_and_watch_options(monkeypatch):
    """Default callback should forward transport/watch options to _run_server."""
    captured: dict = {}

    def fake_run_server(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(mcp_module, "_run_server", fake_run_server)

    mcp_module.callback(
        DummyContext(None),
        version=False,
        project="/tmp/project",
        transport=mcp_module.Transport.http,
        host="0.0.0.0",
        port=8765,
        path="/custom",
        verbose=True,
        watch=True,
        watch_interval=4.5,
        watch_cmd="nbdev_export",
    )

    assert captured == {
        "project": "/tmp/project",
        "transport": mcp_module.Transport.http,
        "host": "0.0.0.0",
        "port": 8765,
        "path": "/custom",
        "verbose": True,
        "watch": True,
        "watch_interval": 4.5,
        "watch_cmd": "nbdev_export",
    }


def test_callback_skips_run_when_subcommand_present(monkeypatch):
    """Callback should not run server when a subcommand is invoked."""
    called = {"value": False}

    def fake_run_server(**kwargs):
        called["value"] = True

    monkeypatch.setattr(mcp_module, "_run_server", fake_run_server)

    mcp_module.callback(
        DummyContext("status"),
        version=False,
        project=None,
        transport=mcp_module.Transport.stdio,
        host="127.0.0.1",
        port=8000,
        path="/mcp",
        verbose=False,
        watch=False,
        watch_interval=2.0,
        watch_cmd="nbdev_export",
    )

    assert called["value"] is False


def test_legacy_script_wrapper_exists_and_calls_main():
    """Legacy scripts/mcp.nbdev.py should remain a thin wrapper."""
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "mcp.nbdev.py"
    text = script_path.read_text(encoding="utf-8")
    assert "from nbdev_mcp.mcp import main" in text
    assert "main()" in text


class _DummyMCP:
    def __init__(self):
        self.calls: list[dict] = []

    def run(self, **kwargs):
        self.calls.append(kwargs)


def _run_server_and_capture_create_kwargs(monkeypatch):
    captured: dict = {}
    dummy = _DummyMCP()

    def fake_create_nbdev_mcp(**kwargs):
        captured.update(kwargs)
        return dummy

    monkeypatch.setattr(mcp_module, "start_stdio_orphan_watchdog", lambda **_: None)
    monkeypatch.setattr(mcp_module, "create_nbdev_mcp", fake_create_nbdev_mcp)
    mcp_module._run_server(transport=mcp_module.Transport.stdio)
    assert dummy.calls == [{"transport": "stdio"}]
    return captured


def test_run_server_recording_env_flag_one_enables_recording_tools(monkeypatch):
    monkeypatch.setenv("NBDEV_MCP_ENABLE_RECORDING_TOOLS", "1")
    monkeypatch.delenv("NBDEV_MCP_AUTO_RECORD", raising=False)
    monkeypatch.delenv("NBDEV_MCP_SESSION_FILE", raising=False)

    captured = _run_server_and_capture_create_kwargs(monkeypatch)
    assert captured["include_recording_tools"] is True


def test_run_server_recording_env_flag_zero_does_not_enable_recording_tools(monkeypatch):
    monkeypatch.setenv("NBDEV_MCP_ENABLE_RECORDING_TOOLS", "0")
    monkeypatch.delenv("NBDEV_MCP_AUTO_RECORD", raising=False)
    monkeypatch.delenv("NBDEV_MCP_SESSION_FILE", raising=False)

    captured = _run_server_and_capture_create_kwargs(monkeypatch)
    assert captured["include_recording_tools"] is False


def test_run_server_auto_record_false_does_not_enable_recording_tools(monkeypatch):
    monkeypatch.delenv("NBDEV_MCP_ENABLE_RECORDING_TOOLS", raising=False)
    monkeypatch.setenv("NBDEV_MCP_AUTO_RECORD", "false")
    monkeypatch.delenv("NBDEV_MCP_SESSION_FILE", raising=False)

    captured = _run_server_and_capture_create_kwargs(monkeypatch)
    assert captured["include_recording_tools"] is False


def test_run_server_session_file_enables_recording_tools(monkeypatch, tmp_path):
    monkeypatch.delenv("NBDEV_MCP_ENABLE_RECORDING_TOOLS", raising=False)
    monkeypatch.delenv("NBDEV_MCP_AUTO_RECORD", raising=False)
    monkeypatch.setenv("NBDEV_MCP_SESSION_FILE", str(tmp_path / "session.json"))

    captured = _run_server_and_capture_create_kwargs(monkeypatch)
    assert captured["include_recording_tools"] is True


def test_should_terminate_stdio_server_respects_grace_period():
    should_terminate = mcp_module.should_terminate_stdio_server(
        initial_parent_pid=111,
        current_parent_pid=1,
        elapsed_seconds=1.5,
        grace_seconds=5.0,
        parent_alive=False,
    )
    assert should_terminate is False


def test_should_terminate_stdio_server_when_parent_pid_changes_after_grace():
    should_terminate = mcp_module.should_terminate_stdio_server(
        initial_parent_pid=111,
        current_parent_pid=222,
        elapsed_seconds=7.5,
        grace_seconds=5.0,
        parent_alive=True,
    )
    assert should_terminate is True


def test_should_terminate_stdio_server_when_parent_dead_after_grace():
    should_terminate = mcp_module.should_terminate_stdio_server(
        initial_parent_pid=111,
        current_parent_pid=111,
        elapsed_seconds=7.5,
        grace_seconds=5.0,
        parent_alive=False,
    )
    assert should_terminate is True


def test_parent_process_alive_handles_missing_and_permission(monkeypatch):
    def missing_pid(pid, sig):
        raise ProcessLookupError("missing")

    monkeypatch.setattr(mcp_module.os, "kill", missing_pid)
    assert mcp_module.parent_process_alive(12345) is False

    def no_permission(pid, sig):
        raise PermissionError("denied")

    monkeypatch.setattr(mcp_module.os, "kill", no_permission)
    assert mcp_module.parent_process_alive(12345) is True


def test_run_server_starts_watchdog_for_stdio(monkeypatch):
    dummy = _DummyMCP()
    started: list[dict] = []

    monkeypatch.delenv("NBDEV_MCP_DISABLE_STDIO_WATCHDOG", raising=False)
    monkeypatch.setattr(mcp_module, "create_nbdev_mcp", lambda **_: dummy)
    monkeypatch.setattr(
        mcp_module,
        "start_stdio_orphan_watchdog",
        lambda **kwargs: started.append(kwargs),
    )

    mcp_module._run_server(transport=mcp_module.Transport.stdio)

    assert dummy.calls == [{"transport": "stdio"}]
    assert len(started) == 1


def test_run_server_does_not_start_watchdog_for_streamable_http(monkeypatch):
    dummy = _DummyMCP()
    started: list[dict] = []

    monkeypatch.setattr(mcp_module, "create_nbdev_mcp", lambda **_: dummy)
    monkeypatch.setattr(
        mcp_module,
        "start_stdio_orphan_watchdog",
        lambda **kwargs: started.append(kwargs),
    )

    mcp_module._run_server(transport=mcp_module.Transport.streamable_http)

    assert dummy.calls == [{"transport": "streamable-http"}]
    assert started == []


def test_run_server_watchdog_can_be_disabled(monkeypatch):
    dummy = _DummyMCP()
    started: list[dict] = []

    monkeypatch.setenv("NBDEV_MCP_DISABLE_STDIO_WATCHDOG", "1")
    monkeypatch.setattr(mcp_module, "create_nbdev_mcp", lambda **_: dummy)
    monkeypatch.setattr(
        mcp_module,
        "start_stdio_orphan_watchdog",
        lambda **kwargs: started.append(kwargs),
    )

    mcp_module._run_server(transport=mcp_module.Transport.stdio)

    assert dummy.calls == [{"transport": "stdio"}]
    assert started == []

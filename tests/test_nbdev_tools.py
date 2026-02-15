"""Tests for nbdev command tool wrappers."""

from pathlib import Path

import nbdev_mcp.tools.nbdev as nbdev_tools


def create_v3_project(tmp_path: Path) -> Path:
    """Create a minimal TOML-configured nbdev project."""
    (tmp_path / "nbs").mkdir()
    (tmp_path / "settings.toml").write_text('lib_name = "v3lib"\nnbs_path = "nbs"\n', encoding="utf-8")
    return tmp_path


def make_ok_result(cmd: list[str], cwd: Path) -> dict:
    """Build a successful subprocess result payload."""
    return {
        "cmd": " ".join(cmd),
        "cwd": str(cwd),
        "returncode": 0,
        "stdout": "",
        "stderr": "",
        "ok": True,
    }


def make_err_result(cmd: list[str], cwd: Path, stderr: str) -> dict:
    """Build a failed subprocess result payload."""
    return {
        "cmd": " ".join(cmd),
        "cwd": str(cwd),
        "returncode": 1,
        "stdout": "",
        "stderr": stderr,
        "ok": False,
    }


def test_nbdev_export_uses_v2_command(monkeypatch, temp_project):
    """V2 project should prefer underscore command names."""
    calls: list[list[str]] = []

    monkeypatch.setattr(nbdev_tools, "resolve_selector", lambda _: temp_project)
    monkeypatch.setattr(nbdev_tools, "wrap_with_env", lambda cmd, _p, _use_env: cmd)

    def fake_run(cmd, cwd):
        calls.append(cmd)
        return make_ok_result(cmd, cwd)

    monkeypatch.setattr(nbdev_tools, "run", fake_run)

    result = nbdev_tools.nbdev_export(project=str(temp_project), use_env=False)

    assert result["ok"] is True
    assert calls[0][0] == "nbdev_export"
    assert result["nbdev_generation"] == "v2"
    assert result["nbdev_command"] == "nbdev_export"


def test_nbdev_export_uses_v3_command(monkeypatch, tmp_path):
    """V3 project should prefer hyphen command names."""
    project = create_v3_project(tmp_path)
    calls: list[list[str]] = []

    monkeypatch.setattr(nbdev_tools, "resolve_selector", lambda _: project)
    monkeypatch.setattr(nbdev_tools, "wrap_with_env", lambda cmd, _p, _use_env: cmd)

    def fake_run(cmd, cwd):
        calls.append(cmd)
        return make_ok_result(cmd, cwd)

    monkeypatch.setattr(nbdev_tools, "run", fake_run)

    result = nbdev_tools.nbdev_export(project=str(project), use_env=False)

    assert result["ok"] is True
    assert calls[0][0] == "nbdev-export"
    assert result["nbdev_generation"] == "v3"
    assert result["nbdev_command"] == "nbdev-export"


def test_nbdev_prepare_falls_back_when_preferred_missing(monkeypatch, tmp_path):
    """If preferred command is missing, tool should retry alternate naming."""
    project = create_v3_project(tmp_path)
    calls: list[list[str]] = []

    monkeypatch.setattr(nbdev_tools, "resolve_selector", lambda _: project)
    monkeypatch.setattr(nbdev_tools, "wrap_with_env", lambda cmd, _p, _use_env: cmd)

    def fake_run(cmd, cwd):
        calls.append(cmd)
        if cmd[0] == "nbdev-prepare":
            return make_err_result(cmd, cwd, "command not found")
        return make_ok_result(cmd, cwd)

    monkeypatch.setattr(nbdev_tools, "run", fake_run)

    result = nbdev_tools.nbdev_prepare(project=str(project), use_env=False)

    assert result["ok"] is True
    assert len(calls) == 2
    assert calls[0][0] == "nbdev-prepare"
    assert calls[1][0] == "nbdev_prepare"
    assert result["nbdev_command"] == "nbdev_prepare"

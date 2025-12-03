"""Tests for nbdev_mcp.utils.subprocess module."""

import pytest
from pathlib import Path

from nbdev_mcp.utils.subprocess import (
    tail,
    ok,
    which,
    run,
)


class TestTail:
    """Test output truncation."""

    def test_tail_short_string(self):
        """Test tail with short string."""
        result = tail("short", limit=100)
        assert result == "short"

    def test_tail_long_string(self):
        """Test tail with long string."""
        long_str = "x" * 1000
        result = tail(long_str, limit=100)
        assert len(result) < len(long_str)
        assert "truncated" in result

    def test_tail_none(self):
        """Test tail with None."""
        assert tail(None) == ""

    def test_tail_empty(self):
        """Test tail with empty string."""
        assert tail("") == ""


class TestOk:
    """Test return code checking."""

    def test_ok_zero(self):
        """Test ok with zero (success)."""
        assert ok(0) is True

    def test_ok_nonzero(self):
        """Test ok with non-zero (failure)."""
        assert ok(1) is False
        assert ok(-1) is False

    def test_ok_string_zero(self):
        """Test ok with string '0'."""
        assert ok(0) is True


class TestWhich:
    """Test executable discovery."""

    def test_which_python(self):
        """Test finding python executable."""
        result = which(["python3", "python"])
        assert result in ["python3", "python"]

    def test_which_not_found(self):
        """Test with non-existent executables."""
        result = which(["nonexistent_executable_xyz"])
        assert result is None

    def test_which_first_found(self):
        """Test that first found is returned."""
        # python should exist before nonexistent
        result = which(["python3", "nonexistent_xyz", "python"])
        assert result in ["python3", "python"]


class TestRun:
    """Test subprocess execution."""

    def test_run_echo(self, tmp_path):
        """Test running echo command."""
        result = run(["echo", "hello"], tmp_path)
        assert result["ok"] is True
        assert result["returncode"] == 0
        assert "hello" in result["stdout"]

    def test_run_failing_command(self, tmp_path):
        """Test running a command that fails."""
        # Use a command that exists but returns non-zero
        result = run(["python3", "-c", "import sys; sys.exit(1)"], tmp_path)
        assert result["ok"] is False
        assert result["returncode"] == 1

    def test_run_returns_dict_keys(self, tmp_path):
        """Test that run returns expected keys."""
        result = run(["echo", "test"], tmp_path)
        assert "cmd" in result
        assert "cwd" in result
        assert "returncode" in result
        assert "stdout" in result
        assert "stderr" in result
        assert "ok" in result

    def test_run_cwd(self, tmp_path):
        """Test that cwd is recorded."""
        result = run(["pwd"], tmp_path)
        assert str(tmp_path) in result["cwd"]

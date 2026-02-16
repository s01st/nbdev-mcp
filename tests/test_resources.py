"""Tests for nbdev_mcp.resources helpers and resource payload safety."""

from __future__ import annotations

import json
from pathlib import Path

import nbdev_mcp.resources as resources


def patch_project(monkeypatch, project_root: Path) -> None:
    """Patch require_project to return a temporary project path."""
    monkeypatch.setattr(resources, "require_project", lambda: project_root)


def test_resource_read_file_blocks_parent_traversal(monkeypatch, tmp_path):
    """Reading outside project via parent traversal should be refused."""
    patch_project(monkeypatch, tmp_path)
    message = resources.resource_read_file("../secret.txt")
    assert "Parent directory traversal is not allowed." in message


def test_resource_read_file_blocks_non_text_suffix(monkeypatch, tmp_path):
    """Non-text file suffixes should be blocked by safety filter."""
    patch_project(monkeypatch, tmp_path)
    binary_file = tmp_path / "artifact.bin"
    binary_file.write_bytes(b"\x00\x01")

    message = resources.resource_read_file("artifact.bin")
    assert "Refusing to read non-text file type" in message


def test_resource_read_file_truncates_large_text(monkeypatch, tmp_path):
    """Large files should be truncated with an explicit suffix message."""
    patch_project(monkeypatch, tmp_path)
    large_file = tmp_path / "LARGE.md"
    large_file.write_text("a" * 210_000, encoding="utf-8")

    content = resources.resource_read_file("LARGE.md")
    assert "...[truncated" in content
    assert len(content) < 210_100


def test_repo_markdown_index_includes_root_and_agent_scoped_docs(monkeypatch, tmp_path):
    """Index should include root markdown and scoped docs under .codex/.claude."""
    (tmp_path / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "TODOs.md").write_text("# TODOs\n", encoding="utf-8")
    patch_project(monkeypatch, tmp_path)

    payload = json.loads(resources.resource_repo_markdown_index())
    relpaths = {item["path"] for item in payload["docs"]}

    assert "ROADMAP.md" in relpaths
    assert ".codex/AGENTS.md" in relpaths
    assert ".claude/TODOs.md" in relpaths


def test_repo_markdown_template_reads_known_key(monkeypatch, tmp_path):
    """Template reader should resolve generated key and return doc content."""
    (tmp_path / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
    patch_project(monkeypatch, tmp_path)

    content = resources.resource_repo_markdown("roadmap")
    assert "# Roadmap" in content


def test_repo_markdown_template_reports_unknown_key(monkeypatch, tmp_path):
    """Template reader should return a helpful message for unknown keys."""
    (tmp_path / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
    patch_project(monkeypatch, tmp_path)

    message = resources.resource_repo_markdown("missing_doc")
    assert "Unknown doc key" in message
    assert "roadmap" in message

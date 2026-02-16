"""Provider config integration tests for install/update/uninstall/status."""

from __future__ import annotations

import json
from pathlib import Path

import nbdev_mcp.mcp as mcp

providerFixturesDir = Path(__file__).parent / "fixtures" / "provider_configs"


def loadProviderFixture(name: str) -> str:
    """Load provider config fixture text by filename."""
    return (providerFixturesDir / name).read_text(encoding="utf-8")


def patch_provider_paths(monkeypatch, provider: mcp.Provider, config_path: Path, settings_path: Path | None = None) -> None:
    """Patch provider path resolution to use temp files."""

    def fake_provider_paths(name: str) -> list[Path]:
        if name == provider.value:
            return [config_path]
        return []

    def fake_selected_path(name: str) -> Path | None:
        if name == provider.value:
            return config_path
        return None

    monkeypatch.setattr(mcp, "get_provider_config_paths", fake_provider_paths)
    monkeypatch.setattr(mcp, "select_provider_config_path", fake_selected_path)

    if settings_path is not None:
        monkeypatch.setattr(mcp, "get_vscode_settings_path_from_utils", lambda: settings_path)
        monkeypatch.setattr(mcp, "get_cursor_settings_path_from_utils", lambda: settings_path)


def test_vscode_install_update_uninstall_with_jsonc(monkeypatch, tmp_path):
    """JSONC configs should be merged safely and support lifecycle actions."""
    config_path = tmp_path / "mcp.json"
    settings_path = tmp_path / "settings.json"
    patch_provider_paths(monkeypatch, mcp.Provider.vscode, config_path, settings_path=settings_path)

    config_path.write_text(
        """{
  // keep existing servers
  "servers": {
    "other": {
      "type": "stdio",
      "command": "python",
      "args": []
    },
  },
}
""",
        encoding="utf-8",
    )

    ok = mcp.update_provider_config(
        mcp.Provider.vscode,
        strategy="merge",
        dry_run=False,
        auto_start=True,
        backup=True,
    )
    assert ok is True

    updated = json.loads(config_path.read_text(encoding="utf-8"))
    assert "servers" in updated
    assert "other" in updated["servers"]
    assert "nbdev" in updated["servers"]
    assert updated["servers"]["nbdev"]["type"] == "stdio"
    assert updated["servers"]["nbdev"]["args"] == ["-u", "-m", "nbdev_mcp"]

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert settings["chat.mcp.autostart"] is True

    backups = list(tmp_path.glob("mcp.json.*.bak"))
    assert backups, "expected backup file to be created"

    status = mcp.check_provider_status(mcp.Provider.vscode)
    assert status["installed"] is True
    assert status["exists"] is True
    assert status["format"] == "json"
    assert status["autostart"] is True

    removed = mcp.uninstall_from_provider(mcp.Provider.vscode, dry_run=False, backup=False)
    assert removed is True
    after_uninstall = json.loads(config_path.read_text(encoding="utf-8"))
    assert "nbdev" not in after_uninstall["servers"]
    assert "other" in after_uninstall["servers"]


def test_update_dry_run_shows_diff_and_does_not_write(monkeypatch, tmp_path, capsys):
    """Dry-run update should print a unified diff and avoid file writes."""
    config_path = tmp_path / "mcp.json"
    patch_provider_paths(monkeypatch, mcp.Provider.vscode, config_path, settings_path=tmp_path / "settings.json")

    before = '{"servers": {}}\n'
    config_path.write_text(before, encoding="utf-8")

    ok = mcp.update_provider_config(
        mcp.Provider.vscode,
        strategy="merge",
        dry_run=True,
        auto_start=False,
        backup=True,
    )
    assert ok is True
    assert config_path.read_text(encoding="utf-8") == before

    captured = capsys.readouterr().out
    assert "Unified diff" in captured


def test_parse_failure_is_fail_safe(monkeypatch, tmp_path):
    """Invalid JSON should abort update without modifying file."""
    config_path = tmp_path / "mcp.json"
    patch_provider_paths(monkeypatch, mcp.Provider.vscode, config_path, settings_path=tmp_path / "settings.json")

    malformed = '{"servers": {"x": [}\n'
    config_path.write_text(malformed, encoding="utf-8")

    ok = mcp.update_provider_config(
        mcp.Provider.vscode,
        strategy="merge",
        dry_run=False,
        auto_start=False,
        backup=True,
    )
    assert ok is False
    assert config_path.read_text(encoding="utf-8") == malformed
    assert not list(tmp_path.glob("mcp.json.*.bak"))


def test_codex_toml_update_and_uninstall(monkeypatch, tmp_path):
    """Codex TOML config should get nbdev table inserted and removed safely."""
    config_path = tmp_path / "config.toml"
    patch_provider_paths(monkeypatch, mcp.Provider.codex, config_path)

    config_path.write_text(
        """model = "gpt-5.1-codex-max"
model_provider = "openai"

[mcp_servers.other]
command = "python"
args = []
""",
        encoding="utf-8",
    )

    ok = mcp.install_to_provider(mcp.Provider.codex, dry_run=False, auto_start=False, backup=False)
    assert ok is True

    content = config_path.read_text(encoding="utf-8")
    assert '[mcp_servers.nbdev]' in content
    assert 'model = "gpt-5.1-codex-max"' in content
    assert '[mcp_servers.other]' in content

    status = mcp.check_provider_status(mcp.Provider.codex)
    assert status["installed"] is True
    assert status["format"] == "toml"

    removed = mcp.uninstall_from_provider(mcp.Provider.codex, dry_run=False, backup=False)
    assert removed is True
    after = config_path.read_text(encoding="utf-8")
    assert '[mcp_servers.nbdev]' not in after
    assert '[mcp_servers.other]' in after


def test_claude_install_status_uninstall_with_jsonc_fixture(monkeypatch, tmp_path):
    """Claude JSONC config should preserve existing entries through lifecycle actions."""
    config_path = tmp_path / "claude.json"
    patch_provider_paths(monkeypatch, mcp.Provider.claude, config_path)

    config_path.write_text(loadProviderFixture("claude_with_existing.jsonc"), encoding="utf-8")

    installed = mcp.install_to_provider(
        mcp.Provider.claude,
        dry_run=False,
        auto_start=False,
        backup=True,
    )
    assert installed is True

    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert "mcpServers" in data
    assert "other" in data["mcpServers"]
    assert "nbdev" in data["mcpServers"]
    assert "type" not in data["mcpServers"]["nbdev"]

    status = mcp.check_provider_status(mcp.Provider.claude)
    assert status["installed"] is True
    assert status["format"] == "json"
    assert status["exists"] is True

    backups = list(tmp_path.glob("claude.json.*.bak"))
    assert backups, "expected backup file to be created"

    removed = mcp.uninstall_from_provider(mcp.Provider.claude, dry_run=False, backup=False)
    assert removed is True
    after = json.loads(config_path.read_text(encoding="utf-8"))
    assert "nbdev" not in after["mcpServers"]
    assert "other" in after["mcpServers"]


def test_cursor_update_sets_autostart_and_status(monkeypatch, tmp_path):
    """Cursor update should write stdio server entry and enable autostart settings."""
    config_path = tmp_path / "mcp.json"
    settings_path = tmp_path / "settings.json"
    patch_provider_paths(monkeypatch, mcp.Provider.cursor, config_path, settings_path=settings_path)

    config_path.write_text(loadProviderFixture("cursor_with_existing.jsonc"), encoding="utf-8")

    updated = mcp.update_provider_config(
        mcp.Provider.cursor,
        strategy="merge",
        dry_run=False,
        auto_start=True,
        backup=False,
    )
    assert updated is True

    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert "servers" in data
    assert "other" in data["servers"]
    assert "nbdev" in data["servers"]
    assert data["servers"]["nbdev"]["type"] == "stdio"
    assert data["servers"]["nbdev"]["autoStart"] is True

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert settings["chat.mcp.autostart"] is True

    status = mcp.check_provider_status(mcp.Provider.cursor)
    assert status["installed"] is True
    assert status["autostart"] is True


def test_codex_invalid_toml_fails_without_write(monkeypatch, tmp_path):
    """Invalid TOML should fail safely without mutating provider config."""
    config_path = tmp_path / "config.toml"
    patch_provider_paths(monkeypatch, mcp.Provider.codex, config_path)

    malformed = loadProviderFixture("codex_invalid.toml")
    config_path.write_text(malformed, encoding="utf-8")

    ok = mcp.update_provider_config(
        mcp.Provider.codex,
        strategy="merge",
        dry_run=False,
        auto_start=False,
        backup=True,
    )
    assert ok is False
    assert config_path.read_text(encoding="utf-8") == malformed
    assert not list(tmp_path.glob("config.toml.*.bak"))


def test_claude_status_reports_parse_error(monkeypatch, tmp_path):
    """Status should flag parse errors and avoid false positive installs."""
    config_path = tmp_path / "claude.json"
    patch_provider_paths(monkeypatch, mcp.Provider.claude, config_path)

    config_path.write_text('{"mcpServers": {"x": [}\n', encoding="utf-8")
    status = mcp.check_provider_status(mcp.Provider.claude)

    assert status["exists"] is True
    assert status["installed"] is False
    assert status["error"] == "parse error"

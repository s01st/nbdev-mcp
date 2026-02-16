"""Tests for nbdev_mcp.tools.project module."""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from nbdev_mcp.tools.project import (
    set_project,
    current_project,
    console_scripts_status,
    find_projects,
    bookmark_project,
    list_bookmarks,
    remove_bookmark,
    config_status,
    prompt_templates_status,
    mcp_scaffold_guide,
    scaffold_mcp_notebooks,
    mcp_contract_snapshot,
    mcp_contract_diff,
    mcp_provider_drift_report,
    mcp_composition_workbench,
    mcp_compatibility_matrix,
    mcp_contract_ci_gate,
    mcp_policy_pack,
)


class TestSetProject:
    """Tests for set_project function."""

    def test_set_project_invalid_path(self):
        """set_project returns error for invalid path."""
        result = set_project('/nonexistent/path/to/project')
        assert result['ok'] is False
        assert 'error' in result

    def test_set_project_not_nbdev(self, tmp_path):
        """set_project returns error for non-nbdev directory."""
        result = set_project(str(tmp_path))
        assert result['ok'] is False
        assert 'error' in result


class TestCurrentProject:
    """Tests for current_project function."""

    def test_current_project_no_project(self, tmp_path):
        """current_project raises when cwd is not nbdev project."""
        import os
        import nbdev_mcp.utils.config
        import nbdev_mcp.utils.paths

        old_project = nbdev_mcp.utils.config.CURRENT_PROJECT
        old_paths_project = nbdev_mcp.utils.paths.CURRENT_PROJECT
        original_cwd = os.getcwd()

        nbdev_mcp.utils.config.CURRENT_PROJECT = None
        nbdev_mcp.utils.paths.CURRENT_PROJECT = None

        try:
            os.chdir(tmp_path)
            with pytest.raises(RuntimeError):
                current_project()
        finally:
            os.chdir(original_cwd)
            nbdev_mcp.utils.config.CURRENT_PROJECT = old_project
            nbdev_mcp.utils.paths.CURRENT_PROJECT = old_paths_project

    def test_current_project_defaults_to_cwd(self, project_root):
        """current_project uses cwd if it's an nbdev project."""
        import os
        import nbdev_mcp.utils.config
        import nbdev_mcp.utils.paths

        old_project = nbdev_mcp.utils.config.CURRENT_PROJECT
        old_paths_project = nbdev_mcp.utils.paths.CURRENT_PROJECT
        original_cwd = os.getcwd()

        nbdev_mcp.utils.config.CURRENT_PROJECT = None
        nbdev_mcp.utils.paths.CURRENT_PROJECT = None

        try:
            os.chdir(project_root)
            result = current_project()
            assert result['ok'] is True
            assert result['project']['project'] == str(project_root)
        finally:
            os.chdir(original_cwd)
            nbdev_mcp.utils.config.CURRENT_PROJECT = old_project
            nbdev_mcp.utils.paths.CURRENT_PROJECT = old_paths_project


class TestConsoleScriptsStatus:
    """Tests for console_scripts_status function."""

    def test_console_scripts_no_project(self, tmp_path):
        """console_scripts_status returns error with no project in non-nbdev dir."""
        import os
        import nbdev_mcp.utils.config
        import nbdev_mcp.utils.paths

        old_project = nbdev_mcp.utils.config.CURRENT_PROJECT
        old_paths_project = nbdev_mcp.utils.paths.CURRENT_PROJECT
        original_cwd = os.getcwd()

        nbdev_mcp.utils.config.CURRENT_PROJECT = None
        nbdev_mcp.utils.paths.CURRENT_PROJECT = None

        try:
            os.chdir(tmp_path)
            result = console_scripts_status()
            assert result['ok'] is False
        finally:
            os.chdir(original_cwd)
            nbdev_mcp.utils.config.CURRENT_PROJECT = old_project
            nbdev_mcp.utils.paths.CURRENT_PROJECT = old_paths_project


class TestFindProjects:
    """Tests for find_projects function."""

    def test_find_projects_empty_roots(self):
        """find_projects with no valid roots returns empty list."""
        result = find_projects(roots=['/nonexistent/path'])
        assert result['ok'] is True
        assert 'results' in result

    def test_find_projects_returns_list(self):
        """find_projects returns a list of project summaries."""
        result = find_projects(max_results=5)
        assert result['ok'] is True
        assert isinstance(result.get('results', []), list)


class TestBookmarks:
    """Tests for bookmark functions."""

    def test_list_bookmarks(self):
        """list_bookmarks returns aliases dict."""
        result = list_bookmarks()
        assert result['ok'] is True
        assert 'aliases' in result
        assert isinstance(result['aliases'], dict)

    def test_remove_nonexistent_bookmark(self):
        """remove_bookmark returns error for unknown alias."""
        result = remove_bookmark('nonexistent_alias_12345')
        assert result['ok'] is False
        assert 'error' in result


class TestProjectToolsIntegration:
    """Integration tests using a real nbdev project structure."""

    @pytest.fixture
    def mock_nbdev_project(self, tmp_path):
        """Create a minimal nbdev project structure."""
        # Create settings.ini
        settings = tmp_path / 'settings.ini'
        settings.write_text("""[DEFAULT]
lib_name = testlib
nbs_path = nbs
""")
        # Create nbs directory
        nbs_dir = tmp_path / 'nbs'
        nbs_dir.mkdir()
        # Create a minimal notebook
        nb = nbs_dir / 'index.ipynb'
        nb.write_text('{"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}')
        return tmp_path

    @pytest.fixture
    def mock_nbdev_project_toml(self, tmp_path):
        """Create a minimal TOML-based nbdev project structure."""
        (tmp_path / 'settings.toml').write_text(
            'lib_name = "testlibtoml"\n'
            'nbs_path = "nbs"\n'
            'console_scripts = ["mycli=testlibtoml:main"]\n'
        )
        nbs_dir = tmp_path / 'nbs'
        nbs_dir.mkdir()
        nb = nbs_dir / 'index.ipynb'
        nb.write_text('{"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}')
        return tmp_path

    def test_set_project_returns_summary(self, mock_nbdev_project):
        """set_project returns project summary on success."""
        result = set_project(str(mock_nbdev_project))
        assert result['ok'] is True
        assert 'project' in result
        assert result['project']['lib_name'] == 'testlib'

    def test_console_scripts_status_with_path(self, mock_nbdev_project):
        """console_scripts_status works with explicit project path."""
        result = console_scripts_status(project=str(mock_nbdev_project))
        assert result['ok'] is True
        assert result['entries'] == []

    def test_console_scripts_status_with_toml_path(self, mock_nbdev_project_toml):
        """console_scripts_status reads TOML-based config."""
        result = console_scripts_status(project=str(mock_nbdev_project_toml))
        assert result['ok'] is True
        assert result['settings_file'] == 'settings.toml'
        assert result['nbdev_generation'] == 'v3'
        assert 'mycli=testlibtoml:main' in result['entries']


class TestConfigStatus:
    """Tests for config_status tool."""

    def test_config_status_returns_ok(self):
        """config_status returns success result."""
        result = config_status()
        assert result['ok'] is True

    def test_config_status_has_config_dict(self):
        """config_status includes config values."""
        result = config_status()
        assert 'config' in result
        cfg = result['config']
        assert 'log_level' in cfg
        assert 'prompt_dir' in cfg
        assert 'env_dir_name' in cfg
        assert 'max_tree_files' in cfg

    def test_config_status_has_bookmarks_path(self):
        """config_status includes bookmarks path."""
        result = config_status()
        assert 'bookmarks_path' in result
        assert '.config' in result['bookmarks_path'] or 'AppData' in result['bookmarks_path']

    def test_config_status_has_pretty_output(self):
        """config_status includes formatted output."""
        result = config_status()
        assert 'pretty' in result
        assert 'Configuration' in result['pretty']

    def test_config_status_shows_env_overrides(self, monkeypatch):
        """config_status detects environment variable overrides."""
        monkeypatch.setenv('NBMCP_LOG_LEVEL', 'DEBUG')
        result = config_status()
        assert 'env_overrides' in result
        assert result['env_overrides'].get('NBMCP_LOG_LEVEL') == 'DEBUG'


class TestPromptTemplatesStatus:
    """Tests for prompt_templates_status tool."""

    def test_prompt_templates_status_returns_ok(self):
        """prompt_templates_status returns success result."""
        result = prompt_templates_status()
        assert result['ok'] is True

    def test_prompt_templates_status_lists_templates(self):
        """prompt_templates_status lists available templates."""
        result = prompt_templates_status()
        assert 'templates' in result
        templates = result['templates']
        assert len(templates) >= 5  # Should have multiple templates

    def test_prompt_templates_status_shows_paths(self):
        """prompt_templates_status shows paths for each template."""
        result = prompt_templates_status()
        for t in result['templates']:
            assert 'name' in t
            assert 'path' in t
            assert 'exists' in t

    def test_prompt_templates_status_has_prompt_dir(self):
        """prompt_templates_status shows configured prompt_dir."""
        result = prompt_templates_status()
        assert 'prompt_dir' in result
        assert result['prompt_dir'] == 'prompt_templates'

    def test_prompt_templates_status_has_pretty_output(self):
        """prompt_templates_status includes formatted output."""
        result = prompt_templates_status()
        assert 'pretty' in result
        assert 'Template' in result['pretty']


class TestMcpScaffoldGuide:
    """Tests for mcp_scaffold_guide tool."""

    def test_mcp_scaffold_guide_returns_expected_sections(self):
        """Guide should include notebooks, symbols, and checklist."""
        result = mcp_scaffold_guide()
        assert result["ok"] is True
        assert result["server_name"] == "mcp.custom"
        assert isinstance(result["notebooks"], list)
        assert isinstance(result["checklist"], list)
        assert "settings_patch" in result

    def test_mcp_scaffold_guide_respects_arguments(self):
        """Guide should reflect server_name/module_prefix arguments."""
        result = mcp_scaffold_guide(server_name="mcp.demo", module_prefix="70_demo")
        assert result["server_name"] == "mcp.demo"
        assert all(item["path"].startswith("nbs/70_demo/") for item in result["notebooks"])


class TestScaffoldMcpNotebooks:
    """Tests for scaffold_mcp_notebooks tool."""

    def test_scaffold_mcp_notebooks_dry_run(self, temp_project):
        """Dry run should report planned file creation."""
        result = scaffold_mcp_notebooks(
            project=str(temp_project),
            module_prefix="70_factory",
            package_name="factory_pkg",
            dry_run=True,
        )
        assert result["ok"] is True
        assert result["create_count"] == 5
        assert all("nbs/70_factory/" in path for path in result["create_paths"])

    def test_scaffold_mcp_notebooks_writes_files(self, temp_project):
        """Non-dry run should create notebook files."""
        result = scaffold_mcp_notebooks(
            project=str(temp_project),
            module_prefix="71_factory",
            package_name="factory_pkg",
            dry_run=False,
        )
        assert result["ok"] is True
        assert result["created_count"] == 5
        for path in result["created_paths"]:
            assert Path(path).exists()


class TestMcpContractTools:
    """Tests for MCP contract snapshot/diff tools."""

    def test_mcp_contract_snapshot_in_memory(self):
        """Snapshot should return contract metadata without writing."""
        result = mcp_contract_snapshot(write_file=False)
        assert result["ok"] is True
        contract = result["contract"]
        assert contract["tool_count"] > 0
        assert len(contract["contract_hash"]) == 64

    def test_mcp_contract_snapshot_write_and_diff(self, tmp_path):
        """Snapshot file should be consumable by contract diff tool."""
        baseline_path = tmp_path / "contract.json"
        snap = mcp_contract_snapshot(
            output_path=str(baseline_path),
            write_file=True,
        )
        assert snap["ok"] is True
        assert baseline_path.exists()

        diff = mcp_contract_diff(baseline_path=str(baseline_path))
        assert diff["ok"] is True
        assert "breaking" in diff


class TestMcpOpsTools:
    """Tests for MCP operational planning/reporting tools."""

    def test_provider_drift_report_returns_rows(self):
        """Provider drift report should return provider summaries."""
        result = mcp_provider_drift_report()
        assert result["ok"] is True
        assert "providers" in result
        assert isinstance(result["providers"], list)
        assert len(result["providers"]) >= 1

    def test_composition_workbench_returns_plan(self):
        """Composition workbench should produce architecture recommendations."""
        result = mcp_composition_workbench(local_servers=2, remote_servers=1, requires_transforms=True)
        assert result["ok"] is True
        assert isinstance(result["architecture"], list)
        assert isinstance(result["recommendations"], list)
        assert len(result["recommendations"]) > 0


class TestMcpGovernanceTools:
    """Tests for MCP governance and compatibility tools."""

    def test_mcp_compatibility_matrix_ready_provider(self, monkeypatch):
        """Compatibility matrix should classify ready providers correctly."""
        monkeypatch.setattr(
            "nbdev_mcp.tools.project.mcp_provider_drift_report",
            lambda provider=None: {
                "ok": True,
                "drifted_count": 0,
                "providers": [
                    {
                        "provider": "codex",
                        "exists": True,
                        "installed": True,
                        "drifted": False,
                        "format": "toml",
                        "path": "/tmp/config.toml",
                    }
                ],
            },
        )
        monkeypatch.setattr("nbdev_mcp.tools.project.resolve_selector", lambda value=None: Path("/tmp/project"))
        monkeypatch.setattr("nbdev_mcp.tools.project.nbdev_generation", lambda path: "v3")

        result = mcp_compatibility_matrix(project="/tmp/project")

        assert result["ok"] is True
        assert result["ready_count"] == 1
        assert result["matrix"][0]["readiness"] == "ready"
        assert result["nbdev_generation"] == "v3"

    def test_mcp_contract_ci_gate_allows_additive_changes(self, monkeypatch):
        """CI gate should pass when only additive changes are present and allowed."""
        monkeypatch.setattr(
            "nbdev_mcp.tools.project.mcp_contract_diff",
            lambda baseline_path, current_path=None, server_name="mcp.nbdev": {
                "ok": True,
                "breaking": False,
                "added_tools": ["new_tool"],
                "removed_tools": [],
                "changed_tool_schemas": [],
                "added_resources": [],
                "removed_resources": [],
                "added_prompts": [],
                "removed_prompts": [],
                "baseline_hash": "abc",
                "current_hash": "def",
            },
        )

        result = mcp_contract_ci_gate(baseline_path="contracts/baseline.json")

        assert result["ok"] is True
        assert result["passed"] is True
        assert result["exit_code"] == 0
        assert result["violations"] == []
        assert len(result["notices"]) == 1

    def test_mcp_contract_ci_gate_blocks_schema_changes(self, monkeypatch):
        """CI gate should fail on schema changes."""
        monkeypatch.setattr(
            "nbdev_mcp.tools.project.mcp_contract_diff",
            lambda baseline_path, current_path=None, server_name="mcp.nbdev": {
                "ok": True,
                "breaking": True,
                "added_tools": [],
                "removed_tools": [],
                "changed_tool_schemas": ["set_project"],
                "added_resources": [],
                "removed_resources": [],
                "added_prompts": [],
                "removed_prompts": [],
                "baseline_hash": "abc",
                "current_hash": "def",
            },
        )

        result = mcp_contract_ci_gate(baseline_path="contracts/baseline.json")

        assert result["ok"] is True
        assert result["passed"] is False
        assert result["exit_code"] == 1
        assert any("schema changes" in item for item in result["violations"])

    def test_mcp_policy_pack_strict_fails_on_provider_drift(self, monkeypatch):
        """Strict policy should fail when provider drift is detected."""
        monkeypatch.setattr(
            "nbdev_mcp.tools.project.mcp_contract_ci_gate",
            lambda baseline_path, current_path=None, server_name="mcp.nbdev", allow_additive_tools=True, allow_additive_resources=True, allow_additive_prompts=True: {
                "ok": True,
                "passed": True,
                "exit_code": 0,
                "violations": [],
            },
        )
        monkeypatch.setattr(
            "nbdev_mcp.tools.project.mcp_provider_drift_report",
            lambda provider=None: {
                "ok": True,
                "drifted_count": 1,
                "providers": [{"provider": "codex", "drifted": True}],
            },
        )

        result = mcp_policy_pack(profile="strict", baseline_path="contracts/baseline.json")

        assert result["ok"] is True
        assert result["passed"] is False
        assert any("Provider drift detected" in item for item in result["violations"])

    def test_mcp_policy_pack_rejects_unknown_profile(self):
        """Unknown profile names should return a validation error."""
        result = mcp_policy_pack(profile="unknown")
        assert result["ok"] is False
        assert "Unknown profile" in result["error"]

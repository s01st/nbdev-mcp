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
        assert isinstance(result["exported_symbols"], list)
        assert isinstance(result["checklist"], list)

    def test_mcp_scaffold_guide_respects_arguments(self):
        """Guide should reflect server_name/module_prefix arguments."""
        result = mcp_scaffold_guide(server_name="mcp.demo", module_prefix="70_demo")
        assert result["server_name"] == "mcp.demo"
        assert all(path.startswith("nbs/70_demo/") for path in result["notebooks"])

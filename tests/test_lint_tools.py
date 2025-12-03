"""Tests for nbdev_mcp.tools.lint module."""
import pytest
import json
from pathlib import Path

from nbdev_mcp.tools.lint import (
    validate_inits,
    lint_rules,
    lint_main_guards,
)


class TestValidateInits:
    """Tests for validate_inits function."""

    def test_validate_inits_no_project(self):
        """validate_inits returns error with no project."""
        import nbdev_mcp.utils.config
        old_project = nbdev_mcp.utils.config.CURRENT_PROJECT
        nbdev_mcp.utils.config.CURRENT_PROJECT = None
        try:
            result = validate_inits()
            assert result['ok'] is False
        finally:
            nbdev_mcp.utils.config.CURRENT_PROJECT = old_project


class TestLintRules:
    """Tests for lint_rules function."""

    def test_lint_rules_no_project(self):
        """lint_rules returns error with no project."""
        import nbdev_mcp.utils.config
        old_project = nbdev_mcp.utils.config.CURRENT_PROJECT
        nbdev_mcp.utils.config.CURRENT_PROJECT = None
        try:
            result = lint_rules()
            assert result['ok'] is False
        finally:
            nbdev_mcp.utils.config.CURRENT_PROJECT = old_project


class TestLintMainGuards:
    """Tests for lint_main_guards function."""

    def test_lint_main_guards_no_project(self):
        """lint_main_guards returns error with no project."""
        import nbdev_mcp.utils.config
        old_project = nbdev_mcp.utils.config.CURRENT_PROJECT
        nbdev_mcp.utils.config.CURRENT_PROJECT = None
        try:
            result = lint_main_guards()
            assert result['ok'] is False
        finally:
            nbdev_mcp.utils.config.CURRENT_PROJECT = old_project


class TestLintToolsIntegration:
    """Integration tests using a mock nbdev project."""

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
        return tmp_path

    @pytest.fixture
    def project_with_notebooks(self, mock_nbdev_project):
        """Add sample notebooks to the project."""
        nbs_dir = mock_nbdev_project / 'nbs'

        # Create index.ipynb
        index_nb = {
            "cells": [
                {"cell_type": "markdown", "metadata": {}, "source": ["# Test Project"]},
                {"cell_type": "code", "metadata": {}, "source": ["#| hide\nimport testlib"], "outputs": [], "execution_count": None}
            ],
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 5
        }
        (nbs_dir / 'index.ipynb').write_text(json.dumps(index_nb))

        # Create a module notebook
        module_nb = {
            "cells": [
                {"cell_type": "code", "metadata": {}, "source": ["#| default_exp utils"], "outputs": [], "execution_count": None},
                {"cell_type": "code", "metadata": {}, "source": ["#| export\ndef helper(): pass"], "outputs": [], "execution_count": None}
            ],
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 5
        }
        (nbs_dir / '01_utils.ipynb').write_text(json.dumps(module_nb))

        return mock_nbdev_project

    def test_validate_inits_no_init_notebooks(self, project_with_notebooks):
        """validate_inits passes when no __init__ notebooks exist."""
        result = validate_inits(project=str(project_with_notebooks))
        assert result['ok'] is True
        assert result['problems'] == []

    def test_lint_rules_clean_project(self, project_with_notebooks):
        """lint_rules on a clean project returns minimal issues."""
        result = lint_rules(project=str(project_with_notebooks))
        assert result['ok'] is True
        assert 'issues' in result

    def test_lint_main_guards_no_guards(self, project_with_notebooks):
        """lint_main_guards passes when no unsafe guards exist."""
        result = lint_main_guards(project=str(project_with_notebooks))
        assert result['ok'] is True
        assert result['issues'] == []

    def test_lint_rules_detects_all_definition(self, mock_nbdev_project):
        """lint_rules detects manual __all__ definitions."""
        nbs_dir = mock_nbdev_project / 'nbs'
        # Create notebook with __all__ definition
        bad_nb = {
            "cells": [
                {"cell_type": "code", "metadata": {}, "source": ["#| default_exp bad"], "outputs": [], "execution_count": None},
                {"cell_type": "code", "metadata": {}, "source": ["#| export\n__all__ = ['foo']"], "outputs": [], "execution_count": None}
            ],
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 5
        }
        (nbs_dir / 'index.ipynb').write_text(json.dumps(bad_nb))

        result = lint_rules(project=str(mock_nbdev_project))

        # Should detect the __all__ issue
        all_issues = [i for i in result['issues'] if i.get('rule') == 'no_manual___all__']
        assert len(all_issues) >= 1

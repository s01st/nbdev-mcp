"""Tests for nbdev_mcp.tools.analysis module."""
import pytest
import json
from pathlib import Path

from nbdev_mcp.tools.analysis import (
    analyze_dependency_order,
    dependency_tree,
)


class TestAnalyzeDependencyOrder:
    """Tests for analyze_dependency_order function."""

    def test_analyze_dependency_order_no_project(self):
        """analyze_dependency_order returns error with no project."""
        import nbdev_mcp.utils.config
        old_project = nbdev_mcp.utils.config.CURRENT_PROJECT
        nbdev_mcp.utils.config.CURRENT_PROJECT = None
        try:
            result = analyze_dependency_order()
            assert result['ok'] is False
        finally:
            nbdev_mcp.utils.config.CURRENT_PROJECT = old_project


class TestDependencyTree:
    """Tests for dependency_tree function."""

    def test_dependency_tree_no_project(self):
        """dependency_tree returns error with no project."""
        import nbdev_mcp.utils.config
        old_project = nbdev_mcp.utils.config.CURRENT_PROJECT
        nbdev_mcp.utils.config.CURRENT_PROJECT = None
        try:
            result = dependency_tree()
            assert result['ok'] is False
        finally:
            nbdev_mcp.utils.config.CURRENT_PROJECT = old_project


class TestAnalysisToolsIntegration:
    """Integration tests using a mock nbdev project."""

    @pytest.fixture
    def mock_nbdev_project(self, tmp_path):
        """Create a minimal nbdev project structure."""
        settings = tmp_path / 'settings.ini'
        settings.write_text("""[DEFAULT]
lib_name = testlib
nbs_path = nbs
""")
        nbs_dir = tmp_path / 'nbs'
        nbs_dir.mkdir()
        return tmp_path

    @pytest.fixture
    def project_with_deps(self, mock_nbdev_project):
        """Create a project with module dependencies."""
        nbs_dir = mock_nbdev_project / 'nbs'

        # Create base module (no deps)
        base_nb = {
            "cells": [
                {"cell_type": "code", "metadata": {}, "source": ["#| default_exp core"], "outputs": [], "execution_count": None},
                {"cell_type": "code", "metadata": {}, "source": ["#| export\ndef base_func(): pass"], "outputs": [], "execution_count": None}
            ],
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 5
        }
        (nbs_dir / '01_core.ipynb').write_text(json.dumps(base_nb))

        # Create dependent module
        utils_nb = {
            "cells": [
                {"cell_type": "code", "metadata": {}, "source": ["#| default_exp utils"], "outputs": [], "execution_count": None},
                {"cell_type": "code", "metadata": {}, "source": ["#| export\nfrom testlib.core import base_func"], "outputs": [], "execution_count": None}
            ],
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 5
        }
        (nbs_dir / '02_utils.ipynb').write_text(json.dumps(utils_nb))

        # Create index.ipynb
        index_nb = {
            "cells": [{"cell_type": "markdown", "metadata": {}, "source": ["# Test"]}],
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 5
        }
        (nbs_dir / 'index.ipynb').write_text(json.dumps(index_nb))

        return mock_nbdev_project

    def test_analyze_dependency_order_basic(self, project_with_deps):
        """analyze_dependency_order works on project with deps."""
        result = analyze_dependency_order(project=str(project_with_deps))
        assert result['ok'] is True
        assert 'suggestions' in result

    def test_dependency_tree_internal(self, project_with_deps):
        """dependency_tree generates internal dependency graph."""
        result = dependency_tree(project=str(project_with_deps), scope='internal')
        assert result['ok'] is True
        assert 'edges' in result
        assert 'mermaid' in result
        assert 'dot' in result

    def test_dependency_tree_external(self, project_with_deps):
        """dependency_tree can show external dependencies."""
        result = dependency_tree(project=str(project_with_deps), scope='external')
        assert result['ok'] is True
        assert 'nodes_external' in result

    def test_dependency_tree_mermaid_format(self, project_with_deps):
        """dependency_tree mermaid output is valid format."""
        result = dependency_tree(project=str(project_with_deps), scope='internal')
        mermaid = result['mermaid']
        assert 'graph LR' in mermaid

    def test_dependency_tree_dot_format(self, project_with_deps):
        """dependency_tree DOT output is valid format."""
        result = dependency_tree(project=str(project_with_deps), scope='internal')
        dot = result['dot']
        assert 'digraph G' in dot
        assert 'rankdir=LR' in dot

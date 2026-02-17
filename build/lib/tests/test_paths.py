"""Tests for nbdev_mcp.utils.paths module."""

import pytest
from pathlib import Path

from nbdev_mcp.utils.paths import (
    expand,
    settings_dict,
    lib_name,
    nbs_dir,
    tutorials_dir,
    is_nbdev_project,
    env_file,
    find_project_root,
    iter_notebooks,
    project_summary,
    read_nb,
    write_nb,
    resolve_relative,
)
from nbdev_mcp.utils.nb import join_source, find_default_exp


class TestExpand:
    """Test path expansion."""

    def test_expand_tilde(self):
        """Test ~ expansion."""
        result = expand("~")
        assert result.is_absolute()
        assert "~" not in str(result)

    def test_expand_relative(self):
        """Test relative path becomes absolute."""
        result = expand(".")
        assert result.is_absolute()


class TestSettingsDict:
    """Test settings.ini parsing."""

    def test_settings_dict_returns_dict(self, temp_project):
        """Test settings_dict returns a dict."""
        result = settings_dict(temp_project)
        assert isinstance(result, dict)
        assert "lib_name" in result

    def test_settings_dict_missing_file(self, tmp_path):
        """Test settings_dict with no settings.ini."""
        result = settings_dict(tmp_path)
        assert result == {}


class TestLibName:
    """Test lib_name extraction."""

    def test_lib_name_from_settings(self, temp_project):
        """Test lib_name reads from settings.ini."""
        result = lib_name(temp_project)
        assert result == "testlib"

    def test_lib_name_fallback(self, tmp_path):
        """Test lib_name fallback to 'pkg'."""
        result = lib_name(tmp_path)
        assert result == "pkg"


class TestProjectDirs:
    """Test project directory functions."""

    def test_nbs_dir(self, temp_project):
        """Test nbs_dir returns correct path."""
        result = nbs_dir(temp_project)
        assert result == temp_project / "nbs"

    def test_tutorials_dir(self, temp_project):
        """Test tutorials_dir returns correct path."""
        result = tutorials_dir(temp_project)
        assert result == temp_project / "tutorials"

    def test_is_nbdev_project_true(self, temp_project):
        """Test is_nbdev_project with valid project."""
        assert is_nbdev_project(temp_project)

    def test_is_nbdev_project_false(self, tmp_path):
        """Test is_nbdev_project with non-project."""
        assert not is_nbdev_project(tmp_path)


class TestIterNotebooks:
    """Test notebook iteration."""

    def test_iter_notebooks(self, temp_project):
        """Test iter_notebooks finds notebooks."""
        notebooks = list(iter_notebooks(temp_project))
        assert len(notebooks) == 1
        assert notebooks[0].suffix == ".ipynb"


class TestProjectSummary:
    """Test project summary."""

    def test_project_summary(self, temp_project):
        """Test project_summary returns expected keys."""
        result = project_summary(temp_project)
        assert "project" in result
        assert "lib_name" in result
        assert "nbs_dir" in result
        assert "has_index_ipynb" in result
        assert "has_readme" in result


class TestNotebookIO:
    """Test notebook read/write."""

    def test_read_nb(self, temp_project):
        """Test reading a notebook."""
        nb_path = temp_project / "nbs" / "00_core.ipynb"
        data = read_nb(nb_path)
        assert "cells" in data
        assert "nbformat" in data

    def test_write_nb(self, temp_project, sample_notebook_data):
        """Test writing a notebook."""
        nb_path = temp_project / "nbs" / "test_write.ipynb"
        write_nb(nb_path, sample_notebook_data)
        assert nb_path.exists()
        data = read_nb(nb_path)
        assert data["nbformat"] == 4


class TestJoinSource:
    """Test source line joining."""

    def test_join_empty(self):
        """Test joining empty list."""
        assert join_source([]) == ""

    def test_join_with_newlines(self):
        """Test joining lines with newlines."""
        lines = ["line1\n", "line2\n"]
        result = join_source(lines)
        # Result should contain both lines joined by newline
        assert "line1" in result
        assert "line2" in result
        assert result.count("\n") >= 1

    def test_join_without_newlines(self):
        """Test joining lines without newlines."""
        lines = ["line1", "line2"]
        result = join_source(lines)
        assert "line1" in result
        assert "line2" in result


class TestFindDefaultExp:
    """Test default_exp finding."""

    def test_find_default_exp(self, sample_notebook_data):
        """Test finding default_exp directive."""
        result = find_default_exp(sample_notebook_data)
        assert result == "test_module"

    def test_find_default_exp_not_found(self):
        """Test when no default_exp exists."""
        data = {"cells": [{"cell_type": "code", "source": ["pass"]}]}
        result = find_default_exp(data)
        assert result is None


class TestResolveRelative:
    """Test relative import resolution."""

    def test_resolve_relative_single_dot(self):
        """Test single dot relative import."""
        result = resolve_relative("pkg.sub.mod", ".utils")
        assert result == "pkg.sub.utils"

    def test_resolve_relative_double_dot(self):
        """Test double dot relative import."""
        result = resolve_relative("pkg.sub.mod", "..core")
        assert result == "pkg.core"

    def test_resolve_relative_no_dots(self):
        """Test absolute import passthrough."""
        result = resolve_relative("pkg.mod", "other.module")
        assert result == "other.module"

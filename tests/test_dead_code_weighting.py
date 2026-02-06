"""Tests for dead-code weighting using module depth and tutorial usage."""

import json
from pathlib import Path

from nbdev_mcp.tools.lint import lint_dead_exports
from nbdev_mcp.tasks.cache import get_orphan_symbols


def _write_nb(path: Path, cells) -> None:
    nb_data = {
        "cells": cells,
        "metadata": {"kernelspec": {"display_name": "python3", "language": "python", "name": "python3"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path.write_text(json.dumps(nb_data, indent=2))


def _setup_project(tmp_path: Path) -> Path:
    (tmp_path / "nbs").mkdir()
    (tmp_path / "tutorials").mkdir()
    (tmp_path / "testlib").mkdir()

    (tmp_path / "settings.ini").write_text(
        "[DEFAULT]\nlib_name = testlib\nnbs_path = nbs\n",
        encoding="utf-8",
    )
    return tmp_path


def test_lint_dead_exports_weighting(tmp_path: Path):
    """lint_dead_exports should weight by module depth and tutorial usage."""
    project = _setup_project(tmp_path)

    # Shallow module: utils (depth 1)
    _write_nb(
        project / "nbs" / "01_utils.ipynb",
        [
            {"cell_type": "code", "metadata": {}, "source": ["#| default_exp utils"], "outputs": [], "execution_count": None},
            {"cell_type": "code", "metadata": {}, "source": ["#| export\n", "def foo():\n", "    return 1\n"], "outputs": [], "execution_count": None},
        ],
    )

    # Deeper module: sub.core (depth 2)
    (project / "nbs" / "10_sub").mkdir()
    _write_nb(
        project / "nbs" / "10_sub" / "02_core.ipynb",
        [
            {"cell_type": "code", "metadata": {}, "source": ["#| default_exp sub.core"], "outputs": [], "execution_count": None},
            {"cell_type": "code", "metadata": {}, "source": ["#| export\n", "def bar():\n", "    return 2\n"], "outputs": [], "execution_count": None},
        ],
    )

    # Tutorial imports foo => treated as used, so foo should not be dead
    _write_nb(
        project / "tutorials" / "00_tut.ipynb",
        [
            {"cell_type": "code", "metadata": {}, "source": ["from testlib.utils import foo\n", "foo()\n"], "outputs": [], "execution_count": None},
        ],
    )

    result = lint_dead_exports(project=str(project))
    assert result["ok"] is False
    items = result["dead_exports"]
    assert len(items) == 1
    assert items[0]["symbol"] == "bar"
    assert items[0]["module_depth"] == 2
    assert items[0]["concern_weight"] == 2


def test_orphan_symbols_weighting(tmp_path: Path):
    """get_orphan_symbols should include weighting metadata."""
    project = _setup_project(tmp_path)

    _write_nb(
        project / "nbs" / "01_utils.ipynb",
        [
            {"cell_type": "code", "metadata": {}, "source": ["#| default_exp utils"], "outputs": [], "execution_count": None},
            {"cell_type": "code", "metadata": {}, "source": ["#| export\n", "def foo():\n", "    return 1\n"], "outputs": [], "execution_count": None},
        ],
    )

    # Tutorial references foo without import; should still mark used_in_tutorials
    _write_nb(
        project / "tutorials" / "00_tut.ipynb",
        [
            {"cell_type": "code", "metadata": {}, "source": ["foo()\n"], "outputs": [], "execution_count": None},
        ],
    )

    result = get_orphan_symbols(project=str(project), min_lines=1)
    assert result["ok"] is True
    items = result["orphans"]
    assert len(items) >= 1
    foo = next(i for i in items if i["symbol"] == "foo")
    assert foo["used_in_tutorials"] is True
    assert foo["concern_weight"] == max(0, foo["module_depth"] - 1)

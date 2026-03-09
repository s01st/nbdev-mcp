"""Tests for execute_cell notebook editing helper."""

import json
from pathlib import Path

from nbdev_mcp.tools.editing import execute_cell


def _write_notebook(path: Path, cells: list[dict]) -> None:
    """Write a minimal notebook payload."""
    payload = {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "python3",
                "language": "python",
                "name": "python3",
            }
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_execute_cell_runs_code_cell(temp_project: Path):
    """Code cells should execute and capture stdout."""
    nb_path = temp_project / "nbs" / "01_exec.ipynb"
    _write_notebook(
        nb_path,
        [
            {
                "cell_type": "code",
                "metadata": {},
                "source": ["print('hello from execute_cell')\n"],
                "outputs": [],
                "execution_count": None,
            }
        ],
    )

    result = execute_cell(project=str(temp_project), notebook="01_exec.ipynb", cell_index=0, timeout=30)

    assert result["ok"] is True
    assert result["cell_type"] == "code"
    assert "hello from execute_cell" in result["stdout"]
    assert result["error"] is None


def test_execute_cell_returns_structured_error(temp_project: Path):
    """Cell exceptions should be returned as structured error payloads."""
    nb_path = temp_project / "nbs" / "02_exec_error.ipynb"
    _write_notebook(
        nb_path,
        [
            {
                "cell_type": "code",
                "metadata": {},
                "source": ["raise ValueError('boom')\n"],
                "outputs": [],
                "execution_count": None,
            }
        ],
    )

    result = execute_cell(project=str(temp_project), notebook="02_exec_error.ipynb", cell_index=0, timeout=30)

    assert result["ok"] is False
    assert isinstance(result["error"], dict)
    assert result["error"]["ename"] == "ValueError"
    assert "boom" in result["error"]["evalue"]
    assert isinstance(result["error"]["traceback"], list)


def test_execute_cell_handles_list_source(temp_project: Path):
    """List-form source should execute without conversion errors."""
    nb_path = temp_project / "nbs" / "03_exec_list_source.ipynb"
    _write_notebook(
        nb_path,
        [
            {
                "cell_type": "code",
                "metadata": {},
                "source": ["x = 1\n", "y = 2\n", "print(x + y)\n"],
                "outputs": [],
                "execution_count": None,
            }
        ],
    )

    result = execute_cell(project=str(temp_project), notebook="03_exec_list_source.ipynb", cell_index=0, timeout=30)

    assert result["ok"] is True
    assert result["stdout"].strip() == "3"
    assert result["error"] is None


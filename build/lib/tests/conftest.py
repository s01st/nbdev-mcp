"""Shared pytest fixtures for nbdev-mcp tests."""

import pytest
from pathlib import Path
import tempfile
import json


@pytest.fixture
def project_root() -> Path:
    """Return the nbmcp project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture
def nbs_dir(project_root: Path) -> Path:
    """Return the notebooks directory."""
    return project_root / "nbs"


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Create a temporary nbdev project structure for testing."""
    # Create minimal nbdev project structure
    (tmp_path / "nbs").mkdir()
    (tmp_path / "testlib").mkdir()

    # Create settings.ini
    settings = tmp_path / "settings.ini"
    settings.write_text("""[DEFAULT]
lib_name = testlib
nbs_path = nbs
""")

    # Create a sample notebook
    nb_data = {
        "cells": [
            {
                "cell_type": "code",
                "source": ["#| default_exp core"],
                "metadata": {},
                "outputs": [],
                "execution_count": None
            },
            {
                "cell_type": "code",
                "source": ["#| export\n", "def hello(): return 'world'"],
                "metadata": {},
                "outputs": [],
                "execution_count": None
            }
        ],
        "metadata": {"kernelspec": {"display_name": "python3", "language": "python", "name": "python3"}},
        "nbformat": 4,
        "nbformat_minor": 5
    }

    nb_path = tmp_path / "nbs" / "00_core.ipynb"
    nb_path.write_text(json.dumps(nb_data, indent=2))

    return tmp_path


@pytest.fixture
def sample_notebook_data() -> dict:
    """Return sample notebook data for testing."""
    return {
        "cells": [
            {
                "cell_type": "markdown",
                "source": ["# Test Notebook\n", "\n", "Description here"],
                "metadata": {}
            },
            {
                "cell_type": "code",
                "source": ["#| default_exp test_module"],
                "metadata": {},
                "outputs": [],
                "execution_count": None
            },
            {
                "cell_type": "code",
                "source": ["#| export\n", "def my_func():\n", "    '''A test function.'''\n", "    pass"],
                "metadata": {},
                "outputs": [],
                "execution_count": None
            },
            {
                "cell_type": "code",
                "source": ["#| hide\n", "# This cell is hidden"],
                "metadata": {},
                "outputs": [],
                "execution_count": None
            },
            {
                "cell_type": "code",
                "source": ["#| eval: false\n", "# This cell won't execute during tests"],
                "metadata": {},
                "outputs": [],
                "execution_count": None
            }
        ],
        "metadata": {"kernelspec": {"display_name": "python3", "language": "python", "name": "python3"}},
        "nbformat": 4,
        "nbformat_minor": 5
    }

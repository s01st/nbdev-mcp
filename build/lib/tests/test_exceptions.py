"""Tests for nbdev_mcp.utils.exceptions module."""

import pytest
import warnings
from pathlib import Path
from nbdev_mcp.utils.exceptions import (
    NotebookLocation,
    NotebookException,
    ProjectNotFoundError,
    NotebookNotFoundError,
    CellNotFoundError,
    ExportError,
    LintError,
    NbdevMcpWarning,
    DeprecationWarningNbdev,
    StyleWarning,
    warn_with_location,
    raise_with_location,
)


class TestNotebookLocation:
    """Test NotebookLocation dataclass."""

    def test_basic_location(self):
        """Test basic location creation."""
        loc = NotebookLocation("03_utils.ipynb", cell=5, line=10)
        assert loc.notebook == "03_utils.ipynb"
        assert loc.cell == 5
        assert loc.line == 10

    def test_str_full(self):
        """Test string representation with all fields."""
        loc = NotebookLocation("03_utils.ipynb", cell=5, line=10)
        assert str(loc) == "03_utils.ipynb:cell[5]:line[10]"

    def test_str_no_line(self):
        """Test string representation without line."""
        loc = NotebookLocation("03_utils.ipynb", cell=5)
        assert str(loc) == "03_utils.ipynb:cell[5]"

    def test_str_no_cell(self):
        """Test string representation without cell."""
        loc = NotebookLocation("03_utils.ipynb")
        assert str(loc) == "03_utils.ipynb"

    def test_from_path(self):
        """Test creation from Path object."""
        path = Path("/some/dir/03_utils.ipynb")
        loc = NotebookLocation.from_path(path, cell=3, line=5)
        assert loc.notebook == "03_utils.ipynb"
        assert loc.cell == 3
        assert loc.line == 5


class TestNotebookException:
    """Test base exception class."""

    def test_basic_error(self):
        """Test basic error without location."""
        err = NotebookException("Something went wrong")
        assert str(err) == "Something went wrong"
        assert err.location is None

    def test_error_with_location(self):
        """Test error with location."""
        loc = NotebookLocation("03_utils.ipynb", cell=5)
        err = NotebookException("Something went wrong", location=loc)
        assert "[03_utils.ipynb:cell[5]]" in str(err)
        assert err.location == loc

    def test_raise_and_catch(self):
        """Test raising and catching."""
        with pytest.raises(NotebookException) as exc_info:
            raise NotebookException("Test error")
        assert "Test error" in str(exc_info.value)


class TestSpecificExceptions:
    """Test specific exception classes."""

    def test_project_not_found_error(self):
        """Test ProjectNotFoundError."""
        err = ProjectNotFoundError("my-project")
        assert "my-project" in str(err)
        assert err.selector == "my-project"

    def test_notebook_not_found_error(self):
        """Test NotebookNotFoundError."""
        err = NotebookNotFoundError("/path/to/notebook.ipynb")
        assert "/path/to/notebook.ipynb" in str(err)
        assert err.path == "/path/to/notebook.ipynb"

    def test_cell_not_found_error(self):
        """Test CellNotFoundError."""
        err = CellNotFoundError("03_utils.ipynb", cell_index=100, total_cells=50)
        assert "100" in str(err)
        assert "50" in str(err)
        assert err.cell_index == 100
        assert err.total_cells == 50
        assert err.location is not None

    def test_export_error(self):
        """Test ExportError."""
        err = ExportError("Export failed")
        assert "Export failed" in str(err)

    def test_lint_error(self):
        """Test LintError."""
        loc = NotebookLocation("03_utils.ipynb", cell=10)
        err = LintError("no-relative-imports", "Found relative import", location=loc)
        assert "[no-relative-imports]" in str(err)
        assert "relative import" in str(err)
        assert err.rule == "no-relative-imports"


class TestWarnings:
    """Test warning classes."""

    def test_base_warning(self):
        """Test base warning class."""
        warn = NbdevMcpWarning("This is a warning")
        assert str(warn) == "This is a warning"

    def test_warning_with_location(self):
        """Test warning with location."""
        loc = NotebookLocation("03_utils.ipynb", cell=5)
        warn = NbdevMcpWarning("This is a warning", location=loc)
        assert "[03_utils.ipynb:cell[5]]" in str(warn)

    def test_deprecation_warning(self):
        """Test deprecation warning subclass."""
        warn = DeprecationWarningNbdev("Feature X is deprecated")
        assert isinstance(warn, NbdevMcpWarning)

    def test_style_warning(self):
        """Test style warning subclass."""
        warn = StyleWarning("Consider using snake_case")
        assert isinstance(warn, NbdevMcpWarning)


class TestHelperFunctions:
    """Test helper functions."""

    def test_warn_with_location(self):
        """Test warn_with_location function."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            warn_with_location("Test warning", notebook="03_utils.ipynb", cell=5)
            assert len(w) == 1
            assert "Test warning" in str(w[0].message)
            assert issubclass(w[0].category, NbdevMcpWarning)

    def test_warn_without_location(self):
        """Test warn_with_location without notebook."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            warn_with_location("Test warning")
            assert len(w) == 1

    def test_raise_with_location(self):
        """Test raise_with_location function."""
        with pytest.raises(NotebookException) as exc_info:
            raise_with_location("Test error", notebook="03_utils.ipynb", cell=5)
        assert "Test error" in str(exc_info.value)
        assert "[03_utils.ipynb:cell[5]]" in str(exc_info.value)

    def test_raise_with_custom_class(self):
        """Test raise_with_location with custom exception class."""
        with pytest.raises(ExportError):
            raise_with_location("Export failed", exc_class=ExportError)

"""Tests for nbdev_mcp.utils.nb module."""
import pytest
from pathlib import Path

from nbdev_mcp.utils.nb import (
    join_source,
    truncate,
    Cell,
    NBFile,
    has_export,
    has_hide,
    has_eval_false,
    get_default_exp,
    find_default_exp,
    Symbol,
    Import,
    extract_symbols,
    extract_imports,
    split_imports,
    iter_export_cells,
    search_cells,
)


class TestJoinSource:
    """Tests for join_source function."""

    def test_join_string_passthrough(self):
        """String input is returned as-is."""
        assert join_source("hello") == "hello"

    def test_join_empty_list(self):
        """Empty list returns empty string."""
        assert join_source([]) == ""

    def test_join_lines_with_newlines(self):
        """Lines already ending with newlines are joined."""
        result = join_source(["line1\n", "line2\n"])
        assert "line1" in result
        assert "line2" in result

    def test_join_lines_without_newlines(self):
        """Lines without newlines get newlines added."""
        result = join_source(["line1", "line2"])
        assert "line1" in result
        assert "line2" in result


class TestTruncate:
    """Tests for truncate function."""

    def test_short_string_unchanged(self):
        """Short strings are returned unchanged."""
        assert truncate("hello", 100) == "hello"

    def test_long_string_truncated(self):
        """Long strings are truncated with indicator."""
        result = truncate("a" * 1000, 100)
        assert len(result) < 1000
        assert "truncated" in result.lower()

    def test_empty_string(self):
        """Empty string returns empty string."""
        assert truncate("") == ""

    def test_none_returns_empty(self):
        """None input returns empty string."""
        assert truncate(None) == ""


class TestCell:
    """Tests for Cell dataclass."""

    def test_cell_creation(self):
        """Cell can be created with required fields."""
        cell = Cell(index=0, cell_type="code", source="print('hi')", raw={})
        assert cell.index == 0
        assert cell.cell_type == "code"
        assert cell.source == "print('hi')"

    def test_cell_lines(self):
        """Cell.lines splits source into lines."""
        cell = Cell(0, "code", "line1\nline2\nline3", {})
        assert cell.lines == ["line1", "line2", "line3"]

    def test_is_code(self):
        """Cell.is_code returns True for code cells."""
        code_cell = Cell(0, "code", "", {})
        md_cell = Cell(0, "markdown", "", {})
        assert code_cell.is_code is True
        assert md_cell.is_code is False

    def test_is_markdown(self):
        """Cell.is_markdown returns True for markdown cells."""
        code_cell = Cell(0, "code", "", {})
        md_cell = Cell(0, "markdown", "", {})
        assert md_cell.is_markdown is True
        assert code_cell.is_markdown is False


class TestNbFile:
    """Tests for NBFile dataclass."""

    def test_nbfile_creation(self):
        """NBFile can be created with path and data."""
        data = {"cells": [{"cell_type": "code", "source": ["print(1)"]}]}
        nb = NBFile(path=Path("test.ipynb"), data=data)
        assert nb.path == Path("test.ipynb")

    def test_cells_property(self):
        """NBFile.cells returns list of Cell objects."""
        data = {
            "cells": [
                {"cell_type": "code", "source": ["x = 1"]},
                {"cell_type": "markdown", "source": ["# Title"]},
            ]
        }
        nb = NBFile(Path("test.ipynb"), data)
        cells = nb.cells
        assert len(cells) == 2
        assert cells[0].is_code
        assert cells[1].is_markdown

    def test_code_cells_method(self):
        """NBFile.code_cells filters to code cells only."""
        data = {
            "cells": [
                {"cell_type": "code", "source": ["x = 1"]},
                {"cell_type": "markdown", "source": ["# Title"]},
                {"cell_type": "code", "source": ["y = 2"]},
            ]
        }
        nb = NBFile(Path("test.ipynb"), data)
        code_cells = list(nb.code_cells())
        assert len(code_cells) == 2
        assert all(c.is_code for c in code_cells)


class TestDirectiveDetection:
    """Tests for directive detection functions."""

    def test_has_export_basic(self):
        """has_export detects #| export."""
        assert has_export("#| export\ndef foo(): pass") is True
        assert has_export("def foo(): pass") is False

    def test_has_export_variants(self):
        """has_export detects exporti and exporta."""
        assert has_export("#| exporti\ndef foo(): pass") is True
        assert has_export("#| exporta\ndef foo(): pass") is True

    def test_has_hide(self):
        """has_hide detects #| hide directive."""
        assert has_hide("#| hide\nimport nbdev") is True
        assert has_hide("import nbdev") is False

    def test_has_eval_false(self):
        """has_eval_false detects #| eval: false."""
        assert has_eval_false("#| eval: false\nrun_slow()") is True
        assert has_eval_false("#| eval: False") is True
        assert has_eval_false("run_slow()") is False

    def test_get_default_exp(self):
        """get_default_exp extracts module name."""
        assert get_default_exp("#| default_exp utils") == "utils"
        assert get_default_exp("#| default_exp core.helpers") == "core.helpers"
        assert get_default_exp("def foo(): pass") is None


class TestFindDefaultExp:
    """Tests for find_default_exp function."""

    def test_find_in_dict(self):
        """find_default_exp works with dict input."""
        data = {
            "cells": [
                {"cell_type": "code", "source": ["#| default_exp mymodule"]}
            ]
        }
        assert find_default_exp(data) == "mymodule"

    def test_find_in_nbfile(self):
        """find_default_exp works with NBFile input."""
        data = {
            "cells": [
                {"cell_type": "code", "source": ["#| default_exp mymodule"]}
            ]
        }
        nb = NBFile(Path("test.ipynb"), data)
        assert find_default_exp(nb) == "mymodule"

    def test_not_found(self):
        """find_default_exp returns None if not found."""
        data = {"cells": [{"cell_type": "code", "source": ["print(1)"]}]}
        assert find_default_exp(data) is None


class TestSymbol:
    """Tests for Symbol dataclass."""

    def test_symbol_creation(self):
        """Symbol can be created with name and kind."""
        sym = Symbol(name="foo", kind="function", lineno=10)
        assert sym.name == "foo"
        assert sym.kind == "function"
        assert sym.lineno == 10


class TestExtractSymbols:
    """Tests for extract_symbols function."""

    def test_extract_function(self):
        """extract_symbols finds function definitions."""
        source = "def foo(): pass"
        symbols = extract_symbols(source)
        assert len(symbols) == 1
        assert symbols[0].name == "foo"
        assert symbols[0].kind == "function"

    def test_extract_class(self):
        """extract_symbols finds class definitions."""
        source = "class MyClass: pass"
        symbols = extract_symbols(source)
        assert len(symbols) == 1
        assert symbols[0].name == "MyClass"
        assert symbols[0].kind == "class"

    def test_extract_variable(self):
        """extract_symbols finds top-level assignments."""
        source = "x = 42"
        symbols = extract_symbols(source)
        assert len(symbols) == 1
        assert symbols[0].name == "x"
        assert symbols[0].kind == "variable"

    def test_syntax_error_returns_empty(self):
        """extract_symbols returns empty list on syntax error."""
        symbols = extract_symbols("def incomplete(")
        assert symbols == []


class TestImport:
    """Tests for Import dataclass."""

    def test_import_creation(self):
        """Import can be created with module name."""
        imp = Import(module="os", is_relative=False)
        assert imp.module == "os"
        assert imp.is_relative is False


class TestExtractImports:
    """Tests for extract_imports function."""

    def test_extract_import(self):
        """extract_imports finds import statements."""
        source = "import os\nimport sys"
        imports = extract_imports(source)
        assert len(imports) == 2
        assert imports[0].module == "os"

    def test_extract_from_import(self):
        """extract_imports finds from...import statements."""
        source = "from pathlib import Path"
        imports = extract_imports(source)
        assert len(imports) == 1
        assert imports[0].module == "pathlib"

    def test_relative_import(self):
        """extract_imports detects relative imports."""
        source = "from .utils import helper"
        imports = extract_imports(source)
        assert len(imports) == 1
        assert imports[0].is_relative is True
        assert imports[0].level == 1


class TestSplitImports:
    """Tests for split_imports function."""

    def test_split_internal_external(self):
        """split_imports separates internal and external."""
        imports = [
            Import("mylib.utils", is_relative=False),
            Import("os", is_relative=False),
            Import(".helpers", is_relative=True, level=1),
        ]
        internal, external = split_imports(imports, "mylib")
        assert "mylib.utils" in internal
        assert "." in internal or ".helpers" in internal
        assert "os" in external


class TestIterExportCells:
    """Tests for iter_export_cells function."""

    def test_iter_export_cells(self):
        """iter_export_cells yields cells with export directives."""
        data = {
            "cells": [
                {"cell_type": "code", "source": ["#| export\ndef foo(): pass"]},
                {"cell_type": "code", "source": ["print('not exported')"]},
                {"cell_type": "code", "source": ["#| export\ndef bar(): pass"]},
            ]
        }
        export_cells = list(iter_export_cells(data))
        assert len(export_cells) == 2


class TestSearchCells:
    """Tests for search_cells function."""

    def test_search_finds_matches(self):
        """search_cells finds cells containing query."""
        data = {
            "cells": [
                {"cell_type": "code", "source": ["def foo(): pass"]},
                {"cell_type": "code", "source": ["def bar(): pass"]},
            ]
        }
        results = search_cells(data, "foo")
        assert len(results) == 1
        assert "def foo(): pass" in results[0][1].source

    def test_search_case_insensitive(self):
        """search_cells is case-insensitive."""
        data = {
            "cells": [
                {"cell_type": "code", "source": ["def FOO(): pass"]},
            ]
        }
        results = search_cells(data, "foo")
        assert len(results) == 1

    def test_search_respects_max_results(self):
        """search_cells respects max_results limit."""
        data = {
            "cells": [
                {"cell_type": "code", "source": [f"x{i} = {i}"]}
                for i in range(20)
            ]
        }
        results = search_cells(data, "x", max_results=5)
        assert len(results) == 5

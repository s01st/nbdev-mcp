"""Tests for nbdev_mcp.utils.config and nbdev_mcp.utils.re modules."""

import pytest
import re
from nbdev_mcp.utils.re import (
    PATTERN_CATALOG,
    HEADER_PATTERN,
    REFERENCE_PATTERN,
    TODO_CODE_PATTERN,
    TODO_MD_PATTERN,
    BUG_PATTERN,
    RELATIVE_IMPORT_PATTERN,
    EXPORT_DIRECTIVE_PATTERN,
    EXPORTA_DIRECTIVE_PATTERN,
    DEFAULT_EXP_PATTERN,
    HIDE_DIRECTIVE_PATTERN,
    EVAL_FALSE_PATTERN,
    YAML_NAME_PATTERN,
    RELATIVE_LEVEL_PATTERN,
    MAIN_GUARD_PATTERN,
    FUNCTION_DEF_PATTERN,
    ASYNC_FUNCTION_DEF_PATTERN,
    CLASS_DEF_PATTERN,
    ALL_DEFINITION_PATTERN,
    IMPORT_FROM_PATTERN,
    IMPORT_PATTERN,
    TEST_FUNCTION_PATTERN,
    ASSERT_PATTERN,
    PYTEST_MARKER_PATTERN,
    NBDEV_CELL_COMMENT_PATTERN,
)
from nbdev_mcp.utils.config import (
    DotConfig,
    configure,
    get_config,
)


class TestRegexPatterns:
    """Test centralized regex patterns."""

    def test_header_pattern(self):
        """Test markdown header matching."""
        assert HEADER_PATTERN.match("# H1")
        assert HEADER_PATTERN.match("## H2")
        assert HEADER_PATTERN.match("###### H6")
        assert not HEADER_PATTERN.match("####### Too many")
        assert not HEADER_PATTERN.match("#NoSpace")

    def test_reference_pattern(self):
        """Test reference link matching."""
        m = REFERENCE_PATTERN.match("[id]: https://example.com")
        assert m
        assert m.group(1) == "id"
        assert m.group(2) == "https://example.com"

        m = REFERENCE_PATTERN.match("  [ref]: /path/to/file")
        assert m
        assert m.group(1) == "ref"

    def test_todo_code_pattern(self):
        """Test TODO comment matching in code."""
        m = TODO_CODE_PATTERN.search("# TODO: Fix this bug")
        assert m
        assert "Fix this bug" in m.group(1)

        m = TODO_CODE_PATTERN.search("# todo implement feature")
        assert m  # Case insensitive

    def test_todo_md_pattern(self):
        """Test TODO matching in markdown."""
        m = TODO_MD_PATTERN.search("TODO: Write docs")
        assert m

        m = TODO_MD_PATTERN.search("Some text TODO add tests")
        assert m

    def test_bug_pattern(self):
        """Test BUG marker matching."""
        m = BUG_PATTERN.search("BUG: Memory leak in function")
        assert m
        assert "Memory leak" in m.group(1)

        m = BUG_PATTERN.search("# bug fix needed")
        assert m  # Case insensitive

    def test_relative_import_pattern(self):
        """Test relative import detection."""
        m = RELATIVE_IMPORT_PATTERN.match("from .utils import foo")
        assert m
        assert m.group(1) == ".utils"
        assert m.group(2) == "foo"

        m = RELATIVE_IMPORT_PATTERN.match("from ..core import bar, baz")
        assert m
        assert m.group(1) == "..core"

        assert not RELATIVE_IMPORT_PATTERN.match("from nbdev import config")

    def test_export_directive_pattern(self):
        """Test export directive matching."""
        assert EXPORT_DIRECTIVE_PATTERN.search("#| export")
        assert EXPORT_DIRECTIVE_PATTERN.search("#| exporti")
        assert EXPORT_DIRECTIVE_PATTERN.search("  #| export")
        assert not EXPORT_DIRECTIVE_PATTERN.search("#| exporta")  # Different pattern

    def test_exporta_directive_pattern(self):
        """Test exporta directive matching."""
        assert EXPORTA_DIRECTIVE_PATTERN.search("#| exporta")
        assert not EXPORTA_DIRECTIVE_PATTERN.search("#| export")

    def test_default_exp_pattern(self):
        """Test default_exp extraction."""
        m = DEFAULT_EXP_PATTERN.search("#| default_exp utils")
        assert m
        assert m.group(1) == "utils"

        m = DEFAULT_EXP_PATTERN.search("#| default_exp subpkg.core")
        assert m
        assert m.group(1) == "subpkg.core"

    def test_hide_directive_pattern(self):
        """Test hide directive matching."""
        assert HIDE_DIRECTIVE_PATTERN.search("#| hide")
        assert HIDE_DIRECTIVE_PATTERN.search("  #| hide")
        assert not HIDE_DIRECTIVE_PATTERN.search("#| hidden")

    def test_eval_false_pattern(self):
        """Test eval:false directive matching."""
        assert EVAL_FALSE_PATTERN.search("#| eval: false")
        assert EVAL_FALSE_PATTERN.search("#| eval:false")
        assert EVAL_FALSE_PATTERN.search("#| eval: FALSE")  # Case insensitive

    def test_yaml_name_pattern(self):
        """Test YAML name extraction."""
        m = YAML_NAME_PATTERN.match("name: my-env")
        assert m
        assert m.group(1) == "my-env"

        m = YAML_NAME_PATTERN.match("  name: test_env123")
        assert m
        assert m.group(1) == "test_env123"

    def test_relative_level_pattern(self):
        """Test relative import level parsing."""
        m = RELATIVE_LEVEL_PATTERN.match("..foo")
        assert m
        assert m.group(1) == ".."
        assert m.group(2) == "foo"

        m = RELATIVE_LEVEL_PATTERN.match("...")
        assert m
        assert m.group(1) == "..."

    def test_main_guard_pattern(self):
        """Test __main__ guard detection."""
        assert MAIN_GUARD_PATTERN.search('if __name__ == "__main__":')
        assert MAIN_GUARD_PATTERN.search("if __name__ == '__main__':")
        assert MAIN_GUARD_PATTERN.search('  if __name__=="__main__":')

    def test_function_def_pattern(self):
        """Test function definition matching."""
        m = FUNCTION_DEF_PATTERN.search("def my_func():")
        assert m
        assert m.group(1) == "my_func"

        m = FUNCTION_DEF_PATTERN.search("def calculate(x, y):")
        assert m
        assert m.group(1) == "calculate"

        m = FUNCTION_DEF_PATTERN.search("  def indented():")
        assert m
        assert m.group(1) == "indented"

    def test_async_function_def_pattern(self):
        """Test async function definition matching."""
        m = ASYNC_FUNCTION_DEF_PATTERN.search("async def fetch():")
        assert m
        assert m.group(1) == "fetch"

        m = ASYNC_FUNCTION_DEF_PATTERN.search("  async def handler(request):")
        assert m
        assert m.group(1) == "handler"

        assert not ASYNC_FUNCTION_DEF_PATTERN.search("def sync_func():")

    def test_class_def_pattern(self):
        """Test class definition matching."""
        m = CLASS_DEF_PATTERN.search("class MyClass:")
        assert m
        assert m.group(1) == "MyClass"

        m = CLASS_DEF_PATTERN.search("class Child(Parent):")
        assert m
        assert m.group(1) == "Child"

        m = CLASS_DEF_PATTERN.search("  class Nested:")
        assert m
        assert m.group(1) == "Nested"

    def test_all_definition_pattern(self):
        """Test __all__ definition detection."""
        assert ALL_DEFINITION_PATTERN.search("__all__ = ['func1', 'func2']")
        assert ALL_DEFINITION_PATTERN.search("__all__=['a']")
        assert ALL_DEFINITION_PATTERN.search("  __all__ = []")
        assert not ALL_DEFINITION_PATTERN.search("all_items = []")

    def test_import_from_pattern(self):
        """Test from...import statement matching."""
        m = IMPORT_FROM_PATTERN.search("from pathlib import Path")
        assert m
        assert m.group(1) == "pathlib"

        m = IMPORT_FROM_PATTERN.search("from os.path import join")
        assert m
        assert m.group(1) == "os.path"

        m = IMPORT_FROM_PATTERN.search("  from typing import List, Dict")
        assert m
        assert m.group(1) == "typing"

    def test_import_pattern(self):
        """Test import statement matching."""
        m = IMPORT_PATTERN.search("import json")
        assert m
        assert m.group(1) == "json"

        m = IMPORT_PATTERN.search("import os.path")
        assert m
        assert m.group(1) == "os.path"

        m = IMPORT_PATTERN.search("  import re")
        assert m
        assert m.group(1) == "re"

    def test_test_function_pattern(self):
        """Test test function detection."""
        assert TEST_FUNCTION_PATTERN.search("def test_something():")
        assert TEST_FUNCTION_PATTERN.search("def test_my_feature(fixture):")
        assert TEST_FUNCTION_PATTERN.search("  def test_nested():")
        assert not TEST_FUNCTION_PATTERN.search("def testing():")
        assert not TEST_FUNCTION_PATTERN.search("def my_test():")

    def test_assert_pattern(self):
        """Test assert statement matching."""
        assert ASSERT_PATTERN.search("assert x == 1")
        assert ASSERT_PATTERN.search("  assert result is not None")
        assert ASSERT_PATTERN.search("assert True")
        assert not ASSERT_PATTERN.search("# assert commented")

    def test_pytest_marker_pattern(self):
        """Test pytest marker detection."""
        assert PYTEST_MARKER_PATTERN.search("@pytest.mark.slow")
        assert PYTEST_MARKER_PATTERN.search("@pytest.mark.parametrize")
        assert PYTEST_MARKER_PATTERN.search("  @pytest.mark.skip")
        assert not PYTEST_MARKER_PATTERN.search("pytest.raises")

    def test_nbdev_cell_comment_pattern(self):
        """Test nbdev cell comment matching in generated .py files."""
        m = NBDEV_CELL_COMMENT_PATTERN.search("# %% ../nbs/04_nb.ipynb 5")
        assert m
        assert m.group(1) == "../nbs/04_nb.ipynb"
        assert m.group(2) == "5"

        m = NBDEV_CELL_COMMENT_PATTERN.search("# %% ../nbs/subdir/utils.ipynb 12")
        assert m
        assert m.group(1) == "../nbs/subdir/utils.ipynb"
        assert m.group(2) == "12"

    def test_pattern_catalog_completeness(self):
        """Verify all patterns are in the catalog."""
        # Markdown patterns
        assert "header" in PATTERN_CATALOG
        assert "reference_link" in PATTERN_CATALOG
        # TODO/BUG patterns
        assert "todo_code" in PATTERN_CATALOG
        assert "todo_markdown" in PATTERN_CATALOG
        assert "bug" in PATTERN_CATALOG
        # Import patterns
        assert "relative_import" in PATTERN_CATALOG
        assert "relative_level" in PATTERN_CATALOG
        assert "import_from" in PATTERN_CATALOG
        assert "import" in PATTERN_CATALOG
        # Nbdev directive patterns
        assert "export_directive" in PATTERN_CATALOG
        assert "exporta_directive" in PATTERN_CATALOG
        assert "default_exp" in PATTERN_CATALOG
        assert "hide_directive" in PATTERN_CATALOG
        assert "eval_false" in PATTERN_CATALOG
        # Symbol definition patterns
        assert "function_def" in PATTERN_CATALOG
        assert "async_function_def" in PATTERN_CATALOG
        assert "class_def" in PATTERN_CATALOG
        assert "all_definition" in PATTERN_CATALOG
        # Test patterns
        assert "test_function" in PATTERN_CATALOG
        assert "assert" in PATTERN_CATALOG
        assert "pytest_marker" in PATTERN_CATALOG
        # Other patterns
        assert "yaml_name" in PATTERN_CATALOG
        assert "main_guard" in PATTERN_CATALOG
        assert "nbdev_cell_comment" in PATTERN_CATALOG


class TestDotConfig:
    """Test DotConfig class."""

    def test_dot_access(self):
        """Test dot notation access."""
        cfg = DotConfig({"key": "value", "nested": {"inner": 1}})
        assert cfg.key == "value"

    def test_dot_assignment(self):
        """Test dot notation assignment."""
        cfg = DotConfig()
        cfg.new_key = "new_value"
        assert cfg["new_key"] == "new_value"

    def test_copy(self):
        """Test config copy."""
        cfg = DotConfig({"a": 1})
        copy = cfg.copy()
        assert isinstance(copy, DotConfig)
        assert copy.a == 1
        copy.a = 2
        assert cfg.a == 1  # Original unchanged

    def test_configure_function(self):
        """Test configure() updates global config."""
        original = get_config().copy()
        try:
            configure(test_key="test_value")
            assert get_config()["test_key"] == "test_value"
        finally:
            # Restore original
            if "test_key" in get_config():
                del get_config()["test_key"]

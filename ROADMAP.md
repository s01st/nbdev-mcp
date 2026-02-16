# nbdev-mcp Refactoring Roadmap

## Status Summary (Updated: 2026-02-16)

| Phase | Status | Tests |
|-------|--------|-------|
| Phase 1: Foundation | ✅ Complete | Passing |
| Phase 2: Module Reorganization | ✅ Complete | Passing |
| Phase 3: Code Quality | ✅ Complete | Passing |
| Phase 4: Documentation | ✅ Complete | N/A |
| Phase 5: Testing | ✅ 248 tests | All Passing |
| Phase 6: MCP Tool Metadata | ✅ Complete | N/A |

**Build Status:**
- `nbdev_export` ✅ OK
- `nbdev_test` ✅ OK
- `pytest` ✅ 248 tests pass
- `nbdev_readme` ⚠️ Known issue with numpydoc parsing (local fastcore)

**Recent Updates (2026-02-16):**
- Added `mcp_compatibility_matrix` for provider/client readiness planning.
- Added `mcp_contract_ci_gate` for CI pass/fail contract enforcement.
- Added `mcp_policy_pack` with strict/balanced/advisory governance profiles.
- Added coverage in `tests/test_project_tools.py` for new governance tools.
- Added safe repo markdown resources (`nbdev://repo-markdown` and template `nbdev://repo-markdown/{doc_key}`).

**Prior Updates (2026-02-06):**
- Weighted dead-code analysis by module depth and tutorial usage.
- Clarified duplicate-analysis guidance (ABC implementations and name variants).
- Made duplicate-scan timeouts configurable with timing metadata.
- Added tests for dead-code weighting and read_notebook_cell truncation.

**Earlier Updates (2025-12-22):**
- Added complete NumPy-style docstrings to config, resources, and paths modules
- Default project resolution: MCP now defaults to cwd if it's an nbdev project
- Fixed `set_current_project()` to sync both config and paths modules
- Added MCP integration tests (30 tests) using FastMCP in-memory testing
- Added `EXPORT_MAIN_PATTERN` and `NUMBERED_NOTEBOOK_PATTERN` to regex catalog
- All ToolAnnotations complete for 45+ tools

## Current Open Items

1. Audit transport/stdio behavior for parity with `scripts/mcp.nbdev.py` (`nbs/30_mcp.ipynb`).
2. Migrate remaining script-only features into nbdev modules; keep `scripts/mcp.nbdev.py` as a thin wrapper.

## Operational Guardrails (Bad Request Mitigation)

The following guardrails remain the guiding policy for large notebooks and tool output:

- Enforce output-size limits and return truncated summaries with a saved output path.
- Avoid full notebook cell dumps; use targeted slices or patch-based edits.
- Prefer formatted notebook JSON for readable diffs; use `nbformat`/`write_nb` when editing notebook content.
- Provide an explicit safe mode for strict output limits.

## Executive Summary

This document outlines the path to a production-ready, well-documented, maintainable nbdev-mcp codebase. The audit identified critical issues in regex duplication, missing documentation, code organization, and test coverage.

---

## Phase 1: Foundation - Centralize Patterns & Add Exceptions

### 1.1 Centralize ALL Regex Patterns (02_config.ipynb)

**Add these missing patterns to `PATTERN_CATALOG`:**

```python
# Directive patterns
HIDE_DIRECTIVE_PATTERN = re.compile(r"^\s*#\|\s*hide\b", re.MULTILINE)
EVAL_FALSE_PATTERN = re.compile(r"^\s*#\|\s*eval:\s*false", re.MULTILINE | re.IGNORECASE)

# Symbol extraction patterns
FUNCTION_DEF_PATTERN = re.compile(r"def\s+(\w+)\s*\(")
CLASS_DEF_PATTERN = re.compile(r"class\s+(\w+)\s*[\(:]")
ASYNC_FUNCTION_DEF_PATTERN = re.compile(r"async\s+def\s+(\w+)\s*\(")

# Code patterns
ALL_DEFINITION_PATTERN = re.compile(r"^\s*__all__\s*=", re.MULTILINE)
MAIN_GUARD_PATTERN = re.compile(r"if\s+__name__\s*==\s*['\"]__main__['\"]")

# Import patterns
IMPORT_FROM_PATTERN = re.compile(r"^\s*from\s+([\w\.]+)\s+import\s+")
IMPORT_PATTERN = re.compile(r"^\s*import\s+([\w\.]+)")

# Test patterns
TEST_DETECTION_PATTERN = re.compile(r"\bpytest\b|^def\s+test_", re.MULTILINE)
ASSERT_PATTERN = re.compile(r"^\s*assert\s+", re.MULTILINE)

# YAML patterns
YAML_NAME_PATTERN = re.compile(r"^\s*name\s*:\s*([A-Za-z0-9._-]+)\s*$")

# nbdev cell comment pattern (for .py file mapping)
NBDEV_CELL_PATTERN = re.compile(r"#\s*%%\s*(\.\./nbs/[\w/]+\.ipynb)\s+(\d+)")
```

### 1.2 Create Custom Exception Classes (new 02a_exceptions.ipynb)

```python
@dataclass
class NotebookLocation:
    """Location within a notebook for error reporting."""
    notebook: Path
    cell_index: int
    line_number: int = 0
    source_preview: str = ""

    def __str__(self) -> str:
        loc = f"{self.notebook}:cell[{self.cell_index}]"
        if self.line_number:
            loc += f":line[{self.line_number}]"
        return loc

class NotebookException(Exception):
    """Base exception with notebook location tracking."""
    def __init__(self, message: str, location: NotebookLocation | None = None):
        self.location = location
        super().__init__(self._format_message(message))

    def _format_message(self, message: str) -> str:
        if self.location:
            return f"{self.location}: {message}"
        return message

class NotebookParseError(NotebookException):
    """Error parsing notebook JSON or cell content."""
    pass

class CellExecutionError(NotebookException):
    """Error during cell execution or testing."""
    pass

class ExportError(NotebookException):
    """Error during nbdev export process."""
    pass

class ConfigurationError(NotebookException):
    """Error in configuration or settings."""
    pass

class NbdevMcpWarning(UserWarning):
    """Base warning with notebook location."""
    def __init__(self, message: str, location: NotebookLocation | None = None):
        self.location = location
        super().__init__(self._format_message(message))
```

### 1.3 Add .py File to Notebook Mapping

```python
def find_notebook_from_py(py_file: Path, project: Path) -> Tuple[Path, int] | None:
    """Find source notebook and cell from a .py file's cell comment.

    Looks for: # %% ../nbs/04_nb.ipynb 4

    Returns (notebook_path, cell_index) or None if not found.
    """
    content = py_file.read_text()
    for i, line in enumerate(content.splitlines()):
        if match := NBDEV_CELL_PATTERN.match(line):
            nb_rel, cell_idx = match.groups()
            nb_path = (py_file.parent / nb_rel).resolve()
            if nb_path.exists():
                return nb_path, int(cell_idx)
    return None
```

---

## Phase 2: Module Reorganization

### 2.1 New Module Structure

```
nbs/
├── index.ipynb                  # README
├── 01_logs.ipynb               # Logging (keep)
├── 02_config.ipynb             # Config + ALL regex patterns
├── 02_exceptions.ipynb         # NEW: Custom exceptions
├── 03_paths.ipynb              # NEW: Path utilities only
├── 04_nb.ipynb                 # Notebook primitives (reorder)
├── 05_tool_helpers.ipynb       # Tool helpers (expand)
├── 06_markdown.ipynb           # NEW: Markdown parsing
├── 07_subprocess.ipynb         # NEW: Subprocess utilities
│
├── 10_resources.ipynb          # MCP Resources (keep)
├── 11_project_tools.ipynb      # Project management tools
├── 12_env_tools.ipynb          # Environment tools
├── 13_nbdev_tools.ipynb        # nbdev build/test tools
├── 14_nb_editing_tools.ipynb   # Notebook editing tools
├── 15_lint_tools.ipynb         # Linting tools
├── 16_analysis_tools.ipynb     # Analysis tools
├── 17_gen_tools.ipynb          # Code generation tools
├── 20_prompts.ipynb            # Prompts (renumber)
│
├── 30_mcp.ipynb                # Server setup (keep)
└── 40__main__.ipynb            # Entry point (keep)
```

### 2.2 Split 03_utils.ipynb

**03_paths.ipynb** (Path & Project utilities):
- `expand()`, `settings_dict()`, `lib_name()`
- `nbs_dir()`, `tutorials_dir()`, `is_nbdev_project()`
- `find_project_root()`, `require_project()`, `resolve_selector()`
- `project_summary()`, `iter_notebooks()`

**06_markdown.ipynb** (Markdown parsing):
- `extract_references()`, `clear_section_buffer()`
- `group_lines_by_sections()`, `refs_used()`
- `readd_reference_links()`, `split_markdown_into_cells()`

**07_subprocess.ipynb** (Subprocess utilities):
- `which()`, `run()`, `wrap_with_env()`
- `tail()`, `ok()`

**Keep in 04_nb.ipynb** (Notebook I/O):
- `read_nb()`, `write_nb()`
- `join_source()`, `truncate()`
- Cell/NBFile classes

### 2.3 Split 11_tools.ipynb

Create 7 focused tool modules:

| Module | Functions | Lines |
|--------|-----------|-------|
| 11_project_tools | set_project, current_project, find_projects, bookmark_*, console_scripts_status | ~150 |
| 12_env_tools | ensure_env, export_env | ~80 |
| 13_nbdev_tools | nbdev_prepare, nbdev_export, nbdev_test, pytest_run | ~100 |
| 14_nb_editing_tools | check_if_generated, find_source_notebook, analyze_exports, *_notebook_cell, split_markdown_cells | ~250 |
| 15_lint_tools | validate_inits, lint_rules, lint_main_guards | ~200 |
| 16_analysis_tools | analyze_dependency_order, dependency_tree | ~200 |
| 17_gen_tools | generate_pytests, scaffold_test_utils, generate_stubs, aggregate_todos, aggregate_bugs | ~250 |

---

## Phase 3: Code Quality

### 3.1 Fix Code Ordering in 04_nb.ipynb

Current (broken flow):
```
Cell → NBFile (uses join_source) → join_source (defined after use!)
```

Correct order:
```
1. Imports
2. join_source(), truncate() - primitives
3. Regex patterns (_EXPORT_RE, etc.) - import from config
4. has_export(), has_hide(), etc. - use patterns
5. get_default_exp(), find_default_exp()
6. Cell dataclass
7. NBFile dataclass (uses join_source, has_export)
8. Symbol, Import dataclasses
9. extract_symbols(), extract_imports()
10. iter_export_cells(), search_cells()
```

### 3.2 Eliminate Duplicate Functions

| Keep | Remove | Reason |
|------|--------|--------|
| `nb.has_export()` | `utils.cell_has_export_directive()` | Same functionality |
| `nb.find_default_exp()` | `utils.find_default_exp_in_nb()` | Same functionality |
| `nb.join_source()` | `utils.join_source_lines()` | Same functionality |
| `nb.truncate()` | `utils.truncate_source()` | Same functionality |

Add aliases for backwards compatibility:
```python
# In utils.py
from nbdev_mcp.nb import join_source as join_source_lines  # backwards compat
from nbdev_mcp.nb import has_export as cell_has_export_directive
from nbdev_mcp.nb import find_default_exp as find_default_exp_in_nb
```

### 3.3 Use Helpers Consistently

**Apply `with_project` decorator to ALL tool functions:**
```python
# Before (repeated 50+ times):
def some_tool(project: Optional[str] = None) -> Dict[str, Any]:
    try:
        p = resolve_selector(project)
    except Exception as e:
        return {'ok': False, 'error': str(e)}
    # ... rest of function

# After:
@with_project(resolve_selector)
def some_tool(project: Path) -> Dict[str, Any]:
    # project is already resolved Path
    # ... rest of function
```

**Use `render_table()` instead of manual Table creation:**
```python
# Before:
c = console()
t = Table(title='issues')
t.add_column('rule')
t.add_column('location')
for item in items:
    t.add_row(item['rule'], item['loc'])
c.print(t)
return {'pretty': export_console(c)}

# After:
rows = [[item['rule'], item['loc']] for item in items]
pretty = render_table('issues', ['rule', 'location'], rows)
return {'pretty': pretty}
```

### 3.4 Extract Common Iteration Pattern

```python
# New helper in 04_nb.ipynb
def iter_project_cells(
    project: Path,
    cell_type: str = 'code',
    with_source: bool = True
) -> Iterable[Tuple[Path, int, Cell]]:
    """Iterate over all cells in project notebooks.

    Yields (notebook_path, cell_index, Cell) tuples.
    """
    for nb_path in iter_notebooks(project):
        data = read_nb(nb_path)
        nb = NBFile(nb_path, data)
        for cell in nb.cells:
            if cell_type and cell.cell_type != cell_type:
                continue
            yield nb_path, cell.index, cell
```

---

## Phase 4: Documentation

### 4.1 Complete Numpydoc Docstrings

**Template for ALL functions:**
```python
def function_name(param1: Type1, param2: Type2 = default) -> ReturnType:
    """Short description (one line).

    Longer description if needed. Explain what the function does,
    not how it does it.

    Parameters
    ----------
    param1 : Type1
        Description of param1.
    param2 : Type2, default=default
        Description of param2.

    Returns
    -------
    ReturnType
        Description of return value.

    Raises
    ------
    ExceptionType
        When this exception is raised.

    Examples
    --------
    >>> function_name("input")
    "output"

    See Also
    --------
    related_function : Brief description.

    Notes
    -----
    Implementation notes if needed.
    """
```

### 4.2 Functions Needing Docstrings

**Critical (11_tools.ipynb - 50+ functions):**
All tool functions need complete docstrings.

**High Priority (03_utils.ipynb - 6 functions):**
- `settings_dict()`, `expand()`, `read_nb()`, `write_nb()`
- `find_default_exp_in_nb()`, `cell_lines()`, `cell_has_export_directive()`
- `set_http_path_if_supported()`, `lib_name()`

**Medium Priority (04_nb.ipynb properties):**
- `Cell.lines`, `Cell.is_code`, `Cell.is_markdown`
- `NBFile.cells`, `NBFile.code_cells`, `NBFile.markdown_cells`

---

## Phase 5: Testing

### 5.1 Create tests/ Directory Structure

```
tests/
├── __init__.py
├── conftest.py              # Shared fixtures
├── fixtures/                # Test data
│   ├── sample_notebook.ipynb
│   ├── sample_settings.ini
│   └── sample_env.yml
│
├── test_config.py           # 02_config tests
├── test_exceptions.py       # 02a_exceptions tests
├── test_paths.py            # 03_paths tests
├── test_nb.py               # 04_nb tests
├── test_tool_helpers.py     # 05_tool_helpers tests
├── test_markdown.py         # 06_markdown tests
├── test_subprocess.py       # 07_subprocess tests
│
├── test_resources.py        # 10_resources tests
├── test_project_tools.py    # 11_project_tools tests
├── test_env_tools.py        # 12_env_tools tests
├── test_nbdev_tools.py      # 13_nbdev_tools tests
├── test_nb_editing.py       # 14_nb_editing tests
├── test_lint_tools.py       # 15_lint_tools tests
├── test_analysis_tools.py   # 16_analysis_tools tests
├── test_gen_tools.py        # 17_gen_tools tests
├── test_prompts.py          # 20_prompts tests
│
└── test_integration.py      # End-to-end tests
```

### 5.2 Test Coverage Goals

| Module | Coverage Target | Priority |
|--------|-----------------|----------|
| 02_config | 100% | High |
| 02a_exceptions | 100% | High |
| 03_paths | 95% | High |
| 04_nb | 95% | High |
| 05_tool_helpers | 95% | High |
| 06_markdown | 90% | Medium |
| 07_subprocess | 80% | Medium |
| 10_resources | 90% | Medium |
| 11-17_tools | 85% | Medium |
| 20_prompts | 80% | Low |

### 5.3 Key Test Cases

**Regex Pattern Tests:**
```python
@pytest.mark.parametrize("source,expected", [
    ("#| export", True),
    ("#| exporti", True),
    ("#|export", True),
    ("# | export", False),
    ("print('export')", False),
])
def test_export_pattern(source, expected):
    assert bool(EXPORT_DIRECTIVE_PATTERN.search(source)) == expected
```

**Exception Location Tests:**
```python
def test_exception_includes_notebook_location():
    loc = NotebookLocation(Path("test.ipynb"), cell_index=5, line_number=10)
    exc = NotebookParseError("Invalid syntax", location=loc)
    assert "test.ipynb:cell[5]:line[10]" in str(exc)
```

**Cell Iteration Tests:**
```python
def test_iter_project_cells_filters_by_type(sample_project):
    code_cells = list(iter_project_cells(sample_project, cell_type='code'))
    md_cells = list(iter_project_cells(sample_project, cell_type='markdown'))
    assert all(c.is_code for _, _, c in code_cells)
    assert all(c.is_markdown for _, _, c in md_cells)
```

---

## Phase 6: MCP Tool Metadata

### 6.1 Complete Tool Descriptions

Every MCP tool should have:
```python
@mcp.tool(
    name="analyze_exports",
    description="Analyze what a notebook exports (functions, classes, variables).",
    tags=["notebook", "analysis"],
)
def analyze_exports(
    project: Optional[str] = None,
    notebook: str = "",
    preview_length: int = 200
) -> Dict[str, Any]:
    """Analyze notebook exports.

    Parameters
    ----------
    project : str, optional
        Project path or alias. Uses current if not specified.
    notebook : str
        Notebook filename relative to nbs/ directory.
    preview_length : int, default=200
        Maximum preview length for cell source.

    Returns
    -------
    Dict[str, Any]
        {
            'ok': bool,
            'notebook': str,
            'module': str,
            'export_count': int,
            'exports': List[Dict],
            'pretty': str
        }
    """
```

---

## Implementation Order

### Week 1: Foundation ✅ COMPLETE
1. [x] Add missing regex patterns to 02_config.ipynb
2. [x] Create 02_exceptions.ipynb with custom exceptions
3. [x] Add .py to notebook mapping function
4. [x] Create tests/ directory with conftest.py
5. [x] Write tests for regex patterns

### Week 2: Module Split ✅ COMPLETE
1. [x] Create 03_paths.ipynb (extract from utils)
2. [x] Create 06_markdown.ipynb (extract from utils)
3. [x] Create 07_subprocess.ipynb (extract from utils)
4. [x] Fix code ordering in 04_nb.ipynb
5. [x] Eliminate duplicate functions, add aliases

### Week 3: Tools Refactor ✅ COMPLETE
1. [x] Split 11_tools.ipynb into 7 modules (11-17)
2. [ ] Apply `@with_project` decorator to all tools
3. [ ] Replace manual Table creation with `render_table()`
4. [x] Add `iter_project_cells()` helper

### Week 4: Documentation 🟡 IN PROGRESS
1. [x] All functions have docstrings (Google style for exceptions module)
2. [ ] Convert remaining NumPy docstrings to Google style (97 remaining)
3. [ ] Add Examples sections to key functions
4. [x] Type annotations on all functions

### Week 5: Testing ✅ COMPLETE
1. [x] Write tests for core modules (config, paths, nb)
2. [x] Write tests for tool helpers
3. [x] Write tests for tools (project, lint, analysis)
4. [x] Write MCP integration tests (30 tests)

**Test Files Created:**
- `test_config.py` - config module tests
- `test_nb.py` - 45 tests for Cell, NBFile, directives, symbols, imports
- `test_tool_helpers.py` - 17 tests for ToolResult, render functions, Issue
- `test_project_tools.py` - project tools integration tests
- `test_lint_tools.py` - lint tools integration tests
- `test_analysis_tools.py` - analysis tools integration tests
- `test_mcp_integration.py` - 30 MCP integration tests (tools, resources, prompts)

### Week 6: Polish ⬜ NOT STARTED
1. [ ] Review and improve error messages
2. [ ] Add tool metadata (tags, descriptions)
3. [ ] Final documentation review
4. [ ] Performance optimization

---

## Success Metrics

| Metric | Start | Current | Target |
|--------|-------|---------|--------|
| Regex patterns in config | 8 | 25+ ✅ | 20+ |
| Functions with docstrings | ~40% | ~95% | 100% |
| Functions with type hints | ~70% | ~95% ✅ | 100% |
| Test count | ~100 | 248 ✅ | 150+ |
| MCP integration tests | 0 | 30 ✅ | 20+ |
| Max lines per module | 1300 | ~300 ✅ | 300 |
| Duplicate code patterns | 10+ | 0 ✅ | 0 |
| Tool modules | 1 (monolith) | 7 ✅ | 7 |

---

## Notes

- Maintain backwards compatibility with aliases
- Run `nbdev_test` after each change
- Commit frequently with descriptive messages
- Update this roadmap as issues are discovered

## Known Issues

### numpydoc Parsing Bug (2025-12-01)

`nbdev_prepare` fails during `nbdev_readme` due to a numpydoc parsing issue in the local fastcore installation:

```
TypeError: sequence item 0: expected str instance, Parameter found
```

**Workaround:** The core build works fine:
- `nbdev_export` - OK
- `nbdev_test` - OK
- `pytest` - 184 tests pass

Only documentation generation (`nbdev_readme`) fails. This appears to be a bug in `/Users/sm1901/GitHub/fastcore/fastcore/docscrape.py` when parsing certain NumPy-style docstrings.

**Partial Fix Applied:** Exception module docstrings converted to Google style format which parses more reliably.

## Completed Work Summary

### 2025-12-01
1. **Phase 1 Complete:** Added 20+ regex patterns to config, created exceptions module with NotebookLocation tracking
2. **Phase 2 Complete:** Split utils into paths/markdown/subprocess modules, split 11_tools.ipynb into 7 focused modules (11-17)
3. **Phase 3 Mostly Complete:** Eliminated duplicate functions with backwards-compat aliases, added `iter_project_cells()` helper
4. **Phase 5 Mostly Complete:** Created comprehensive test suite with 184 tests across 12 test files

### 2025-12-22
1. **Default Project Resolution:** `require_project()` now defaults to cwd if it's an nbdev project
2. **State Sync Fix:** `set_current_project()` now updates both config and paths modules
3. **MCP Integration Tests:** Added 30 tests using FastMCP in-memory testing pattern
4. **Regex Patterns:** Added `EXPORT_MAIN_PATTERN` and `NUMBERED_NOTEBOOK_PATTERN`
5. **Phase 5 Complete:** Test count now at 248 tests, all passing
6. **Phase 6 Complete:** All 45+ tools have ToolAnnotations

# ⚠️ nbdev Workflow Philosophy for {lib}

## CRITICAL: Notebooks Are Source Code

**In nbdev projects, .ipynb notebooks are the SOURCE. Python .py files are GENERATED.**

### Golden Rules:
1. ✅ **ALWAYS edit notebooks** in `{nbs_path}/`
2. ✅ **ALWAYS run nbdev_export** after editing notebooks
3. ❌ **NEVER edit .py files** in `{lib}/` directly (they're auto-generated!)
4. ❌ **NEVER edit README.md** directly (it's generated from index.ipynb)

## Before Editing ANY Code:

**If user asks to edit code in a .py file:**
1. STOP! Use `check_if_generated(file_path)` first
2. If generated, use `find_source_notebook(py_file)` to find the notebook
3. Edit the notebook instead
4. Run `nbdev_export` to regenerate the .py file

## Correct Workflow Example:

```
User: "Fix the bug in {lib}/core.py in the process_data function"

✅ CORRECT Claude Response:
1. check_if_generated("{lib}/core.py") → Yes, it's generated
2. find_source_notebook("{lib}/core.py") → "{nbs_path}/core.ipynb"
3. read_notebook_cell(notebook="core.ipynb", search="process_data")
4. edit_notebook_cell(notebook="core.ipynb", cell_index=X, new_source="...")
5. nbdev_export() → Regenerates {lib}/core.py
6. "Done! Fixed in {nbs_path}/core.ipynb and regenerated {lib}/core.py"

❌ WRONG Response:
- Directly editing {lib}/core.py (changes will be lost on next export!)
```

## Project Structure:
```
{nbs_path}/           ← SOURCE CODE (edit here!)
├── index.ipynb       ← Becomes README.md
├── core.ipynb        ← Exports to {lib}/core.py
└── utils.ipynb       ← Exports to {lib}/utils.py

{lib}/                ← GENERATED CODE (do not edit!)
├── __init__.py       ← Auto-generated
├── core.py           ← Auto-generated from core.ipynb
└── utils.py          ← Auto-generated from utils.ipynb
```

## Available Tools:
- `check_if_generated(file)` - Check if file is auto-generated
- `find_source_notebook(py_file)` - Find which notebook created a .py file
- `analyze_exports(notebook)` - See what a notebook exports
- `read_notebook_cell(notebook, search)` - Find cells in notebook
- `edit_notebook_cell(notebook, cell_index, new_source)` - Edit a cell
- `add_notebook_cell(notebook, source)` - Add new cell
- `nbdev_export()` - Generate .py files from notebooks
- `nbdev_test()` - Run tests in notebooks (quick checks)
- `pytest` via `tests/` - Preferred for all substantive tests

## Remember:
- Notebooks = code + narrative; keep long tests in `tests/` with pytest.
- Prefer writing tests under `tests/` (pytest). Use `nbs/99_tests/` only for shared fixtures/mocks.
- `nbs/index.ipynb` becomes README.md and does not need `default_exp`.
- For long/expensive notebook examples, mark cells with `#| eval: false`.
- Always export after editing notebooks.
- Never manually edit generated files.
- Use tools to find and edit source notebooks.
- Avoid private names (leading underscore) for functions, classes, attributes, or vars; dunder methods like `__init__` are OK.
- Dead-code reports are signals: weigh by module depth and tutorial usage; tutorial usage implies public API and lowers concern.
- The `tutorials/` directory is for tutorial notebooks only — do not write artifacts/outputs/cache there (use repo root or `~/Downloads/<repo>/`).
- Prefer writing notebooks with indentation (for example `indent=2`) so diffs stay readable; using nbformat or `write_nb` is recommended.
- Keep living docs current: `ROADMAP.md`, `TODOs.md`, `*_PLAN.md`, and agent docs under `.claude/` or `.codex/`.
- All scripting/CLI logic must live in `nbs/` and be exposed via `settings.ini` (`console_scripts`). Avoid ad-hoc scripts outside nbdev.
- Repo-level `.md` files can be incorporated into `nbs/index.ipynb` as markdown cells (use `split_markdown_cells` to convert).
- Do not add manual "Documentation" sections or call `show_doc()`; nbdev builds API docs from docstrings automatically.

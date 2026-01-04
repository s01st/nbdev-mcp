# nbdev Advanced Patterns

## Exports
- 🚫 Do not define `__all__` anywhere. nbdev builds exports automatically.
- Avoid private names (leading underscore) for functions/classes/vars; dunder methods like `__init__` are OK.

## Package Structure
- Top-level init: `nbs/00__init__.ipynb` → `#| default_exp __init__`
- Subpackage init: `nbs/<pkg>/00__init__.ipynb` → `#| default_exp <pkg>.__init__`
- Submodules: use dotted `default_exp` (e.g., `core.data`) to create directories.
- `nbs/index.ipynb` becomes README.md and does not need `default_exp`.
- Scripting/CLI logic belongs in `nbs/` and should be exposed via `settings.ini` (`console_scripts`).
- Repo-level `.md` files can be incorporated into `nbs/index.ipynb` as markdown cells (use `split_markdown_cells`).

## Imports
- Never use relative imports. Prefer: `from mylib.core.data import Foo`.

## Lifting Symbols
- Let users import from specific submodules. Avoid lifting to package level with manual `__init__` tricks.

## Common Pitfalls
- ❌ Relative imports (`from .x import y`)
- ❌ Wrong `default_exp` for `00__init__.ipynb` in subpackages
- ❌ Manual `__all__`

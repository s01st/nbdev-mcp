# nbdev Advanced Patterns

## Exports
- 🚫 Do not define `__all__` anywhere. nbdev builds exports automatically.

## Package Structure
- Top-level init: `nbs/00__init__.ipynb` → `#| default_exp _init__`
- Subpackage init: `nbs/<pkg>/00__init__.ipynb` → `#| default_exp <pkg>.__init__`
- Submodules: use dotted `default_exp` (e.g., `core.data`) to create directories.

## Imports
- Never use relative imports. Prefer: `from mylib.core.data import Foo`.

## Lifting Symbols
- Let users import from specific submodules. Avoid lifting to package level with manual `__init__` tricks.

## Common Pitfalls
- ❌ Relative imports (`from .x import y`)
- ❌ Wrong `default_exp` for `00__init__.ipynb` in subpackages
- ❌ Manual `__all__`

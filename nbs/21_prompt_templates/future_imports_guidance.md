# Guidance for `__future__` Imports
- Place `from _future__ import annotations` at the top of the first export cell if you rely on postponed annotations.
- Keep all `__future__` imports at the beginning of a code cell and avoid repeating them across many cells.
- Prefer string annotations (or `from _future__ import annotations`) to avoid runtime import cycles.
- In Python 3.12+, `annotations` remains useful for forward references in type hints.

# nbdev Principles (concise)

- Edit notebooks in `{nbs_path}/`, never generated `{lib}/` .py files.

- `nbs/index.ipynb` → README.md; never edit README.md directly.
- `nbs/index.ipynb` does not need `default_exp`.

- Do not define `__all__`; nbdev generates exports.
- Avoid private names (leading underscore) for functions/classes/vars; dunder methods like `__init__` are OK.

- No relative imports; use absolute imports from `{lib}`.

- One function or class per code cell; define helpers before they are used.

- For submodules, `00__init__.ipynb` → `#| default_exp <sub>.__init__`.

- Prefer pytest in `tests/`; use `nbs/99_tests/` only for fixtures/mocks.

- Mark long examples with `#| eval: false`.

- Split long narrative with `####` in separate markdown cells.

- Use NumPy-style docstrings (Parameters, Returns, Raises, Examples).
- Dead-code reports are signals: weigh by module depth and tutorial usage; tutorial usage implies public API and lowers concern.
- The `tutorials/` directory is for tutorial notebooks only — do not write artifacts/outputs/cache there (use repo root or `~/Downloads/<repo>/`).
- Never write notebooks via `json.dumps` without indentation. Use nbformat or `write_nb`; single-line notebook JSON is corruption and should be restored.
- Keep living docs current: `ROADMAP.md`, `TODOs.md`, `*_PLAN.md`, and agent docs under `.claude/` or `.codex/`.
- All scripting/CLI logic must live in `nbs/` and be exposed via `settings.ini` (`console_scripts`); avoid ad-hoc scripts outside nbdev.
- Repo-level `.md` files can be added to `nbs/index.ipynb` as markdown cells (use `split_markdown_cells` to convert).

## State Management for MCP Tools

- MCP is stateless between calls; avoid private attributes (`self._xxx`) in exported classes. Dunder methods like `__init__` are OK.

- Use computed properties instead of stored state: `@property def config_path(self): return get_config_path()`.

- Prefer pure functions with explicit parameters over classes with hidden state.

- If caching is needed, use explicit cache modules or functools.lru_cache, not instance attributes.

- All tool functions should be idempotent where possible.

## Utilities Belong in Utils

- Path functions → `00_utils/08_paths.ipynb`
- I/O functions (JSON/TOML/YAML) → `00_utils/11_io.ipynb`
- Type definitions (dataclasses, TypedDicts) → `00_utils/01_types.ipynb`
- Regex patterns → `00_utils/05_re.ipynb`
- Subprocess helpers → `00_utils/10_subprocess.ipynb`
- Notebook helpers → `00_utils/07_nb.ipynb`

Before creating new utility modules, use `check_before_create` and `suggest_location` tools.

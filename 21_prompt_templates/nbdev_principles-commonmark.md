

# nbdev Principles (concise)

- Edit notebooks in `{nbs_path}/`, never generated `{lib}/` .py files.

- `nbs/index.ipynb` → README.md; never edit README.md directly.

- Do not define `__all__`; nbdev generates exports.

- No relative imports; use absolute imports from `{lib}`.

- One function or class per code cell; define helpers before they are
  used.

- For submodules, `00__init__.ipynb` → `#| default_exp <sub>.__init__`.

- Prefer pytest in `tests/`; use `nbs/99_tests/` only for
  fixtures/mocks.

- Mark long examples with `#| eval: false`.

- Split long narrative with `####` in separate markdown cells.

- Use NumPy-style docstrings (Parameters, Returns, Raises, Examples).

## State Management for MCP Tools

- MCP is stateless between calls; avoid private attributes (`self._xxx`)
  in exported classes.

- Use computed properties instead of stored state:
  `@property def config_path(self): return get_config_path()`.

- Prefer pure functions with explicit parameters over classes with
  hidden state.

- If caching is needed, use explicit cache modules or
  functools.lru_cache, not instance attributes.

- All tool functions should be idempotent where possible.

## Utilities Belong in Utils

- Path functions → `00_utils/08_paths.ipynb`
- I/O functions (JSON/TOML/YAML) → `00_utils/11_io.ipynb`
- Type definitions (dataclasses, TypedDicts) → `00_utils/01_types.ipynb`
- Regex patterns → `00_utils/05_re.ipynb`
- Subprocess helpers → `00_utils/10_subprocess.ipynb`
- Notebook helpers → `00_utils/07_nb.ipynb`

Before creating new utility modules, use `check_before_create` and
`suggest_location` tools.

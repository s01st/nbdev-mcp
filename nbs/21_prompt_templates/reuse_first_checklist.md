# Reuse-First Checklist for {lib}

1. Search existing notebooks in `{nbs_path}/` (ripgrep, `analyze_exports`, `read_notebook_cell`) for a helper to reuse.

2. Use `find_symbol("name")` (backed by `_modidx.py`) to see if the symbol already exists before adding a new cell.

3. Generate a dependency snapshot early: `dependency_snapshot(scope="both", write_qmd="docs/deps.qmd")` (or `dependency_tree`) and refresh after meaningful changes.

4. Check `roadmap.ipynb` (project root or nbs/) for priorities before adding new notebooks or APIs.

5. Extend or patch existing modules before creating new ones; keep related symbols together.

6. Match package hierarchy: notebook path `{nbs_path}/a/b/` → `#| default_exp a.b.<module>`; if the notebook is `00__init__.ipynb`, use `a.b.__init__`.

7. `nbs/index.ipynb` becomes README.md and does not need `default_exp`.

8. Prefer imports over duplication; if you add a helper, ensure downstream callers import it instead of copying logic.

9. When a block is 5–10 lines of control flow, extract a small utility and call it; keep top-level functions small.

10. After edits, run `nbdev_export` and appropriate tests (`pytest` or `nbdev_test`).

11. Review `{lib}/_modidx.py` (or run `modidx_audit` / `dependency_snapshot`) to confirm exports are unique, non-private, and notebooks are numbered.

12. Dead-code reports are signals: some symbols are used in tutorials/docs, but unused exports can also indicate duplication.

13. Duplicate analysis is heuristic: ABC method implementations and name variants may be intentional (e.g., diamonds_2d/3d/nd vs diamonds, foo_numpy/foo_torch vs foo); only merge when reasoning supports a shared helper.

14. Keep living docs current: `ROADMAP.md`, `TODOs.md`, `*_PLAN.md`, and agent docs under `.claude/` or `.codex/`.

15. Put all scripting/CLI logic in `nbs/` and expose it via `settings.ini` (`console_scripts`); avoid ad-hoc scripts outside nbdev.

16. Repo-level `.md` files can be added to `nbs/index.ipynb` as markdown cells (use `split_markdown_cells` to convert).

17. Keep export/cleanup cells (e.g., `#| hide\nimport nbdev; nbdev.nbdev_export()`) at the end; place new code cells above them and add a fitting markdown subsection heading.

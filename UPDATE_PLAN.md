# Update Plan (as of 2026-01-02)

Goal: fold deltas from scripts/mcp.nbdev.py into the nbdev-mcp package while keeping notebook-first workflow and living docs current.

Notebooks to edit/add
- [x] nbs/00_utils/04_config.ipynb — add configurable timeout defaults for long-running scans.
- [x] nbs/12_tasks/03_dedup.ipynb — add deadline-aware duplicate scanning and timing metadata.
- [x] nbs/20_prompts.ipynb — update workflow guidance (README/index, dunder methods, dead-code nuance, living docs).
- [ ] nbs/10_resources.ipynb — register safe read-file resource and describe repo-level markdown ingestion.
- [ ] nbs/30_mcp.ipynb — audit transport/stdio behavior for parity with scripts/mcp.nbdev.py.
- [ ] nbs/index.ipynb — optionally pull in CHANGE_LOG.md and UPDATE_PLAN.md as markdown cells.

Functions/tools to edit/add
- [x] find_all_duplicates, find_functional_duplicates, find_named_duplicates, find_semantic_duplicates — accept deadlines and honor time budgets.
- [x] find_duplicates tool — timeout param with config default.
- [x] find_semantic_duplicates_tool — timeout param plus timing metadata.
- [ ] add_resources — include read_file resource registration.
- [ ] CLI wiring — verify settings.ini console scripts and transport defaults match script behavior.

Classes/data structures
- [ ] No new classes planned; avoid private members/vars.

Other files
- [ ] scripts/mcp.nbdev.py — audit deltas and migrate missing behavior into nbs/ modules; keep script as a thin wrapper.

# Change Log

## 2026-01-02 (Unreleased)

Core functionality changes
- Long-running operations now use configurable time budgets instead of fixed limits.
- Duplicate-scan tools can return partial results when time budgets are exceeded.
- Duplicate-scan responses now include timing metadata (elapsed time and timeout status).
- Workflow guidance clarified for nbdev: README derives from nbs/index.ipynb (no default_exp needed), dunder methods are valid, and dead code signals are nuanced.

New features
- Environment-configurable timeout defaults for duplicate scans (structural and semantic).
- Expanded guidance for maintaining living docs (e.g., ROADMAP.md, TODOs, *_PLAN.md) and keeping repo-level markdown in sync with index.ipynb.
- Clear directive that script logic should live in nbs/ and be exposed via settings.ini console scripts.

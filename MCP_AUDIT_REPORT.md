# MCP Audit Report

Date: 2026-02-16  
Repository: `NBDevMCP`

## Scope

This audit answers two questions:

1. How usable is this MCP for building new MCPs?
2. How functional is it for auto-setup / auto-update of Codex, Claude Code, and VS Code MCP configs?

## Method

- Code and docs review of core entry points and setup logic.
- CLI validation via dry run and status checks.
- Targeted test runs:
  - `pytest -q tests/test_paths.py tests/test_nbdev_tools.py tests/test_project_tools.py` -> 53 passed
  - `pytest -q tests/test_dead_code_weighting.py tests/test_lint_tools.py tests/test_analysis_tools.py` -> 18 passed

## Executive Summary

| Area | Score (10) | Verdict |
|---|---:|---|
| Usability for making new MCPs | 7.5 | Strong internal architecture and tooling; weak explicit scaffolding/docs for non-nbdev MCP authoring. |
| Auto-setup / auto-update for Codex, Claude Code, VS Code | 6.0 | Good install/status primitives; inconsistent config targets and limited update safety/test coverage. |

---

## 1) Usability for Making New MCPs

### What works well

- Clear composition pattern for assembling an MCP server from modular subsystems:
  - `create_nbdev_mcp` composes resources, tools, prompts, tasks in one place (`nbdev_mcp/mcp.py:73`).
  - Modular registrars (`add_resources`, `add_*_tools`, `add_prompts`) improve reuse and extension (`nbdev_mcp/mcp.py:81`).
- Broad, practical tool surface already exposed and integration-tested:
  - Integration test asserts expected core tools and minimum tool count (`tests/test_mcp_integration.py:119`).
- Strong nbdev workflow support:
  - Notebook-first guardrails and version-aware nbdev command execution (`nbdev_mcp/tools/nbdev.py:25`, `nbdev_mcp/utils/paths.py:188`).

### Current limits

- This project is excellent as an nbdev MCP, but not yet a first-class “new MCP scaffolder”:
  - No dedicated “create a new MCP package/server skeleton” tool or template workflow.
- Repo has parallel server script implementations in `scripts/` that can blur source-of-truth for contributors:
  - `scripts/mcp.nbdev.py`
  - `scripts/mcp.style.py`
- README emphasizes manual integration snippets, with limited guidance on reusing this codebase as a generic MCP framework.

### Assessment

Usability is high for extending this MCP and medium for bootstrapping entirely new MCPs from scratch.  
The architecture is reusable; the developer experience for “start a new MCP project” needs dedicated scaffolding docs/tools.

---

## 2) Auto-Setup / Auto-Update (Codex, Claude Code, VS Code)

### What is functional today

- One command installs config entries across providers (`install` command) with dry-run support (`nbdev_mcp/mcp.py:607`).
- Provider-aware config schemas are handled (`mcpServers` vs `servers`) (`nbdev_mcp/mcp.py:234`).
- VS Code / Cursor autostart helper exists (`nbdev_mcp/mcp.py:346`).
- `status` gives quick installation visibility (`nbdev_mcp/mcp.py:651`).

### Gaps and risks

- **Provider config inconsistency (high impact):**
  - Codex path/format differs by module:
    - `nbdev_mcp/mcp.py` writes `~/.codex/config.json` (`nbdev_mcp/mcp.py:211`)
    - path utils point to `~/.codex/config.toml` (`nbdev_mcp/utils/paths.py:1017`)
  - README documents Codex TOML (`README.md:203`) while installer currently targets JSON.
- **Claude target mismatch (high impact):**
  - Installer targets Claude Desktop config path (`nbdev_mcp/mcp.py:161`)
  - README documents Claude Code `~/.claude.json` flow (`README.md:152`)
- **Parse safety risk (high impact):**
  - `_parse_jsonc` falls back to `{}` on parse failures (`nbdev_mcp/mcp.py:328`).
  - `install_to_provider` will then write a new config object, risking overwrite/clobber of existing settings (`nbdev_mcp/mcp.py:384`).
- **“Auto-update” is partial:**
  - Current behavior is idempotent re-install/update when command is re-run.
  - No background update agent, version migration planner, or schema drift detector.
- **Test gap:**
  - Strong tests exist for many tool domains, but no direct tests found for install/uninstall/status config mutation paths in `nbdev_mcp/mcp.py`.

### Assessment

Auto-setup is operational for basic cases.  
Auto-update is currently “manual re-run update” and needs stronger consistency, safety, and test coverage to be robust across Codex/Claude Code/VS Code.

---

## Priority Recommendations

1. Unify provider config resolution in a single source of truth used by installer + path utilities + docs.
2. Add provider integration tests for install/uninstall/status using temp config files and JSONC fixtures.
3. Make parse failures fail-safe: abort write + surface clear error, optionally create backup before mutation.
4. Add explicit `nbdev-mcp update` semantics (reconcile/merge strategy + dry-run diff).
5. Update README/index docs to match actual installer behavior, including Codex and Claude variants.
6. Add a “new MCP scaffolding” guide/tool if MCP authoring is a primary product goal.

## Overall Conclusion

This repo is a strong nbdev-focused MCP platform with a good modular core and mature analysis/lint/test tooling.  
For the two target outcomes, it is already useful, but production-grade cross-client setup/update needs consistency fixes and dedicated mutation tests before being considered robust.

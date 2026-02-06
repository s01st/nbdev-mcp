# Bad Request Mitigation Proposal (MCP / nbdev-mcp)

## Context
Recent sessions show recurring `{"detail":"Bad Request"}` errors originating from the **LLM response payload**, not the repo or shell. These are triggered by oversized tool responses (e.g., dumping large notebook cells) or malformed tool payloads. A second failure mode was also observed: notebook JSON accidentally minified to a single line via `json.dumps` without indentation. This proposal adds guardrails inside NBDevMCP to prevent those errors at the source.

## Goals
1. Prevent oversized outputs from tools and notebook reads.
2. Make notebook edits safe and minimal (no full JSON dumps).
3. Prevent minified notebook JSON (single-line) from being written or silently accepted.
4. Provide explicit “safe mode” for LLMs with strict output limits.
5. Offer ergonomic utilities to update large notebooks without manual cell dumps.

## Proposed Changes

### 1) Global Output Guard
- Add a hard **max-response-size** gate in tool responses.
- If a tool would exceed the limit:
  - return a short summary
  - add a `truncated: true` flag with a **path to saved output**
- Implement a shared `SAFE_OUTPUT_LIMIT` (default ~32KB) and per-tool caps.
- If MCP server middleware hooks are unavailable, enforce this at the tool layer.

### 2) Safe Notebook Read
- Extend `read_notebook_cell` with a **hard truncate limit** and `max_lines` option.
- If the cell exceeds limits, return:
  - leading/trailing slices
  - `hash` of full cell
  - saved full text to repo root or `~/Downloads/<repo>/` with a path reference

### 3) Safe Notebook Edit API
- Add `edit_notebook_cell_safe`:
  - accepts **line-range patches** instead of full cell replacement
  - optional `ast.parse` validation before save
  - writes with nbformat / `write_nb`, never raw `json.dumps`

### 4) Large Cell Policies
- Detect when a notebook cell is > N lines or > M chars.
- For large cells, avoid full cell print and require:
  - `read_notebook_cell` slices only
  - `edit_notebook_cell_safe` patch edits

### 5) Logging / Audit
- Add a lightweight **response-size log** and a `tool_response_bytes` field in server logs.
- If response size > threshold, log warning and auto-truncate.

### 6) Safe Mode (Explicit)
- Add `SAFE_MODE` toggle (env var or config) that:
  - forces truncation
  - disables full cell dumps
  - enforces all edits through patch APIs
  - rejects oversized outputs with clear guidance
  - blocks single-line notebook JSON reads/writes

## Rollout Plan
1. Block minified notebook JSON reads/writes (minimal, fast)
2. Implement guard + safe read (minimal)
3. Add safe edit patch tool (medium)
4. Enable SAFE_MODE by default for stdio transport
5. Add logs for response-size and truncation reasons

## Test Plan
- Unit tests for truncation behavior on `read_notebook_cell`.
- Unit tests that reject minified notebook JSON reads/writes.
- Unit tests for `edit_notebook_cell_safe` with AST validation.
- Simulated large notebook cell response and ensure server returns summary + path.

## Expected Impact
- Eliminates `Bad Request` errors caused by oversized responses.
- Makes large notebook workflows robust.
- Improves reliability for large nbdev projects.

## Out of Scope
- LLM client UI limits.
- Remote notebook rendering.

---

**Status:** Proposal
**Owner:** NBDevMCP maintainers
**Next action:** Implement output guard + safe read API

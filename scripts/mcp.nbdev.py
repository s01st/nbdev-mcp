#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nbdev MCP server (multi-project, rich output, workflow-aware) — Python 3.12+

Features:
- Works from anywhere: select a project by path or alias, or pass project= per call.
- Multi-project support: bookmarks (alias -> path), discovery via NBDEV_PROJECTS or common roots.
- Tools: nbdev_prepare/export/test, pytest, ensure_env/export_env (mamba/conda).
- **Notebook editing**: check_if_generated, find_source_notebook, edit/read/add notebook cells.
- **Workflow guidance**: Prompts that instruct Claude to use nbdev properly (edit notebooks, not .py files).
- Resources: project summary, tree, settings.ini, env file, read file (safe, read-only).
- Prompts: nbdev_workflow_philosophy (CRITICAL), nbdev_howto, module_scaffold.
- Transports: stdio (for desktop clients), streamable-http (built-in default HTTP), or HTTP via Uvicorn for custom host/port/path.
- Rich-formatted "pretty" output for UI display; never prints to stdout in stdio mode.

Philosophy:
In nbdev, .ipynb notebooks are SOURCE CODE. Python .py files are GENERATED.
This MCP guides Claude Code to follow this philosophy by providing tools to:
1. Check if files are generated (check_if_generated)
2. Find source notebooks (find_source_notebook)
3. Edit notebooks instead of .py files (edit_notebook_cell)
4. Always run nbdev_export after editing

$ python mcp.nbdev.v2.py --transport http --host 127.0.0.1 --port 8766 --path /mcp

`~/Library/Application Support/Code/User/mcp.json`
{
    "servers": {
        "nbdev-mcp-v2": {
            "type": "stdio",
            "command": "mamba",
            "args": [
                "run",
                "-n",
                "core",
                "python",
                "/Users/sm1901/MCPs/mcp.nbdev.v2.py",
                "--transport",
                "stdio"
            ]
        }
    }
}
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import re
import runpy
import shlex
import subprocess
import sys
import textwrap
from configparser import ConfigParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Iterable, Tuple, Set

from mcp.server.fastmcp import FastMCP  # official MCP Python SDK (FastMCP 2.0+)
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

__version__ = "1.0.0"  # Added console-script guidance and __main__ guard lint/prompt

# ----------------------------- logging (stderr) ------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("mcp.nbdev")

# ----------------------------- config & bookmarks ---------------------------
def _config_dir() -> Path:
    """Return the directory for storing MCP nbdev config (bookmarks)."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / "mcp.nbdev"
    d.mkdir(parents=True, exist_ok=True)
    return d

BOOKMARKS_PATH = _config_dir() / "projects.json"

def _load_bookmarks() -> Dict[str, str]:
    """Load saved project path aliases from the bookmarks JSON file."""
    if BOOKMARKS_PATH.exists():
        try:
            data = json.loads(BOOKMARKS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "aliases" in data and isinstance(data["aliases"], dict):
                # Normalize paths
                return {k: str(Path(v)) for k, v in data["aliases"].items()}
        except Exception:
            pass
    return {}

def _save_bookmarks(aliases: Dict[str, str]) -> None:
    """Save the project path aliases to the bookmarks JSON file."""
    BOOKMARKS_PATH.write_text(json.dumps({"aliases": aliases}, indent=2), encoding="utf-8")

# ----------------------------- globals & helpers ----------------------------
CURRENT_PROJECT: Optional[Path] = None  # currently selected nbdev project (None if not set)

def _expand(p: str) -> Path:
    """Expand user/home variables and return an absolute Path."""
    return Path(os.path.expanduser(os.path.expandvars(p))).resolve()

def _console(width: int = 100) -> Console:
    """Create a Rich Console for capturing formatted text (never prints to stdout)."""
    # record=True lets us export styled output; use StringIO so no stdout output.
    return Console(file=io.StringIO(), force_terminal=True, width=width, record=True)

def _export_console(c: Console) -> str:
    """Export the recorded console output as text (with rich formatting)."""
    return c.export_text(clear=False)

def _ok(errcode: int) -> bool:
    """Return True if the given error code is zero (indicating success)."""
    return int(errcode) == 0

def _tail(s: str | None, limit: int = 40000) -> str:
    """Return the tail of a long string (truncate if exceeds limit)."""
    if not s:
        return ""
    return s if len(s) <= limit else f"...[truncated {len(s)-limit} chars]...\\n" + s[-limit:]

def _truncate_source(s: str, limit: int = 1000) -> str:
    """Truncate source code with indication if too long."""
    if not s:
        return ""
    if len(s) <= limit:
        return s
    return s[:limit] + f"\\n... [truncated {len(s)-limit} more chars]"

def _join_source_lines(source_lines: List[str]) -> str:
    """
    Properly join notebook source lines, ensuring newlines between lines.

    Jupyter notebooks store cell source as a list of strings. Each string
    should have a trailing newline, but this isn't always guaranteed.
    This function ensures proper line breaks.
    """
    if not source_lines:
        return ""

    # Join lines, adding newline if not present
    result = []
    for line in source_lines:
        if line.endswith('\\n'):
            result.append(line)
        else:
            # Last line might not have trailing newline, or it's malformed
            result.append(line + '\\n' if line else line)

    # Join and remove final trailing newline if it's just empty
    joined = "".join(result)
    return joined.rstrip('\\n') if joined.endswith('\\n\\n') else joined


def split_markdown_into_cells(markdown: str) -> List[Dict[str, Any]]:
    """
    Split a markdown document into notebook-ready markdown cells.

    Rules:
    - Each heading line (`#`, `##`, …) is its own cell.
    - Text after a heading up to the next heading is a separate cell.
    - Reference link definitions (`[id]: url`) are propagated to every cell that uses that id.
    """
    lines = markdown.splitlines()

    # Collect reference link definitions and strip them from content
    ref_defs: Dict[str, str] = {}
    content_lines: List[str] = []
    ref_pattern = re.compile(r"^\\s*\\[([^\\]]+)\\]:\\s*(.+)$")
    for ln in lines:
        m = ref_pattern.match(ln)
        if m:
            ref_defs[m.group(1)] = ln
        else:
            content_lines.append(ln)

    cells_raw: List[str] = []
    buffer: List[str] = []

    def flush_buffer():
        if buffer:
            cells_raw.append("\\n".join(buffer).rstrip())
            buffer.clear()

    header_pattern = re.compile(r"^#{1,6}\\s")
    for ln in content_lines:
        if header_pattern.match(ln):
            flush_buffer()
            cells_raw.append(ln.rstrip())
        else:
            buffer.append(ln)
    flush_buffer()

    def refs_used(text: str) -> List[str]:
        # [text][id] or bare [id] not followed by (
        ids: Set[str] = set()
        for m in re.finditer(r"\\[([^\\]]+)\\]\\[([^\\]]+)\\]", text):
            ids.add(m.group(2))
        for m in re.finditer(r"(?<!\\!)\\[(?!\\[)([^\\]]+)\\](?!\\()", text):
            token = m.group(1)
            if token in ref_defs:
                ids.add(token)
        return list(ids)

    cells: List[Dict[str, Any]] = []
    for cell_text in cells_raw:
        used = refs_used(cell_text)
        lines_out = [cell_text] if cell_text else []
        if used:
            if lines_out and lines_out[-1].strip():
                lines_out.append("")
            for ref in used:
                lines_out.append(ref_defs[ref])
        cells.append({"cell_type": "markdown", "source": "\\n".join(lines_out).rstrip()})

    return cells

def _settings_dict(project: Path) -> Dict[str, str]:
    """Read nbdev settings.ini from the project and return key settings in a dict."""
    cfg = ConfigParser()
    f = project / "settings.ini"
    if not f.exists():
        return {}
    cfg.read(f)
    d = dict(cfg["DEFAULT"]) if "DEFAULT" in cfg else {}
    return {
        "lib_name": d.get("lib_name", "").strip(),
        "nbs_path": d.get("nbs_path", "").strip(),
        "doc_path": d.get("doc_path", "").strip(),
        "branch": d.get("branch", "").strip(),
        "repo": d.get("repo", "").strip(),
        "user": d.get("user", "").strip(),
        "black_formatting": d.get("black_formatting", "").strip(),
    }

def _nbs_dir(project: Path) -> Path:
    """Get the notebook directory Path for the project (resolves nbs_path or defaults to 'nbs')."""
    s = _settings_dict(project)
    return (project / (s.get("nbs_path") or "nbs")).resolve()

def _is_nbdev_project(p: Path) -> bool:
    """Check if the given Path is an nbdev project (has settings.ini and nbs directory)."""
    return (p / "settings.ini").is_file() and _nbs_dir(p).exists()

def _find_project_root(start: Path) -> Optional[Path]:
    """Ascend from the given path to find the root of an nbdev project (or return None)."""
    p = start.resolve()
    if p.is_file():
        p = p.parent
    while True:
        if _is_nbdev_project(p):
            return p
        if p.parent == p:
            return None  # reached filesystem root
        p = p.parent

def _env_file(project: Path) -> Path:
    """Return the Path to the conda environment YAML file (env.<lib_name>.yml) for the project."""
    lib = _settings_dict(project).get("lib_name") or "pkg"
    return project / f"env.{lib}.yml"

def _discover_env_name(project: Path) -> Optional[str]:
    """Read the env YAML file and extract the environment 'name' field, if present."""
    yml = _env_file(project)
    if not yml.exists():
        return None
    for line in yml.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\\s*name\\s*:\\s*([A-Za-z0-9._-]+)\\s*$", line)
        if m:
            return m.group(1)
    return None

def _which(names: List[str]) -> Optional[str]:
    """Find the first executable in the given list of names that exists in PATH (returns the name)."""
    for n in names:
        try:
            subprocess.run([n, "-V"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return n
        except Exception:
            continue
    return None

def _wrap_with_env(cmd: List[str], project: Path, use_env: bool = True) -> List[str]:
    """
    If use_env is True and the project has an associated conda/mamba env, 
    prefix the command with 'mamba/conda run -n <env_name>' to run inside that env.
    """
    if not use_env:
        return cmd
    env_name = _discover_env_name(project)
    exe = _which(["mamba", "conda"])
    if env_name and exe:
        return [exe, "run", "-n", env_name] + cmd
    return cmd  # fallback: run in the current server environment

def _run(cmd: List[str], cwd: Path) -> Dict[str, Any]:
    """Execute a subprocess command and capture its output and return code."""
    proc = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True)
    return {
        "cmd": " ".join(shlex.quote(x) for x in cmd),
        "cwd": str(cwd),
        "returncode": proc.returncode,
        "stdout": _tail(proc.stdout),
        "stderr": _tail(proc.stderr),
        "ok": _ok(proc.returncode),
    }

def _project_summary(project: Path) -> Dict[str, Any]:
    """Gather key info about the nbdev project (paths, existence of index.ipynb, README, env file)."""
    s = _settings_dict(project)
    return {
        "project": str(project),
        "lib_name": s.get("lib_name"),
        "nbs_dir": str(_nbs_dir(project)),
        "has_index_ipynb": (_nbs_dir(project) / "index.ipynb").exists(),
        "has_readme": (project / "README.md").exists(),
        "env_file": str(_env_file(project)) if _env_file(project).exists() else None,
    }

def _require_project() -> Path:
    """Get the currently active project Path or raise an error if none is selected."""
    if CURRENT_PROJECT is None:
        raise RuntimeError("No project selected. Use set_project(...) or pass a project before using nbdev tools.")
    return CURRENT_PROJECT

def _resolve_selector(selector: Optional[str]) -> Path:
    """
    Resolve a project selector string to an nbdev project Path.
    Selector formats:
      - None -> returns CURRENT_PROJECT (if set, otherwise raises error).
      - '@alias' or 'alias:NAME' -> looks up the alias in bookmarks.
      - any other string -> treated as a filesystem path (absolute, relative, ~/ expansion, etc.),
        which can point directly to a project folder or to a subdirectory/file within a project.
    """
    if not selector:
        return _require_project()
    aliases = _load_bookmarks()
    sel = selector.strip()
    if sel.startswith("alias:"):
        sel = sel.split(":", 1)[1]
    if sel.startswith("@"):
        sel = sel[1:]
    if sel in aliases:
        # If it's a known alias, use that path
        p = _expand(aliases[sel])
        root = _find_project_root(p) or p
        if _is_nbdev_project(root):
            return root
        raise RuntimeError(f"Alias '{sel}' points to a directory that is not an nbdev project: {p}")
    # Otherwise, treat selector as a path (or a path within a project)
    p = _expand(sel)
    root = _find_project_root(p) or p
    if _is_nbdev_project(root):
        return root
    raise RuntimeError(f"Not an nbdev project (requires settings.ini and nbs/ folder): {p}")

# ----------------------------- MCP server definitions -----------------------
def add_resources(mcp: FastMCP) -> None:
    """Attach nbdev resource endpoints to the MCP."""
    @mcp.resource("nb://project")
    def resource_project_summary() -> str:
        """Resource: JSON summary of the current project."""
        p = _require_project()
        return json.dumps(_project_summary(p), indent=2)

    @mcp.resource("nb://projects")
    def resource_projects() -> str:
        """Resource: JSON of saved project bookmarks and NBDEV_PROJECTS env variable."""
        data = {
            "bookmarks": _load_bookmarks(),
            "NBDEV_PROJECTS": os.environ.get("NBDEV_PROJECTS", ""),
        }
        return json.dumps(data, indent=2)

    @mcp.resource("nb://tree")
    def resource_tree() -> str:
        """Resource: JSON listing of notebooks in the current project (limited to 600 files)."""
        p = _require_project()
        nbs = _nbs_dir(p)
        files: List[str] = []
        if nbs.exists():
            for q in nbs.rglob("*.ipynb"):
                try:
                    files.append(str(q.relative_to(p)))
                except Exception:
                    files.append(str(q))
        payload = {
            "root": str(p),
            "nbs_dir": str(nbs),
            "notebooks": files[:600],
            "has_settings_ini": (p / "settings.ini").exists(),
            "has_readme": (p / "README.md").exists(),
        }
        return json.dumps(payload, indent=2)

    @mcp.resource("nb://roadmap")
    def resource_roadmap() -> str:
        """Resource: pointer to roadmap.ipynb if it exists (project root or nbs/)."""
        p = _require_project()
        candidates = [p / "roadmap.ipynb", _nbs_dir(p) / "roadmap.ipynb"]
        for c in candidates:
            if c.exists():
                return json.dumps({"path": str(c.relative_to(p)), "exists": True}, indent=2)
        return json.dumps({"path": None, "exists": False, "message": "roadmap.ipynb not found in project root or nbs/"}, indent=2)

    @mcp.resource("nb://settings")
    def resource_settings() -> str:
        """Resource: contents of the current project's settings.ini file (text)."""
        p = _require_project()
        f = p / "settings.ini"
        return f.read_text(encoding="utf-8") if f.exists() else "No settings.ini found."

    @mcp.resource("nb://env")
    def resource_env_file() -> str:
        """Resource: contents of the current project's environment YAML file (text)."""
        p = _require_project()
        ef = _env_file(p)
        return ef.read_text(encoding="utf-8") if ef.exists() else f"No env file at {ef}"

    @mcp.resource("nb://file/{relpath}")
    def resource_read_file(relpath: str) -> str:
        """Resource: read a file by relative path within the current project (text content)."""
        p = _require_project()
        f = (p / relpath).resolve()
        try:
            f.relative_to(p)
        except Exception:
            return f"Refusing to read outside project: {f}"
        if not f.exists():
            return f"Not found: {f}"
        try:
            return f.read_text(encoding="utf-8")
        except Exception as e:
            return f"Could not read {f}: {e}"

    @mcp.resource("nb://note/index-to-readme")
    def resource_index_to_readme_note() -> str:
        """Resource: JSON note explaining that nbs/index.ipynb becomes README.md in nbdev."""
        p = _require_project()
        lib = _settings_dict(p).get("lib_name") or "<your_lib>"
        msg = "In nbdev, `nbs/index.ipynb` becomes `README.md` (the docs home page)."
        return json.dumps({"lib": lib, "message": msg}, indent=2)

def add_project_tools(mcp: FastMCP) -> None:
    """Attach project management tools (select/list/bookmark projects) to the MCP."""
    @mcp.tool()
    def set_project(selector: str) -> Dict[str, Any]:
        """Tool: Select an nbdev project to make it active (by path or alias)."""
        global CURRENT_PROJECT
        try:
            p = _resolve_selector(selector)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        CURRENT_PROJECT = p
        meta = _project_summary(p)
        pretty = _render_result("Project selected", meta)
        return {"ok": True, "project": meta, "pretty": pretty}

    @mcp.tool()
    def current_project() -> Dict[str, Any]:
        """Tool: Show the currently active project's summary information."""
        p = _require_project()
        meta = _project_summary(p)
        pretty = _render_result("Current project", meta)
        return {"ok": True, "project": meta, "pretty": pretty}

    @mcp.tool()
    def console_scripts_status(project: Optional[str] = None) -> Dict[str, Any]:
        """Tool: Show console_scripts entry points from settings.ini and suggest how to add them."""
        try:
            p = _resolve_selector(project)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        cfg = ConfigParser()
        cfg.read(p / "settings.ini")
        cs = (cfg["DEFAULT"].get("console_scripts", "") if "DEFAULT" in cfg else "").strip()
        entries = [e for e in cs.split() if e] if cs else []
        msg = "No console_scripts configured. Add e.g. `console_scripts = mycli=mypkg:main` in settings.ini." if not entries else "console_scripts present."
        pretty = _render_result("console_scripts", {"entries": entries or "None"}, {})
        return {"ok": True, "entries": entries, "message": msg, "pretty": pretty}

    @mcp.tool()
    def find_projects(roots: Optional[List[str]] = None, max_results: int = 50) -> Dict[str, Any]:
        """Tool: Scan given directories (or common defaults) for nbdev projects."""
        search_dirs: List[Path] = []
        if roots:
            search_dirs += [_expand(r) for r in roots]
        env = os.environ.get("NBDEV_PROJECTS")
        if env:
            for r in env.split(os.pathsep):
                pr = _expand(r)
                if pr.exists():
                    search_dirs.append(pr)
        # Heuristic: search typical folders in user home for projects
        home = Path.home()
        for sub in ("code", "projects", "repos", "src", "Dev", "dev", "Documents"):
            d = home / sub
            if d.exists():
                search_dirs.append(d)

        seen, results = set(), []
        for base in search_dirs:
            if not base.is_dir():
                continue
            for p in base.iterdir():
                if p.is_dir() and p not in seen:
                    try:
                        if _is_nbdev_project(p):
                            results.append(_project_summary(p))
                            seen.add(p)
                    except Exception:
                        continue
            if len(results) >= max_results:
                break

        # Format a pretty table of found projects
        c = _console()
        t = Table(title="Discovered nbdev projects")
        t.add_column("lib_name")
        t.add_column("path")
        t.add_column("nbs_dir")
        for r in results:
            t.add_row(r.get("lib_name") or "?", r["project"], r["nbs_dir"])
        c.print(t)
        return {"ok": True, "results": results, "pretty": _export_console(c)}

    @mcp.tool()
    def bookmark_project(alias: str, path: str) -> Dict[str, Any]:
        """Tool: Bookmark an nbdev project path with a short alias name."""
        try:
            root = _resolve_selector(path)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        aliases = _load_bookmarks()
        aliases[alias] = str(root)
        _save_bookmarks(aliases)
        meta = {"alias": alias, "path": str(root)}
        pretty = _render_result("Bookmarked project", meta)
        return {"ok": True, **meta, "pretty": pretty}

    @mcp.tool()
    def list_bookmarks() -> Dict[str, Any]:
        """Tool: List all saved project bookmarks (alias -> path)."""
        aliases = _load_bookmarks()
        c = _console()
        t = Table(title="Project bookmarks")
        t.add_column("alias")
        t.add_column("path")
        for k, v in aliases.items():
            t.add_row(k, v)
        c.print(t)
        return {"ok": True, "aliases": aliases, "pretty": _export_console(c)}

    @mcp.tool()
    def remove_bookmark(alias: str) -> Dict[str, Any]:
        """Tool: Remove a saved project bookmark by alias."""
        aliases = _load_bookmarks()
        if alias in aliases:
            path = aliases.pop(alias)
            _save_bookmarks(aliases)
            meta = {"alias": alias, "removed": path}
            pretty = _render_result("Removed bookmark", meta)
            return {"ok": True, **meta, "pretty": pretty}
        return {"ok": False, "error": f"No such alias: {alias}"}

def add_env_tools(mcp: FastMCP) -> None:
    """Attach environment management tools (conda/mamba env creation/export) to the MCP."""
    @mcp.tool()
    def ensure_env(project: Optional[str] = None, update: bool = False) -> Dict[str, Any]:
        """Tool: Create or update the project's conda environment from its env YAML file."""
        try:
            p = _resolve_selector(project)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        env_name = _discover_env_name(p)
        env_file = _env_file(p)
        exe = _which(["mamba", "conda"])
        c = _console()

        if not env_file.exists() or not env_name:
            c.print(Panel("No env.<lib>.yml found or missing 'name:' field in YAML.", title="Environment"))
            return {"ok": False, "pretty": _export_console(c)}

        if not exe:
            c.print(Panel("Neither 'mamba' nor 'conda' was found on PATH.", title="Environment"))
            return {"ok": False, "pretty": _export_console(c)}

        cmd = [exe, "env", "update" if update else "create", "-f", str(env_file)]
        if update and env_name:
            cmd += ["-n", env_name]
        logs = _run(cmd, cwd=p)
        meta = {"env_file": str(env_file), "env_name": env_name, "project": str(p)}
        pretty = _render_result("Environment created/updated", meta, logs)
        return {**logs, **meta, "pretty": pretty}

    @mcp.tool()
    def export_env(project: Optional[str] = None, out_path: Optional[str] = None) -> Dict[str, Any]:
        """Tool: Export the current environment (the server's env) to the project's env YAML file."""
        try:
            p = _resolve_selector(project)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        env_file = _env_file(p) if out_path is None else _expand(out_path)
        exe = _which(["mamba", "conda"]) or "conda"
        cmd = [exe, "env", "export", "--no-builds", "--prefix", sys.prefix, "--file", str(env_file)]
        logs = _run(cmd, cwd=p)
        meta = {"exported_to": str(env_file), "project": str(p)}
        pretty = _render_result("Environment exported", meta, logs)
        return {**logs, **meta, "pretty": pretty}

def add_nbdev_tools(mcp: FastMCP) -> None:
    """Attach nbdev build/test tools (prepare, export, test, etc.) to the MCP."""
    @mcp.tool()
    def nbdev_prepare(project: Optional[str] = None, extra_args: Optional[List[str]] = None,
                      use_env: bool = True) -> Dict[str, Any]:
        """Tool: Run nbdev_prepare (export, test, clean notebooks) for the selected project."""
        try:
            p = _resolve_selector(project)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        cmd = _wrap_with_env(["nbdev_prepare"] + (extra_args or []), p, use_env)
        logs = _run(cmd, cwd=p)
        pretty = _render_result("nbdev_prepare", _project_summary(p), logs)
        return {**logs, "project": str(p), "pretty": pretty}

    @mcp.tool()
    def nbdev_export(project: Optional[str] = None,
                     processors: Optional[List[str]] = None,
                     extra_args: Optional[List[str]] = None,
                     use_env: bool = True) -> Dict[str, Any]:
        """Tool: Run nbdev_export on the project. Optionally specify pre/post processors."""
        try:
            p = _resolve_selector(project)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        cmd = ["nbdev_export"]
        if processors:
            cmd += ["--procs"] + processors
        if extra_args:
            cmd += extra_args
        cmd = _wrap_with_env(cmd, p, use_env)
        logs = _run(cmd, cwd=p)
        pretty = _render_result("nbdev_export", _project_summary(p), logs)
        return {**logs, "project": str(p), "pretty": pretty}

    @mcp.tool()
    def nbdev_test(project: Optional[str] = None,
                   path: Optional[str] = None,
                   flags: str = "",
                   n_workers: Optional[int] = None,
                   do_print: bool = False,
                   file_re: Optional[str] = None,
                   use_env: bool = True) -> Dict[str, Any]:
        """Tool: Run nbdev_test for the project (with optional filtering and flags)."""
        try:
            p = _resolve_selector(project)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        cmd = ["nbdev_test"]
        if path:
            cmd += ["--path", path]
        if flags:
            cmd += ["--flags", flags]
        if n_workers is not None:
            cmd += ["--n_workers", str(n_workers)]
        if do_print:
            cmd += ["--do_print"]
        if file_re:
            cmd += ["--file_re", file_re]
        cmd = _wrap_with_env(cmd, p, use_env)
        logs = _run(cmd, cwd=p)
        pretty = _render_result("nbdev_test", _project_summary(p), logs)
        return {**logs, "project": str(p), "pretty": pretty}

    @mcp.tool()
    def pytest_run(project: Optional[str] = None,
                   args: Optional[List[str]] = None,
                   use_env: bool = True) -> Dict[str, Any]:
        """Tool: Run pytest on the project's tests/ directory (e.g., pass ['-q'] or other pytest args)."""
        try:
            p = _resolve_selector(project)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        cmd = _wrap_with_env(["pytest"] + (args or ["-q"]), p, use_env)
        logs = _run(cmd, cwd=p)
        pretty = _render_result("pytest", _project_summary(p), logs)
        return {**logs, "project": str(p), "pretty": pretty}

def add_notebook_editing_tools(mcp: FastMCP) -> None:
    """Attach tools for finding, reading, and editing notebook cells."""

    @mcp.tool()
    def check_if_generated(project: Optional[str] = None, file_path: str = "") -> Dict[str, Any]:
        """
        Tool: Check if a file is auto-generated by nbdev (should not be edited directly).
        USE THIS BEFORE EDITING ANY PYTHON FILE IN A NBDEV PROJECT!
        """
        try:
            p = _resolve_selector(project)
        except Exception as e:
            return {"ok": False, "error": str(e)}

        s = _settings_dict(p)
        lib_name = s.get("lib_name", "")

        # Check if file is in the library directory
        is_in_lib = lib_name and (file_path.startswith(lib_name + "/") or file_path.startswith(lib_name + "\\"))
        is_py_file = file_path.endswith(".py")
        is_readme = file_path == "README.md" or file_path.endswith("/README.md")

        if is_in_lib and is_py_file:
            nbs = _nbs_dir(p)
            return {
                "ok": True,
                "is_generated": True,
                "file": file_path,
                "warning": "⚠️ This file is GENERATED by nbdev. DO NOT EDIT DIRECTLY!",
                "action": f"1. Use find_source_notebook(py_file='{file_path}') to find the source notebook\n2. Edit that notebook instead\n3. Run nbdev_export() to regenerate this file",
                "pretty": f"⚠️ {file_path} is AUTO-GENERATED\nEdit the source notebook in {nbs}/ instead!"
            }

        if is_readme:
            return {
                "ok": True,
                "is_generated": True,
                "file": file_path,
                "warning": "⚠️ README.md is GENERATED from index.ipynb. DO NOT EDIT DIRECTLY!",
                "action": "Edit nbs/index.ipynb instead, then run nbdev_readme()",
                "pretty": "⚠️ README.md is AUTO-GENERATED\nEdit nbs/index.ipynb instead!"
            }

        return {
            "ok": True,
            "is_generated": False,
            "file": file_path,
            "message": "✓ This file is safe to edit (not generated by nbdev)"
        }

    @mcp.tool()
    def find_source_notebook(project: Optional[str] = None, py_file: str = "") -> Dict[str, Any]:
        """
        Tool: Find which notebook generated a given Python file.
        CRITICAL: Use this to find the source before editing any .py file!
        """
        try:
            p = _resolve_selector(project)
        except Exception as e:
            return {"ok": False, "error": str(e)}

        if not py_file:
            return {"ok": False, "error": "py_file parameter is required"}

        s = _settings_dict(p)
        lib_name = s.get("lib_name", "")
        nbs = _nbs_dir(p)

        # Extract module name from py_file (e.g., "mylib/core.py" → "core")
        py_path = Path(py_file)
        if lib_name and py_file.startswith(lib_name):
            module_name = py_file.replace(lib_name + "/", "").replace(lib_name + "\\", "")
            module_name = Path(module_name).stem
        else:
            module_name = py_path.stem

        # Look for notebook with matching default_exp
        matching_notebooks = []

        if nbs.exists():
            for nb_path in nbs.rglob("*.ipynb"):
                if ".ipynb_checkpoints" in str(nb_path):
                    continue
                try:
                    nb_data = json.loads(nb_path.read_text(encoding="utf-8"))
                    for cell in nb_data.get("cells", []):
                        if cell.get("cell_type") == "code":
                            source = _join_source_lines(cell.get("source", []))
                            match = re.search(r'#\|\s*default_exp\s+(\w+)', source)
                            if match and match.group(1) == module_name:
                                matching_notebooks.append({
                                    "notebook": str(nb_path.relative_to(p)),
                                    "full_path": str(nb_path),
                                    "module": module_name,
                                    "confidence": "high"
                                })
                                break
                            if nb_path.stem == module_name:
                                matching_notebooks.append({
                                    "notebook": str(nb_path.relative_to(p)),
                                    "full_path": str(nb_path),
                                    "module": module_name,
                                    "confidence": "medium"
                                })
                                break
                except Exception:
                    continue

        if not matching_notebooks:
            return {
                "ok": False,
                "error": f"Could not find source notebook for {py_file}",
                "hint": f"Expected notebook with '#| default_exp {module_name}' in {nbs}/"
            }

        best_match = sorted(matching_notebooks, key=lambda x: x["confidence"], reverse=True)[0]
        c = _console()
        c.print(Panel(f"[bold green]✓[/] {py_file} is generated from:\n[cyan]{best_match['notebook']}[/]",
                      title="Source Notebook Found"))

        return {
            "ok": True,
            "py_file": py_file,
            "notebook": best_match["notebook"],
            "notebook_full_path": best_match["full_path"],
            "module": module_name,
            "message": f"✓ Source: {best_match['notebook']}",
            "pretty": _export_console(c)
        }

    @mcp.tool()
    def analyze_exports(project: Optional[str] = None, notebook: str = "",
                       preview_length: int = 200) -> Dict[str, Any]:
        """
        Tool: Analyze what a notebook exports (functions, classes, etc.).

        Parameters:
            preview_length: Maximum chars for cell preview (default: 200)
        """
        try:
            p = _resolve_selector(project)
        except Exception as e:
            return {"ok": False, "error": str(e)}

        nbs = _nbs_dir(p)
        nb_path = (nbs / notebook).resolve() if "/" not in notebook else (p / notebook).resolve()

        if not nb_path.exists():
            return {"ok": False, "error": f"Notebook not found: {notebook}"}

        try:
            nb_data = json.loads(nb_path.read_text(encoding="utf-8"))
        except Exception as e:
            return {"ok": False, "error": f"Could not read notebook: {e}"}

        exports = []
        module_name = None

        for i, cell in enumerate(nb_data.get("cells", [])):
            if cell.get("cell_type") != "code":
                continue
            source = _join_source_lines(cell.get("source", []))

            # Check for default_exp
            match = re.search(r'#\|\s*default_exp\s+(\w+)', source)
            if match:
                module_name = match.group(1)

            # Check for export directives
            has_export = bool(re.search(r'#\|\s*export\s*$', source, re.MULTILINE))
            has_exporti = bool(re.search(r'#\|\s*exporti', source))

            if has_export or has_exporti:
                symbols = []
                for func_match in re.finditer(r'def\s+(\w+)\s*\(', source):
                    symbols.append({"type": "function", "name": func_match.group(1)})
                for class_match in re.finditer(r'class\s+(\w+)\s*[\(:]', source):
                    symbols.append({"type": "class", "name": class_match.group(1)})

                exports.append({
                    "cell_index": i,
                    "export_type": "exporti" if has_exporti else "export",
                    "symbols": symbols,
                    "preview": _truncate_source(source, preview_length)
                })

        c = _console()
        t = Table(title=f"Exports from {notebook}")
        t.add_column("Cell")
        t.add_column("Type")
        t.add_column("Symbols")
        for exp in exports[:50]:  # Limit table to 50 rows
            symbols_str = ", ".join(f"{s['name']}" for s in exp["symbols"]) or "(no named symbols)"
            t.add_row(str(exp["cell_index"]), exp["export_type"], symbols_str)
        if len(exports) > 50:
            t.add_row("...", "...", f"+ {len(exports) - 50} more")
        c.print(t)

        return {
            "ok": True,
            "notebook": str(nb_path.relative_to(p)),
            "module": module_name,
            "export_count": len(exports),
            "exports": exports[:50],  # Limit returned exports
            "total_exports": len(exports),
            "limited": len(exports) > 50,
            "pretty": _export_console(c)
        }

    @mcp.tool()
    def read_notebook_cell(project: Optional[str] = None, notebook: str = "",
                          cell_index: Optional[int] = None, search: Optional[str] = None,
                          max_results: int = 10, truncate_length: int = 2000) -> Dict[str, Any]:
        """
        Tool: Read specific cells from a notebook by index or search.

        Parameters:
            max_results: Maximum number of search results to return (default: 10)
            truncate_length: Maximum chars per cell source (default: 2000)
        """
        try:
            p = _resolve_selector(project)
        except Exception as e:
            return {"ok": False, "error": str(e)}

        nbs = _nbs_dir(p)
        nb_path = (nbs / notebook).resolve() if "/" not in notebook else (p / notebook).resolve()

        if not nb_path.exists():
            return {"ok": False, "error": f"Notebook not found: {notebook}"}

        try:
            nb_data = json.loads(nb_path.read_text(encoding="utf-8"))
        except Exception as e:
            return {"ok": False, "error": f"Could not read notebook: {e}"}

        cells = nb_data.get("cells", [])

        if cell_index is not None:
            if cell_index < 0 or cell_index >= len(cells):
                return {"ok": False, "error": f"Cell index {cell_index} out of range (0-{len(cells)-1})"}
            cell = cells[cell_index]
            source = _join_source_lines(cell.get("source", []))
            return {
                "ok": True,
                "notebook": str(nb_path.relative_to(p)),
                "cell_index": cell_index,
                "cell_type": cell.get("cell_type"),
                "source": _truncate_source(source, truncate_length),
                "source_length": len(source),
                "truncated": len(source) > truncate_length
            }

        if search:
            matching_cells = []
            for i, cell in enumerate(cells):
                if len(matching_cells) >= max_results:
                    break
                source = _join_source_lines(cell.get("source", []))
                if search.lower() in source.lower():
                    matching_cells.append({
                        "cell_index": i,
                        "cell_type": cell.get("cell_type"),
                        "source": _truncate_source(source, truncate_length),
                        "source_length": len(source),
                        "truncated": len(source) > truncate_length
                    })

            total_matches = sum(1 for cell in cells if search.lower() in _join_source_lines(cell.get("source", [])).lower())

            return {
                "ok": True,
                "notebook": str(nb_path.relative_to(p)),
                "search": search,
                "total_matches": total_matches,
                "returned": len(matching_cells),
                "limited": total_matches > max_results,
                "cells": matching_cells,
                "message": f"Showing {len(matching_cells)} of {total_matches} matches" if total_matches > max_results else f"Found {total_matches} matches"
            }

        return {"ok": False, "error": "Either cell_index or search must be provided"}

    @mcp.tool()
    def edit_notebook_cell(project: Optional[str] = None, notebook: str = "",
                          cell_index: int = 0, new_source: str = "") -> Dict[str, Any]:
        """Tool: Edit a specific cell in a notebook. Run nbdev_export afterward!"""
        try:
            p = _resolve_selector(project)
        except Exception as e:
            return {"ok": False, "error": str(e)}

        nbs = _nbs_dir(p)
        nb_path = (nbs / notebook).resolve() if "/" not in notebook else (p / notebook).resolve()

        if not nb_path.exists():
            return {"ok": False, "error": f"Notebook not found: {notebook}"}

        try:
            nb_data = json.loads(nb_path.read_text(encoding="utf-8"))
        except Exception as e:
            return {"ok": False, "error": f"Could not read notebook: {e}"}

        cells = nb_data.get("cells", [])
        if cell_index < 0 or cell_index >= len(cells):
            return {"ok": False, "error": f"Cell index {cell_index} out of range (0-{len(cells)-1})"}

        old_source = "".join(cells[cell_index].get("source", []))
        cells[cell_index]["source"] = new_source.splitlines(True)

        try:
            nb_path.write_text(json.dumps(nb_data, indent=2), encoding="utf-8")
        except Exception as e:
            return {"ok": False, "error": f"Could not write notebook: {e}"}

        c = _console()
        c.print(Panel(f"[green]✓[/] Updated cell {cell_index} in {notebook}\n\n[yellow]⚠ Next step: Run nbdev_export()[/]",
                      title="Cell Edited"))

        return {
            "ok": True,
            "notebook": str(nb_path.relative_to(p)),
            "cell_index": cell_index,
            "message": f"✓ Cell {cell_index} updated",
            "next_step": "Run nbdev_export() to regenerate Python modules",
            "pretty": _export_console(c)
        }

    @mcp.tool()
    def add_notebook_cell(project: Optional[str] = None, notebook: str = "",
                         source: str = "", cell_type: str = "code",
                         position: str = "end", after_index: Optional[int] = None) -> Dict[str, Any]:
        """Tool: Add a new cell to a notebook."""
        try:
            p = _resolve_selector(project)
        except Exception as e:
            return {"ok": False, "error": str(e)}

        nbs = _nbs_dir(p)
        nb_path = (nbs / notebook).resolve() if "/" not in notebook else (p / notebook).resolve()

        if not nb_path.exists():
            return {"ok": False, "error": f"Notebook not found: {notebook}"}

        try:
            nb_data = json.loads(nb_path.read_text(encoding="utf-8"))
        except Exception as e:
            return {"ok": False, "error": f"Could not read notebook: {e}"}

        new_cell = {
            "cell_type": cell_type,
            "metadata": {},
            "source": source.splitlines(True)
        }
        if cell_type == "code":
            new_cell["execution_count"] = None
            new_cell["outputs"] = []

        cells = nb_data.get("cells", [])

        if position == "start":
            cells.insert(0, new_cell)
            insert_idx = 0
        elif position == "end":
            cells.append(new_cell)
            insert_idx = len(cells) - 1
        elif position == "after" and after_index is not None:
            if after_index < 0 or after_index >= len(cells):
                return {"ok": False, "error": f"after_index {after_index} out of range"}
            cells.insert(after_index + 1, new_cell)
            insert_idx = after_index + 1
        else:
            return {"ok": False, "error": "Invalid position or missing after_index"}

        nb_data["cells"] = cells

        try:
            nb_path.write_text(json.dumps(nb_data, indent=2), encoding="utf-8")
        except Exception as e:
            return {"ok": False, "error": f"Could not write notebook: {e}"}

        return {
            "ok": True,
            "notebook": str(nb_path.relative_to(p)),
            "inserted_at": insert_idx,
            "message": f"✓ Added {cell_type} cell at index {insert_idx}",
            "next_step": "Run nbdev_export() if this is an export cell"
        }

    @mcp.tool()
    def split_markdown_cells(markdown: str) -> Dict[str, Any]:
        """
        Tool: Split a markdown blob into notebook-friendly markdown cells.

        - Each heading line (`#`…`######`) is its own cell.
        - The paragraph chunk after a heading becomes the next cell.
        - Reference link definitions (`[id]: url`) are copied to every cell that uses that id.
        """
        cells = split_markdown_into_cells(markdown)
        preview = [{"index": i, "source": c["source"][:160]} for i, c in enumerate(cells[:5])]
        return {
            "ok": True,
            "count": len(cells),
            "cells": cells,
            "preview": preview,
            "message": f"Split into {len(cells)} markdown cells"
        }

def add_prompts(mcp: FastMCP) -> None:
    """Attach custom prompts (nbdev usage help, module scaffold) to the MCP."""
    @mcp.prompt()
    def nbdev_workflow_philosophy() -> str:
        """
        CRITICAL: Prompt that instructs Claude on how to work with nbdev projects.
        This should be the FIRST thing Claude reads when working with nbdev.
        """
        p = CURRENT_PROJECT or Path("<set with set_project()>")
        s = _settings_dict(p) if isinstance(p, Path) and p.exists() else {}
        lib = s.get("lib_name") or "<lib_name>"
        nbs_path = s.get("nbs_path") or "nbs"

        return textwrap.dedent(f"""
        # ⚠️ nbdev Workflow Philosophy for {lib}

        ## CRITICAL: Notebooks Are Source Code

        **In nbdev projects, .ipynb notebooks are the SOURCE. Python .py files are GENERATED.**

        ### Golden Rules:
        1. ✅ **ALWAYS edit notebooks** in `{nbs_path}/`
        2. ✅ **ALWAYS run nbdev_export** after editing notebooks
        3. ❌ **NEVER edit .py files** in `{lib}/` directly (they're auto-generated!)
        4. ❌ **NEVER edit README.md** directly (it's generated from index.ipynb)

        ## Before Editing ANY Code:

        **If user asks to edit code in a .py file:**
        1. STOP! Use `check_if_generated(file_path)` first
        2. If generated, use `find_source_notebook(py_file)` to find the notebook
        3. Edit the notebook instead
        4. Run `nbdev_export` to regenerate the .py file

        ## Reuse First & Package Hygiene

        - Search existing notebooks **before adding new code**. Use `find_source_notebook`, `analyze_exports`, `read_notebook_cell`, or ripgrep in `{nbs_path}/` to find helpers to reuse.
        - Prefer extending an existing module (or adding a small helper) rather than creating a new one; keep symbols close to where they logically belong.
        - Align notebook paths with package hierarchy: `{nbs_path}/vision/data/01_models.ipynb` → `#| default_exp vision.data.models`.
        - For any `00__init__.ipynb` inside a subpackage, the `default_exp` **must** be `<subpackage>.__init__` (append `.__init__`, never just `<subpackage>`).

        ## Correct Workflow Example:

        ```
        User: "Fix the bug in {lib}/core.py in the process_data function"

        ✅ CORRECT Claude Response:
        1. check_if_generated("{lib}/core.py") → Yes, it's generated
        2. find_source_notebook("{lib}/core.py") → "{nbs_path}/core.ipynb"
        3. read_notebook_cell(notebook="core.ipynb", search="process_data")
        4. edit_notebook_cell(notebook="core.ipynb", cell_index=X, new_source="...")
        5. nbdev_export() → Regenerates {lib}/core.py
        6. "Done! Fixed in {nbs_path}/core.ipynb and regenerated {lib}/core.py"

        ❌ WRONG Response:
        - Directly editing {lib}/core.py (changes will be lost on next export!)
        ```

        ## Project Structure:
        ```
        {nbs_path}/           ← SOURCE CODE (edit here!)
        ├── index.ipynb       ← Becomes README.md
        ├── core.ipynb        ← Exports to {lib}/core.py
        └── utils.ipynb       ← Exports to {lib}/utils.py

        {lib}/                ← GENERATED CODE (do not edit!)
        ├── __init__.py       ← Auto-generated
        ├── core.py           ← Auto-generated from core.ipynb
        └── utils.py          ← Auto-generated from utils.ipynb
        ```

        ## Available Tools:
        - `check_if_generated(file)` - Check if file is auto-generated
        - `find_source_notebook(py_file)` - Find which notebook created a .py file
        - `analyze_exports(notebook)` - See what a notebook exports
        - `read_notebook_cell(notebook, search)` - Find cells in notebook
        - `edit_notebook_cell(notebook, cell_index, new_source)` - Edit a cell
        - `add_notebook_cell(notebook, source)` - Add new cell
        - `nbdev_export()` - Generate .py files from notebooks
        - `nbdev_test()` - Run tests in notebooks (quick checks)
        - `pytest` via `tests/` - Preferred for all substantive tests

        ## Remember:
        - Notebooks = code + narrative; keep long tests in `tests/` with pytest.
        - Prefer writing tests under `tests/` (pytest). Use `nbs/99_tests/` only for shared fixtures/mocks.
        - For long/expensive notebook examples, mark cells with `#| eval: false`.
        - Always export after editing notebooks.
        - Never manually edit generated files.
        - Use tools to find and edit source notebooks.
        - Do not add manual "Documentation" sections or call `show_doc()`; nbdev builds API docs from docstrings automatically.
        - Tutorials: keep one function/class per cell and run every cell in order from a fresh kernel to avoid hidden state errors.
        """)

    # Additional concise prompts to reinforce best practices
    @mcp.prompt()
    def nbdev_principles() -> str:
        p = CURRENT_PROJECT or Path("<set with set_project()>")
        s = _settings_dict(p) if isinstance(p, Path) and p.exists() else {}
        lib = s.get("lib_name") or "<lib_name>"
        nbs_path = s.get("nbs_path") or "nbs"
        return textwrap.dedent(f"""
        # nbdev Principles (concise)
        - Edit notebooks in `{nbs_path}/`, never generated `{lib}/` .py files.
        - `nbs/index.ipynb` → README.md; never edit README.md directly.
        - Reuse first: search existing notebooks for helpers before writing new code; keep additions in the nearest logical subpackage.
          - Use `find_symbol("name")` (fast _modidx lookup) before adding a duplicate; skim recent cells for helpers you just wrote.
          - Prefer small, reusable helpers over new Protocol/ABC layers unless polymorphism is required; keep abstractions lightweight for model clarity.
          - Generate a dependency tree early (`dependency_tree(scope="both", write_qmd="docs/deps.qmd")`) and refresh after new modules to stay oriented.
        - Do not define `__all__`; nbdev generates exports.
        - No relative imports; use absolute imports from `{lib}`.
        - One function or class per code cell; define helpers before they are used (never stack multiple defs in one cell).
        - Tutorials: write cells to run top-to-bottom from a fresh kernel; avoid hidden state and rerun all cells to verify.
        - After `nbdev_export`, inspect `{lib}/_modidx.py` (or use `modidx_audit`) to spot duplicate exports, private symbols, and numbering issues.
        - Keep the final `nbdev_export` / `#| hide` export cell at the bottom; insert new code cells (with a section header) **before** that export cell.
        - For large projects: extract 5–10 line logic chunks into small utilities, then call them; this improves readability and reuse.
        - Check `roadmap.ipynb` (root or nbs/) for priorities before adding new modules.
        - For submodules, `00__init__.ipynb` → `#| default_exp <sub>.__init__`.
        - Prefer pytest in `tests/`; use `nbs/99_tests/` only for fixtures/mocks.
        - Mark long examples with `#| eval: false`.
        - Split long narrative with `####` in separate markdown cells.
        - Use NumPy-style docstrings (Parameters, Returns, Raises, Examples).
        """)

    @mcp.prompt()
    def reuse_first_checklist() -> str:
        """Prompt: Enforce a reuse-first mindset and package-hierarchy alignment before adding code."""
        p = CURRENT_PROJECT or Path("<set with set_project()>")
        s = _settings_dict(p) if isinstance(p, Path) and p.exists() else {}
        lib = s.get("lib_name") or "<lib_name>"
        nbs_path = s.get("nbs_path") or "nbs"
        return textwrap.dedent(f"""
        # Reuse-First Checklist for {lib}

        1. Search existing notebooks in `{nbs_path}/` (ripgrep, `analyze_exports`, `read_notebook_cell`) for a helper to reuse.
        2. Use `find_symbol("name")` (backed by `_modidx.py`) to see if the symbol already exists before adding a new cell.
        3. Generate a dependency snapshot early: `dependency_snapshot(scope="both", write_qmd="docs/deps.qmd")` (or `dependency_tree`) and refresh after meaningful changes.
        4. Check `roadmap.ipynb` (project root or nbs/) for priorities before adding new notebooks or APIs.
        5. Extend or patch existing modules before creating new ones; keep related symbols together.
        6. Match package hierarchy: notebook path `{nbs_path}/a/b/` → `#| default_exp a.b.<module>`; if the notebook is `00__init__.ipynb`, use `a.b.__init__`.
        7. Prefer imports over duplication; if you add a helper, ensure downstream callers import it instead of copying logic.
        8. When a block is 5–10 lines of control flow, extract a small utility and call it; keep top-level functions small.
        9. After edits, run `nbdev_export` and appropriate tests (`pytest` or `nbdev_test`).
        10. Review `{lib}/_modidx.py` (or run `modidx_audit` / `dependency_snapshot`) to confirm exports are unique, non-private, and notebooks are numbered.
        11. Keep export/cleanup cells (e.g., `#| hide\nimport nbdev; nbdev.nbdev_export()`) at the end; place new code cells above them and add a fitting markdown subsection heading.
        """)

    @mcp.prompt()
    def documentation_best_practices() -> str:
        return textwrap.dedent("""
        # Documentation Best Practices
        - Use NumPy-style docstrings (Sections: Parameters, Returns, Raises, Examples).
        - Do not add a manual "Documentation" section or call `show_doc()`.
        - Keep one function/class per code cell; place helper definitions before they are referenced.
        - Prefer short, runnable examples close to definitions.
        - Add YAML frontmatter for page metadata when needed.
        - Use Quarto directives (callouts, mermaid, dot) as appropriate.
        """)

    @mcp.prompt()
    def future_imports_guidance() -> str:
        return textwrap.dedent("""
        # Guidance for `__future__` Imports
        - Place `from __future__ import annotations` at the top of the first export cell if you rely on postponed annotations.
        - Keep all `__future__` imports at the beginning of a code cell and avoid repeating them across many cells.
        - Prefer string annotations (or `from __future__ import annotations`) to avoid runtime import cycles.
        - In Python 3.12+, `annotations` remains useful for forward references in type hints.
        """)

    @mcp.prompt()
    def nbdev_howto() -> str:
        """Prompt: Provide a quick reference guide on how to use nbdev features in notebooks."""
        p = CURRENT_PROJECT or Path("<set with set_project()>")
        s = _settings_dict(p) if isinstance(p, Path) and p.exists() else {}
        nbs_path = s.get("nbs_path") or "nbs"
        lib = s.get("lib_name") or "<your_lib>"
        # Multi-line string with indentation preserved using textwrap.dedent
        return textwrap.dedent(f"""
        # nbdev quick how-to for {lib}

        - **Notebooks live in** `{nbs_path}/`. The `index.ipynb` becomes **README.md** and the docs home page.
        - **Declare module** at top of notebook:
          ```python
          #| default_exp your_module_name
          ```
        - **Exports**: mark cells with `#| export` (to include in library) or `#| exporti` (to include as internal).
        - **Hide or control output**: `#| hide` to hide a cell, `#| echo: false` to hide code, `#| output: false` to hide outputs.
        - **Collapse sections**: Use `#| code-fold: true` to make a long code cell folded by default.
        - **Skip execution**: `#| eval: false` to prevent a cell from running during tests.
        - **Doclinks**: Use backticks to reference symbols (e.g., `` `numpy.array` ``) which auto-link in docs.
        - **Quarto features**: You can use callouts, columns, figures, mermaid diagrams, math blocks, etc., in Markdown.
        - **Frontmatter**: Add YAML between `---` at the top or use the first cell (with `# Title` and possibly a description and key metadata).
        - **Cell granularity**: keep one function/class per code cell; split markdown by headings (use the `split_markdown_cells` tool when converting large markdown blobs).
        - **Tutorials**: restart the kernel and **Run All** to ensure cells work in order; avoid relying on skipped/hidden state.
        - **Code reuse**: before adding a new cell, scan earlier cells and use `find_symbol("name")` to check for existing exports; call helpers instead of redefining them. Prefer extracting 5–10 line control-flow chunks into small utilities for clarity.
        - **Dependency maps early**: generate a dependency snapshot/tree early and refresh after changes (`dependency_snapshot(scope="both", write_qmd="docs/deps.qmd")`).
        - **Export cell placement**: leave the final export/cleanup cell (e.g., `#| hide\nimport nbdev; nbdev.nbdev_export()`) at the bottom; insert any new code cells above it and add an appropriate subsection heading first.
        - **Roadmap**: open `roadmap.ipynb` (root or nbs/) to align examples and priorities before expanding APIs.
        - **Live reload**: Use autoreload in notebooks for iterative development:
          ```python
          %load_ext autoreload
          %autoreload 2
          from nbdev.showdoc import show_doc
          ```
        """)

    @mcp.prompt()
    def nbdev_documentation_guide() -> str:
        """
        Prompt: Comprehensive guide to notebook structure, markdown cells, docstrings, and nbdev conventions.
        Use this when creating or documenting notebooks.
        """
        return textwrap.dedent("""
        # nbdev Documentation Guide

        ## Top Markdown Cell Structure

        The **first markdown cell** sets up the notebook page. Use YAML frontmatter for metadata:

        ```markdown
        ---
        title: Module Name
        description: Brief description of what this module does
        output-file: custom_name.html
        ---

        # Module Name
        > Detailed description and overview

        This module provides functionality for...
        ```

        **Frontmatter options:**
        - `title`: Page title (appears in docs navigation)
        - `description`: Meta description for SEO and previews
        - `output-file`: Custom HTML filename (defaults to notebook name)
        - `skip_showdoc`: Set to `true` to skip automatic show_doc
        - `skip_exec`: Set to `true` to skip execution

        **Without frontmatter**, just use a markdown cell:
        ```markdown
        # Module Name
        > Brief description

        More details here...
        ```

        ## Notebook Headings Structure

        Use markdown headings to organize notebooks (they become doc sections):

        ```markdown
        # Main Module Title (H1 - use once at top)

        ## Section Name (H2 - major sections)
        Description of this section...

        ### Subsection (H3 - functions/classes)
        Details about specific items...

        #### Notes (H4 - detailed notes)
        Additional information...
        ```

        **Best practices:**
        - **H1 (#)**: Module title (once per notebook)
        - **H2 (##)**: Major sections (Imports, Core Functions, Utilities, Tests)
        - **H3 (###)**: Individual functions or classes
        - **H4 (####)**: Detailed notes or subsections

        **Example structure:**
        ```markdown
        # Data Processing Module

        ## Setup
        (imports and configuration)

        ## Core Functions
        ### process_data
        ### validate_input

        ## Utilities
        ### helper_function

        ## Examples
        ### Basic Usage
        ### Advanced Usage

        ## Tests
        ```

        ## The `@patch` Decorator

        Use `@patch` to add methods to existing classes (monkey patching):

        ```python
        #| export
        from fastcore.basics import patch

        @patch
        def new_method(self:MyClass, x):
            "Add a new method to MyClass"
            return self.value + x
        ```

        **When to use `@patch`:**
        - ✅ Adding methods to classes defined elsewhere (even external libraries)
        - ✅ Splitting class methods across multiple notebook cells
        - ✅ Organizing related functionality together
        - ✅ Extending third-party classes without subclassing

        **Example - extending pandas DataFrame:**
        ```python
        #| export
        from fastcore.basics import patch
        import pandas as pd

        @patch
        def my_summary(self:pd.DataFrame):
            "Custom summary method for DataFrame"
            return {
                'rows': len(self),
                'columns': len(self.columns),
                'missing': self.isna().sum().sum()
            }
        ```

        **Multiple patches for one class:**
        ```python
        #| export
        class DataProcessor:
            def __init__(self, data):
                self.data = data

        @patch
        def process(self:DataProcessor):
            "Process the data"
            return self.data * 2

        @patch
        def validate(self:DataProcessor):
            "Validate the data"
            return self.data > 0
        ```

        ## NumPy-Style Docstrings

        nbdev uses **NumPy docstring format** (https://numpydoc.readthedocs.io/en/latest/format.html)

        ### Standard Sections (in order):

        ```python
        #| export
        def function_name(param1, param2, param3=None):
            '''
            Short one-line description.

            Extended description paragraph. Can be multiple paragraphs.
            Explain what the function does in detail.

            Parameters
            ----------
            param1 : type
                Description of param1
            param2 : int or str
                Description of param2. Can specify multiple types.
            param3 : float, optional
                Description of param3 (default is None)

            Returns
            -------
            type or tuple
                Description of return value
                Can be multiple lines

            Raises
            ------
            ValueError
                When invalid input is provided
            TypeError
                When wrong type is passed

            See Also
            --------
            other_function : Related function
            AnotherClass : Related class

            Notes
            -----
            Additional notes about implementation, algorithms, or edge cases.
            Math can be included:

            .. math:: X(e^{j\\omega } ) = x(n)e^{ - j\\omega n}

            References
            ----------
            .. [1] Author, "Title", Journal, Year.

            Examples
            --------
            >>> function_name(1, 2)
            3
            >>> function_name(1, 2, param3=0.5)
            3.5
            '''
            pass
        ```

        ### Class Docstrings

        ```python
        #| export
        class MyClass:
            '''
            One-line summary.

            Extended description of the class.

            Parameters
            ----------
            param1 : type
                Description
            param2 : type, optional
                Description (default is value)

            Attributes
            ----------
            attr1 : type
                Description of attribute
            attr2 : type
                Description of attribute

            Methods
            -------
            method1(arg1, arg2)
                Brief description
            method2()
                Brief description

            See Also
            --------
            RelatedClass : Description

            Examples
            --------
            >>> obj = MyClass(param1)
            >>> obj.method1(x, y)
            result
            '''

            def __init__(self, param1, param2=None):
                self.attr1 = param1
                self.attr2 = param2

            def method1(self, arg1, arg2):
                '''
                Method description.

                Parameters
                ----------
                arg1 : type
                    Description
                arg2 : type
                    Description

                Returns
                -------
                type
                    Description
                '''
                pass
        ```

        ### Module Docstrings (Top of Notebook)

        Put module-level docstring in first code cell after default_exp:

        ```python
        #| default_exp module_name
        '''
        Module Name
        ===========

        Brief description of the module.

        This module provides...

        Main Features
        -------------
        - Feature 1
        - Feature 2

        See Also
        --------
        other_module : Related module
        '''
        ```

        ### Property Docstrings

        ```python
        #| export
        class MyClass:
            @property
            def value(self):
                '''
                Description of property.

                Returns
                -------
                type
                    Description of return value
                '''
                return self._value
        ```

        ### Docstring Sections Reference

        **Always include:**
        - Short description (one line)
        - `Parameters` (if function takes arguments)
        - `Returns` (if function returns value)

        **Include when relevant:**
        - Extended description
        - `Raises` (exceptions that can be raised)
        - `Examples` (executable examples with >>>)
        - `See Also` (related functions/classes)

        **Include occasionally:**
        - `Notes` (implementation details, algorithms)
        - `References` (citations, papers)
        - `Warnings` (important caveats)
        - `Attributes` (for classes)
        - `Methods` (brief method list in class docstring)

        **Type specifications:**
        ```
        param : int
        param : str or None
        param : list of int
        param : dict of {str : int}
        param : array-like, shape (n, m)
        param : callable
        param : MyClass instance
        ```

        ## Quarto Callouts in Notebooks

        Use callouts for highlighting important information:

        ```markdown
        ::: {.callout-note}
        This is a note
        :::

        ::: {.callout-warning}
        This is a warning
        :::

        ::: {.callout-important}
        This is important
        :::

        ::: {.callout-tip}
        This is a tip
        :::

        ::: {.callout-caution}
        This is a caution
        :::
        ```

        ## Documentation Best Practices

        1. **Start with top markdown cell** - Set title and description
        2. **Use headings** - Organize with ##, ###, ####
        3. **Write docstrings first** - Before implementation
        4. **Include examples** - Show usage in docstrings
        5. **Use `show_doc`** - Display formatted documentation
        6. **Add tests after examples** - Verify examples work
        7. **Use `@patch`** - When extending classes
        8. **Keep notebooks focused** - One module per notebook

        ## Complete Example

        ```python
        # First cell - Markdown
        ---
        title: Data Processing
        description: Tools for processing and validating data
        ---

        # Data Processing
        > Utilities for data transformation and validation

        # Second cell - Code
        #| default_exp data_processing

        # Third cell - Code
        #| export
        from fastcore.basics import patch
        import pandas as pd

        # Fourth cell - Code
        #| export
        def process_data(df, scale=1.0):
            '''
            Process and scale data.

            Parameters
            ----------
            df : pd.DataFrame
                Input data
            scale : float, optional
                Scaling factor (default is 1.0)

            Returns
            -------
            pd.DataFrame
                Processed data

            Examples
            --------
            >>> df = pd.DataFrame({'a': [1, 2, 3]})
            >>> process_data(df, scale=2.0)
            '''
            return df * scale

        # Fifth cell - Code (example)
        df = pd.DataFrame({'a': [1, 2, 3]})
        result = process_data(df, scale=2.0)
        assert result['a'].tolist() == [2, 4, 6]
        ```
        """)

    @mcp.prompt()
    def module_scaffold(module: str, pkg: Optional[str] = None, package_init: bool = False) -> str:
        """Prompt: Generate a scaffold for a new module notebook in nbdev, given a module name.

        Parameters
        ----------
        module : str
            Dotted or slash-separated module path (e.g., "core.data" or "core/data").
        pkg : str, optional
            Override for project lib_name; defaults to settings.ini lib_name.
        package_init : bool, default False
            Set True when scaffolding `00__init__.ipynb` inside a subpackage so
            `#| default_exp` ends with `.__init__` (e.g., `vision.data.__init__`).
        """
        # Determine package name (lib_name from settings unless overridden)
        s = _settings_dict(_require_project()) if CURRENT_PROJECT else {}
        lib = pkg or s.get("lib_name") or "<your_pkg>"

        # Normalize module path and enforce __init__ when requested
        mod_path = module.replace("/", ".").strip(".") or "__init__"
        parts = [p for p in mod_path.split(".") if p]
        # Treat 00__init__ or digit-prefixed init as __init__
        if parts and re.fullmatch(r"\d+__init__", parts[-1]):
            parts[-1] = "__init__"
            package_init = True
        if parts and parts[-1] == "__init__":
            package_init = True
        if package_init and (not parts or parts[-1] != "__init__"):
            parts.append("__init__")
        default_mod = ".".join(parts) if parts else "__init__"

        mod_title = default_mod.replace(".__init__", " (init)") if package_init else default_mod
        md = f"""\
        # {mod_title}
        > Auto-generated scaffold for `{lib}.{default_mod}`

        ## Imports
        ```python
        %load_ext autoreload
        %autoreload 2
        ```

        ```python
        #| default_exp {default_mod}
        ```

        ## {parts[-2].capitalize() if package_init and len(parts) > 1 else parts[-1].capitalize() if parts else 'Module'} API
        ```python
        #| export
        def my_function(x: int) -> int:
            "Example function"
            return x + 1
        ```

        ## Reuse checklist
        - Prefer importing existing helpers from `{lib}` instead of duplicating code.
        - Keep symbols in the closest relevant subpackage (follow `{lib}`'s directory tree).

        ## Examples
        ```python
        y = my_function(1)
        assert y == 2
        ```
        """
        return textwrap.dedent(md)

    @mcp.prompt()
    def nbdev_advanced_patterns() -> str:
        """
        Prompt: Advanced nbdev patterns for package structure and imports.

        Updated guidance:
        - Never define __all__; nbdev generates exports from `#| export` directives.
        - Default export for `00__init__.ipynb` in submodules must be `<submodule>.__init__`.
        - Never use relative imports; always use absolute imports from your package root.
        """
        return textwrap.dedent("""
        # nbdev Advanced Patterns (Updated)

        ## Exports
        - 🚫 Do not define `__all__` anywhere. nbdev builds exports automatically.

        ## Package Structure
        - Top-level init: `nbs/00__init__.ipynb` → `#| default_exp __init__`
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
        """)

    @mcp.prompt()
    def nbdev_main_patterns() -> str:
        """
        Prompt: Safe patterns for `if __name__ == "__main__":` blocks and console scripts in nbdev projects.
        """
        return textwrap.dedent("""\
        # nbdev __main__ and Console Scripts

        ## Safe __main__ patterns
        1) Same notebook, separate cell:
        ```python
        #| export
        #| eval: False
        if __name__ == "__main__":
            import sys
            sys.exit(main())
        ```

        2) Dedicated __main__ notebook:
        - Notebook name: `01__main__.ipynb`
        - Cell: `#| default_exp pkg.__main__`
        - Export a tiny wrapper that imports and calls your real `main`.

        3) Export directly to __main__:
        ```python
        #| export __main__
        #| eval: False
        if __name__ == "__main__":
            import sys
            sys.exit(main())
        ```

        ## Console scripts
        - Add to settings.ini: `console_scripts = mycli=mypkg:main`
        - After `nbdev_export`, setuptools exposes `mycli` as an entry point.
        """)

# ----------------------------- extensions (tools) ----------------------------
def add_extensions(mcp: FastMCP) -> None:
    """Register extended tools and aggregators (no 'v2_' prefixes)."""

    # Helpers
    def _tutorials_dir(project: Path) -> Path:
        return (project / "tutorials").resolve()

    def _modidx_path(project: Path) -> Path:
        lib = _settings_dict(project).get("lib_name") or "pkg"
        return (project / lib / "_modidx.py").resolve()

    def _iter_notebooks(project: Path, *, include_tutorials: bool = True, include_nbs: bool = True) -> Iterable[Path]:
        """Yield notebooks from nbs/ and (optionally) tutorials/ folders."""
        nbs = _nbs_dir(project)
        if include_nbs and nbs.exists():
            for p in sorted(nbs.rglob("*.ipynb")):
                if ".ipynb_checkpoints" in str(p):
                    continue
                yield p
        tuts = _tutorials_dir(project)
        if include_tutorials and tuts.exists():
            for p in sorted(tuts.rglob("*.ipynb")):
                if ".ipynb_checkpoints" in str(p):
                    continue
                yield p

    def _load_modidx(project: Path) -> Dict[str, Any]:
        path = _modidx_path(project)
        if not path.exists():
            raise FileNotFoundError(f"_modidx.py not found at {path}")
        data = runpy.run_path(str(path))
        d = data.get("d") if isinstance(data, dict) else None
        if not isinstance(d, dict):
            raise ValueError("Invalid _modidx.py format: missing dict 'd'")
        return d

    def _symbol_locations(modidx: Dict[str, Any], symbol: str) -> List[Dict[str, str]]:
        """Return list of modules and sources where a symbol is exported (using modidx syms)."""
        out: List[Dict[str, str]] = []
        syms = modidx.get("syms", {}) if isinstance(modidx, dict) else {}
        for mod, entries in syms.items():
            if not isinstance(entries, dict):
                continue
            for sym, meta in entries.items():
                if sym.split(".")[-1] != symbol:
                    continue
                src = meta.get("source") if isinstance(meta, dict) else None
                out.append({"module": mod, "source": str(src) if src else ""})
        return out

    def _read_nb(path: Path) -> Dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_nb(path: Path, data: Dict[str, Any]) -> None:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _find_default_exp_in_nb(data: Dict[str, Any]) -> Optional[str]:
        for cell in data.get("cells", []):
            if cell.get("cell_type") != "code":
                continue
            src = _join_source_lines(cell.get("source", []))
            m = re.search(r"#\|\s*default_exp\s+([\w\.]+)", src)
            if m:
                return m.group(1)
        return None

    def _cell_lines(source: str) -> List[str]:
        return source.splitlines()

    def _cell_has_export_directive(source: str) -> bool:
        return bool(re.search(r"^\s*#\|\s*export[ia]?\b", source, flags=re.MULTILINE))

    def _resolve_relative(current: str, rel: str) -> str:
        m = re.match(r"(\.+)(.*)$", rel)
        if not m:
            return rel
        dots, tail = m.groups()
        level = len(dots)
        parts = current.split(".")
        if "__init__" in parts:
            parts = parts[:-1]
        base_parts = parts[:-level]
        tail_parts = [p for p in tail.split(".") if p]
        return ".".join(base_parts + tail_parts)

    def _abs_module_for_nb(project: Path, nb_path: Path) -> Tuple[str, str]:
        s = _settings_dict(project)
        lib = s.get("lib_name") or "pkg"
        data = _read_nb(nb_path)
        mod = _find_default_exp_in_nb(data)
        nbs_root = _nbs_dir(project)
        try:
            rel = nb_path.relative_to(nbs_root)
        except ValueError:
            # Notebook outside nbs (e.g., tutorials); fall back to project-relative or basename.
            try:
                rel = nb_path.relative_to(project)
            except ValueError:
                rel = nb_path.name if isinstance(nb_path, Path) else Path(nb_path)
        if not mod:
            parts = list(rel.parts) if isinstance(rel, Path) else [rel]
            name = Path(parts[-1]).stem if parts else Path(nb_path).stem
            name = re.sub(r"^\d+_", "", name)
            if len(parts) > 1:
                mod = ".".join(parts[:-1] + [name])
            else:
                mod = name
        if isinstance(rel, Path) and rel.name == "00__init__.ipynb" and len(rel.parts) > 1:
            mod = ".".join(list(rel.parent.parts) + ["__init__"])
        return lib, mod

    # 1) Validate 00__init__ default_exp
    @mcp.tool(description="Validate that every nbdev 00__init__ notebook has the correct default_exp metadata and optionally fix it.")
    def validate_inits(project: Optional[str] = None, fix: bool = False) -> Dict[str, Any]:
        try:
            p = _resolve_selector(project)
        except Exception as e:
            return {"ok": False, "error": str(e)}

        nbs = _nbs_dir(p)
        problems: List[Dict[str, Any]] = []
        fixed = 0
        for nb in _iter_notebooks(p):
            if nb.name != "00__init__.ipynb":
                continue
            rel = nb.relative_to(nbs) if nbs in nb.parents else nb
            expected = "__init__" if len(rel.parts) == 1 else ".".join(list(rel.parent.parts) + ["__init__"])
            data = _read_nb(nb)
            found = _find_default_exp_in_nb(data)
            cell_idx, line_no = -1, -1
            for i, cell in enumerate(data.get("cells", [])):
                if cell.get("cell_type") != "code":
                    continue
                src = _join_source_lines(cell.get("source", []))
                for j, ln in enumerate(_cell_lines(src), 1):
                    if re.search(r"#\|\s*default_exp\s+", ln):
                        cell_idx, line_no = i, j
                        break
                if cell_idx != -1:
                    break
            if found != expected:
                problems.append({
                    "notebook": str(nb.relative_to(p)),
                    "found": found,
                    "expected": expected,
                    "cell": cell_idx,
                    "line": line_no,
                })
                if fix:
                    cells = data.get("cells", [])
                    if cell_idx != -1:
                        src = _join_source_lines(cells[cell_idx].get("source", []))
                        new_src = re.sub(r"(#\|\s*default_exp\s+)[\w\.]+", rf"\1{expected}", src)
                        cells[cell_idx]["source"] = new_src.splitlines(True)
                    else:
                        new_cell = {"cell_type": "code", "metadata": {}, "source": [f"#| default_exp {expected}\n"], "outputs": [], "execution_count": None}
                        cells.insert(0, new_cell)
                        data["cells"] = cells
                    _write_nb(nb, data)
                    fixed += 1

        c = _console()
        if problems:
            t = Table(title="__init__ default_exp issues")
            t.add_column("notebook"); t.add_column("found"); t.add_column("expected"); t.add_column("cell"); t.add_column("line")
            for pr in problems[:100]:
                t.add_row(pr["notebook"], str(pr["found"]), pr["expected"], str(pr["cell"]), str(pr["line"]))
            c.print(t)
        else:
            c.print(Panel("All 00__init__ notebooks have correct default_exp", title="validate_inits"))
        return {"ok": len(problems) == 0, "problems": problems, "fixed": fixed, "pretty": _export_console(c)}

    # 2) Lint rules
    @mcp.tool(description="Lint notebooks for nbdev best practices such as no __all__ definitions and absolute imports.")
    def lint_rules(project: Optional[str] = None, fix_relative: bool = False) -> Dict[str, Any]:
        import ast
        try:
            p = _resolve_selector(project)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        s = _settings_dict(p)
        lib = s.get("lib_name") or "pkg"
        issues: List[Dict[str, Any]] = []
        changed = 0
        export_map: Dict[str, Set[str]] = {}
        readme = p / "README.md"
        if readme.exists():
            issues.append({"rule": "readme_generated", "file": str(readme.relative_to(p)), "message": "README.md is generated from nbs/index.ipynb — do not edit directly."})
        for nb in _iter_notebooks(p, include_tutorials=False):
            data = _read_nb(nb)
            mod = _find_default_exp_in_nb(data) or _abs_module_for_nb(p, nb)[1]
            modified = False
            for i, cell in enumerate(data.get("cells", [])):
                if cell.get("cell_type") != "code":
                    continue
                src = _join_source_lines(cell.get("source", []))
                lines = _cell_lines(src)
                if re.search(r"^\s*__all__\s*=", src, flags=re.MULTILINE):
                    row_lines = [j for j, ln in enumerate(lines, 1) if re.match(r"\s*__all__\s*=", ln)]
                    issues.append({"rule": "no_manual___all__", "notebook": str(nb.relative_to(p)), "cell": i, "lines": row_lines, "message": "Never define __all__; nbdev auto-generates exports."})
                rel_pat = re.compile(r"^\s*from\s+(\.+[\w\.]*)\s+import\s+(.+)$")
                new_lines: List[str] = []
                line_changed = False
                for ln in lines:
                    m = rel_pat.match(ln)
                    if m:
                        target = m.group(1)
                        abs_mod = _resolve_relative(mod, target)
                        abs_imp = f"from {lib}.{abs_mod} import {m.group(2)}"
                        issues.append({"rule": "no_relative_imports", "notebook": str(nb.relative_to(p)), "cell": i, "line": len(new_lines)+1, "message": f"Relative import '{ln.strip()}' → '{abs_imp}'", "suggestion": abs_imp})
                        if fix_relative:
                            ln = abs_imp; line_changed = True
                    new_lines.append(ln)
                if fix_relative and line_changed:
                    cell["source"] = "\n".join(new_lines).splitlines(True)
                    modified = True
                if _cell_has_export_directive(src):
                    try:
                        tree = ast.parse(src)
                    except SyntaxError:
                        tree = None
                    if tree is not None:
                        for node in tree.body:
                            names: List[str] = []
                            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                                names.append(node.name)
                            elif isinstance(node, ast.Assign):
                                for tgt in node.targets:
                                    if isinstance(tgt, ast.Name):
                                        names.append(tgt.id)
                            for nm in names:
                                if not nm:
                                    continue
                                export_map.setdefault(nm, set()).add(mod)
            if modified:
                _write_nb(nb, data); changed += 1
        for sym, mods in sorted(export_map.items()):
            if len(mods) > 1:
                mods_sorted = sorted(mods)
                issues.append({
                    "rule": "duplicate_export",
                    "file": sym,
                    "modules": mods_sorted,
                    "message": f"Symbol '{sym}' exported in multiple modules: {', '.join(mods_sorted)}. Prefer a single source and re-use imports."
                })
        c = _console()
        t = Table(title="lint issues"); t.add_column("rule"); t.add_column("location"); t.add_column("msg")
        for it in issues[:200]:
            loc = it.get("file") or f"{it.get('notebook')}#cell{it.get('cell')}"
            t.add_row(it.get("rule", ""), str(loc), it.get("message", ""))
        c.print(t)
        if fix_relative: c.print(Panel(f"Modified notebooks: {changed}", title="relative import fixes"))
        return {"ok": True, "issues": issues, "modified": changed, "pretty": _export_console(c)}

    # 3) __main__ guard safety
    @mcp.tool(description="Detect '__main__' guards that would execute during nbdev_prepare and suggest safe patterns (eval: False or __main__ export).")
    def lint_main_guards(project: Optional[str] = None) -> Dict[str, Any]:
        try:
            p = _resolve_selector(project)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        issues: List[Dict[str, Any]] = []
        for nb in _iter_notebooks(p):
            data = _read_nb(nb)
            for i, cell in enumerate(data.get("cells", [])):
                if cell.get("cell_type") != "code":
                    continue
                src = _join_source_lines(cell.get("source", []))
                lines = _cell_lines(src)
                has_guard = any(re.search(r"if __name__\\s*==\\s*[\"']__main__[\"']", ln) for ln in lines)
                if not has_guard:
                    continue
                has_eval_false = any("#| eval: false" in ln.lower() for ln in lines)
                has_export_main = any(re.match(r"\\s*#\\|\\s*export\\s+__main__", ln, flags=re.IGNORECASE) for ln in lines)
                if has_eval_false and has_export_main:
                    continue
                issues.append({
                    "notebook": str(nb.relative_to(p)),
                    "cell": i,
                    "has_eval_false": has_eval_false,
                    "has_export_main": has_export_main,
                    "message": "Add '#| eval: False' and/or export to __main__ notebook to keep nbdev_prepare from running main()."
                })
        c = _console()
        if issues:
            t = Table(title="__main__ guard warnings")
            t.add_column("notebook"); t.add_column("cell"); t.add_column("eval_false"); t.add_column("export__main__")
            for it in issues[:200]:
                t.add_row(it["notebook"], str(it["cell"]), str(it["has_eval_false"]), str(it["has_export_main"]))
            c.print(t)
            c.print(Panel("See prompt: nbdev_main_patterns", title="Fix suggestions"))
        else:
            c.print(Panel("No unsafe __main__ guards detected", title="lint_main_guards"))
        return {"ok": len(issues) == 0, "issues": issues, "pretty": _export_console(c)}

    # 4) Execute tutorials to ensure they run
    @mcp.tool(description="Execute tutorial notebooks (tutorials/*.ipynb) to confirm they run without errors.")
    def run_tutorials(project: Optional[str] = None, timeout: int = 600, allow_errors: bool = False) -> Dict[str, Any]:
        try:
            p = _resolve_selector(project)
        except Exception as e:
            return {"ok": False, "error": str(e)}

        tut_dir = _tutorials_dir(p)
        if not tut_dir.exists():
            return {"ok": False, "error": f"tutorials directory not found at {tut_dir}"}

        try:
            import nbformat  # type: ignore
            from nbclient import NotebookClient  # type: ignore
            import time, traceback as tb
        except Exception as e:
            return {"ok": False, "error": f"Missing dependency for executing notebooks: {e}"}

        results: List[Dict[str, Any]] = []
        failures = 0
        for nb in _iter_notebooks(p, include_tutorials=True, include_nbs=False):
            data = nbformat.read(nb, as_version=4)
            kernel_name = data.metadata.get("kernelspec", {}).get("name", "python3")
            start = time.perf_counter()
            err_txt = None; trace_txt = None; ok_exec = True
            try:
                client = NotebookClient(data, timeout=timeout, kernel_name=kernel_name)
                client.execute(cwd=str(nb.parent), allow_errors=allow_errors)
            except Exception as exc:
                ok_exec = False
                err_txt = str(exc)
                trace_txt = _tail(tb.format_exc(), 4000)
                failures += 1
            duration = round(time.perf_counter() - start, 2)
            results.append({
                "notebook": str(nb.relative_to(p)),
                "ok": ok_exec,
                "seconds": duration,
                "error": err_txt,
                "traceback": trace_txt,
            })

        c = _console()
        t = Table(title="tutorial execution")
        t.add_column("notebook")
        t.add_column("ok")
        t.add_column("seconds")
        for r in results[:200]:
            t.add_row(r["notebook"], str(r["ok"]), str(r["seconds"]))
        c.print(t)
        if failures:
            c.print(Panel(f"Failures: {failures}/{len(results)}", title="run_tutorials"))
        else:
            c.print(Panel("All tutorials executed without errors", title="run_tutorials"))
        return {"ok": failures == 0, "results": results, "pretty": _export_console(c)}

    # 5) Scan notebook outputs for error cells
    @mcp.tool(description="Scan notebooks (nbs and tutorials) for existing error outputs without executing them.")
    def scan_notebook_errors(project: Optional[str] = None,
                             include_tutorials: bool = True,
                             include_nbs: bool = True,
                             max_trace_chars: int = 1200) -> Dict[str, Any]:
        try:
            p = _resolve_selector(project)
        except Exception as e:
            return {"ok": False, "error": str(e)}

        issues: List[Dict[str, Any]] = []
        for nb in _iter_notebooks(p, include_tutorials=include_tutorials, include_nbs=include_nbs):
            data = _read_nb(nb)
            rel = str(nb.relative_to(p))
            for i, cell in enumerate(data.get("cells", [])):
                if cell.get("cell_type") != "code":
                    continue
                outputs = cell.get("outputs", []) or []
                for oi, out in enumerate(outputs):
                    if out.get("output_type") == "error":
                        trace_list = out.get("traceback", []) or []
                        trace_txt = _tail("\n".join(trace_list), max_trace_chars)
                        issues.append({
                            "notebook": rel,
                            "cell": i,
                            "output": oi,
                            "ename": out.get("ename"),
                            "evalue": out.get("evalue"),
                            "traceback": trace_txt,
                        })

        c = _console()
        if issues:
            t = Table(title="error outputs found")
            t.add_column("notebook")
            t.add_column("cell")
            t.add_column("error")
            t.add_column("message")
            for it in issues[:200]:
                msg = it.get("evalue") or ""
                errname = it.get("ename") or "error"
                t.add_row(it["notebook"], str(it["cell"]), errname, msg)
            c.print(t)
        else:
            c.print(Panel("No error outputs detected in notebooks.", title="scan_notebook_errors"))

        return {"ok": len(issues) == 0, "errors": issues, "pretty": _export_console(c)}

    # 6) Audit _modidx.py (exports, duplication, numbering)
    @mcp.tool(description="Audit nbdev-generated _modidx.py for duplicate exports, private symbols, and notebook numbering issues.")
    def modidx_audit(project: Optional[str] = None,
                     require_number_prefix: bool = True) -> Dict[str, Any]:
        try:
            p = _resolve_selector(project)
            modidx = _load_modidx(p)
        except Exception as e:
            return {"ok": False, "error": str(e)}

        syms = modidx.get("syms", {}) if isinstance(modidx, dict) else {}
        dup: List[Dict[str, Any]] = []
        private: List[Dict[str, Any]] = []
        numbering: List[Dict[str, Any]] = []
        sym_to_mods: Dict[str, List[str]] = {}

        num_re = re.compile(r"^\d{2}_.+\.ipynb$")

        for mod, entries in syms.items():
            if not isinstance(entries, dict):
                continue
            for sym, meta in entries.items():
                sym_to_mods.setdefault(sym, []).append(mod)
                name = sym.split(".")[-1]
                if name.startswith("_") and name not in ("__init__",):
                    private.append({"symbol": sym, "module": mod})
                src = meta.get("source") if isinstance(meta, dict) else None
                if src:
                    file_part = str(src).split("#", 1)[0]
                    fname = Path(file_part).name
                    if require_number_prefix and not num_re.match(fname):
                        numbering.append({"module": mod, "file": file_part})

        for sym, mods in sym_to_mods.items():
            if len(mods) > 1:
                dup.append({"symbol": sym, "modules": sorted(set(mods))})

        c = _console()
        if dup:
            t = Table(title="duplicate exports (_modidx)")
            t.add_column("symbol"); t.add_column("modules")
            for d in dup[:200]:
                t.add_row(d["symbol"], ", ".join(d["modules"]))
            c.print(t)
        if private:
            t = Table(title="private symbols exported")
            t.add_column("symbol"); t.add_column("module")
            for it in private[:200]:
                t.add_row(it["symbol"], it["module"])
            c.print(t)
        if numbering:
            t = Table(title="unnumbered notebooks")
            t.add_column("module"); t.add_column("file")
            for it in numbering[:200]:
                t.add_row(it["module"], it["file"])
            c.print(t)
        if not (dup or private or numbering):
            c.print(Panel("_modidx audit passed (no duplicates, no private exports, numbering ok).", title="modidx_audit"))

        return {
            "ok": not (dup or private or numbering),
            "duplicates": dup,
            "private_exports": private,
            "numbering_issues": numbering,
            "pretty": _export_console(c),
            "modidx_path": str(_modidx_path(p)),
        }

    # 7) Find where a symbol is exported (reuse helper)
    @mcp.tool(description="Find modules/notebooks exporting a given symbol using nbdev _modidx.py.")
    def find_symbol(symbol: str, project: Optional[str] = None) -> Dict[str, Any]:
        try:
            p = _resolve_selector(project)
            modidx = _load_modidx(p)
        except Exception as e:
            return {"ok": False, "error": str(e)}

        locs = _symbol_locations(modidx, symbol)
        c = _console()
        if locs:
            t = Table(title=f"exports for '{symbol}'")
            t.add_column("module")
            t.add_column("source")
            for it in locs[:200]:
                t.add_row(it.get("module", ""), it.get("source", ""))
            c.print(t)
        else:
            c.print(Panel(f"No exports found for symbol '{symbol}' in _modidx.py", title="find_symbol"))

        return {
            "ok": bool(locs),
            "matches": locs,
            "modidx_path": str(_modidx_path(p)),
            "pretty": _export_console(c),
        }

    # 8) Numbering by dependency order
    @mcp.tool(description="Analyze notebook dependency graph to suggest numbering order and optionally enforce it.")
    def analyze_dependency_order(project: Optional[str] = None, enforce: bool = False) -> Dict[str, Any]:
        try:
            p = _resolve_selector(project)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        s = _settings_dict(p); lib = s.get("lib_name") or "pkg"; nbs_root = _nbs_dir(p)
        nodes: Dict[str, Path] = {}; imports: Dict[str, Set[str]] = {}
        for nb in _iter_notebooks(p):
            if not str(nb).startswith(str(nbs_root)) or nb.name.startswith("00__init__"): continue
            mod = _find_default_exp_in_nb(_read_nb(nb)) or _abs_module_for_nb(p, nb)[1]
            fq = f"{lib}.{mod}"; nodes[fq] = nb; imports[fq] = set()
            data = _read_nb(nb)
            for cell in data.get("cells", []):
                if cell.get("cell_type") != "code": continue
                src = _join_source_lines(cell.get("source", []))
                for m in re.finditer(r"^\s*from\s+([\w\.]+)\s+import\s+", src, flags=re.MULTILINE):
                    tmod = m.group(1);  
                    if tmod.startswith(f"{lib}."): imports[fq].add(tmod)
                for m in re.finditer(r"^\s*import\s+([\w\.]+)", src, flags=re.MULTILINE):
                    tmod = m.group(1);
                    if tmod.startswith(f"{lib}."): imports[fq].add(tmod)
        rank: Dict[str, int] = {k: 1 for k in nodes}; changed=True; iters=0
        while changed and iters < 1000:
            changed=False; iters+=1
            for a, deps in imports.items():
                for b in deps:
                    if b in rank and rank[a] <= rank[b]: rank[a] = rank[b] + 1; changed=True
        suggestions: List[Dict[str, Any]] = []
        for fq, nb in nodes.items():
            rel = nb.relative_to(nbs_root); cur_name = rel.name; base_name = re.sub(r"^\d+_", "", cur_name)
            rn = f"{rank[fq]:02d}_{base_name}"
            if rn != cur_name:
                suggestions.append({"notebook": str(nb.relative_to(p)), "suggested": str(rel.with_name(rn)), "reason": f"rank {rank[fq]} from dependency graph"})
        applied=0
        if enforce:
            for s in suggestions:
                src = p / s["notebook"]; dst = p / s["suggested"]; dst.parent.mkdir(parents=True, exist_ok=True); os.replace(src, dst); applied+=1
        c = _console(); t = Table(title="numbering suggestions"); t.add_column("notebook"); t.add_column("suggested"); t.add_column("why")
        for s in suggestions[:200]: t.add_row(s["notebook"], s["suggested"], s["reason"]); c.print(t)
        if enforce: c.print(Panel(f"Applied renames: {applied}", title="enforced"))
        return {"ok": True, "suggestions": suggestions, "applied": applied, "pretty": _export_console(c)}

    # 9) Generate PyTests into tests/
    @mcp.tool(description="Generate pytest-compatible modules under tests/ by extracting test code from notebooks.")
    def generate_pytests(project: Optional[str] = None, dry_run: bool = False, long_test_eval_false: bool = True) -> Dict[str, Any]:
        try: p = _resolve_selector(project)
        except Exception as e: return {"ok": False, "error": str(e)}
        s = _settings_dict(p); lib = s.get("lib_name") or "pkg"; nbs_root = _nbs_dir(p); outdir = p / "tests"; outdir.mkdir(exist_ok=True)
        generated: List[str] = []; modified_cells: List[Tuple[str, int]] = []
        for nb in _iter_notebooks(p):
            if not str(nb).startswith(str(nbs_root)) or nb.name == "index.ipynb": continue
            data = _read_nb(nb); mod = _find_default_exp_in_nb(data) or _abs_module_for_nb(p, nb)[1]
            test_funcs: List[str] = []
            for i, cell in enumerate(data.get("cells", [])):
                if cell.get("cell_type") != "code": continue
                src = _join_source_lines(cell.get("source", []))
                if "assert" not in src and not re.search(r"\bpytest\b|^def\s+test_", src, flags=re.MULTILINE): continue
                body_lines = [ln for ln in _cell_lines(src) if not ln.strip().startswith("#|")]
                if not body_lines: continue
                func_name = f"test_nb_cell_{i:03d}"; test_funcs.append("\n".join([f"def {func_name}():", *[f"    {ln}" if ln.strip() else "" for ln in body_lines], ""]))
                if long_test_eval_false and len(body_lines) >= 40 and "#| eval: false" not in src:
                    cell["source"] = ("#| eval: false\n" + src).splitlines(True); modified_cells.append((str(nb.relative_to(p)), i))
            if test_funcs:
                py = [f"# Auto-generated from {nb.relative_to(p)}\n", f"import {lib}.{mod} as m\n\n"]; py.extend(test_funcs)
                out_file = outdir / f"test_{mod.replace('.', '_')}.py"; 
                if not dry_run: out_file.write_text("\n".join(py), encoding="utf-8")
                generated.append(str(out_file.relative_to(p))); 
                if long_test_eval_false and modified_cells and not dry_run: _write_nb(nb, data)
        c = _console(); 
        if generated:
            t = Table(title="generated pytest files"); t.add_column("path"); 
            for g in generated: t.add_row(g); c.print(t)
        else: c.print(Panel("No tests found to extract.", title="pytest generator"))
        return {"ok": True, "generated": generated, "modified_cells": modified_cells, "dry_run": dry_run, "pretty": _export_console(c)}

    # 10) Test utils in nbs/99_tests
    @mcp.tool(description="Create the standard nbs/99_tests/00_utils.ipynb notebook for shared testing utilities.")
    def scaffold_test_utils(project: Optional[str] = None) -> Dict[str, Any]:
        try: p = _resolve_selector(project)
        except Exception as e: return {"ok": False, "error": str(e)}
        nb_dir = _nbs_dir(p) / "99_tests"; nb_dir.mkdir(parents=True, exist_ok=True); nb_path = nb_dir / "00_utils.ipynb"
        if nb_path.exists(): return {"ok": True, "message": f"Exists: {nb_path.relative_to(p)}"}
        nb = {"cells": [
            {"cell_type": "markdown", "metadata": {}, "source": ["# Test Utilities\n", "> Helpers and mocks for tests\n"]},
            {"cell_type": "code", "metadata": {}, "source": ["#| default_exp tests.utils\n"], "outputs": [], "execution_count": None},
            {"cell_type": "code", "metadata": {}, "source": ["#| export\n", "def make_example_data(n: int = 3):\n", "    \"Return a simple list of ints for testing.\"\n", "    return list(range(n))\n"], "outputs": [], "execution_count": None},
        ], "metadata": {"kernelspec": {"name": "python3", "language": "python"}}, "nbformat": 4, "nbformat_minor": 5}
        _write_nb(nb_path, nb); return {"ok": True, "created": str(nb_path.relative_to(p))}

    # 11) Stubs
    @mcp.tool(description="Generate .pyi stub files for exported symbols by scanning notebooks.")
    def generate_stubs(project: Optional[str] = None, out_path: Optional[str] = None, include_methods: bool = True) -> Dict[str, Any]:
        import ast
        try: p = _resolve_selector(project)
        except Exception as e: return {"ok": False, "error": str(e)}
        s = _settings_dict(p); lib = s.get("lib_name") or "pkg"; stubs_dir = p / "stubs"; stubs_dir.mkdir(exist_ok=True); out = Path(out_path) if out_path else (stubs_dir / f"{lib}.pyi")
        modules: Dict[str, List[str]] = {}
        def add_stub(mod: str, text: str) -> None: modules.setdefault(mod, []).append(text)
        for nb in _iter_notebooks(p):
            data = _read_nb(nb); mod = _find_default_exp_in_nb(data) or _abs_module_for_nb(p, nb)[1]
            for i, cell in enumerate(data.get("cells", [])):
                if cell.get("cell_type") != "code": continue
                src = _join_source_lines(cell.get("source", []))
                if not _cell_has_export_directive(src): continue
                try: tree = ast.parse(src)
                except SyntaxError: continue
                for node in tree.body:
                    if isinstance(node, ast.FunctionDef): sig = ast.get_source_segment(src, node.args) or "(…)"; add_stub(mod, f"def {node.name}{sig}: ...  # from {nb.name}#cell{i}")
                    elif isinstance(node, ast.AsyncFunctionDef): sig = ast.get_source_segment(src, node.args) or "(…)"; add_stub(mod, f"async def {node.name}{sig}: ...  # from {nb.name}#cell{i}")
                    elif isinstance(node, ast.ClassDef):
                        bases = [ast.get_source_segment(src, b) or "object" for b in node.bases]; add_stub(mod, f"class {node.name}({', '.join(bases) if bases else 'object'}): ...  # from {nb.name}#cell{i}")
                        if include_methods:
                            for sub in node.body:
                                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                    sig = ast.get_source_segment(src, sub.args) or "(…)"; prefix = "async def" if isinstance(sub, ast.AsyncFunctionDef) else "def"; add_stub(mod, f"    {prefix} {sub.name}{sig}: ...")
        lines = ["# Auto-generated stubs — do not edit\n", f"# Package: {lib}\n\n", "from __future__ import annotations\n", "from typing import *\n\n"]
        for mod in sorted(modules):
            lines.append(f"# --- {lib}.{mod} ---\n");
            for item in modules[mod]: lines.append(item + "\n")
            lines.append("\n")
        out.write_text("".join(lines), encoding="utf-8"); c = _console(); c.print(Panel(f"Stub written: {out}", title="stubs"))
        return {"ok": True, "out_file": str(out.relative_to(p)), "pretty": _export_console(c)}

    # 12) Dependency tree
    @mcp.tool(description="Summarize internal and external module dependencies, optional unused imports, and export diagrams.")
    def dependency_tree(project: Optional[str] = None, scope: str = "internal", include_unused: Optional[str] = None, write_qmd: Optional[str] = None) -> Dict[str, Any]:
        try: p = _resolve_selector(project)
        except Exception as e: return {"ok": False, "error": str(e)}
        s = _settings_dict(p); lib = s.get("lib_name") or "pkg"
        internal_nodes: Set[str] = set(); external_nodes: Set[str] = set(); edges: Set[Tuple[str, str]] = set(); in_deg: Dict[str, int] = {}; unused_external: List[Dict[str, Any]] = []
        for nb in _iter_notebooks(p):
            data = _read_nb(nb); mod = _find_default_exp_in_nb(data) or _abs_module_for_nb(p, nb)[1]; me = f"{lib}.{mod}"; internal_nodes.add(me); in_deg.setdefault(me, 0)
            for ci, cell in enumerate(data.get("cells", [])):
                if cell.get("cell_type") != "code": continue
                src = _join_source_lines(cell.get("source", []))
                try:
                    import ast; tree = ast.parse(src)
                except SyntaxError:
                    tree = None
                imported_aliases: Set[str] = set(); used_names: Set[str] = set()
                if tree is not None:
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for n in node.names:
                                alias = n.asname or n.name.split(".")[0]; imported_aliases.add(alias)
                                if not n.name.startswith(f"{lib}."):
                                    external_nodes.add(n.name)
                                    if scope in ("external", "both"): edges.add((me, n.name))
                        elif isinstance(node, ast.ImportFrom):
                            modname = node.module or ""
                            for n in node.names:
                                alias = n.asname or n.name; imported_aliases.add(alias)
                            if modname:
                                if modname.startswith(f"{lib}."):
                                    tgt = modname
                                    if scope in ("internal", "both"):
                                        edges.add((me, tgt)); in_deg[tgt] = in_deg.get(tgt, 0) + 1
                                else:
                                    external_nodes.add(modname)
                                    if scope in ("external", "both"): edges.add((me, modname))
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Name): used_names.add(node.id)
                for alias in imported_aliases:
                    if alias not in used_names:
                        unused_external.append({"notebook": str(nb.relative_to(p)), "cell": ci, "alias": alias})
        unreferenced_internal = [n for n in sorted(internal_nodes) if in_deg.get(n, 0) == 0]
        mermaid = ["graph LR\n"]; 
        for a, b in sorted(edges): mermaid.append(f"  {a.replace('.', '_')}[{a}] --> {b.replace('.', '_')}[{b}]\n")
        dot = ["digraph G {\n", "  rankdir=LR;\n"]; 
        for a, b in sorted(edges): dot.append(f"  \"{a}\" -> \"{b}\";\n"); dot.append("}\n")
        written = None
        if write_qmd:
            qmd = p / write_qmd; qmd.parent.mkdir(parents=True, exist_ok=True)
            qmd.write_text(textwrap.dedent(f"""
            ---
            title: Dependency Tree for {lib}
            format: html
            ---

            > This diagram shows module import dependencies (not a Python statement!).

            ## Mermaid
            ```{{mermaid}}
            {''.join(mermaid)}
            ```

            ## Graphviz DOT
            ```{{dot}}
            {''.join(dot)}
            ```
            """), encoding="utf-8"); written = str(qmd.relative_to(p))
        c = _console(); c.print(Panel("Dependency tree generated (internal/external).", title="dependency tree"))
        return {
            "ok": True,
            "scope": scope,
            "nodes_internal": sorted(internal_nodes) if scope in ("internal", "both") else [],
            "nodes_external": sorted(external_nodes) if scope in ("external", "both") else [],
            "edges": sorted(list(edges)),
            "unreferenced_internal": unreferenced_internal if (include_unused in ("internal", "both")) else [],
            "unused_external_aliases": unused_external if (include_unused in ("external", "both")) else [],
            "mermaid": "".join(mermaid),
            "dot": "".join(dot),
            "written": written,
            "pretty": _export_console(c),
        }

    # 13) Dependency snapshot (dependency tree + _modidx coverage)
    @mcp.tool(description="Combine dependency tree with _modidx to spot missing modules, duplicates, and unreferenced exports.")
    def dependency_snapshot(project: Optional[str] = None,
                             scope: str = "internal",
                             include_unused: Optional[str] = None,
                             write_qmd: Optional[str] = None) -> Dict[str, Any]:
        try:
            p = _resolve_selector(project)
            modidx = _load_modidx(p)
        except Exception as e:
            return {"ok": False, "error": str(e)}

        tree = dependency_tree(project=p, scope=scope, include_unused=include_unused, write_qmd=write_qmd)
        if not tree.get("ok"):
            return tree

        modidx_syms = modidx.get("syms", {}) if isinstance(modidx, dict) else {}
        modidx_modules = set(modidx_syms.keys())
        tree_internal = set(tree.get("nodes_internal", []))

        missing_in_modidx = sorted(tree_internal - modidx_modules)
        unused_in_tree = sorted(modidx_modules - tree_internal)

        c = _console()
        t = Table(title="dependency snapshot")
        t.add_column("metric"); t.add_column("count")
        t.add_row("internal modules (tree)", str(len(tree_internal)))
        t.add_row("modules in _modidx", str(len(modidx_modules)))
        t.add_row("missing in _modidx", str(len(missing_in_modidx)))
        t.add_row("unused in tree", str(len(unused_in_tree)))
        c.print(t)

        if missing_in_modidx:
            c.print(Panel("Missing in _modidx (export cells?):\n" + "\n".join(missing_in_modidx[:50]), title="missing modules"))
        if unused_in_tree:
            c.print(Panel("Modules listed in _modidx but not seen in dependency tree (stale exports?):\n" + "\n".join(unused_in_tree[:50]), title="unused modules"))

        return {
            "ok": True,
            "missing_in_modidx": missing_in_modidx,
            "unused_in_tree": unused_in_tree,
            "modidx_path": str(_modidx_path(p)),
            "tree": tree,
            "pretty": _export_console(c),
        }

    # 14) Aggregators
    @mcp.tool(description="Aggregate TODO comments from notebooks into a Markdown TODOs.md file.")
    def aggregate_todos(project: Optional[str] = None, out_file: str = "TODOs.md") -> Dict[str, Any]:
        try: p = _resolve_selector(project)
        except Exception as e: return {"ok": False, "error": str(e)}
        rows: List[Tuple[str, int, int, str]] = []
        todo_re_code = re.compile(r"#\s*TODO:?\s*(.*)", re.IGNORECASE); todo_re_md = re.compile(r"(?:^|\s)TODO:?(.*)", re.IGNORECASE)
        for nb in _iter_notebooks(p):
            data = _read_nb(nb); rel = str(nb.relative_to(p))
            for i, cell in enumerate(data.get("cells", [])):
                src = _join_source_lines(cell.get("source", []))
                if cell.get("cell_type") == "code":
                    for j, ln in enumerate(_cell_lines(src), 1):
                        m = todo_re_code.search(ln)
                        if m: rows.append((rel, i, j, m.group(0).strip()))
                else:
                    for j, ln in enumerate(_cell_lines(src), 1):
                        if "TODO" in ln.upper():
                            m = todo_re_md.search(ln)
                            if m: rows.append((rel, i, j, m.group(0).strip()))
        outp = p / out_file; lines = ["# TODOs\n\n", "| Notebook | Cell | Line | Comment |\n", "|---|---:|---:|---|\n"]
        for rel, i, j, txt in rows: lines.append(f"| {rel} | {i} | {j} | {txt.replace('|','\\|')} |\n")
        outp.write_text("".join(lines), encoding="utf-8"); return {"ok": True, "count": len(rows), "out_file": str(outp.relative_to(p))}

    @mcp.tool(description="Aggregate BUG comments from notebooks into a Markdown BUGs.md file.")
    def aggregate_bugs(project: Optional[str] = None, out_file: str = "BUGs.md") -> Dict[str, Any]:
        try: p = _resolve_selector(project)
        except Exception as e: return {"ok": False, "error": str(e)}
        rows: List[Tuple[str, int, int, str]] = []; bug_re = re.compile(r"\bBUG:?\s*(.*)", re.IGNORECASE)
        skip_files = {"nbs/00_tk/07_bugs.ipynb"}
        for nb in _iter_notebooks(p):
            data = _read_nb(nb); rel = str(nb.relative_to(p))
            if rel in skip_files:
                continue  # skip curated bugs notebook
            for i, cell in enumerate(data.get("cells", [])):
                src = _join_source_lines(cell.get("source", []))
                for j, ln in enumerate(_cell_lines(src), 1):
                    if bug_re.search(ln): rows.append((rel, i, j, ln.strip()))
        outp = p / out_file; lines = ["# BUGs\n\n", "| Notebook | Cell | Line | Comment |\n", "|---|---:|---:|---|\n"]
        for rel, i, j, txt in rows: lines.append(f"| {rel} | {i} | {j} | {txt.replace('|','\\|')} |\n")
        outp.write_text("".join(lines), encoding="utf-8"); return {"ok": True, "count": len(rows), "out_file": str(outp.relative_to(p))}

def create_nbdev_mcp(name: str = "mcp.nbdev") -> FastMCP:
    """Create and configure the nbdev MCP server with all resources, tools, and prompts."""
    mcp = FastMCP(name)
    # Attach all nbdev-related resources, tools, and prompts
    add_resources(mcp)
    add_project_tools(mcp)
    add_env_tools(mcp)
    add_nbdev_tools(mcp)
    add_notebook_editing_tools(mcp)  # CRITICAL: Notebook editing and workflow tools
    add_prompts(mcp)  # Philosophy prompts must come after tools are registered
    add_extensions(mcp)  # v2 extensions: rules, dependency tree, tests, stubs, aggregators
    return mcp

# ----------------------------- HTTP helpers ---------------------------------
def _set_http_path_if_supported(target_path: str) -> bool:
    """
    Try to set the HTTP mount path on the SDK settings if supported.
    Returns True if successfully set, else False (if attribute not found).
    """
    try:
        # Newer SDKs (FastMCP 2.x)
        mcp.settings.streamable_http_path = target_path  # type: ignore[attr-defined]
        return True
    except Exception:
        try:
            # Older attribute name in some SDK versions
            mcp.settings.http_path = target_path  # type: ignore[attr-defined]
            return True
        except Exception:
            return False

# ----------------------------- entrypoint -----------------------------------
def _render_result(title: str, meta: Dict[str, Any], logs: Dict[str, Any] | None = None) -> str:
    """
    Render a result panel with a title and optional tables of metadata and logs.
    (Used for pretty-printing command results back to the user interface.)
    """
    c = _console()
    c.print(Panel.fit(Text(title, style="bold"), title="nbdev MCP"))
    if meta:
        t = Table(title="Context", expand=False)
        t.add_column("Key")
        t.add_column("Value")
        for k, v in meta.items():
            t.add_row(k, str(v))
        c.print(t)
    if logs:
        t2 = Table(title="Command", expand=False)
        t2.add_column("Field")
        t2.add_column("Value")
        for k in ("cmd", "cwd", "returncode", "ok"):
            if k in logs:
                t2.add_row(k, str(logs[k]))
        c.print(t2)
        if logs.get("stdout"):
            c.print(Panel.fit(Markdown(f"```\\n{logs['stdout']}\\n```"), title="stdout"))
        if logs.get("stderr"):
            c.print(Panel.fit(Markdown(f"```\\n{logs['stderr']}\\n```"), title="stderr"))
    return _export_console(c)

def main() -> None:
    """Entry point for the nbdev MCP server CLI."""
    parser = argparse.ArgumentParser(
        description="nbdev MCP server (multi-project, rich output)",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Example: python mcp.nbdev.py --transport http --host 0.0.0.0 --port 8765 --path /mcp\\n"
            "Note: Ensure 'uvicorn' is installed for custom HTTP server."
        )
    )
    parser.add_argument("--project", help="Path or alias for an nbdev project to load initially.")
    parser.add_argument("--transport", choices=("stdio", "http", "streamable-http"), 
                        default=os.environ.get("NBDEV_MCP_TRANSPORT", "stdio"),
                        help="Transport mode: 'stdio' (for CLI/desktop clients), 'streamable-http' (built-in HTTP on default port/path), or 'http' (custom host/port via Uvicorn).")
    parser.add_argument("--host", default=os.environ.get("NBDEV_MCP_HOST", "127.0.0.1"),
                        help="Host interface to serve on (default: NBDEV_MCP_HOST or 127.0.0.1).")
    parser.add_argument("--port", type=int, default=int(os.environ.get("NBDEV_MCP_PORT", "8000")),
                        help="Port to serve on (default: NBDEV_MCP_PORT or 8000).")
    parser.add_argument("--path", default=os.environ.get("NBDEV_MCP_PATH", "/mcp"),
                        help="Base URL path for HTTP transport (default: NBDEV_MCP_PATH or /mcp).")
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args()

    # If an initial project path or alias is provided, set it now
    if args.project:
        try:
            proj_path = _resolve_selector(args.project)
            CURRENT_PROJECT = proj_path  # set the global current project
        except Exception as e:
            log.error(str(e))

    # Build the MCP server with all nbdev features
    mcp = create_nbdev_mcp()

    # Decide transport using structural pattern matching (Python 3.10+)
    default_host, default_port, default_path = "127.0.0.1", 8000, "/mcp"
    using_defaults = (args.host == default_host and args.port == default_port and args.path == default_path)

    match args.transport:
        case "stdio":
            mcp.run(transport="stdio")
        case "streamable-http":
            if using_defaults:
                # Default behavior: run built-in server on 127.0.0.1:8000 at /mcp
                mcp.run(transport="streamable-http")
            else:
                # Custom host/port for streamable HTTP – use Uvicorn as fallback
                try:
                    import uvicorn
                except ImportError:
                    log.error("uvicorn is required for custom host/port HTTP transport. Please install uvicorn and try again.")
                    sys.exit(1)
                if args.path and args.path != default_path:
                    ok = _set_http_path_if_supported(args.path)
                    if not ok:
                        log.warning("Could not set custom HTTP path on this SDK; using default '/mcp'.")
                app = mcp.streamable_http_app()
                uvicorn.run(app, host=args.host, port=args.port)
        case "http":
            # Use Uvicorn to serve HTTP on the specified host/port
            try:
                import uvicorn
            except ImportError:
                log.error("uvicorn is required for custom host/port HTTP transport. Please install uvicorn and try again.")
                sys.exit(1)
            if args.path and args.path != default_path:
                ok = _set_http_path_if_supported(args.path)
                if not ok:
                    log.warning("Could not set custom HTTP path on this SDK; using default '/mcp'.")
            app = mcp.streamable_http_app()
            uvicorn.run(app, host=args.host, port=args.port)
        case _:
            raise SystemExit(f"Unsupported transport option: {args.transport!r}")

if __name__ == "__main__":
    main()

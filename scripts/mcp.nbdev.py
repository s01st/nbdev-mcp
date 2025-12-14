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

$ python mcp.nbdev.py --transport http --host 127.0.0.1 --port 8765 --path /mcp
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import re
import shlex
import subprocess
import sys
import textwrap
from configparser import ConfigParser
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP  # official MCP Python SDK (FastMCP 2.0+)
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

__version__ = "1.2.0"  # Added advanced patterns prompt for __all__ and package structure

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
        - `nbdev_test()` - Run tests in notebooks

        ## Remember:
        - Notebooks = code + documentation + tests in one file
        - Always export after editing notebooks
        - Never manually edit generated files
        - Use tools to find and edit source notebooks
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

        # Sixth cell - Code (documentation)
        from nbdev.showdoc import show_doc
        show_doc(process_data)
        ```
        """)

    @mcp.prompt()
    def module_scaffold(module: str, pkg: Optional[str] = None) -> str:
        """Prompt: Generate a scaffold for a new module notebook in nbdev, given a module name."""
        # Determine package name (lib_name from settings unless overridden)
        s = _settings_dict(_require_project()) if CURRENT_PROJECT else {}
        lib = pkg or s.get("lib_name") or "<your_pkg>"
        md = f"""\
        # {module}
        > Auto-generated scaffold for `{lib}.{module}`

        ## Imports
        ```python
        %load_ext autoreload
        %autoreload 2
        from nbdev.showdoc import show_doc
        ```

        ```python
        #| default_exp {module}
        ```

        ## {module.capitalize()} API
        ```python
        #| export
        def my_function(x: int) -> int:
            "Example function"
            return x + 1
        ```

        ## Examples and tests
        ```python
        y = my_function(1)
        assert y == 2
        ```

        ## Documentation
        ```python
        show_doc(my_function)
        ```
        """
        return textwrap.dedent(md)

    @mcp.prompt()
    def nbdev_advanced_patterns() -> str:
        """
        Prompt: Advanced nbdev patterns for __all__ exports, package structure, and lifting symbols.

        Covers:
        - When to define __all__ (only in __init__.py files)
        - How to create subpackages/submodules
        - Lifting symbols to package level
        - Module organization best practices
        """
        return textwrap.dedent("""
        # nbdev Advanced Patterns

        ## __all__ Exports: The Golden Rule

        **🚫 DON'T define `__all__` in regular modules**

        nbdev automatically generates `__all__` from your `#| export` directives.

        ```python
        # ❌ DON'T DO THIS in regular notebooks:
        #| export
        __all__ = ['MyClass', 'my_function']  # nbdev will override this!

        # ✅ DO THIS - let nbdev auto-generate:
        #| export
        def my_function():
            pass

        #| export
        class MyClass:
            pass
        ```

        ## When to Define __all__: ONLY in __init__.py Files

        **✅ Define `__all__` ONLY when:**
        1. Creating `__init__.py` for a package
        2. You want to lift symbols from submodules to package level

        **Example: Lifting to Package Level**

        ```python
        # nbs/00__init__.ipynb
        #| default_exp __init__

        #| export
        # Import from submodules
        from .core import MyClass, process_data
        from .utils import helper_function

        #| export
        # Explicitly define what's available at package level
        __all__ = [
            'MyClass',
            'process_data',
            'helper_function',
        ]
        ```

        **Result:** Users can do `from mylib import MyClass` instead of `from mylib.core import MyClass`

        ## Creating Submodules and Packages

        ### Use Dot Notation in default_exp

        To create `mylib/core/data.py`:

        ```python
        # nbs/core/01_data.ipynb
        #| default_exp core.data
        ```

        The dot notation `core.data` tells nbdev to create the `core/` subdirectory.

        ### Create __init__.py for Each Package

        For every package/subpackage, create a `00__init__.ipynb`:

        ```python
        # nbs/core/00__init__.ipynb
        #| default_exp core.__init__

        #| export
        from .data import DataLoader
        from .processing import Processor

        #| export
        __all__ = ['DataLoader', 'Processor']
        ```

        This creates `mylib/core/__init__.py` and lifts symbols to `mylib.core` level.

        ## Complete Package Structure Example

        **Directory structure:**
        ```
        nbs/
        ├── 00__init__.ipynb           # mylib.__init__
        ├── core/
        │   ├── 00__init__.ipynb       # mylib.core.__init__
        │   ├── 01_data.ipynb          # mylib.core.data
        │   └── 02_processing.ipynb    # mylib.core.processing
        └── utils/
            ├── 00__init__.ipynb       # mylib.utils.__init__
            └── 01_helpers.ipynb       # mylib.utils.helpers
        ```

        **Subpackage init (nbs/core/00__init__.ipynb):**
        ```python
        #| default_exp core.__init__

        #| export
        from .data import DataLoader, Dataset
        from .processing import Processor

        #| export
        __all__ = ['DataLoader', 'Dataset', 'Processor']
        ```

        **Top-level init (nbs/00__init__.ipynb):**
        ```python
        #| default_exp __init__

        #| export
        # Lift most commonly-used symbols to top level
        from .core import DataLoader, Processor
        from .utils import helper

        #| export
        __all__ = [
            'DataLoader',
            'Processor',
            'helper',
            # Dataset NOT listed - users must use mylib.core.Dataset
        ]
        ```

        ## Lifting Symbols: Multi-Level Access

        With proper lifting, users can import at any level:

        ```python
        # All three work:
        from mylib import DataLoader                    # Top-level (lifted)
        from mylib.core import DataLoader               # Subpackage level (lifted)
        from mylib.core.data import DataLoader          # Module level (original)
        ```

        ## Decision Tree: Do I Define __all__?

        ```
        Is this an __init__.py file?
        ├─ YES → Am I lifting symbols from submodules?
        │        ├─ YES → ✅ Define __all__ with lifted symbols
        │        └─ NO  → ❌ Don't define __all__
        └─ NO  → ❌ Don't define __all__ (nbdev auto-generates)
        ```

        ## Quick Reference

        | Notebook | default_exp | Generated File |
        |----------|-------------|----------------|
        | 01_core.ipynb | `core` | mylib/core.py |
        | 00__init__.ipynb | `__init__` | mylib/__init__.py |
        | core/01_data.ipynb | `core.data` | mylib/core/data.py |
        | core/00__init__.ipynb | `core.__init__` | mylib/core/__init__.py |

        ## Common Mistakes to Avoid

        1. **❌ Defining __all__ in regular modules** - nbdev auto-generates it
        2. **❌ Forgetting subpackage __init__.py** - Each package needs one
        3. **❌ Circular imports** - Don't import from parent in submodules
        4. **❌ Wrong default_exp** - Use dots for subdirectories: `core.data` not `core/data`

        ## Checklist: Creating a New Submodule

        For `mylib/foo/bar.py`:

        1. ✅ Create `nbs/foo/01_bar.ipynb`
        2. ✅ Set `#| default_exp foo.bar`
        3. ✅ Create `nbs/foo/00__init__.ipynb`
        4. ✅ Set `#| default_exp foo.__init__`
        5. ✅ Lift symbols:
           ```python
           #| export
           from .bar import MyClass
           #| export
           __all__ = ['MyClass']
           ```
        6. ✅ Run `nbdev_export`
        7. ✅ Test: `from mylib.foo import MyClass`

        ## See Also

        - NBDEV_ADVANCED_PATTERNS.md - Full guide with examples
        - nbdev docs: https://nbdev.fast.ai
        """)

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
"""Cursor IDE MCP client for reading IDE state (open files, diagnostics, etc.).

This module bridges the AI_support agent to Cursor IDE's Model Context Protocol tools.
Place this file at the path referenced by context_provider.py.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

# Path to Cursor's MCP tools folder
TERMINALS_FOLDER = Path(__file__).resolve().parents[1] / ".cursor" / "projects" / "c-Users-thang-Desktop-carv" / "terminals"


def list_open_files() -> List[str]:
    """Get list of currently open files in Cursor."""
    try:
        # Try reading from Cursor's workspace state
        cursor_data = Path.home() / ".cursor" / "data" / "workspace-state.json"
        if cursor_data.exists():
            data = json.loads(cursor_data.read_text(encoding="utf-8"))
            return data.get("openFiles", [])
    except Exception:
        pass

    # Fallback: scan recently accessed files
    try:
        recent = Path.home() / ".cursor" / "data" / "recently-opened.json"
        if recent.exists():
            files = json.loads(recent.read_text(encoding="utf-8"))
            return [f for f in files if Path(f).exists() and f.endswith((".c", ".h", ".py", ".md", ".ts", ".js"))]
    except Exception:
        pass

    return []


def get_diagnostics() -> List[Dict]:
    """Get current diagnostics (errors/warnings) from Cursor's language servers."""
    try:
        diag_file = Path.home() / ".cursor" / "data" / "diagnostics.json"
        if diag_file.exists():
            return json.loads(diag_file.read_text(encoding="utf-8"))
    except Exception:
        pass

    return []


def get_terminal_output() -> str:
    """Get output from the active terminal in Cursor."""
    terminals_dir = TERMINALS_FOLDER
    if not terminals_dir.exists():
        return ""

    try:
        txt_files = sorted(terminals_dir.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
        if txt_files:
            content = txt_files[0].read_text(encoding="utf-8", errors="ignore")
            # Strip metadata header (first ~10 lines with pid, cwd, etc.)
            lines = content.splitlines()
            output_lines = []
            skip_mode = False
            for line in lines:
                if line.startswith("---"):
                    skip_mode = True
                    continue
                if skip_mode and line.startswith("last_command:"):
                    skip_mode = False
                    continue
                if not skip_mode:
                    output_lines.append(line)
            return "\n".join(output_lines[-100:])
    except Exception:
        pass

    return ""


def get_cursor_errors() -> List[Dict]:
    """Get current error list from Cursor problems panel."""
    try:
        problems_file = Path.home() / ".cursor" / "data" / "problems.json"
        if problems_file.exists():
            problems = json.loads(problems_file.read_text(encoding="utf-8"))
            return [p for p in problems if p.get("severity") in ("error", "warning")]
    except Exception:
        pass
    return []


def get_recent_changes() -> Dict[str, str]:
    """Get recently changed files from Cursor's file watchers."""
    try:
        changes_file = Path.home() / ".cursor" / "data" / "recent-changes.json"
        if changes_file.exists():
            return json.loads(changes_file.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

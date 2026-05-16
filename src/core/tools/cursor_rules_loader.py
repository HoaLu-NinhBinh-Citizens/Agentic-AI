"""Loader for .cursor/rules/*.mdc files."""

import re
from pathlib import Path
from typing import Optional


CURSOR_RULES_DIR = Path(__file__).resolve().parents[2] / ".cursor" / "rules"
MDC_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _parse_frontmatter(content: str) -> dict:
    match = MDC_FRONTMATTER_RE.match(content)
    if not match:
        return {}
    fm = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip()
    return fm


def load_all_cursor_rules() -> str:
    """Load all .cursor/rules/*.mdc files into a single string for injection."""
    rules_dir = CURSOR_RULES_DIR
    if not rules_dir.is_dir():
        return ""

    sections = []
    mdc_files = sorted(rules_dir.glob("*.mdc"))

    for mdc_path in mdc_files:
        try:
            raw = mdc_path.read_text(encoding="utf-8")
        except OSError:
            continue

        fm = _parse_frontmatter(raw)
        # Strip frontmatter from content
        body = MDC_FRONTMATTER_RE.sub("", raw).strip()

        if body:
            rule_name = mdc_path.stem  # filename without .mdc
            # Use description from frontmatter if available
            desc = fm.get("description", rule_name)
            sections.append(f"## {rule_name} ({desc})\n\n{body}")

    if not sections:
        return ""

    header = (
        "You MUST follow the rules below. These are Cursor IDE project rules — "
        "treat them as binding instructions.\n\n"
    )
    return header + "\n\n---\n\n".join(sections)


def load_cursor_rules_for_file(filepath: str) -> str:
    """Load only rules that match the given file path via glob patterns."""
    rules_dir = CURSOR_RULES_DIR
    if not rules_dir.is_dir():
        return ""

    matching_sections = []
    mdc_files = sorted(rules_dir.glob("*.mdc"))

    for mdc_path in mdc_files:
        try:
            raw = mdc_path.read_text(encoding="utf-8")
        except OSError:
            continue

        fm = _parse_frontmatter(raw)
        globs_str = fm.get("globs", "")
        if not globs_str:
            continue

        # Check if filepath matches any glob in the rule
        matched = False
        for pattern in globs_str.split(","):
            pattern = pattern.strip()
            if _path_matches_glob(filepath, pattern):
                matched = True
                break

        if not matched:
            continue

        body = MDC_FRONTMATTER_RE.sub("", raw).strip()
        if body:
            rule_name = mdc_path.stem
            desc = fm.get("description", rule_name)
            matching_sections.append(f"## {rule_name} ({desc})\n\n{body}")

    if not matching_sections:
        return ""

    header = (
        f"Rules for `{filepath}`:\n\n"
    )
    return header + "\n\n---\n\n".join(matching_sections)


def _path_matches_glob(filepath: str, pattern: str) -> bool:
    """Simple glob match for file paths (supports **, *, ?)."""
    import fnmatch
    return fnmatch.fnmatch(filepath.replace("\\", "/"), pattern.replace("\\", "/"))

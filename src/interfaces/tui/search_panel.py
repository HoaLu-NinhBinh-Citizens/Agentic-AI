"""Search Panel — Cursor-like search and replace interface.

Provides:
- Text search (grep) across files
- Regex search
- Search history
- Search results with preview
- Multi-file replace
- Find references
- Go to line / symbol
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional


@dataclass
class SearchResult:
    """A search result."""
    file_path: str
    line: int
    col: int
    end_col: int
    line_content: str
    match_text: str
    context_before: str = ""
    context_after: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file_path,
            "line": self.line,
            "column": self.col,
            "endColumn": self.end_col,
            "lineContent": self.line_content,
            "match": self.match_text,
            "contextBefore": self.context_before,
            "contextAfter": self.context_after,
        }


@dataclass
class SearchQuery:
    """A search query."""
    pattern: str
    is_regex: bool = False
    is_case_sensitive: bool = False
    is_whole_word: bool = False
    is_include_only: bool = False
    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)
    max_results: int = 1000


@dataclass
class ReplacePreview:
    """A preview of a replace operation."""
    result: SearchResult
    new_text: str
    replaced_text: str = ""


class SearchPanel:
    """Cursor-like search panel."""

    def __init__(self, root_dir: str = "."):
        self._root_dir = Path(root_dir)
        self._callbacks: list[Callable[[dict], None]] = []
        self._history: list[str] = []
        self._last_results: list[SearchResult] = []
        self._stats = {
            "searches": 0,
            "results_found": 0,
            "replacements": 0,
            "files_modified": 0,
        }

    async def search(
        self,
        query: SearchQuery,
        paths: Optional[list[str]] = None,
    ) -> list[SearchResult]:
        """Search for a pattern and return results."""
        self._stats["searches"] += 1

        if query.pattern not in self._history:
            self._history.append(query.pattern)
            if len(self._history) > 50:
                self._history.pop(0)

        flags = 0
        if not query.is_case_sensitive:
            flags |= re.IGNORECASE

        if query.is_regex:
            try:
                compiled = re.compile(query.pattern, flags)
            except re.error:
                return []
        else:
            pattern = re.escape(query.pattern)
            if query.is_whole_word:
                pattern = r"\b" + pattern + r"\b"
            compiled = re.compile(pattern, flags)

        results: list[SearchResult] = []
        search_paths = paths or ["."]

        for search_path in search_paths:
            path = self._root_dir / search_path
            if not path.exists():
                continue

            if path.is_file():
                file_results = await self._search_file(path, compiled, query)
                results.extend(file_results)
            else:
                files = self._get_files(path, query)
                file_results_list = await asyncio.gather(*[
                    self._search_file(f, compiled, query)
                    for f in files
                ], return_exceptions=True)
                for file_results in file_results_list:
                    if isinstance(file_results, list):
                        results.extend(file_results)

            if len(results) >= query.max_results:
                break

        results.sort(key=lambda r: (r.file_path, r.line))
        self._last_results = results
        self._stats["results_found"] += len(results)

        self._send_to_ide({
            "type": "search/completed",
            "query": query.pattern,
            "resultsCount": len(results),
            "results": [r.to_dict() for r in results[:100]],
        })

        return results

    async def _search_file(
        self,
        file_path: Path,
        compiled: re.Pattern,
        query: SearchQuery,
    ) -> list[SearchResult]:
        """Search within a single file."""
        results = []

        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            return results

        for i, line in enumerate(lines):
            matches = list(compiled.finditer(line))
            if matches:
                for m in matches:
                    context_before = lines[i - 1].strip() if i > 0 else ""
                    context_after = lines[i + 1].strip() if i < len(lines) - 1 else ""

                    result = SearchResult(
                        file_path=str(file_path),
                        line=i,
                        col=m.start(),
                        end_col=m.end(),
                        line_content=line.rstrip(),
                        match_text=m.group(),
                        context_before=context_before,
                        context_after=context_after,
                    )
                    results.append(result)

                    if len(results) >= query.max_results:
                        return results

        return results

    def _get_files(self, root: Path, query: SearchQuery) -> list[Path]:
        """Get files to search in, respecting include/exclude patterns."""
        files = []

        for ext in [".py", ".js", ".ts", ".rs", ".go", ".java", ".c", ".cpp", ".h", ".sh", ".md"]:
            for f in root.rglob(f"*{ext}"):
                if self._should_exclude(f, query.exclude_patterns):
                    continue
                if query.include_patterns and not self._should_include(f, query.include_patterns):
                    continue
                files.append(f)

        return files[:1000]

    def _should_exclude(self, path: Path, patterns: list[str]) -> bool:
        """Check if a path should be excluded."""
        for pattern in patterns:
            if pattern in str(path):
                return True
        for ignore in ["__pycache__", ".git", "node_modules", ".venv", "dist", "build"]:
            if ignore in str(path):
                return True
        return False

    def _should_include(self, path: Path, patterns: list[str]) -> bool:
        """Check if a path matches include patterns."""
        if not patterns:
            return True
        for pattern in patterns:
            if pattern in str(path):
                return True
        return False

    async def replace_all(
        self,
        query: SearchQuery,
        replacement: str,
        results: Optional[list[SearchResult]] = None,
    ) -> dict[str, Any]:
        """Replace all matches."""
        results = results or self._last_results
        if not results:
            return {"success": False, "error": "No search results"}

        self._stats["replacements"] += len(results)

        files_modified: set[str] = set()
        replacements = []

        by_file: dict[str, list[SearchResult]] = {}
        for result in results:
            if result.file_path not in by_file:
                by_file[result.file_path] = []
            by_file[result.file_path].append(result)

        for file_path, file_results in by_file.items():
            try:
                with open(file_path, encoding="utf-8", errors="replace") as f:
                    content = f.read()

                lines = content.split("\n")
                file_results.sort(key=lambda r: r.line, reverse=True)

                for result in file_results:
                    if 0 <= result.line < len(lines):
                        old_line = lines[result.line]
                        new_line = old_line[:result.col] + replacement + old_line[result.end_col:]
                        lines[result.line] = new_line
                        files_modified.add(file_path)
                        replacements.append({
                            "file": file_path,
                            "line": result.line,
                            "old": result.match_text,
                            "new": replacement,
                        })

                with open(file_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))

            except OSError:
                continue

        self._stats["files_modified"] += len(files_modified)

        return {
            "success": True,
            "replacements": len(replacements),
            "filesModified": len(files_modified),
            "files": list(files_modified),
            "details": replacements,
        }

    async def replace_one(
        self,
        result: SearchResult,
        replacement: str,
    ) -> bool:
        """Replace a single match."""
        try:
            with open(result.file_path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            if 0 <= result.line < len(lines):
                old_line = lines[result.line]
                new_line = old_line[:result.col] + replacement + old_line[result.end_col:]
                lines[result.line] = new_line

                with open(result.file_path, "w", encoding="utf-8") as f:
                    f.write("".join(lines))

                self._stats["replacements"] += 1
                self._stats["files_modified"] += 1
                return True
        except OSError:
            pass
        return False

    def get_history(self) -> list[str]:
        """Get search history."""
        return list(reversed(self._history))

    def on_message(self, callback: Callable[[dict], None]) -> None:
        self._callbacks.append(callback)

    def _send_to_ide(self, message: dict) -> None:
        for cb in self._callbacks:
            try:
                cb(message)
            except Exception:
                pass

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "last_results_count": len(self._last_results),
            "history_count": len(self._history),
        }

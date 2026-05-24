"""AST (Abstract Syntax Tree) tools for Agentic-AI CLI.

Provides:
- Structural code queries (ast-grep style)
- Code pattern matching
- Find and replace with AST awareness
- Language support detection
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ASTMatch:
    """A single AST match."""
    file: str
    line: int
    column: int
    content: str
    metavars: dict[str, str] = field(default_factory=dict)  # Named captures
    
    def __str__(self) -> str:
        return f"{self.file}:{self.line}:{self.column} {self.content}"


@dataclass
class ASTQueryResult:
    """Result of an AST query."""
    matches: list[ASTMatch]
    total_matches: int
    
    def __len__(self) -> int:
        return self.total_matches


class ASTQuery:
    """AST query engine using tree-sitter/ast-grep patterns."""
    
    def __init__(self, pattern: str, language: str | None = None):
        self.pattern = pattern
        self.language = language or "auto"
        self._query_cache: dict[str, str] = {}
    
    async def search(self, paths: list[str | Path]) -> ASTQueryResult:
        """Search for pattern in paths."""
        matches = []
        
        for path in paths:
            path_obj = Path(path) if isinstance(path, str) else path
            
            if path_obj.is_dir():
                matches.extend(await self._search_directory(path_obj))
            elif path_obj.is_file():
                matches.extend(await self._search_file(path_obj))
        
        return ASTQueryResult(
            matches=matches[:100],  # Limit results
            total_matches=len(matches),
        )
    
    async def _search_file(self, path: Path) -> list[ASTMatch]:
        """Search in a single file."""
        lang = self.language
        if lang == "auto":
            lang = self._detect_language(path)
        
        # Try ast-grep first
        try:
            return await self._search_with_ast_grep(path, lang)
        except Exception as e:
            logger.debug(f"ast-grep not available: {e}")
        
        # Fall back to simple pattern matching
        return await self._search_simple(path)
    
    async def _search_directory(self, path: Path) -> list[ASTMatch]:
        """Search in a directory."""
        matches = []
        
        # Find matching files
        for ext in self._get_extensions(self.language):
            for file_path in path.rglob(f"*{ext}"):
                if file_path.is_file():
                    try:
                        matches.extend(await self._search_file(file_path))
                    except Exception:
                        pass
        
        return matches
    
    async def _search_with_ast_grep(self, path: Path, language: str) -> list[ASTMatch]:
        """Search using ast-grep CLI."""
        matches = []
        
        # Run ast-grep
        try:
            result = subprocess.run(
                [
                    "ast-grep", "search",
                    "--pattern", self.pattern,
                    "--lang", language,
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.strip():
                        match = self._parse_ast_grep_output(line)
                        if match:
                            matches.append(match)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        return matches
    
    async def _search_simple(self, path: Path) -> list[ASTMatch]:
        """Simple text-based search when AST not available."""
        matches = []
        
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            lines = content.splitlines()
            
            for i, line in enumerate(lines, 1):
                if self._matches_pattern(line, self.pattern):
                    matches.append(ASTMatch(
                        file=str(path),
                        line=i,
                        column=0,
                        content=line.strip(),
                    ))
        except Exception:
            pass
        
        return matches
    
    def _parse_ast_grep_output(self, line: str) -> ASTMatch | None:
        """Parse ast-grep JSON output."""
        try:
            data = json.loads(line)
            
            # Extract location
            location = data.get("location", {})
            file = data.get("file", "")
            line = location.get("start", {}).get("line", 0)
            column = location.get("start", {}).get("column", 0)
            
            # Extract content
            content = data.get("content", "").strip()
            
            # Extract metavars
            metavars = {}
            for key, value in data.get("metavars", {}).get("$", {}).items():
                if isinstance(value, dict):
                    metavars[key] = value.get("text", "")
            
            return ASTMatch(
                file=file,
                line=line,
                column=column,
                content=content,
                metavars=metavars,
            )
        except json.JSONDecodeError:
            return None
    
    def _matches_pattern(self, line: str, pattern: str) -> bool:
        """Check if line matches pattern."""
        # Simple substring match
        return pattern.lower() in line.lower()
    
    def _detect_language(self, path: Path) -> str:
        """Detect language from file extension."""
        ext = path.suffix.lower()
        lang_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".c": "c",
            ".cpp": "cpp",
            ".h": "c",
        }
        return lang_map.get(ext, "unknown")
    
    def _get_extensions(self, language: str) -> list[str]:
        """Get file extensions for a language."""
        lang_map = {
            "python": [".py"],
            "javascript": [".js", ".jsx", ".mjs"],
            "typescript": [".ts", ".tsx"],
            "go": [".go"],
            "rust": [".rs"],
            "java": [".java"],
            "c": [".c", ".h"],
            "cpp": [".cpp", ".cc", ".hpp", ".h"],
        }
        return lang_map.get(language, [])


@dataclass
class ASTRewrite:
    """An AST-based rewrite rule."""
    name: str
    pattern: str
    replacement: str
    language: str = "auto"
    
    async def apply(self, path: Path) -> tuple[int, list[str]]:
        """Apply rewrite to file.
        
        Returns:
            (number of changes, list of modified files)
        """
        changes = 0
        modified_files = []
        
        try:
            # Run ast-grep rewrite
            result = subprocess.run(
                [
                    "ast-grep", "rewrite",
                    "--rule", self._create_rule_file(),
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if result.returncode == 0:
                output = json.loads(result.stdout)
                changes = output.get("changedFiles", 0)
                modified_files = output.get("files", [])
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
            pass
        
        return changes, modified_files
    
    def _create_rule_file(self) -> str:
        """Create temporary rule file for ast-grep."""
        import tempfile
        
        rule = {
            "id": self.name,
            "language": self.language,
            "rule": {
                "pattern": self.pattern,
            },
            "rewrite": {
                "to": self.replacement,
            },
        }
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            json.dump(rule, f)
            return f.name


class ASTEdit:
    """AST-aware edit tool (like omp's ast_edit)."""
    
    def __init__(self):
        self.pending_edits: dict[str, dict] = {}
    
    def propose(
        self,
        path: str | Path,
        rule: str,
        replacement: str,
        language: str = "auto",
    ) -> dict[str, Any]:
        """Propose an AST edit without applying.
        
        Like omp's ast_edit that returns a proposed card.
        """
        path_obj = Path(path) if isinstance(path, str) else path
        
        # Count matches
        query = ASTQuery(rule, language)
        result = asyncio.run(query.search([path_obj]))
        
        proposal = {
            "action": "ast_edit",
            "file": str(path_obj),
            "rule": rule,
            "replacement": replacement,
            "language": language,
            "matches": result.total_matches,
            "proposed": True,
        }
        
        # Store for later resolve
        edit_id = f"{path_obj}:{rule}"
        self.pending_edits[edit_id] = proposal
        
        return proposal
    
    def resolve(
        self,
        path: str | Path,
        rule: str,
        accept: bool = True,
        reason: str = "",
    ) -> dict[str, Any]:
        """Resolve (accept or reject) a proposed edit.
        
        Like omp's resolve tool.
        """
        path_obj = Path(path) if isinstance(path, str) else path
        edit_id = f"{path_obj}:{rule}"
        
        if edit_id not in self.pending_edits:
            return {"error": "No pending edit found"}
        
        proposal = self.pending_edits.pop(edit_id)
        
        if not accept:
            return {"accepted": False, "reason": "rejected", "message": reason}
        
        # Apply the edit
        query = ASTQuery(proposal["rule"], proposal["language"])
        rewrite = ASTRewrite(
            name="inline_edit",
            pattern=proposal["rule"],
            replacement=proposal["replacement"],
            language=proposal["language"],
        )
        
        changes, modified = asyncio.run(rewrite.apply(path_obj))
        
        return {
            "accepted": True,
            "reason": reason,
            "changes": changes,
            "modified_files": modified,
            "message": f"Applied {changes} replacements in {len(modified)} files",
        }


# Convenience functions
async def ast_search(pattern: str, paths: list[str | Path], language: str = "auto") -> ASTQueryResult:
    """Search for AST pattern in paths."""
    query = ASTQuery(pattern, language)
    return await query.search(paths)


def ast_edit_propose(path: str | Path, rule: str, replacement: str, language: str = "auto") -> dict:
    """Propose an AST edit."""
    editor = ASTEdit()
    return editor.propose(path, rule, replacement, language)


def ast_edit_resolve(path: str | Path, rule: str, accept: bool = True, reason: str = "") -> dict:
    """Resolve a proposed AST edit."""
    editor = ASTEdit()
    return editor.resolve(path, rule, accept, reason)

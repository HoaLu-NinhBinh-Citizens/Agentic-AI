"""Semantic search across codebase.
Search by meaning, not just text.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.infrastructure.indexing.tree_sitter import SafeTreeSitterIndexer


@dataclass
class SearchResult:
    """A search result with context."""
    file: str
    line: int
    snippet: str
    match_type: str  # "symbol", "comment", "docstring", "code", "import"
    score: float
    context_before: str = ""
    context_after: str = ""


class SemanticSearch:
    """Semantic search using embeddings, symbol index, and keyword matching.
    
    Features:
    - Symbol search (functions, classes, variables)
    - Comment and docstring search
    - Code pattern search
    - Multi-language support
    - Relevance scoring
    
    Usage:
        searcher = SemanticSearch(project_root=Path("."))
        searcher.index_project()
        
        results = searcher.search("error handling function")
    """
    
    def __init__(
        self,
        project_root: Path | str,
        indexer: Optional["SafeTreeSitterIndexer"] = None,
    ):
        self.project_root = Path(project_root)
        self.indexer = indexer
        self._symbol_index: dict[str, list[str]] = {}  # symbol_name -> ["file:line", ...]
        self._is_indexed: bool = False
        self._common_patterns = self._load_patterns()
    
    def _load_patterns(self) -> dict[str, str]:
        """Load regex patterns for code search."""
        return {
            "error handling": r"try:|except\s*\w*:|except\s*\w*\s+as\s+\w*:",
            "async": r"async\s+def|await\s+|asyncio\.",
            "class": r"class\s+\w+",
            "function": r"def\s+\w+",
            "import": r"^import\s+|^from\s+",
            "decorator": r"@\w+",
            "context manager": r"with\s+.+\s+as\s+:",
            "list comprehension": r"\[.+for\s+.+in\s+.+\]",
            "type hint": r":\s*\w+\s*=|->\s*\w+:",
            "property": r"@property|@\.setter",
            "exception": r"raise\s+\w+|raise\s+\w+\(|RuntimeError|ValueError|TypeError",
            "test": r"def\s+test_|unittest|pytest|assert\s+",
            "logging": r"logger\.|logging\.|print\(",
            "config": r"config\.|settings\.|yaml\.|json\.load",
            "database": r"SELECT|INSERT|UPDATE|DELETE|sqlalchemy|sqlite3",
            "api": r"request\.|response\.|endpoint|@app\.route",
        }
    
    def index_project(self) -> None:
        """Build semantic index of the project.
        
        This indexes:
        - All symbols (functions, classes, variables)
        - File structure
        - Import statements
        """
        if self._is_indexed:
            logger.info("Project already indexed")
            return
        
        # Try to use tree-sitter indexer if available
        if self.indexer:
            try:
                self._index_with_tree_sitter()
                self._is_indexed = True
                logger.info("Project indexed with tree-sitter")
                return
            except Exception as e:
                logger.warning("Tree-sitter indexing failed: %s, falling back to regex", e)
        
        # Fall back to regex-based indexing
        self._index_with_regex()
        self._is_indexed = True
        logger.info("Project indexed with regex")
    
    def _index_with_tree_sitter(self) -> None:
        """Index project using tree-sitter."""
        from src.infrastructure.indexing.tree_sitter import SafeTreeSitterIndexer
        
        if self.indexer is None:
            self.indexer = SafeTreeSitterIndexer()
        
        for ext in ["*.py", "*.js", "*.ts", "*.c", "*.h", "*.go", "*.rs"]:
            for file_path in self.project_root.rglob(ext):
                if not self._should_index(file_path):
                    continue
                
                try:
                    tree = self.indexer.index_file(str(file_path))
                    self._index_tree(file_path, tree)
                except Exception as e:
                    logger.debug("Failed to index %s: %s", file_path, e)
    
    def _index_tree(self, file_path: Path, tree: dict) -> None:
        """Index symbols from a parsed tree."""
        symbols = tree.get("symbols", [])
        
        for sym in symbols:
            name = sym.get("name", "")
            kind = sym.get("kind", "")
            line = sym.get("line", 0)
            
            if not name or name.startswith("_"):
                continue
            
            key = name
            if kind in ("method", "function"):
                key = name
            
            location = f"{file_path}:{line}"
            
            if key not in self._symbol_index:
                self._symbol_index[key] = []
            
            if location not in self._symbol_index[key]:
                self._symbol_index[key].append(location)
    
    def _index_with_regex(self) -> None:
        """Index project using regex patterns."""
        patterns = [
            (r"def\s+(\w+)", "function"),
            (r"async\s+def\s+(\w+)", "function"),
            (r"class\s+(\w+)", "class"),
            (r"const\s+(\w+)", "const"),
            (r"let\s+(\w+)", "variable"),
            (r"var\s+(\w+)", "variable"),
            (r"interface\s+(\w+)", "interface"),
            (r"type\s+(\w+)", "type"),
            (r"struct\s+(\w+)", "struct"),
        ]
        
        for ext in ["*.py", "*.js", "*.ts", "*.c", "*.h", "*.go", "*.rs"]:
            for file_path in self.project_root.rglob(ext):
                if not self._should_index(file_path):
                    continue
                
                try:
                    content = file_path.read_text(encoding='utf-8')
                    lines = content.split('\n')
                    
                    for i, line in enumerate(lines):
                        for pattern, kind in patterns:
                            match = re.search(pattern, line)
                            if match:
                                name = match.group(1)
                                location = f"{file_path}:{i + 1}"
                                
                                if name not in self._symbol_index:
                                    self._symbol_index[name] = []
                                
                                if location not in self._symbol_index[name]:
                                    self._symbol_index[name].append(location)
                except Exception as e:
                    logger.debug("Failed to index %s: %s", file_path, e)
    
    def search(
        self,
        query: str,
        limit: int = 20,
        match_type: Optional[str] = None,
    ) -> list[SearchResult]:
        """Search for query across codebase.
        
        Args:
            query: Search query
            limit: Maximum results to return
            match_type: Filter by type ("all", "symbol", "comment", "code")
            
        Returns:
            List of SearchResult objects
        """
        results: list[SearchResult] = []
        
        # Determine search type
        if match_type is None or match_type == "all":
            # Search all types
            results.extend(self._search_symbols(query))
            results.extend(self._search_patterns(query))
            results.extend(self._search_comments(query))
            results.extend(self._search_imports(query))
        elif match_type == "symbol":
            results.extend(self._search_symbols(query))
        elif match_type == "comment":
            results.extend(self._search_comments(query))
        elif match_type == "code":
            results.extend(self._search_patterns(query))
        
        # Sort by score
        results.sort(key=lambda x: x.score, reverse=True)
        
        # Remove duplicates
        seen: set[str] = set()
        unique: list[SearchResult] = []
        for r in results:
            key = f"{r.file}:{r.line}"
            if key not in seen:
                seen.add(key)
                unique.append(r)
        
        return unique[:limit]
    
    def _search_symbols(self, query: str) -> list[SearchResult]:
        """Search for symbols matching query."""
        results: list[SearchResult] = []
        query_lower = query.lower()
        
        # Direct symbol matches
        for symbol, locations in self._symbol_index.items():
            symbol_lower = symbol.lower()
            
            if query_lower == symbol_lower:
                # Exact match
                score = 1.0
            elif query_lower in symbol_lower:
                # Contains match
                score = 0.8
            elif self._fuzzy_match(query_lower, symbol_lower):
                # Fuzzy match
                score = 0.6
            else:
                continue
            
            for loc in locations[:3]:  # Limit locations per symbol
                parts = loc.split(":")
                if len(parts) >= 2:
                    file_path, line_str = parts[0], parts[1]
                    try:
                        line_num = int(line_str)
                        results.append(SearchResult(
                            file=file_path,
                            line=line_num,
                            snippet=f"{symbol} defined here",
                            match_type="symbol",
                            score=score,
                        ))
                    except ValueError:
                        pass
        
        return results
    
    def _search_comments(self, query: str) -> list[SearchResult]:
        """Search comments and docstrings."""
        results: list[SearchResult] = []
        query_lower = query.lower()
        
        comment_patterns = {
            ".py": [r'#\s*[^\n]+', r'"""\s*[^\n]*', r"'''\s*[^\n]*"],
            ".js": [r'//\s*[^\n]+', r'/\*\s*[^\n]*'],
            ".ts": [r'//\s*[^\n]+', r'/\*\s*[^\n]*'],
            ".c": [r'//\s*[^\n]+', r'/\*\s*[^\n]*', r'/\*\*\s*[^\n]*'],
            ".h": [r'//\s*[^\n]+', r'/\*\s*[^\n]*'],
        }
        
        for ext, patterns in comment_patterns.items():
            for file_path in self.project_root.rglob(f"*{ext}"):
                if not self._should_index(file_path):
                    continue
                
                try:
                    content = file_path.read_text(encoding='utf-8')
                    lines = content.split('\n')
                    
                    for i, line in enumerate(lines):
                        for pattern in patterns:
                            if re.search(pattern, line):
                                if query_lower in line.lower():
                                    # Get context
                                    before = lines[i-1] if i > 0 else ""
                                    after = lines[i+1] if i < len(lines)-1 else ""
                                    
                                    results.append(SearchResult(
                                        file=str(file_path),
                                        line=i + 1,
                                        snippet=line.strip()[:100],
                                        match_type="comment",
                                        score=0.5,
                                        context_before=before,
                                        context_after=after,
                                    ))
                except Exception as e:
                    logger.debug("Comment search failed in %s: %s", file_path, e)
        
        return results
    
    def _search_patterns(self, query: str) -> list[SearchResult]:
        """Search code patterns."""
        results: list[SearchResult] = []
        query_lower = query.lower()
        
        # Check for pattern match
        pattern = None
        for pattern_name, pattern_re in self._common_patterns.items():
            if query_lower in pattern_name.lower() or query_lower == pattern_name:
                pattern = pattern_re
                break
        
        if not pattern:
            # Use query as-is
            pattern = re.escape(query)
        
        for ext in ["*.py", "*.js", "*.ts", "*.c", "*.h", "*.go", "*.rs"]:
            for file_path in self.project_root.rglob(ext):
                if not self._should_index(file_path):
                    continue
                
                try:
                    content = file_path.read_text(encoding='utf-8')
                    lines = content.split('\n')
                    
                    for i, line in enumerate(lines):
                        if re.search(pattern, line, re.IGNORECASE):
                            before = lines[i-1] if i > 0 else ""
                            after = lines[i+1] if i < len(lines)-1 else ""
                            
                            results.append(SearchResult(
                                file=str(file_path),
                                line=i + 1,
                                snippet=line.strip()[:100],
                                match_type="code",
                                score=0.4,
                                context_before=before,
                                context_after=after,
                            ))
                except Exception as e:
                    logger.debug("Pattern search failed in %s: %s", file_path, e)
        
        return results
    
    def _search_imports(self, query: str) -> list[SearchResult]:
        """Search import statements."""
        results: list[SearchResult] = []
        query_lower = query.lower()
        
        import_patterns = {
            ".py": r"^(?:import\s+|from\s+)\s*\S+",
            ".js": r"^(?:import|export)\s+.+",
            ".ts": r"^(?:import|export)\s+.+",
        }
        
        for ext, pattern in import_patterns.items():
            for file_path in self.project_root.rglob(f"*{ext}"):
                if not self._should_index(file_path):
                    continue
                
                try:
                    content = file_path.read_text(encoding='utf-8')
                    lines = content.split('\n')
                    
                    for i, line in enumerate(lines):
                        if re.match(pattern, line.strip()):
                            if query_lower in line.lower():
                                results.append(SearchResult(
                                    file=str(file_path),
                                    line=i + 1,
                                    snippet=line.strip()[:100],
                                    match_type="import",
                                    score=0.5,
                                ))
                except Exception as e:
                    logger.debug("Import search failed in %s: %s", file_path, e)
        
        return results
    
    def _should_index(self, path: Path) -> bool:
        """Check if file should be indexed."""
        skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "build", "dist", ".venv", ".venv", ".tox"}
        return not any(part in skip_dirs for part in path.parts)
    
    def _fuzzy_match(self, query: str, text: str) -> bool:
        """Simple fuzzy matching."""
        if not query or not text:
            return False
        
        # Check if all query chars appear in order
        query_idx = 0
        for char in text:
            if query_idx < len(query) and char == query[query_idx]:
                query_idx += 1
        
        return query_idx == len(query)
    
    def reindex(self) -> None:
        """Force reindexing of the project."""
        self._symbol_index = {}
        self._is_indexed = False
        self.index_project()

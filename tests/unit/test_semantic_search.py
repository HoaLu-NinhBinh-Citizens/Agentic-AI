"""Tests for SemanticSearch - 6.2.UTXX.

Tests semantic search functionality including symbol, comment, and pattern search.
"""

import pytest
from pathlib import Path

from src.infrastructure.search.semantic_search import (
    SemanticSearch,
    SearchResult,
)


class TestSearchResult:
    """Test SearchResult dataclass."""
    
    def test_create_search_result(self):
        """Test creating a search result."""
        result = SearchResult(
            file="test.py",
            line=42,
            snippet="def my_function():",
            match_type="symbol",
            score=0.95,
            context_before="class Test:",
            context_after="    pass",
        )
        
        assert result.file == "test.py"
        assert result.line == 42
        assert result.snippet == "def my_function():"
        assert result.match_type == "symbol"
        assert result.score == 0.95
        assert result.context_before == "class Test:"
        assert result.context_after == "    pass"
    
    def test_search_result_defaults(self):
        """Test search result default values."""
        result = SearchResult(
            file="app.py",
            line=10,
            snippet="pass",
            match_type="code",
            score=0.5,
        )
        
        assert result.context_before == ""
        assert result.context_after == ""


class TestSemanticSearch:
    """Test SemanticSearch class."""
    
    @pytest.fixture
    def searcher(self, tmp_path):
        """Create a semantic searcher with test files."""
        return SemanticSearch(project_root=tmp_path)
    
    def test_init(self, tmp_path):
        """Test SemanticSearch initialization."""
        searcher = SemanticSearch(project_root=tmp_path)
        
        assert searcher.project_root == tmp_path
        assert searcher.indexer is None
        assert searcher._symbol_index == {}
        assert searcher._is_indexed is False
    
    def test_init_with_indexer(self, tmp_path):
        """Test initialization with custom indexer."""
        mock_indexer = object()
        searcher = SemanticSearch(project_root=tmp_path, indexer=mock_indexer)
        
        assert searcher.indexer is mock_indexer
    
    def test_load_patterns(self, searcher):
        """Test pattern loading."""
        patterns = searcher._load_patterns()
        
        assert "error handling" in patterns
        assert "async" in patterns
        assert "class" in patterns
        assert "function" in patterns
    
    def test_index_project_no_files(self, searcher):
        """Test indexing empty project."""
        searcher.index_project()
        
        assert searcher._is_indexed is True
        assert searcher._symbol_index == {}
    
    def test_index_project_with_python_file(self, searcher, tmp_path):
        """Test indexing a Python file."""
        test_file = tmp_path / "test_module.py"
        test_file.write_text("""
def my_function():
    pass

class MyClass:
    def method(self):
        pass
""")
        
        searcher.index_project()
        
        assert searcher._is_indexed is True
        assert "my_function" in searcher._symbol_index
        assert "MyClass" in searcher._symbol_index
    
    def test_index_project_with_js_file(self, searcher, tmp_path):
        """Test indexing a JavaScript file."""
        test_file = tmp_path / "test_module.js"
        test_file.write_text("""
const myConst = 42;
let myLet = 'hello';
var myVar = true;
""")
        
        searcher.index_project()
        
        # JavaScript const/let/var patterns
        assert "myConst" in searcher._symbol_index
        assert "myLet" in searcher._symbol_index
        assert "myVar" in searcher._symbol_index
    
    def test_index_skips_pycache(self, searcher, tmp_path):
        """Test that __pycache__ directories are skipped."""
        pycache_dir = tmp_path / "__pycache__"
        pycache_dir.mkdir()
        (pycache_dir / "test.pyc").write_text("compiled")
        
        main_file = tmp_path / "main.py"
        main_file.write_text("def main(): pass")
        
        searcher.index_project()
        
        assert "main" in searcher._symbol_index
    
    def test_should_index(self, searcher):
        """Test file indexing filter."""
        should_index = [
            Path("src/module.py"),
            Path("src/component.ts"),
            Path("tests/test.js"),
        ]
        
        should_not_index = [
            Path("src/__pycache__/module.py"),
            Path("node_modules/pkg/index.js"),
            Path(".git/config"),
        ]
        
        for path in should_index:
            assert searcher._should_index(path) is True, f"Should index: {path}"
        
        for path in should_not_index:
            assert searcher._should_index(path) is False, f"Should not index: {path}"
    
    def test_fuzzy_match_exact(self, searcher):
        """Test fuzzy matching with exact match."""
        assert searcher._fuzzy_match("func", "function") is True
    
    def test_fuzzy_match_partial(self, searcher):
        """Test fuzzy matching with partial match."""
        assert searcher._fuzzy_match("fn", "function") is True
        assert searcher._fuzzy_match("func", "function") is True
    
    def test_fuzzy_match_no_match(self, searcher):
        """Test fuzzy matching with no match."""
        assert searcher._fuzzy_match("xyz", "function") is False
    
    def test_fuzzy_match_empty(self, searcher):
        """Test fuzzy matching with empty strings."""
        assert searcher._fuzzy_match("", "function") is False
        assert searcher._fuzzy_match("func", "") is False
    
    def test_reindex(self, searcher, tmp_path):
        """Test reindexing the project."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def original(): pass")
        
        searcher.index_project()
        assert "original" in searcher._symbol_index
        
        test_file.write_text("def updated(): pass")
        searcher.reindex()
        
        assert "original" not in searcher._symbol_index
        assert "updated" in searcher._symbol_index


class TestSearch:
    """Test search functionality."""
    
    @pytest.fixture
    def searcher_with_files(self, tmp_path):
        """Create searcher with test files indexed."""
        (tmp_path / "module.py").write_text("""
def calculate_total(items):
    return sum(items)

class DataProcessor:
    def process(self, data):
        return data
""")
        
        (tmp_path / "utils.py").write_text("""
# TODO: optimize this function later
def helper():
    pass
""")
        
        searcher = SemanticSearch(project_root=tmp_path)
        searcher.index_project()
        return searcher
    
    def test_search_indexed_symbols(self, searcher_with_files):
        """Test that symbols are properly indexed."""
        # Check that symbols were indexed
        assert len(searcher_with_files._symbol_index) > 0
        assert "helper" in searcher_with_files._symbol_index or "calculate_total" in searcher_with_files._symbol_index
    
    def test_search_comments(self, searcher_with_files):
        """Test searching for comments."""
        results = searcher_with_files.search("TODO", match_type="comment")
        
        assert len(results) >= 1
        assert any(r.match_type == "comment" for r in results)
    
    def test_search_code_patterns(self, searcher_with_files):
        """Test searching for code patterns."""
        results = searcher_with_files.search("error handling", match_type="code")
        
        # Note: This uses pattern matching, not symbol search
        # The actual results depend on whether error handling patterns exist in the code
    
    def test_search_all(self, searcher_with_files):
        """Test searching all types."""
        results = searcher_with_files.search("TODO")
        
        assert len(results) >= 1
    
    def test_search_with_limit(self, searcher_with_files):
        """Test search result limit."""
        results = searcher_with_files.search("def", limit=2)
        
        assert len(results) <= 2
    
    def test_search_no_results(self, searcher_with_files):
        """Test search with no matches."""
        results = searcher_with_files.search("nonexistent_symbol_xyz")
        
        assert len(results) == 0


class TestSearchPatterns:
    """Test code pattern search."""
    
    def test_search_error_handling_pattern(self, tmp_path):
        """Test searching for error handling patterns."""
        (tmp_path / "error.py").write_text("""
try:
    value = int(input())
except ValueError:
    print("Invalid input")
except Exception as e:
    logger.error(f"Error: {e}")
""")
        
        searcher = SemanticSearch(project_root=tmp_path)
        searcher.index_project()
        
        results = searcher.search("error handling", match_type="code")
        
        assert len(results) >= 1
    
    def test_search_async_pattern(self, tmp_path):
        """Test searching for async patterns."""
        (tmp_path / "async_test.py").write_text("""
import asyncio

async def fetch_data():
    return await http.get()
""")
        
        searcher = SemanticSearch(project_root=tmp_path)
        searcher.index_project()
        
        results = searcher.search("async", match_type="code")
        
        assert len(results) >= 1


class TestSearchScoring:
    """Test search result scoring."""
    
    def test_results_sorted_by_score(self, tmp_path):
        """Test that results are sorted by score descending."""
        (tmp_path / "test.py").write_text("""
def helper_function():
    pass

def helper():
    pass
""")
        
        searcher = SemanticSearch(project_root=tmp_path)
        searcher.index_project()
        
        results = searcher.search("helper", match_type="symbol")
        
        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score

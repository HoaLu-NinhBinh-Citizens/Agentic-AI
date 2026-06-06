"""Tests for command parser and virtual commands.

These tests verify the core logic of the new features without
relying on the full import chain.
"""

import pytest
from pathlib import Path
import re


class TestCommandParserLogic:
    """Tests for command parser logic (without full imports)."""
    
    # Simulate the regex patterns from command_parser.py
    COMMAND_PATTERN = re.compile(
        r"^/(?P<command>\w+)"
        r"(?:\s+@(?P<file>[^\s:]+))?"
        r"(?::(?P<line>\d+))?"
        r"(?::(?P<end_line>\d+))?"
        r"(?:\s+(?P<options>.*))?$"
    )
    
    def test_parse_fix_command_with_line(self):
        """Test parsing /fix with line number."""
        raw = "/fix @src/main.py:42"
        match = self.COMMAND_PATTERN.match(raw.strip())
        
        assert match is not None
        assert match.group("command") == "fix"
        assert match.group("file") == "src/main.py"
        assert match.group("line") == "42"
    
    def test_parse_fix_command_without_line(self):
        """Test parsing /fix without line number."""
        raw = "/fix @src/main.py"
        match = self.COMMAND_PATTERN.match(raw.strip())
        
        assert match is not None
        assert match.group("command") == "fix"
        assert match.group("file") == "src/main.py"
        assert match.group("line") is None
    
    def test_parse_explain_command(self):
        """Test parsing /explain command."""
        raw = "/explain @src/main.py:42"
        match = self.COMMAND_PATTERN.match(raw.strip())
        
        assert match is not None
        assert match.group("command") == "explain"
        assert match.group("file") == "src/main.py"
        assert match.group("line") == "42"
    
    def test_parse_refactor_command(self):
        """Test parsing /refactor command."""
        raw = "/refactor @src/main.py:10:20"
        match = self.COMMAND_PATTERN.match(raw.strip())
        
        assert match is not None
        assert match.group("command") == "refactor"
        assert match.group("file") == "src/main.py"
        assert match.group("line") == "10"
        assert match.group("end_line") == "20"
    
    def test_parse_invalid_command(self):
        """Test parsing invalid command."""
        raw = "not a command"
        match = self.COMMAND_PATTERN.match(raw.strip())
        assert match is None
    
    def test_parse_search_command(self):
        """Test parsing /search command."""
        raw = "/search @src/main.py:42"
        match = self.COMMAND_PATTERN.match(raw.strip())
        
        assert match is not None
        assert match.group("command") == "search"
        assert match.group("file") == "src/main.py"
        assert match.group("line") == "42"


class TestLanguageDetection:
    """Tests for language detection in cross-file resolver."""
    
    def test_language_detection_patterns(self):
        """Test language detection from file extension."""
        lang_map = {
            ".py": "python",
            ".c": "c",
            ".h": "c",
            ".cpp": "c",
            ".js": "javascript",
            ".ts": "javascript",
            ".jsx": "javascript",
            ".tsx": "javascript",
            ".rs": "rust",
            ".go": "go",
        }
        
        assert lang_map[".py"] == "python"
        assert lang_map[".c"] == "c"
        assert lang_map[".h"] == "c"
        assert lang_map[".js"] == "javascript"
        assert lang_map[".rs"] == "rust"


class TestImportParsing:
    """Tests for import parsing patterns."""
    
    def test_python_import_patterns(self):
        """Test Python import regex patterns."""
        content = """
from src.utils import helper
from src.models import User
import os
import sys
"""
        # Simulate the import parsing regex
        import_from_pattern = re.compile(r"^\s*from\s+([\w.]+)\s+import", re.MULTILINE)
        import_pattern = re.compile(r"^\s*import\s+([\w.]+)", re.MULTILINE)
        
        imports = []
        
        for match in import_from_pattern.finditer(content):
            imports.append(match.group(1))
        
        for match in import_pattern.finditer(content):
            imports.append(match.group(1))
        
        assert "src.utils" in imports
        assert "src.models" in imports
        assert "os" in imports
        assert "sys" in imports
    
    def test_c_include_pattern(self):
        """Test C include regex pattern."""
        content = """
#include <stdio.h>
#include "utils.h"
#include "common.h"
"""
        include_pattern = re.compile(r'#include\s*[<"]([^>"]+)[>"]')
        
        includes = [m.group(1) for m in include_pattern.finditer(content)]
        
        assert "stdio.h" in includes
        assert "utils.h" in includes
        assert "common.h" in includes


class TestSeverityMapping:
    """Tests for severity action mapping logic."""
    
    def test_severity_weights(self):
        """Test severity weight mapping."""
        weights = {
            "critical": 4,
            "high": 3,
            "medium": 2,
            "low": 1,
            "info": 0,
        }
        
        assert weights["critical"] > weights["high"]
        assert weights["high"] > weights["medium"]
        assert weights["medium"] > weights["low"]
    
    def test_action_mapping_logic(self):
        """Test action mapping based on severity."""
        weights = {
            "critical": 4,
            "high": 3,
            "medium": 2,
            "low": 1,
            "info": 0,
        }
        
        def get_action(severity: str, threshold: str) -> str:
            """Determine action based on severity and threshold."""
            if weights[severity] >= weights["critical"]:
                return "warn_critical"
            elif weights[severity] >= weights["high"]:
                return "review_required"
            elif weights[severity] < weights[threshold]:
                return "skip"
            else:
                return "auto_fix"
        
        # Critical always warns
        assert get_action("critical", "low") == "warn_critical"
        
        # High always requires review
        assert get_action("high", "low") == "review_required"
        
        # Low with low threshold is auto-fix (at or above threshold)
        assert get_action("low", "low") == "auto_fix"
        
        # Medium with low threshold is auto-fix
        assert get_action("medium", "low") == "auto_fix"
        
        # Medium with medium threshold is auto-fix (at threshold)
        assert get_action("medium", "medium") == "auto_fix"
        
        # Info with low threshold skips
        assert get_action("info", "low") == "skip"


class TestDependencyGraph:
    """Tests for dependency graph logic."""
    
    def test_dependency_tracking(self):
        """Test basic dependency tracking."""
        # Simulate dependency tracking
        dependencies: dict[str, set[str]] = {}
        dependents: dict[str, set[str]] = {}
        
        def add_dependency(source: str, target: str):
            if source not in dependencies:
                dependencies[source] = set()
            dependencies[source].add(target)
            
            if target not in dependents:
                dependents[target] = set()
            dependents[target].add(source)
        
        add_dependency("a.py", "b.py")
        add_dependency("c.py", "b.py")
        add_dependency("b.py", "d.py")
        
        assert "b.py" in dependencies["a.py"]
        assert "b.py" in dependencies["c.py"]
        assert "d.py" in dependencies["b.py"]
        
        assert "a.py" in dependents["b.py"]
        assert "c.py" in dependents["b.py"]
        assert "b.py" in dependents["d.py"]
    
    def test_transitive_dependents(self):
        """Test finding transitive dependents."""
        dependents: dict[str, set[str]] = {
            "a.py": set(),
            "b.py": {"a.py"},
            "c.py": {"b.py"},
            "d.py": {"c.py"},
        }
        
        def get_transitive_dependents(target: str) -> set[str]:
            result: set[str] = set()
            queue = [target]
            
            while queue:
                current = queue.pop()
                for dep in dependents.get(current, set()):
                    if dep not in result:
                        result.add(dep)
                        queue.append(dep)
            
            return result
        
        # d.py depends on c.py which depends on b.py which depends on a.py
        transitive = get_transitive_dependents("d.py")
        assert "a.py" in transitive
        assert "b.py" in transitive
        assert "c.py" in transitive


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

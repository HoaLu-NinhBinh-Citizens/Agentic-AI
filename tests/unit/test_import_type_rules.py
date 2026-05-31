"""Tests for import, type, and naming rules."""

import pytest
from src.infrastructure.analysis.rules.imports.unused_import import UnusedImportRule
from src.infrastructure.analysis.rules.imports.circular_import import CircularImportRule
from src.infrastructure.analysis.rules.types.any_type import AnyTypeRule
from src.infrastructure.analysis.rules.naming.inconsistent_naming import InconsistentNamingRule


class TestUnusedImportRule:
    """Tests for unused import detection."""

    def test_detects_unused_import(self):
        """Should detect unused import."""
        rule = UnusedImportRule()
        code = '''import os
import sys
def hello():
    print("hello")'''
        findings = rule.detect(code, "test.py")
        assert len(findings) >= 1
        assert findings[0]["rule_id"] == "IMP001"

    def test_allows_used_import(self):
        """Should not flag used imports."""
        rule = UnusedImportRule()
        code = '''import os
def get_path():
    return os.path.join("a", "b")'''
        findings = rule.detect(code, "test.py")
        assert len(findings) == 0


class TestCircularImportRule:
    """Tests for circular import detection."""

    def test_detects_self_import_in_init(self):
        """Should detect import from self in __init__.py."""
        rule = CircularImportRule()
        code = '''from . import mymodule'''
        findings = rule.detect(code, "mymodule/__init__.py")
        assert len(findings) >= 1
        assert findings[0]["rule_id"] == "IMP002"


class TestAnyTypeRule:
    """Tests for Any type detection."""

    def test_detects_any_type(self):
        """Should detect Any type usage."""
        rule = AnyTypeRule()
        code = '''from typing import Any
def func(x: Any) -> Any:
    return x'''
        findings = rule.detect(code, "test.py")
        assert len(findings) >= 1
        assert findings[0]["rule_id"] == "TYPE001"


class TestInconsistentNamingRule:
    """Tests for inconsistent naming detection."""

    def test_detects_wrong_function_name(self):
        """Should detect function not following snake_case."""
        rule = InconsistentNamingRule()
        code = '''def WrongFunctionName():
    pass'''
        findings = rule.detect(code, "test.py")
        assert len(findings) >= 1
        assert findings[0]["rule_id"] == "NAME001"

    def test_detects_wrong_class_name(self):
        """Should detect class not following PascalCase."""
        rule = InconsistentNamingRule()
        code = '''class wrong_class_name:
    pass'''
        findings = rule.detect(code, "test.py")
        assert len(findings) >= 1

    def test_allows_correct_naming(self):
        """Should not flag correct naming."""
        rule = InconsistentNamingRule()
        code = '''def correct_function_name():
    pass
class CorrectClassName:
    pass'''
        findings = rule.detect(code, "test.py")
        assert len(findings) == 0

"""Tests for quality rules."""

import pytest
from src.infrastructure.analysis.rules.quality.cognitive_complexity import CognitiveComplexityRule
from src.infrastructure.analysis.rules.quality.empty_except import EmptyExceptRule
from src.infrastructure.analysis.rules.quality.broad_except import BroadExceptRule
from src.infrastructure.analysis.rules.quality.global_statement import GlobalVariableRule
from src.infrastructure.analysis.rules.quality.commented_code import CommentedCodeRule
from src.infrastructure.analysis.rules.quality.deprecated_import import DeprecatedImportRule


class TestCognitiveComplexityRule:
    """Tests for cognitive complexity detection."""

    def test_detects_high_complexity(self):
        """Should detect high cognitive complexity."""
        rule = CognitiveComplexityRule(threshold=2)
        code = '''def complex_function(a, b, c):
    if a:
        if b:
            if c:
                print(a)'''
        findings = rule.detect(code, "test.py")
        assert len(findings) >= 1
        assert findings[0]["rule_id"] == "QUAL001"

    def test_allows_low_complexity(self):
        """Should not flag low complexity functions."""
        rule = CognitiveComplexityRule(threshold=15)
        code = '''def simple_function(a, b):
    if a:
        return b
    return None'''
        findings = rule.detect(code, "test.py")
        assert len(findings) == 0


class TestEmptyExceptRule:
    """Tests for empty except block detection."""

    def test_detects_empty_except(self):
        """Should detect empty except block."""
        rule = EmptyExceptRule()
        code = '''try:
    dangerous_operation()
except:
    pass'''
        findings = rule.detect(code, "test.py")
        assert len(findings) >= 1
        assert findings[0]["rule_id"] == "QUAL002"

    def test_allows_proper_except(self):
        """Should not flag except with logging."""
        rule = EmptyExceptRule()
        code = '''try:
    dangerous_operation()
except Exception as e:
    print(e)'''
        findings = rule.detect(code, "test.py")
        assert len(findings) == 0


class TestBroadExceptRule:
    """Tests for broad except detection."""

    def test_detects_bare_except(self):
        """Should detect bare except clause."""
        rule = BroadExceptRule()
        code = '''try:
    dangerous_operation()
except:
    print("error")'''
        findings = rule.detect(code, "test.py")
        assert len(findings) >= 1
        assert findings[0]["rule_id"] == "QUAL003"

    def test_detects_except_exception(self):
        """Should detect except Exception clause."""
        rule = BroadExceptRule()
        code = '''try:
    dangerous_operation()
except Exception:
    print("error")'''
        findings = rule.detect(code, "test.py")
        assert len(findings) >= 1


class TestGlobalVariableRule:
    """Tests for global variable detection."""

    def test_detects_global_statement(self):
        """Should detect global statement."""
        rule = GlobalVariableRule()
        code = '''counter = 0
def increment():
    global counter
    counter += 1'''
        findings = rule.detect(code, "test.py")
        assert len(findings) >= 1
        assert findings[0]["rule_id"] == "QUAL004"


class TestCommentedCodeRule:
    """Tests for commented code detection."""

    def test_detects_commented_function(self):
        """Should detect commented function."""
        rule = CommentedCodeRule()
        code = '''# def old_function():
#     pass
def new_function():
    pass'''
        findings = rule.detect(code, "test.py")
        assert len(findings) >= 1
        assert findings[0]["rule_id"] == "QUAL005"


class TestDeprecatedImportRule:
    """Tests for deprecated import detection."""

    def test_detects_imp_import(self):
        """Should detect imp module import."""
        rule = DeprecatedImportRule()
        code = '''import imp'''
        findings = rule.detect(code, "test.py")
        assert len(findings) >= 1
        assert findings[0]["rule_id"] == "QUAL006"

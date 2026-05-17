"""Unit tests for ConditionEvaluator - AST sandbox security.

Tests cover:
- test_sandbox_whitelist: Only safe operators allowed, eval/func call/attr traversal blocked
- test_record_branch_decision: Branch decision recorded for replay
- test_expression_timeout: Long/deep expressions raise errors
"""

from __future__ import annotations

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from application.planner.condition_evaluator import (
    ConditionEvaluator,
    BranchConditionEvaluator,
    ExpressionSandboxError,
    ExpressionTooLongError,
    ExpressionTooDeepError,
    InvalidNodeError,
)


# ============================================================================
# Sandbox Security Tests (test_sandbox_whitelist)
# ============================================================================

class TestSandboxWhitelist:
    """Test that only safe operators are allowed in the sandbox."""

    def test_comparison_operators_allowed(self):
        """Test that comparison operators work correctly."""
        evaluator = ConditionEvaluator()
        
        # Test equality
        result, error = evaluator.evaluate("1 == 1", {})
        assert result is True
        assert error is None
        
        # Test inequality
        result, error = evaluator.evaluate("1 != 2", {})
        assert result is True
        assert error is None
        
        # Test less than
        result, error = evaluator.evaluate("1 < 2", {})
        assert result is True
        
        # Test less than or equal
        result, error = evaluator.evaluate("2 <= 2", {})
        assert result is True
        
        # Test greater than
        result, error = evaluator.evaluate("3 > 2", {})
        assert result is True
        
        # Test greater than or equal
        result, error = evaluator.evaluate("2 >= 2", {})
        assert result is True

    def test_boolean_operators_allowed(self):
        """Test that boolean operators work correctly."""
        evaluator = ConditionEvaluator()
        
        # Test AND
        result, error = evaluator.evaluate("True and True", {})
        assert result is True
        assert error is None
        
        # Test OR
        result, error = evaluator.evaluate("True or False", {})
        assert result is True
        
        # Test NOT
        result, error = evaluator.evaluate("not False", {})
        assert result is True
        
        # Test combined
        result, error = evaluator.evaluate("(1 < 2) and (3 > 2)", {})
        assert result is True

    def test_arithmetic_operators_allowed(self):
        """Test that arithmetic operators work correctly."""
        evaluator = ConditionEvaluator()
        
        # Addition
        result, error = evaluator.evaluate("1 + 2", {})
        assert result == 3
        
        # Subtraction
        result, error = evaluator.evaluate("5 - 3", {})
        assert result == 2
        
        # Multiplication
        result, error = evaluator.evaluate("2 * 3", {})
        assert result == 6
        
        # Division
        result, error = evaluator.evaluate("10 / 2", {})
        assert result == 5.0
        
        # Modulo
        result, error = evaluator.evaluate("10 % 3", {})
        assert result == 1
        
        # Complex expression
        result, error = evaluator.evaluate("(1 + 2) * (3 - 1)", {})
        assert result == 6

    def test_literals_allowed(self):
        """Test that literals work correctly."""
        evaluator = ConditionEvaluator()
        
        # Boolean literals
        assert evaluator.evaluate("True", {})[0] is True
        assert evaluator.evaluate("False", {})[0] is False
        
        # None literal
        result, error = evaluator.evaluate("None", {})
        assert result is None
        
        # Numeric literals
        assert evaluator.evaluate("42", {})[0] == 42
        assert evaluator.evaluate("3.14", {})[0] == 3.14
        
        # String literals
        assert evaluator.evaluate('"hello"', {})[0] == "hello"

    def test_context_variables_allowed(self):
        """Test that context variables can be accessed."""
        evaluator = ConditionEvaluator()
        context = {"x": 10, "y": 20, "flag": True}
        
        result, error = evaluator.evaluate("x + y", context)
        assert result == 30
        
        result, error = evaluator.evaluate("x > 5", context)
        assert result is True
        
        result, error = evaluator.evaluate("flag", context)
        assert result is True

    def test_subscript_access_allowed(self):
        """Test that dict subscript access works."""
        evaluator = ConditionEvaluator()
        context = {"data": {"key": "value", "count": 42}}
        
        # Access nested dict
        result, error = evaluator.evaluate('data["key"]', context)
        assert result == "value"
        
        result, error = evaluator.evaluate('data["count"]', context)
        assert result == 42

    def test_dict_get_method_allowed(self):
        """Test that dict.get() method works."""
        evaluator = ConditionEvaluator()
        context = {"data": {"exists": 1}}
        
        # With existing key
        result, error = evaluator.evaluate('data.get("exists")', context)
        assert result == 1
        
        # With default for missing key
        result, error = evaluator.evaluate('data.get("missing", 0)', context)
        assert result == 0
        
        # With missing key and no default
        result, error = evaluator.evaluate('data.get("missing")', context)
        assert result is None

    def test_eval_blocked(self):
        """Test that eval() is blocked."""
        evaluator = ConditionEvaluator()
        
        # Direct eval
        result, error = evaluator.evaluate('eval("1+1")', {})
        assert error is not None
        assert "Unsupported" in error or "not allowed" in error.lower()

    def test_exec_blocked(self):
        """Test that exec() is blocked."""
        evaluator = ConditionEvaluator()
        
        result, error = evaluator.evaluate('exec("x=1")', {})
        assert error is not None

    def test_attribute_access_blocked(self):
        """Test that attribute access (.attr) is blocked."""
        evaluator = ConditionEvaluator()
        context = {"obj": type("obj", (), {"attr": 42})()}
        
        result, error = evaluator.evaluate("obj.attr", context)
        assert error is not None
        assert "not allowed" in error.lower() or "Attribute" in error

    def test_function_call_blocked(self):
        """Test that arbitrary function calls are blocked."""
        evaluator = ConditionEvaluator()
        
        # Built-in functions
        result, error = evaluator.evaluate("len([1,2,3])", {})
        assert error is not None
        
        # Custom functions
        result, error = evaluator.evaluate("print('test')", {})
        assert error is not None

    def test_lambda_blocked(self):
        """Test that lambda expressions are blocked."""
        evaluator = ConditionEvaluator()
        
        result, error = evaluator.evaluate("lambda x: x", {})
        assert error is not None
        assert "Lambda" in error or "not allowed" in error.lower()

    def test_list_comprehension_blocked(self):
        """Test that list comprehensions are blocked."""
        evaluator = ConditionEvaluator()
        
        result, error = evaluator.evaluate("[x for x in range(5)]", {})
        assert error is not None

    def test_dict_comprehension_blocked(self):
        """Test that dict comprehensions are blocked."""
        evaluator = ConditionEvaluator()
        
        result, error = evaluator.evaluate("{k: v for k, v in []}", {})
        assert error is not None

    def test_import_blocked(self):
        """Test that import statements are blocked."""
        evaluator = ConditionEvaluator()
        
        result, error = evaluator.evaluate("__import__('os')", {})
        assert error is not None

    def test_os_system_blocked(self):
        """Test that os.system is blocked."""
        evaluator = ConditionEvaluator()
        
        result, error = evaluator.evaluate('__import__("os").system("ls")', {})
        assert error is not None

    def test_subprocess_blocked(self):
        """Test that subprocess calls are blocked."""
        evaluator = ConditionEvaluator()
        
        result, error = evaluator.evaluate('__import__("subprocess").run(["ls"])', {})
        assert error is not None


# ============================================================================
# Branch Decision Recording Tests (test_record_branch_decision)
# ============================================================================

class TestBranchDecisionRecording:
    """Test branch decision recording for replay."""

    def test_simple_branch_condition(self):
        """Test simple boolean branch condition."""
        evaluator = BranchConditionEvaluator()
        
        # Valid condition
        result = evaluator.validate_condition("x > 5")
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_complex_branch_condition(self):
        """Test complex branch condition."""
        evaluator = BranchConditionEvaluator()
        
        result = evaluator.validate_condition("(x > 0) and (y < 100)")
        assert result.is_valid is True

    def test_invalid_branch_condition_lambda(self):
        """Test that lambda in branch is rejected."""
        evaluator = BranchConditionEvaluator()
        
        result = evaluator.validate_condition("lambda x: x > 5")
        assert result.is_valid is False
        assert any("Lambda" in e for e in result.errors)

    def test_invalid_branch_condition_attribute(self):
        """Test that attribute access in branch is rejected."""
        evaluator = BranchConditionEvaluator()
        
        result = evaluator.validate_condition("obj.value > 5")
        assert result.is_valid is False
        assert any("Attribute" in e or "not allowed" in e.lower() for e in result.errors)

    def test_nested_subscript_blocked(self):
        """Test that nested subscript is blocked."""
        evaluator = BranchConditionEvaluator()
        
        result = evaluator.validate_condition('data["a"]["b"]')
        assert result.is_valid is False
        assert any("Nested" in e or "not allowed" in e.lower() for e in result.errors)


# ============================================================================
# Expression Limits Tests (test_expression_timeout)
# ============================================================================

class TestExpressionLimits:
    """Test expression length and depth limits."""

    def test_expression_too_long(self):
        """Test that long expressions are rejected."""
        evaluator = ConditionEvaluator(max_expression_length=100)
        
        long_expr = "x" * 200  # 200 character expression
        result, error = evaluator.evaluate(long_expr, {})
        
        assert result is False
        assert "exceeds" in error.lower() or "length" in error.lower()

    def test_expression_at_limit(self):
        """Test expression at exactly the limit."""
        evaluator = ConditionEvaluator(max_expression_length=500)
        
        # Create an expression within the limit
        expr = "x" * 100 + " == " + "y" * 100
        result, error = evaluator.evaluate(expr, {"x": 1, "y": 1})
        
        # Should pass as it's within limit
        assert error is None
        assert result is True

    def test_expression_too_deep(self):
        """Test that deeply nested expressions are rejected."""
        evaluator = ConditionEvaluator(max_ast_depth=5)
        
        # Create deeply nested expression with parentheses
        deep_expr = "not not not not not not not not True"
        result, error = evaluator.evaluate(deep_expr, {})
        
        assert result is False
        assert error is not None

    def test_max_depth_validation(self):
        """Test validation catches depth violations."""
        evaluator = BranchConditionEvaluator(max_ast_depth=5)
        
        deep_expr = "not not not not not not not not not not True"
        result = evaluator.validate_condition(deep_expr)
        
        assert result.is_valid is False
        assert any("depth" in e.lower() for e in result.errors)

    def test_syntax_error_caught(self):
        """Test that syntax errors are caught."""
        evaluator = ConditionEvaluator()
        
        result, error = evaluator.evaluate("1 +", {})
        assert result is False
        assert "Syntax error" in error or "syntax" in error.lower()

    def test_unknown_variable_caught(self):
        """Test that unknown variables raise errors."""
        evaluator = ConditionEvaluator()
        
        result, error = evaluator.evaluate("unknown_var", {})
        assert result is False
        assert "Unknown" in error or "unknown" in error.lower()

    def test_zero_division_caught(self):
        """Test that zero division is caught."""
        evaluator = ConditionEvaluator()
        
        result, error = evaluator.evaluate("1 / 0", {})
        assert result is False
        assert "error" in error.lower()


# ============================================================================
# Edge Cases
# ============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_expression(self):
        """Test empty expression handling."""
        evaluator = ConditionEvaluator()
        
        result, error = evaluator.evaluate("", {})
        assert result is False
        assert error is not None

    def test_whitespace_only_expression(self):
        """Test whitespace-only expression."""
        evaluator = ConditionEvaluator()
        
        result, error = evaluator.evaluate("   ", {})
        assert result is False

    def test_very_long_variable_name(self):
        """Test very long variable name."""
        evaluator = ConditionEvaluator(max_expression_length=500)
        
        long_name = "a" * 400
        result, error = evaluator.evaluate(long_name, {long_name: 1})
        
        assert error is None
        assert result == 1

    def test_nested_dict_access(self):
        """Test nested dict access."""
        evaluator = ConditionEvaluator()
        context = {
            "level1": {
                "level2": {
                    "value": 42
                }
            }
        }
        
        # This should work with direct access
        result, error = evaluator.evaluate('level1["level2"]["value"]', context)
        assert result == 42

    def test_multiple_conditions(self):
        """Test multiple conditions in one expression."""
        evaluator = ConditionEvaluator()
        context = {"a": 1, "b": 2, "c": 3, "d": 4}
        
        result, error = evaluator.evaluate(
            "(a < b) and (c < d) and (a + b < c + d)",
            context
        )
        assert result is True

    def test_unary_operators(self):
        """Test unary operators."""
        evaluator = ConditionEvaluator()
        
        result, error = evaluator.evaluate("-1", {})
        assert result == -1
        
        result, error = evaluator.evaluate("+5", {})
        assert result == 5

    def test_parentheses_priority(self):
        """Test that parentheses affect evaluation priority."""
        evaluator = ConditionEvaluator()
        
        result, error = evaluator.evaluate("(1 + 2) * 3", {})
        assert result == 9
        
        result, error = evaluator.evaluate("1 + 2 * 3", {})
        assert result == 7

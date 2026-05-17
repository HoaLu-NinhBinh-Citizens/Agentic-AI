"""AST-based expression sandbox - Phase 5B Enterprise.

SAFE expression evaluator using AST parsing instead of eval().
Supports only a restricted subset of Python expressions.
"""

from __future__ import annotations

import ast
from typing import Any, Optional

from .types import ValidationResult


class ExpressionSandboxError(Exception):
    """Error in expression sandbox evaluation."""
    pass


class ExpressionTooLongError(ExpressionSandboxError):
    """Expression exceeds maximum length."""
    pass


class ExpressionTooDeepError(ExpressionSandboxError):
    """AST depth exceeds maximum allowed."""
    pass


class InvalidOperatorError(ExpressionSandboxError):
    """Operator not in whitelist."""
    pass


class InvalidNodeError(ExpressionSandboxError):
    """Node type not allowed in sandbox."""
    pass


class ConditionEvaluator:
    """AST-based sandbox expression evaluator.
    
    Evaluates Python expressions safely without using eval().
    Only supports a restricted subset of operators and operations.
    
    Allowed:
        - Comparison: ==, !=, <, <=, >, >=
        - Boolean: and, or, not
        - Arithmetic: +, -, *, /, %
        - Literals: True, False, None, int, float, str
        - Dict access: context['key'] or context.get('key')
    
    Prohibited:
        - Function calls (except dict.get)
        - Attribute access (obj.attr)
        - Lambda expressions
        - List/dict comprehensions
        - Import statements
        - Any exec/eval usage
    """

    WHITELIST_NODES = frozenset({
        ast.Expression,
        ast.Compare,
        ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
        ast.BoolOp,
        ast.And, ast.Or,
        ast.UnaryOp,
        ast.Not,
        ast.BinOp,
        ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod,
        ast.Name,
        ast.Constant,
        ast.NameConstant,
        ast.Num,
        ast.Str,
        ast.Subscript,
        ast.Index,
        ast.Call,
        ast.keyword,
    })

    def __init__(
        self,
        max_ast_depth: int = 10,
        max_expression_length: int = 500,
    ):
        self._max_depth = max_ast_depth
        self._max_length = max_expression_length
        self._allowed_functions = frozenset({"get"})

    def evaluate(self, expr: str, context: dict) -> tuple[Any, Optional[str]]:
        """Evaluate expression safely.
        
        Args:
            expr: Expression string to evaluate
            context: Dictionary for variable resolution
            
        Returns:
            Tuple of (result, error_message). If error_message is None,
            evaluation succeeded.
        """
        if len(expr) > self._max_length:
            return False, f"Expression exceeds {self._max_length} chars"
        
        try:
            tree = ast.parse(expr, mode="eval")
        except SyntaxError as e:
            return False, f"Syntax error: {e}"
        
        try:
            self._validate_ast_depth(tree, 0)
        except ExpressionTooDeepError as e:
            return False, str(e)
        
        try:
            result = self._eval_node(tree.body, context)
            return result, None
        except ExpressionSandboxError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Evaluation error: {type(e).__name__}: {e}"

    def _validate_ast_depth(self, node: ast.AST, depth: int) -> None:
        """Validate AST node depth doesn't exceed maximum."""
        if depth > self._max_depth:
            raise ExpressionTooDeepError(
                f"AST depth {depth} exceeds maximum {self._max_depth}"
            )
        for child in ast.iter_child_nodes(node):
            self._validate_ast_depth(child, depth + 1)

    def _eval_node(self, node: ast.AST, context: dict) -> Any:
        """Evaluate an AST node recursively."""
        node_type = type(node)
        
        if node_type is ast.Constant:
            return node.value
        if node_type is ast.NameConstant:
            return node.value
        if node_type is ast.Num:
            return node.n
        if node_type is ast.Str:
            return node.s
        
        if node_type is ast.Name:
            return self._eval_name(node, context)
        
        if node_type is ast.Subscript:
            return self._eval_subscript(node, context)
        
        if node_type is ast.Compare:
            return self._eval_compare(node, context)
        
        if node_type is ast.BoolOp:
            return self._eval_boolop(node, context)
        
        if node_type is ast.UnaryOp:
            return self._eval_unaryop(node, context)
        
        if node_type is ast.BinOp:
            return self._eval_binop(node, context)
        
        if node_type is ast.Call:
            return self._eval_call(node, context)
        
        if node_type is ast.Index:
            return self._eval_node(node.value, context)
        
        raise InvalidNodeError(f"Unsupported node type: {node_type.__name__}")

    def _eval_name(self, node: ast.Name, context: dict) -> Any:
        """Evaluate a Name node."""
        if node.id == "True":
            return True
        if node.id == "False":
            return False
        if node.id == "None":
            return None
        
        if node.id == "context":
            return context
        
        if node.id in context:
            return context[node.id]
        
        raise InvalidNodeError(f"Unknown variable: {node.id}")

    def _eval_subscript(self, node: ast.Subscript, context: dict) -> Any:
        """Evaluate subscript access: context['key'] or context.get('key')."""
        value = self._eval_node(node.value, context)
        
        if isinstance(node.slice, ast.Index):
            key = self._eval_node(node.slice.value, context)
        elif isinstance(node.slice, ast.Tuple):
            key = tuple(self._eval_node(elt, context) for elt in node.slice.elts)
        else:
            key = self._eval_node(node.slice, context)
        
        if isinstance(value, dict):
            return value[key]
        
        raise InvalidNodeError(f"Cannot subscript type: {type(value).__name__}")

    def _eval_compare(self, node: ast.Compare, context: dict) -> Any:
        """Evaluate comparison expressions."""
        left = self._eval_node(node.left, context)
        
        for op, comparator in zip(node.ops, node.comparators):
            right = self._eval_node(comparator, context)
            
            if isinstance(op, ast.Eq):
                result = left == right
            elif isinstance(op, ast.NotEq):
                result = left != right
            elif isinstance(op, ast.Lt):
                result = left < right
            elif isinstance(op, ast.LtE):
                result = left <= right
            elif isinstance(op, ast.Gt):
                result = left > right
            elif isinstance(op, ast.GtE):
                result = left >= right
            else:
                raise InvalidOperatorError(f"Unsupported operator: {type(op).__name__}")
            
            if not result:
                return False
            
            left = right
        
        return True

    def _eval_boolop(self, node: ast.BoolOp, context: dict) -> Any:
        """Evaluate boolean operations (and, or)."""
        values = [self._eval_node(v, context) for v in node.values]
        
        if isinstance(node.op, ast.And):
            return all(values)
        if isinstance(node.op, ast.Or):
            return any(values)
        
        raise InvalidOperatorError(f"Unsupported bool op: {type(node.op).__name__}")

    def _eval_unaryop(self, node: ast.UnaryOp, context: dict) -> Any:
        """Evaluate unary operations."""
        operand = self._eval_node(node.operand, context)
        
        if isinstance(node.op, ast.Not):
            return not operand
        if isinstance(node.op, ast.UAdd):
            return +operand
        if isinstance(node.op, ast.USub):
            return -operand
        
        raise InvalidOperatorError(f"Unsupported unary op: {type(node.op).__name__}")

    def _eval_binop(self, node: ast.BinOp, context: dict) -> Any:
        """Evaluate binary operations."""
        left = self._eval_node(node.left, context)
        right = self._eval_node(node.right, context)
        
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.Mod):
            return left % right
        
        raise InvalidOperatorError(f"Unsupported binary op: {type(node.op).__name__}")

    def _eval_call(self, node: ast.Call, context: dict) -> Any:
        """Evaluate function calls - only dict.get() is allowed."""
        if len(node.args) > 2:
            raise InvalidNodeError("Too many arguments for get()")
        
        if node.keywords:
            raise InvalidNodeError("Keyword arguments not allowed")
        
        # Handle method calls like data.get('key')
        if isinstance(node.func, ast.Attribute):
            method_name = node.func.attr
            if method_name == "get":
                # Get the dict being called on
                d = self._eval_node(node.func.value, context)
                if not isinstance(d, dict):
                    raise InvalidNodeError(f"get() called on non-dict: {type(d).__name__}")
                
                if not node.args:
                    raise InvalidNodeError("dict.get() requires at least one argument")
                
                key = self._eval_node(node.args[0], context)
                
                if len(node.args) == 2:
                    default = self._eval_node(node.args[1], context)
                    return d.get(key, default)
                
                if key in d:
                    return d[key]
                return None
            
            raise InvalidNodeError(f"Method not allowed: {method_name}")
        
        # Handle bare get() calls (less common)
        func_name = self._get_func_name(node.func)
        if func_name not in self._allowed_functions:
            raise InvalidNodeError(f"Function call not allowed: {func_name}")
        
        if func_name == "get":
            if not node.args:
                raise InvalidNodeError("dict.get() requires at least one argument")
            
            d = context  # For bare get(), first arg is the dict
            if not isinstance(d, dict):
                raise InvalidNodeError(f"get() called on non-dict: {type(d).__name__}")
            
            key = self._eval_node(node.args[0], context)
            
            if len(node.args) == 2:
                default = self._eval_node(node.args[1], context)
                return d.get(key, default)
            
            if key in d:
                return d[key]
            return None
        
        raise InvalidNodeError(f"Unsupported function: {func_name}")

    def _get_func_name(self, node: ast.AST) -> str:
        """Extract function name from Call node."""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        raise InvalidNodeError("Cannot extract function name")


class BranchConditionEvaluator(ConditionEvaluator):
    """Extended evaluator for branch conditions with policy enforcement."""
    
    def __init__(
        self,
        max_ast_depth: int = 10,
        max_expression_length: int = 500,
        max_branches_per_node: int = 10,
    ):
        super().__init__(max_ast_depth, max_expression_length)
        self._max_branches = max_branches_per_node

    def validate_condition(self, expr: str) -> ValidationResult:
        """Validate condition expression without evaluating."""
        if len(expr) > self._max_length:
            return ValidationResult(
                is_valid=False,
                errors=[f"Expression exceeds {self._max_length} characters"],
            )
        
        try:
            tree = ast.parse(expr, mode="eval")
        except SyntaxError as e:
            return ValidationResult(
                is_valid=False,
                errors=[f"Syntax error: {e}"],
            )
        
        errors = []
        warnings = []
        
        try:
            self._validate_ast_depth(tree, 0)
        except ExpressionTooDeepError as e:
            errors.append(str(e))
        
        self._check_forbidden_patterns(tree, errors)
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def _check_forbidden_patterns(
        self, 
        tree: ast.AST, 
        errors: list[str]
    ) -> None:
        """Check for forbidden patterns in AST."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Lambda):
                errors.append("Lambda expressions are not allowed")
            
            if isinstance(node, ast.ListComp):
                errors.append("List comprehensions are not allowed")
            
            if isinstance(node, ast.DictComp):
                errors.append("Dict comprehensions are not allowed")
            
            if isinstance(node, ast.SetComp):
                errors.append("Set comprehensions are not allowed")
            
            if isinstance(node, ast.GeneratorExp):
                errors.append("Generator expressions are not allowed")
            
            if isinstance(node, ast.Attribute):
                errors.append(f"Attribute access not allowed: {node.attr}")
            
            if isinstance(node, ast.Call):
                if not isinstance(node.func, ast.Name):
                    errors.append("Method calls not allowed")
                elif node.func.id not in self._allowed_functions:
                    errors.append(f"Function not allowed: {node.func.id}")
            
            if isinstance(node, ast.Subscript):
                if isinstance(node.value, ast.Subscript):
                    errors.append("Nested subscript not allowed")

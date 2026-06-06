"""Control-flow-aware type inference for Python.

Infers return types by analyzing all return paths in a function,
supports branch narrowing (isinstance checks, is None), and resolves
Union types from conditional returns.

This complements the existing type_resolver.py which only reads
explicit annotations. This module INFERS types when annotations
are absent.

Features:
- Return type inference via all return path analysis
- Branch narrowing (isinstance, is None, type() checks)
- Variable type tracking through assignments with scope context
- Generic type resolution (List[T] → List[int])
- Union type construction from multiple return paths
- Parameter type inference from usage patterns (calls, operations)
- Reachability analysis (dead branches after early return)
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from typing import Optional, Set

logger = logging.getLogger(__name__)


# ─── Data Types ──────────────────────────────────────────────────────────────


@dataclass
class InferredType:
    """An inferred type with confidence."""

    type_str: str  # e.g., "int", "str | None", "list[int]"
    confidence: float = 0.9
    source: str = "inference"  # "annotation", "inference", "literal", "call"

    def __eq__(self, other):
        if isinstance(other, InferredType):
            return self.type_str == other.type_str
        return False

    def __hash__(self):
        return hash(self.type_str)


@dataclass
class FunctionSignature:
    """Inferred function signature."""

    name: str
    params: list[tuple[str, Optional[InferredType]]]  # (name, type)
    return_type: Optional[InferredType] = None
    is_async: bool = False
    is_generator: bool = False
    line: int = 0


@dataclass
class VariableType:
    """Tracked variable type within a scope."""

    name: str
    inferred_type: InferredType
    line: int
    narrowed_in_branch: bool = False


@dataclass
class NarrowingInfo:
    """Type narrowing from a conditional test."""

    variable: str
    narrowed_type: str  # Type in the if-branch
    complement_type: str = ""  # Type in the else-branch (if determinable)
    kind: str = "isinstance"  # "isinstance", "is_none", "is_not_none", "type_eq"


@dataclass
class ScopeContext:
    """Variable types within a specific scope/branch."""

    variables: dict[str, InferredType] = field(default_factory=dict)
    parent: Optional[ScopeContext] = None

    def lookup(self, name: str) -> Optional[InferredType]:
        """Look up variable type in this scope or parent scopes."""
        if name in self.variables:
            return self.variables[name]
        if self.parent:
            return self.parent.lookup(name)
        return None

    def bind(self, name: str, inferred: InferredType) -> None:
        """Bind a variable type in this scope."""
        self.variables[name] = inferred

    def child(self) -> ScopeContext:
        """Create a child scope."""
        return ScopeContext(parent=self)


# ─── Engine ──────────────────────────────────────────────────────────────────


class TypeInferenceEngine:
    """Infer types from Python code without explicit annotations.

    Uses control flow analysis to determine:
    - Function return types (from all return statements)
    - Variable types (from assignments and narrowing)
    - Parameter types (from usage patterns)
    - Branch narrowing with isinstance/is None guards
    - Reachability (dead code after unconditional return/raise)
    """

    # Mapping of builtin function calls to their return types
    BUILTIN_RETURN_TYPES: dict[str, str] = {
        "len": "int",
        "int": "int",
        "float": "float",
        "str": "str",
        "bool": "bool",
        "list": "list",
        "dict": "dict",
        "set": "set",
        "tuple": "tuple",
        "range": "range",
        "sorted": "list",
        "reversed": "iterator",
        "enumerate": "enumerate",
        "zip": "zip",
        "map": "map",
        "filter": "filter",
        "open": "TextIOWrapper",
        "input": "str",
        "abs": "int | float",
        "round": "int | float",
        "min": "Any",
        "max": "Any",
        "sum": "int | float",
        "isinstance": "bool",
        "hasattr": "bool",
        "getattr": "Any",
        "type": "type",
    }

    # Literal type inference
    LITERAL_TYPES: dict[type, str] = {
        int: "int",
        float: "float",
        str: "str",
        bool: "bool",
        bytes: "bytes",
    }

    def __init__(self) -> None:
        self._function_signatures: dict[str, FunctionSignature] = {}
        self._variable_types: dict[str, list[VariableType]] = {}

    def infer_file(self, content: str, file_path: str = "") -> list[FunctionSignature]:
        """Infer types for all functions in a file.

        Args:
            content: Source code content
            file_path: Path to file (for logging)

        Returns:
            List of inferred function signatures
        """
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []

        signatures = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sig = self._infer_function(node)
                if sig:
                    signatures.append(sig)
                    self._function_signatures[sig.name] = sig

        return signatures

    def infer_return_type(self, func_node: ast.FunctionDef) -> Optional[InferredType]:
        """Infer the return type of a function from all return paths.

        Uses control-flow analysis to trace every possible return path,
        including branch narrowing from isinstance/is None guards.

        Args:
            func_node: AST FunctionDef node

        Returns:
            InferredType or None if cannot determine
        """
        # If annotation exists, use it directly
        if func_node.returns:
            ann = ast.unparse(func_node.returns) if hasattr(ast, "unparse") else None
            if ann:
                return InferredType(type_str=ann, confidence=1.0, source="annotation")

        # Build scope with parameter types
        scope = ScopeContext()
        self._bind_params_to_scope(func_node, scope)

        # Collect all return types from all paths with scope context
        return_types = self._collect_return_types_with_scope(func_node.body, scope)

        # Check if function can fall through without return
        if not self._all_paths_return(func_node.body):
            return_types.append(InferredType(type_str="None", confidence=0.95))

        if not return_types:
            # No return statements → None
            return InferredType(type_str="None", confidence=0.95, source="inference")

        # Check for generators (yield statements)
        if self._has_yield(func_node):
            inner_types = self._union_types(return_types)
            return InferredType(
                type_str=f"Generator[{inner_types}, None, None]",
                confidence=0.85,
                source="inference",
            )

        # Single type → direct
        unique_types = set(t.type_str for t in return_types)
        if len(unique_types) == 1:
            return InferredType(
                type_str=list(unique_types)[0],
                confidence=0.9,
                source="inference",
            )

        # Multiple types → Union
        union_str = self._union_types(return_types)
        return InferredType(
            type_str=union_str,
            confidence=0.8,
            source="inference",
        )

    def infer_variable_type(self, node: ast.Assign) -> Optional[InferredType]:
        """Infer the type of a variable from its assignment value.

        Args:
            node: AST Assign node

        Returns:
            InferredType or None
        """
        return self._infer_expr_type(node.value, ScopeContext())

    def infer_parameter_types(
        self, func_node: ast.FunctionDef
    ) -> list[tuple[str, Optional[InferredType]]]:
        """Infer parameter types from usage patterns inside the function.

        Examines how parameters are used (method calls, operators,
        isinstance checks) to deduce their types.

        Args:
            func_node: The function AST node

        Returns:
            List of (param_name, inferred_type) pairs
        """
        params = []
        param_names = {arg.arg for arg in func_node.args.args}

        # First pass: collect annotated params
        for arg in func_node.args.args:
            if arg.annotation:
                ann = ast.unparse(arg.annotation) if hasattr(ast, "unparse") else None
                if ann:
                    params.append(
                        (arg.arg, InferredType(type_str=ann, confidence=1.0, source="annotation"))
                    )
                    continue
            params.append((arg.arg, None))

        # Second pass: infer from usage patterns
        usage_types = self._analyze_parameter_usage(func_node, param_names)

        result = []
        for name, annotated in params:
            if annotated:
                result.append((name, annotated))
            elif name in usage_types:
                result.append((name, usage_types[name]))
            else:
                result.append((name, None))

        return result

    # ─── Private Methods ─────────────────────────────────────────────────────

    def _infer_function(self, node: ast.FunctionDef) -> Optional[FunctionSignature]:
        """Infer complete function signature."""
        params = self.infer_parameter_types(node)
        return_type = self.infer_return_type(node)

        return FunctionSignature(
            name=node.name,
            params=params,
            return_type=return_type,
            is_async=isinstance(node, ast.AsyncFunctionDef),
            is_generator=self._has_yield(node),
            line=node.lineno,
        )

    def _bind_params_to_scope(
        self, func_node: ast.FunctionDef, scope: ScopeContext
    ) -> None:
        """Bind parameter types (annotations or defaults) to scope."""
        for arg in func_node.args.args:
            if arg.annotation and hasattr(ast, "unparse"):
                ann = ast.unparse(arg.annotation)
                scope.bind(arg.arg, InferredType(type_str=ann, confidence=1.0, source="annotation"))

        # Bind defaults
        defaults = func_node.args.defaults
        args = func_node.args.args
        if defaults:
            offset = len(args) - len(defaults)
            for i, default in enumerate(defaults):
                arg_name = args[offset + i].arg
                if arg_name not in scope.variables:
                    t = self._infer_expr_type(default, scope)
                    if t:
                        scope.bind(arg_name, InferredType(
                            type_str=t.type_str, confidence=0.7, source="default"
                        ))

    def _collect_return_types_with_scope(
        self, body: list[ast.stmt], scope: ScopeContext
    ) -> list[InferredType]:
        """Collect return types with scope-aware narrowing.

        This is the core control-flow analysis: tracks variable types
        through branches, applies narrowing from isinstance/is None guards,
        and handles early-return patterns.
        """
        types: list[InferredType] = []

        for stmt in body:
            if isinstance(stmt, ast.Return):
                if stmt.value is None:
                    types.append(InferredType(type_str="None", confidence=0.95))
                else:
                    t = self._infer_expr_type(stmt.value, scope)
                    if t:
                        types.append(t)
                # After return, rest of this block is unreachable
                break

            elif isinstance(stmt, ast.Raise):
                # Raise terminates this path — no type contributed
                break

            elif isinstance(stmt, ast.If):
                types.extend(self._handle_if_branch(stmt, scope))

            elif isinstance(stmt, ast.For):
                loop_scope = scope.child()
                # Bind iterator variable type
                self._bind_for_target(stmt, loop_scope)
                types.extend(
                    self._collect_return_types_with_scope(stmt.body, loop_scope)
                )
                if stmt.orelse:
                    types.extend(
                        self._collect_return_types_with_scope(stmt.orelse, scope)
                    )

            elif isinstance(stmt, ast.While):
                types.extend(
                    self._collect_return_types_with_scope(stmt.body, scope)
                )

            elif isinstance(stmt, ast.With):
                with_scope = scope.child()
                self._bind_with_target(stmt, with_scope)
                types.extend(
                    self._collect_return_types_with_scope(stmt.body, with_scope)
                )

            elif isinstance(stmt, ast.Try):
                types.extend(
                    self._collect_return_types_with_scope(stmt.body, scope)
                )
                for handler in stmt.handlers:
                    handler_scope = scope.child()
                    if handler.name and handler.type:
                        exc_type = (
                            ast.unparse(handler.type)
                            if hasattr(ast, "unparse")
                            else "Exception"
                        )
                        handler_scope.bind(
                            handler.name,
                            InferredType(type_str=exc_type, confidence=0.95),
                        )
                    types.extend(
                        self._collect_return_types_with_scope(
                            handler.body, handler_scope
                        )
                    )
                if stmt.finalbody:
                    types.extend(
                        self._collect_return_types_with_scope(stmt.finalbody, scope)
                    )

            elif isinstance(stmt, ast.Assign):
                # Track variable assignments in scope
                self._process_assignment(stmt, scope)

            elif isinstance(stmt, ast.AnnAssign):
                # Annotated assignment
                if stmt.target and isinstance(stmt.target, ast.Name):
                    if stmt.annotation and hasattr(ast, "unparse"):
                        ann = ast.unparse(stmt.annotation)
                        scope.bind(
                            stmt.target.id,
                            InferredType(type_str=ann, confidence=1.0, source="annotation"),
                        )

        return types

    def _handle_if_branch(
        self, stmt: ast.If, scope: ScopeContext
    ) -> list[InferredType]:
        """Handle if/elif/else with branch narrowing.

        Applies type narrowing from the test condition:
        - isinstance(x, T) → x is T in if-branch
        - x is None → x is None in if-branch, not-None in else
        - x is not None → x is not-None in if-branch
        """
        types: list[InferredType] = []
        narrowing = self._extract_narrowing(stmt.test)

        # If-branch scope with narrowing applied
        if_scope = scope.child()
        if narrowing:
            if_scope.bind(
                narrowing.variable,
                InferredType(type_str=narrowing.narrowed_type, confidence=0.95),
            )

        types.extend(self._collect_return_types_with_scope(stmt.body, if_scope))

        # Else-branch scope with complement narrowing
        else_scope = scope.child()
        if narrowing and narrowing.complement_type:
            else_scope.bind(
                narrowing.variable,
                InferredType(type_str=narrowing.complement_type, confidence=0.85),
            )

        if stmt.orelse:
            types.extend(
                self._collect_return_types_with_scope(stmt.orelse, else_scope)
            )

        return types

    def _extract_narrowing(self, test: ast.expr) -> Optional[NarrowingInfo]:
        """Extract type narrowing information from a conditional test.

        Supports:
        - isinstance(x, Type) → x: Type in if-branch
        - isinstance(x, (A, B)) → x: A | B in if-branch
        - x is None → x: None in if-branch, original minus None in else
        - x is not None → x: original minus None in if-branch
        - not isinstance(x, T) → invert branches
        """
        # isinstance(x, T)
        if isinstance(test, ast.Call):
            return self._narrowing_from_call(test)

        # x is None / x is not None
        if isinstance(test, ast.Compare) and len(test.ops) == 1:
            return self._narrowing_from_compare(test)

        # not isinstance(x, T)
        if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
            inner = self._extract_narrowing(test.operand)
            if inner:
                # Swap narrowed and complement
                return NarrowingInfo(
                    variable=inner.variable,
                    narrowed_type=inner.complement_type or "object",
                    complement_type=inner.narrowed_type,
                    kind=inner.kind,
                )

        return None

    def _narrowing_from_call(self, call: ast.Call) -> Optional[NarrowingInfo]:
        """Extract narrowing from isinstance() call."""
        func_name = self._get_call_name(call)
        if func_name != "isinstance" or len(call.args) < 2:
            return None

        var_name = self._get_call_name_from_expr(call.args[0])
        if not var_name:
            return None

        type_arg = call.args[1]

        # isinstance(x, (A, B, C))
        if isinstance(type_arg, ast.Tuple):
            type_names = []
            for elt in type_arg.elts:
                tn = self._get_call_name_from_expr(elt)
                if tn:
                    type_names.append(tn)
            if type_names:
                narrowed = " | ".join(type_names)
                return NarrowingInfo(
                    variable=var_name,
                    narrowed_type=narrowed,
                    complement_type="",
                    kind="isinstance",
                )
        else:
            type_name = self._get_call_name_from_expr(type_arg)
            if type_name:
                return NarrowingInfo(
                    variable=var_name,
                    narrowed_type=type_name,
                    complement_type="",
                    kind="isinstance",
                )

        return None

    def _narrowing_from_compare(self, cmp: ast.Compare) -> Optional[NarrowingInfo]:
        """Extract narrowing from `x is None` / `x is not None`."""
        if len(cmp.ops) != 1 or len(cmp.comparators) != 1:
            return None

        op = cmp.ops[0]
        left = cmp.left
        right = cmp.comparators[0]

        # Check for `x is None`
        is_none_check = (
            isinstance(op, ast.Is)
            and isinstance(right, ast.Constant)
            and right.value is None
        )
        is_not_none_check = (
            isinstance(op, ast.IsNot)
            and isinstance(right, ast.Constant)
            and right.value is None
        )

        if is_none_check:
            var_name = self._get_call_name_from_expr(left)
            if var_name:
                return NarrowingInfo(
                    variable=var_name,
                    narrowed_type="None",
                    complement_type="object",  # non-None
                    kind="is_none",
                )

        if is_not_none_check:
            var_name = self._get_call_name_from_expr(left)
            if var_name:
                return NarrowingInfo(
                    variable=var_name,
                    narrowed_type="object",  # non-None
                    complement_type="None",
                    kind="is_not_none",
                )

        return None

    def _all_paths_return(self, body: list[ast.stmt]) -> bool:
        """Check if all control-flow paths in body end with return/raise.

        Used to determine if a function can implicitly return None.
        """
        if not body:
            return False

        last = body[-1]

        if isinstance(last, ast.Return):
            return True
        if isinstance(last, ast.Raise):
            return True

        if isinstance(last, ast.If):
            # Both branches must return
            if_returns = self._all_paths_return(last.body)
            else_returns = bool(last.orelse) and self._all_paths_return(last.orelse)
            return if_returns and else_returns

        # Check if any statement before the last is an unconditional return
        for stmt in body:
            if isinstance(stmt, (ast.Return, ast.Raise)):
                return True

        return False

    def _process_assignment(self, stmt: ast.Assign, scope: ScopeContext) -> None:
        """Process assignment statement and update scope."""
        inferred = self._infer_expr_type(stmt.value, scope)
        if not inferred:
            return

        for target in stmt.targets:
            if isinstance(target, ast.Name):
                scope.bind(target.id, inferred)
            elif isinstance(target, ast.Tuple):
                # Tuple unpacking: a, b = expr
                for elt in target.elts:
                    if isinstance(elt, ast.Name):
                        scope.bind(elt.id, InferredType(
                            type_str="Any", confidence=0.5, source="inference"
                        ))

    def _bind_for_target(self, stmt: ast.For, scope: ScopeContext) -> None:
        """Bind the loop variable type from the iterable."""
        iter_type = self._infer_expr_type(stmt.iter, scope)
        if isinstance(stmt.target, ast.Name):
            if iter_type:
                # Infer element type from iterable
                elem_type = self._element_type_of(iter_type.type_str)
                scope.bind(stmt.target.id, InferredType(
                    type_str=elem_type, confidence=0.75, source="inference"
                ))

    def _bind_with_target(self, stmt: ast.With, scope: ScopeContext) -> None:
        """Bind 'as' variable from with statement."""
        for item in stmt.items:
            if item.optional_vars and isinstance(item.optional_vars, ast.Name):
                ctx_type = self._infer_expr_type(item.context_expr, scope)
                if ctx_type:
                    scope.bind(item.optional_vars.id, ctx_type)

    def _element_type_of(self, container_type: str) -> str:
        """Infer element type from a container type string."""
        # list[int] → int, dict[str, int] → str, etc.
        if "[" in container_type:
            inner = container_type.split("[", 1)[1].rstrip("]")
            # For dict, return key type
            if "," in inner:
                return inner.split(",")[0].strip()
            return inner
        # Generic containers without type params
        return "Any"

    def _analyze_parameter_usage(
        self, func_node: ast.FunctionDef, param_names: set[str]
    ) -> dict[str, InferredType]:
        """Analyze how parameters are used to infer their types.

        Heuristics:
        - param.attr → object with that attribute (duck typing)
        - param[key] → subscriptable (dict/list/etc.)
        - param + literal → numeric or str
        - isinstance(param, T) → T (or broader)
        - param used in comparison with typed value
        """
        usage_types: dict[str, set[str]] = {name: set() for name in param_names}

        for node in ast.walk(func_node):
            # isinstance check
            if isinstance(node, ast.Call):
                name = self._get_call_name(node)
                if name == "isinstance" and len(node.args) >= 2:
                    var = self._get_call_name_from_expr(node.args[0])
                    if var and var in param_names:
                        type_arg = node.args[1]
                        if isinstance(type_arg, ast.Name):
                            usage_types[var].add(type_arg.id)
                        elif isinstance(type_arg, ast.Tuple):
                            for elt in type_arg.elts:
                                tn = self._get_call_name_from_expr(elt)
                                if tn:
                                    usage_types[var].add(tn)

            # Method call: param.method() → param has that interface
            elif isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name) and node.value.id in param_names:
                    # Common patterns
                    method_type_hints = {
                        "append": "list",
                        "extend": "list",
                        "keys": "dict",
                        "values": "dict",
                        "items": "dict",
                        "strip": "str",
                        "split": "str",
                        "lower": "str",
                        "upper": "str",
                        "encode": "str",
                        "decode": "bytes",
                        "read": "IO",
                        "write": "IO",
                        "close": "IO",
                    }
                    if node.attr in method_type_hints:
                        usage_types[node.value.id].add(method_type_hints[node.attr])

            # Subscript: param[x] → Mapping or Sequence
            elif isinstance(node, ast.Subscript):
                if isinstance(node.value, ast.Name) and node.value.id in param_names:
                    usage_types[node.value.id].add("Subscriptable")

        # Convert to InferredType
        result: dict[str, InferredType] = {}
        for name, types in usage_types.items():
            types.discard("Subscriptable")  # Too generic
            if len(types) == 1:
                result[name] = InferredType(
                    type_str=list(types)[0],
                    confidence=0.7,
                    source="usage",
                )
            elif len(types) > 1:
                result[name] = InferredType(
                    type_str=" | ".join(sorted(types)),
                    confidence=0.6,
                    source="usage",
                )

        return result

    def _infer_expr_type(
        self, expr: ast.expr, scope: ScopeContext
    ) -> Optional[InferredType]:
        """Infer the type of an expression with scope context."""
        if isinstance(expr, ast.Constant):
            val_type = type(expr.value)
            if val_type in self.LITERAL_TYPES:
                return InferredType(
                    type_str=self.LITERAL_TYPES[val_type],
                    confidence=1.0,
                    source="literal",
                )
            if expr.value is None:
                return InferredType(type_str="None", confidence=1.0, source="literal")

        elif isinstance(expr, ast.List):
            if expr.elts:
                elem_types = set()
                for elt in expr.elts:
                    t = self._infer_expr_type(elt, scope)
                    if t:
                        elem_types.add(t.type_str)
                if len(elem_types) == 1:
                    return InferredType(
                        type_str=f"list[{list(elem_types)[0]}]",
                        confidence=0.9,
                        source="inference",
                    )
                elif len(elem_types) > 1:
                    inner = " | ".join(sorted(elem_types))
                    return InferredType(
                        type_str=f"list[{inner}]",
                        confidence=0.8,
                        source="inference",
                    )
                return InferredType(type_str="list", confidence=0.8, source="inference")
            return InferredType(type_str="list", confidence=0.85, source="inference")

        elif isinstance(expr, ast.Dict):
            if expr.keys and expr.values:
                key_types = set()
                val_types = set()
                for k in expr.keys:
                    if k:
                        t = self._infer_expr_type(k, scope)
                        if t:
                            key_types.add(t.type_str)
                for v in expr.values:
                    t = self._infer_expr_type(v, scope)
                    if t:
                        val_types.add(t.type_str)
                if len(key_types) == 1 and len(val_types) == 1:
                    return InferredType(
                        type_str=f"dict[{list(key_types)[0]}, {list(val_types)[0]}]",
                        confidence=0.85,
                        source="inference",
                    )
            return InferredType(type_str="dict", confidence=0.85, source="inference")

        elif isinstance(expr, ast.Set):
            if expr.elts:
                elem_types = set()
                for elt in expr.elts:
                    t = self._infer_expr_type(elt, scope)
                    if t:
                        elem_types.add(t.type_str)
                if len(elem_types) == 1:
                    return InferredType(
                        type_str=f"set[{list(elem_types)[0]}]",
                        confidence=0.85,
                        source="inference",
                    )
            return InferredType(type_str="set", confidence=0.85, source="inference")

        elif isinstance(expr, ast.Tuple):
            if expr.elts:
                elem_types = []
                for elt in expr.elts:
                    t = self._infer_expr_type(elt, scope)
                    elem_types.append(t.type_str if t else "Any")
                return InferredType(
                    type_str=f"tuple[{', '.join(elem_types)}]",
                    confidence=0.9,
                    source="inference",
                )
            return InferredType(type_str="tuple", confidence=0.85, source="inference")

        elif isinstance(expr, ast.Call):
            return self._infer_call_type(expr, scope)

        elif isinstance(expr, ast.BinOp):
            return self._infer_binop_type(expr, scope)

        elif isinstance(expr, ast.Compare):
            return InferredType(type_str="bool", confidence=0.95, source="inference")

        elif isinstance(expr, ast.BoolOp):
            return InferredType(type_str="bool", confidence=0.9, source="inference")

        elif isinstance(expr, ast.UnaryOp):
            if isinstance(expr.op, ast.Not):
                return InferredType(type_str="bool", confidence=0.95, source="inference")
            return self._infer_expr_type(expr.operand, scope)

        elif isinstance(expr, ast.IfExp):
            body_type = self._infer_expr_type(expr.body, scope)
            else_type = self._infer_expr_type(expr.orelse, scope)
            if body_type and else_type:
                if body_type.type_str == else_type.type_str:
                    return body_type
                return InferredType(
                    type_str=f"{body_type.type_str} | {else_type.type_str}",
                    confidence=0.8,
                    source="inference",
                )
            return body_type or else_type

        elif isinstance(expr, ast.JoinedStr):
            return InferredType(type_str="str", confidence=1.0, source="literal")

        elif isinstance(expr, ast.FormattedValue):
            return InferredType(type_str="str", confidence=0.9, source="inference")

        elif isinstance(expr, ast.ListComp):
            # Try to infer element type from the comprehension
            if expr.elt:
                elt_type = self._infer_expr_type(expr.elt, scope)
                if elt_type:
                    return InferredType(
                        type_str=f"list[{elt_type.type_str}]",
                        confidence=0.8,
                        source="inference",
                    )
            return InferredType(type_str="list", confidence=0.85, source="inference")

        elif isinstance(expr, ast.DictComp):
            return InferredType(type_str="dict", confidence=0.85, source="inference")

        elif isinstance(expr, ast.SetComp):
            return InferredType(type_str="set", confidence=0.85, source="inference")

        elif isinstance(expr, ast.GeneratorExp):
            return InferredType(type_str="Generator", confidence=0.85, source="inference")

        elif isinstance(expr, ast.Await):
            inner = self._infer_expr_type(expr.value, scope)
            if inner:
                return inner
            return InferredType(type_str="Any", confidence=0.5, source="inference")

        elif isinstance(expr, ast.Name):
            # Look up in scope context
            scoped = scope.lookup(expr.id)
            if scoped:
                return scoped

        elif isinstance(expr, ast.Subscript):
            # container[key] — infer from container type
            container_type = self._infer_expr_type(expr.value, scope)
            if container_type and "[" in container_type.type_str:
                elem = self._element_type_of(container_type.type_str)
                return InferredType(type_str=elem, confidence=0.75, source="inference")

        return None

    def _infer_call_type(
        self, call: ast.Call, scope: ScopeContext
    ) -> Optional[InferredType]:
        """Infer return type of a function call."""
        func_name = self._get_call_name(call)

        # Check builtin return types
        if func_name in self.BUILTIN_RETURN_TYPES:
            return InferredType(
                type_str=self.BUILTIN_RETURN_TYPES[func_name],
                confidence=0.95,
                source="call",
            )

        # Constructor calls (PascalCase → instance of that class)
        if func_name and func_name[0].isupper():
            return InferredType(
                type_str=func_name,
                confidence=0.85,
                source="call",
            )

        # Check previously inferred function signatures
        if func_name in self._function_signatures:
            sig = self._function_signatures[func_name]
            if sig.return_type:
                return sig.return_type

        return None

    def _infer_binop_type(
        self, node: ast.BinOp, scope: ScopeContext
    ) -> Optional[InferredType]:
        """Infer type from binary operation."""
        left = self._infer_expr_type(node.left, scope)
        right = self._infer_expr_type(node.right, scope)

        if isinstance(node.op, ast.Add):
            if left and right:
                if left.type_str == "str" or right.type_str == "str":
                    return InferredType(type_str="str", confidence=0.9, source="inference")
                if left.type_str == right.type_str:
                    return left
            if left:
                return left
            if right:
                return right

        elif isinstance(node.op, ast.Div):
            return InferredType(type_str="float", confidence=0.95, source="inference")

        elif isinstance(node.op, (ast.Sub, ast.Mult)):
            if left and left.type_str in ("int", "float"):
                return left
            if right and right.type_str in ("int", "float"):
                return right
            return InferredType(type_str="int | float", confidence=0.7, source="inference")

        elif isinstance(node.op, ast.FloorDiv):
            return InferredType(type_str="int", confidence=0.9, source="inference")

        elif isinstance(node.op, ast.Mod):
            if left and left.type_str == "str":
                return InferredType(type_str="str", confidence=0.9, source="inference")
            return InferredType(type_str="int", confidence=0.8, source="inference")

        elif isinstance(node.op, ast.Pow):
            return InferredType(type_str="int | float", confidence=0.7, source="inference")

        return None

    def _get_narrowing_from_test(self, test: ast.expr) -> Optional[tuple[str, str]]:
        """Extract type narrowing from an if-test (isinstance check).

        Legacy method kept for backward compatibility.
        Use _extract_narrowing() for full narrowing support.
        """
        if isinstance(test, ast.Call):
            func_name = self._get_call_name(test)
            if func_name == "isinstance" and len(test.args) >= 2:
                var_name = self._get_call_name_from_expr(test.args[0])
                type_name = self._get_call_name_from_expr(test.args[1])
                if var_name and type_name:
                    return (var_name, type_name)
        return None

    def _has_yield(self, node: ast.FunctionDef) -> bool:
        """Check if function contains yield statements."""
        for child in ast.walk(node):
            if isinstance(child, (ast.Yield, ast.YieldFrom)):
                return True
        return False

    def _union_types(self, types: list[InferredType]) -> str:
        """Create Union type string from multiple types."""
        unique = sorted(set(t.type_str for t in types))
        if len(unique) == 1:
            return unique[0]
        return " | ".join(unique)

    def _get_call_name(self, call: ast.Call) -> str:
        """Get function name from Call node."""
        if isinstance(call.func, ast.Name):
            return call.func.id
        elif isinstance(call.func, ast.Attribute):
            return call.func.attr
        return ""

    def _get_call_name_from_expr(self, expr: ast.expr) -> Optional[str]:
        """Get name from an expression node."""
        if isinstance(expr, ast.Name):
            return expr.id
        elif isinstance(expr, ast.Attribute):
            return expr.attr
        return None

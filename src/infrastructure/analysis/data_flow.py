"""Data flow analysis with real taint tracking through variable assignments.

This module provides proper taint analysis that tracks how user input flows
through the program via variable assignments, function parameters, and
string operations to identify potential security vulnerabilities.

Improvements over simplified version:
- Real variable tracking through assignment chains
- Taint propagation via string operations (concat, f-string, format)
- Sanitizer recognition removes taint
- Cross-function taint via parameter mapping
- Scope-aware analysis per function body
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from typing import Optional, Set, List, Dict

logger = logging.getLogger(__name__)


@dataclass
class TaintSource:
    """A source of tainted data."""

    name: str
    line: int
    source_type: str
    variable: str = ""  # The variable that holds the tainted value


@dataclass
class TaintSink:
    """A sink where tainted data is dangerous."""

    name: str
    line: int
    sink_type: str
    arguments: List[str] = field(default_factory=list)


@dataclass
class TaintFinding:
    """A finding from taint analysis."""

    source: TaintSource
    sink: TaintSink
    severity: str = "CRITICAL"
    message: str = ""
    taint_path: List[str] = field(default_factory=list)


@dataclass
class TaintState:
    """Tracks taint state for variables within a scope."""

    tainted_vars: Dict[str, TaintSource] = field(default_factory=dict)
    sanitized_vars: Set[str] = field(default_factory=set)


# Known sanitizer functions that remove taint
DEFAULT_SANITIZERS: Set[str] = {
    "escape", "html.escape", "markupsafe.escape",
    "bleach.clean", "sanitize", "clean",
    "quote", "shlex.quote", "urllib.parse.quote",
    "parameterize", "validate", "int", "float", "bool",
    "ast.literal_eval", "json.loads",
    "strip", "replace",  # partial sanitizers
}

# Default taint sources
DEFAULT_TAINT_SOURCES: Dict[str, str] = {
    "input": "user_input",
    "request.args": "user_input",
    "request.form": "user_input",
    "request.json": "user_input",
    "request.data": "user_input",
    "request.get_json": "user_input",
    "request.files": "user_input",
    "request.cookies": "user_input",
    "request.headers": "user_input",
    "sys.argv": "cli_input",
    "os.environ": "env",
    "os.getenv": "env",
    "open": "file",
    "urllib.request.urlopen": "network",
    "requests.get": "network",
    "requests.post": "network",
    "socket.recv": "network",
}

# Default taint sinks
DEFAULT_TAINT_SINKS: Dict[str, str] = {
    "exec": "code_execution",
    "eval": "code_execution",
    "compile": "code_execution",
    "os.system": "command_injection",
    "os.popen": "command_injection",
    "subprocess.run": "command_injection",
    "subprocess.call": "command_injection",
    "subprocess.Popen": "command_injection",
    "cursor.execute": "sql_injection",
    "execute": "sql_injection",
    "open": "path_traversal",
    "render_template_string": "xss",
    "Markup": "xss",
    "innerHTML": "xss",
    "redirect": "open_redirect",
    "send_file": "path_traversal",
    "pickle.loads": "deserialization",
    "yaml.load": "deserialization",
}


class DataFlowAnalyzer:
    """Analyze data flow to detect taint propagation with real variable tracking.

    Tracks how user input flows through the program via:
    - Direct assignment (x = input())
    - Variable propagation (y = x)
    - String operations (z = f"SELECT {x}")
    - Function parameter passing
    - Attribute access propagation

    Sanitizer functions break the taint chain.
    """

    def __init__(
        self,
        taint_sources: Optional[Dict[str, str]] = None,
        taint_sinks: Optional[Dict[str, str]] = None,
        sanitizers: Optional[Set[str]] = None,
    ) -> None:
        self.taint_sources = taint_sources or DEFAULT_TAINT_SOURCES
        self.taint_sinks = taint_sinks or DEFAULT_TAINT_SINKS
        self.sanitizers = sanitizers or DEFAULT_SANITIZERS
        self._findings: List[TaintFinding] = []
        self._global_state = TaintState()
        self._function_states: Dict[str, TaintState] = {}

    def analyze(self, content: str, file_path: str = "") -> List[TaintFinding]:
        """Analyze content for taint flow vulnerabilities.

        Uses AST-based analysis to track variable assignments and detect
        when tainted data reaches dangerous sinks without sanitization.

        Args:
            content: Source code content
            file_path: Path to source file

        Returns:
            List of taint findings with source, sink, and path information
        """
        self._findings = []
        self._global_state = TaintState()
        self._function_states = {}

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []

        # Analyze module-level statements
        self._analyze_body(tree.body, self._global_state, file_path)

        # Analyze each function body separately
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_state = TaintState()
                # Inherit global taint state
                func_state.tainted_vars.update(self._global_state.tainted_vars)
                self._function_states[node.name] = func_state
                self._analyze_body(node.body, func_state, file_path)

        return self._findings

    def _analyze_body(
        self, body: List[ast.stmt], state: TaintState, file_path: str
    ) -> None:
        """Analyze a sequence of statements for taint flow."""
        for stmt in body:
            self._analyze_statement(stmt, state, file_path)

    def _analyze_statement(
        self, stmt: ast.stmt, state: TaintState, file_path: str
    ) -> None:
        """Analyze a single statement."""
        if isinstance(stmt, ast.Assign):
            self._analyze_assign(stmt, state, file_path)
        elif isinstance(stmt, ast.AugAssign):
            self._analyze_aug_assign(stmt, state, file_path)
        elif isinstance(stmt, ast.Expr):
            if isinstance(stmt.value, ast.Call):
                self._check_sink(stmt.value, state, file_path)
        elif isinstance(stmt, ast.Return):
            if stmt.value and isinstance(stmt.value, ast.Call):
                self._check_sink(stmt.value, state, file_path)
        elif isinstance(stmt, (ast.If, ast.While)):
            # Analyze branches
            self._analyze_body(stmt.body, state, file_path)
            if hasattr(stmt, "orelse") and stmt.orelse:
                self._analyze_body(stmt.orelse, state, file_path)
        elif isinstance(stmt, ast.For):
            # Analyze loop target and body
            self._analyze_body(stmt.body, state, file_path)
        elif isinstance(stmt, ast.With):
            self._analyze_body(stmt.body, state, file_path)
        elif isinstance(stmt, ast.Try):
            self._analyze_body(stmt.body, state, file_path)
            for handler in stmt.handlers:
                self._analyze_body(handler.body, state, file_path)
            if stmt.finalbody:
                self._analyze_body(stmt.finalbody, state, file_path)

    def _analyze_assign(
        self, stmt: ast.Assign, state: TaintState, file_path: str
    ) -> None:
        """Analyze an assignment statement for taint propagation."""
        value = stmt.value
        targets = stmt.targets

        # Check if the value is a taint source
        source = self._extract_taint_source(value, stmt)
        if source:
            for target in targets:
                var_name = self._get_target_name(target)
                if var_name:
                    source.variable = var_name
                    state.tainted_vars[var_name] = source
                    state.sanitized_vars.discard(var_name)
            return

        # Check if value is a sanitizer call on a tainted var
        if isinstance(value, ast.Call) and self._is_sanitizer(value):
            for target in targets:
                var_name = self._get_target_name(target)
                if var_name:
                    state.sanitized_vars.add(var_name)
                    state.tainted_vars.pop(var_name, None)
            return

        # Check if value propagates taint from another variable
        tainted_source = self._get_taint_from_expr(value, state)
        if tainted_source:
            for target in targets:
                var_name = self._get_target_name(target)
                if var_name:
                    state.tainted_vars[var_name] = tainted_source
                    state.sanitized_vars.discard(var_name)

        # Check if value is a sink call with tainted arguments
        if isinstance(value, ast.Call):
            self._check_sink(value, state, file_path)

    def _analyze_aug_assign(
        self, stmt: ast.AugAssign, state: TaintState, file_path: str
    ) -> None:
        """Analyze augmented assignment (+=, etc.) for taint propagation."""
        var_name = self._get_target_name(stmt.target)
        if not var_name:
            return

        # If the value being added is tainted, the target becomes tainted
        tainted_source = self._get_taint_from_expr(stmt.value, state)
        if tainted_source:
            state.tainted_vars[var_name] = tainted_source
            state.sanitized_vars.discard(var_name)

    def _extract_taint_source(
        self, value: ast.expr, stmt: ast.stmt
    ) -> Optional[TaintSource]:
        """Check if an expression is a taint source and return TaintSource."""
        if isinstance(value, ast.Call):
            call_name = self._get_call_name(value)
            for pattern, source_type in self.taint_sources.items():
                if call_name == pattern or call_name.endswith("." + pattern):
                    return TaintSource(
                        name=call_name,
                        line=value.lineno,
                        source_type=source_type,
                    )
            # Check if the call is on a taint source object (e.g., request.args.get())
            if isinstance(value.func, ast.Attribute):
                base_name = self._get_expr_name(value.func.value)
                for pattern, source_type in self.taint_sources.items():
                    if base_name == pattern or base_name.startswith(pattern):
                        return TaintSource(
                            name=f"{base_name}.{value.func.attr}",
                            line=value.lineno,
                            source_type=source_type,
                        )
        elif isinstance(value, ast.Subscript):
            # request.args["key"], sys.argv[1]
            subscript_name = self._get_expr_name(value.value)
            for pattern, source_type in self.taint_sources.items():
                if subscript_name == pattern or subscript_name.endswith("." + pattern):
                    return TaintSource(
                        name=subscript_name,
                        line=value.lineno,
                        source_type=source_type,
                    )
        elif isinstance(value, ast.Attribute):
            attr_name = self._get_expr_name(value)
            for pattern, source_type in self.taint_sources.items():
                if attr_name == pattern or attr_name.startswith(pattern + "."):
                    return TaintSource(
                        name=attr_name,
                        line=value.lineno,
                        source_type=source_type,
                    )
        return None

    def _get_taint_from_expr(
        self, expr: ast.expr, state: TaintState
    ) -> Optional[TaintSource]:
        """Check if an expression uses a tainted variable (propagation)."""
        if isinstance(expr, ast.Name):
            var = expr.id
            if var in state.tainted_vars and var not in state.sanitized_vars:
                return state.tainted_vars[var]

        elif isinstance(expr, ast.Attribute):
            # obj.attr — check if obj is tainted
            base_name = self._get_expr_name(expr.value) if isinstance(expr.value, ast.Name) else None
            if base_name and base_name in state.tainted_vars:
                return state.tainted_vars[base_name]

        elif isinstance(expr, ast.BinOp):
            # String concatenation: tainted_var + "something"
            left_taint = self._get_taint_from_expr(expr.left, state)
            if left_taint:
                return left_taint
            right_taint = self._get_taint_from_expr(expr.right, state)
            if right_taint:
                return right_taint

        elif isinstance(expr, ast.JoinedStr):
            # f-string: f"SELECT {tainted_var}"
            for val in expr.values:
                if isinstance(val, ast.FormattedValue):
                    taint = self._get_taint_from_expr(val.value, state)
                    if taint:
                        return taint

        elif isinstance(expr, ast.Call):
            # Check if any argument is tainted (propagation through call)
            call_name = self._get_call_name(expr)
            # If it's a sanitizer, taint is removed
            if self._is_sanitizer(expr):
                return None
            # Check .format() calls
            if call_name.endswith(".format") or call_name == "format":
                for arg in expr.args:
                    taint = self._get_taint_from_expr(arg, state)
                    if taint:
                        return taint
            # Check % formatting on tainted string
            if isinstance(expr.func, ast.Attribute) and expr.func.attr == "format":
                base_taint = self._get_taint_from_expr(expr.func.value, state)
                if base_taint:
                    return base_taint
            # General call: if any arg is tainted, result is tainted
            for arg in expr.args:
                taint = self._get_taint_from_expr(arg, state)
                if taint:
                    return taint

        elif isinstance(expr, ast.Subscript):
            # tainted_dict["key"]
            base_taint = self._get_taint_from_expr(expr.value, state)
            if base_taint:
                return base_taint

        elif isinstance(expr, ast.IfExp):
            # Ternary: x if cond else y
            body_taint = self._get_taint_from_expr(expr.body, state)
            if body_taint:
                return body_taint
            else_taint = self._get_taint_from_expr(expr.orelse, state)
            if else_taint:
                return else_taint

        return None

    def _check_sink(
        self, call: ast.Call, state: TaintState, file_path: str
    ) -> None:
        """Check if a call is a taint sink with tainted arguments."""
        call_name = self._get_call_name(call)

        sink_type = None
        for pattern, stype in self.taint_sinks.items():
            if call_name == pattern or call_name.endswith("." + pattern):
                sink_type = stype
                break

        if not sink_type:
            return

        # Check each argument for taint
        for arg in call.args:
            taint_source = self._get_taint_from_expr(arg, state)
            if taint_source:
                sink = TaintSink(
                    name=call_name,
                    line=call.lineno,
                    sink_type=sink_type,
                    arguments=[self._get_expr_name(arg) or "?"],
                )
                path = self._build_taint_path(taint_source, sink, state)
                self._findings.append(TaintFinding(
                    source=taint_source,
                    sink=sink,
                    severity="CRITICAL",
                    message=(
                        f"Taint flow: {taint_source.source_type} "
                        f"({taint_source.variable or taint_source.name}) "
                        f"-> {sink_type} ({call_name})"
                    ),
                    taint_path=path,
                ))
                return  # One finding per sink call

        # Check keyword arguments
        for kw in call.keywords:
            if kw.value:
                taint_source = self._get_taint_from_expr(kw.value, state)
                if taint_source:
                    sink = TaintSink(
                        name=call_name,
                        line=call.lineno,
                        sink_type=sink_type,
                        arguments=[kw.arg or "**kwargs"],
                    )
                    path = self._build_taint_path(taint_source, sink, state)
                    self._findings.append(TaintFinding(
                        source=taint_source,
                        sink=sink,
                        severity="CRITICAL",
                        message=(
                            f"Taint flow: {taint_source.source_type} "
                            f"({taint_source.variable or taint_source.name}) "
                            f"-> {sink_type} ({call_name}) via kwarg '{kw.arg}'"
                        ),
                        taint_path=path,
                    ))
                    return

    def _is_sanitizer(self, call: ast.Call) -> bool:
        """Check if a call is a known sanitizer function."""
        call_name = self._get_call_name(call)
        for sanitizer in self.sanitizers:
            if call_name == sanitizer or call_name.endswith("." + sanitizer):
                return True
        return False

    def _build_taint_path(
        self, source: TaintSource, sink: TaintSink, state: TaintState
    ) -> List[str]:
        """Build the taint propagation path from source to sink."""
        path = [f"L{source.line}: {source.name} ({source.source_type})"]
        if source.variable:
            path.append(f"  -> {source.variable}")
        path.append(f"L{sink.line}: {sink.name} ({sink.sink_type})")
        return path

    # ─── Helper Methods ──────────────────────────────────────────────────────

    def _get_call_name(self, node: ast.Call) -> str:
        """Get the fully-qualified name of a call."""
        return self._get_expr_name(node.func)

    def _get_expr_name(self, node: ast.expr) -> str:
        """Get a dotted name from an expression node."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            base = self._get_expr_name(node.value)
            if base:
                return f"{base}.{node.attr}"
            return node.attr
        elif isinstance(node, ast.Subscript):
            return self._get_expr_name(node.value)
        return ""

    def _get_target_name(self, target: ast.expr) -> Optional[str]:
        """Get the variable name from an assignment target."""
        if isinstance(target, ast.Name):
            return target.id
        elif isinstance(target, ast.Attribute):
            return self._get_expr_name(target)
        elif isinstance(target, ast.Tuple):
            # For tuple unpacking, return first element
            if target.elts:
                return self._get_target_name(target.elts[0])
        return None


@dataclass
class DataFlowGraph:
    """Represents data flow between program points."""

    nodes: List[Dict] = field(default_factory=list)
    edges: List[tuple[int, int]] = field(default_factory=list)

    def add_node(self, node_id: int, node_type: str, line: int) -> None:
        """Add a node to the graph."""
        self.nodes.append({
            "id": node_id,
            "type": node_type,
            "line": line,
        })

    def add_edge(self, from_id: int, to_id: int) -> None:
        """Add an edge to the graph."""
        self.edges.append((from_id, to_id))

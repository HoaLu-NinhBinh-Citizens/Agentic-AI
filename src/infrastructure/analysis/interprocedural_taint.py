"""Inter-procedural taint tracking across function boundaries.

Extends the intra-procedural DataFlowAnalyzer (data_flow.py) with
cross-function taint propagation:

- Caller passes tainted argument -> callee parameter becomes tainted
- Callee returns tainted value -> caller's receiving variable tainted
- Taint flows through call chains (A -> B -> C) up to a configurable depth
- Function summaries cache per-function taint behavior (which params
  flow to which sinks / return value)

This catches vulnerabilities that intra-procedural analysis misses:

    def get_user_data():
        return request.args["id"]      # source

    def query(uid):                     # uid is tainted via caller
        cursor.execute(uid)             # sink reached cross-function

    def handler():
        data = get_user_data()          # data tainted via return
        query(data)                     # taint flows into query()

Uses AST + a function-call map. Designed to layer on top of
DataFlowAnalyzer without changing its public API.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from typing import Optional

from src.infrastructure.analysis.data_flow import (
    DEFAULT_SANITIZERS,
    DEFAULT_TAINT_SINKS,
    DEFAULT_TAINT_SOURCES,
    TaintFinding,
    TaintSink,
    TaintSource,
)

logger = logging.getLogger(__name__)

# Maximum call-chain depth to follow (prevents infinite recursion)
DEFAULT_MAX_DEPTH = 5


@dataclass
class FunctionSummary:
    """Taint behavior summary for a single function.

    Captures which parameters, when tainted, flow to a dangerous sink
    or to the function's return value. Used to propagate taint across
    call boundaries without re-analyzing the callee every time.
    """

    name: str
    params: list[str] = field(default_factory=list)
    # Param indices/names whose taint reaches a sink inside this function
    tainted_param_to_sink: dict[str, str] = field(default_factory=dict)
    # Param names whose taint flows to the return value
    tainted_param_to_return: set[str] = field(default_factory=set)
    # Does the function return a directly-tainted value (from a source)?
    returns_source_taint: bool = False
    # Line of definition
    line: int = 0


@dataclass
class CallEdge:
    """A function call with argument-to-parameter mapping."""

    caller: str
    callee: str
    line: int
    # Positional args as expressions (for taint checking at call site)
    arg_exprs: list[ast.expr] = field(default_factory=list)
    # Variable receiving the return value (if any)
    result_var: Optional[str] = None


class InterproceduralTaintAnalyzer:
    """Track taint across function boundaries using function summaries.

    Algorithm:
    1. Parse all functions, build function summaries (intra-procedural)
    2. Build call graph (who calls whom, with arg mapping)
    3. Iteratively propagate taint through the call graph until fixpoint
    4. Report findings where tainted data reaches a sink (possibly
       several calls deep)
    """

    def __init__(
        self,
        taint_sources: Optional[dict[str, str]] = None,
        taint_sinks: Optional[dict[str, str]] = None,
        sanitizers: Optional[set[str]] = None,
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> None:
        self.taint_sources = taint_sources or DEFAULT_TAINT_SOURCES
        self.taint_sinks = taint_sinks or DEFAULT_TAINT_SINKS
        self.sanitizers = sanitizers or DEFAULT_SANITIZERS
        self.max_depth = max_depth

        self._functions: dict[str, ast.FunctionDef] = {}
        self._summaries: dict[str, FunctionSummary] = {}
        self._call_edges: list[CallEdge] = []
        self._findings: list[TaintFinding] = []

    def analyze(self, content: str, file_path: str = "") -> list[TaintFinding]:
        """Run inter-procedural taint analysis on source content.

        Args:
            content: Python source code
            file_path: Path (for reporting)

        Returns:
            List of taint findings including cross-function flows
        """
        self._functions = {}
        self._summaries = {}
        self._call_edges = []
        self._findings = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []

        # Phase 1: collect all function definitions
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._functions[node.name] = node

        # Phase 2: build per-function summaries
        for name, func in self._functions.items():
            self._summaries[name] = self._build_summary(func)

        # Phase 3: collect call edges (caller -> callee with arg mapping)
        for name, func in self._functions.items():
            self._collect_call_edges(func)

        # Phase 4: propagate taint across calls until fixpoint
        self._propagate_taint()

        # Phase 5: report cross-function findings
        self._report_findings(file_path)

        return self._findings

    # ─── Phase 2: Function Summaries ─────────────────────────────────────────

    def _build_summary(self, func: ast.FunctionDef) -> FunctionSummary:
        """Build a taint summary for a single function.

        Tracks (assuming each parameter is tainted):
        - Which params reach a sink inside this function
        - Which params flow to the return value
        - Whether the function returns directly-tainted data (from a source)
        """
        params = [arg.arg for arg in func.args.args]
        summary = FunctionSummary(name=func.name, params=params, line=func.lineno)

        # Local taint set: start with all params tainted (symbolic)
        # We track which symbolic param a variable derives from.
        var_origin: dict[str, set[str]] = {p: {p} for p in params}

        for stmt in ast.walk(func):
            # Track assignments to propagate param-origin
            if isinstance(stmt, ast.Assign):
                origins = self._expr_param_origins(stmt.value, var_origin)
                if origins:
                    for target in stmt.targets:
                        tname = self._target_name(target)
                        if tname:
                            var_origin[tname] = origins

            # Return statement: which params flow to return?
            elif isinstance(stmt, ast.Return) and stmt.value is not None:
                origins = self._expr_param_origins(stmt.value, var_origin)
                summary.tainted_param_to_return.update(origins)
                # Direct source in return?
                if self._expr_contains_source(stmt.value):
                    summary.returns_source_taint = True

            # Call that is a sink: which params reach it?
            elif isinstance(stmt, ast.Call):
                sink_type = self._sink_type(stmt)
                if sink_type:
                    for arg in stmt.args:
                        origins = self._expr_param_origins(arg, var_origin)
                        for origin in origins:
                            summary.tainted_param_to_sink[origin] = sink_type

        return summary

    def _expr_param_origins(
        self, expr: ast.expr, var_origin: dict[str, set[str]]
    ) -> set[str]:
        """Find which function parameters an expression derives from.

        Returns the set of parameter names whose taint would flow into
        this expression. Sanitizer calls break the chain.
        """
        origins: set[str] = set()

        if isinstance(expr, ast.Name):
            if expr.id in var_origin:
                origins.update(var_origin[expr.id])

        elif isinstance(expr, ast.BinOp):
            origins.update(self._expr_param_origins(expr.left, var_origin))
            origins.update(self._expr_param_origins(expr.right, var_origin))

        elif isinstance(expr, ast.JoinedStr):
            for val in expr.values:
                if isinstance(val, ast.FormattedValue):
                    origins.update(self._expr_param_origins(val.value, var_origin))

        elif isinstance(expr, ast.Call):
            # Sanitizer breaks taint
            if self._is_sanitizer(expr):
                return set()
            # .format() and general args propagate
            for arg in expr.args:
                origins.update(self._expr_param_origins(arg, var_origin))
            if isinstance(expr.func, ast.Attribute):
                origins.update(self._expr_param_origins(expr.func.value, var_origin))

        elif isinstance(expr, ast.Subscript):
            origins.update(self._expr_param_origins(expr.value, var_origin))

        elif isinstance(expr, ast.Attribute):
            origins.update(self._expr_param_origins(expr.value, var_origin))

        elif isinstance(expr, ast.IfExp):
            origins.update(self._expr_param_origins(expr.body, var_origin))
            origins.update(self._expr_param_origins(expr.orelse, var_origin))

        return origins

    def _expr_contains_source(self, expr: ast.expr) -> bool:
        """Check if an expression directly contains a taint source."""
        for node in ast.walk(expr):
            if isinstance(node, ast.Call):
                name = self._call_name(node)
                for pattern in self.taint_sources:
                    if name == pattern or name.endswith("." + pattern):
                        return True
                if isinstance(node.func, ast.Attribute):
                    base = self._expr_name(node.func.value)
                    for pattern in self.taint_sources:
                        if base == pattern or base.startswith(pattern):
                            return True
            elif isinstance(node, ast.Subscript):
                base = self._expr_name(node.value)
                for pattern in self.taint_sources:
                    if base == pattern or base.endswith("." + pattern):
                        return True
        return False

    # ─── Phase 3: Call Edges ─────────────────────────────────────────────────

    def _collect_call_edges(self, func: ast.FunctionDef) -> None:
        """Collect all calls to known functions within a function body."""
        # Track which variable receives a call's result
        for node in ast.walk(func):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                callee = self._call_name(node.value)
                if callee in self._functions:
                    result_var = self._target_name(node.targets[0]) if node.targets else None
                    self._call_edges.append(CallEdge(
                        caller=func.name,
                        callee=callee,
                        line=node.value.lineno,
                        arg_exprs=list(node.value.args),
                        result_var=result_var,
                    ))
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                callee = self._call_name(node.value)
                if callee in self._functions:
                    self._call_edges.append(CallEdge(
                        caller=func.name,
                        callee=callee,
                        line=node.value.lineno,
                        arg_exprs=list(node.value.args),
                        result_var=None,
                    ))

    # ─── Phase 4: Taint Propagation ──────────────────────────────────────────

    def _propagate_taint(self) -> None:
        """Iteratively propagate taint through call edges until fixpoint.

        For each call:
        - If an argument expression is tainted (from a source or a
          tainted-returning function), mark the callee's corresponding
          parameter as tainted.
        - If callee returns taint and result_var is captured, mark it tainted.

        We track tainted variables per function scope.
        """
        # tainted_vars[func_name] = set of tainted variable names
        tainted_vars: dict[str, set[str]] = {fn: set() for fn in self._functions}
        # Which functions are known to return tainted data
        returns_taint: set[str] = {
            fn for fn, s in self._summaries.items() if s.returns_source_taint
        }

        # Seed: variables assigned directly from a source in each function
        for fn, func in self._functions.items():
            for stmt in ast.walk(func):
                if isinstance(stmt, ast.Assign) and self._expr_contains_source(stmt.value):
                    for target in stmt.targets:
                        tname = self._target_name(target)
                        if tname:
                            tainted_vars[fn].add(tname)

        # Fixpoint iteration
        changed = True
        iterations = 0
        while changed and iterations < self.max_depth * 3:
            changed = False
            iterations += 1

            for edge in self._call_edges:
                caller_tainted = tainted_vars[edge.caller]
                callee_summary = self._summaries.get(edge.callee)
                if not callee_summary:
                    continue

                # Map tainted args to callee params
                for i, arg in enumerate(edge.arg_exprs):
                    if i >= len(callee_summary.params):
                        break
                    param = callee_summary.params[i]
                    if self._arg_is_tainted(arg, caller_tainted, returns_taint):
                        if param not in tainted_vars[edge.callee]:
                            tainted_vars[edge.callee].add(param)
                            changed = True

                # Return-value taint: if callee returns taint of a now-tainted
                # param, propagate to result_var
                if edge.result_var:
                    callee_tainted = tainted_vars[edge.callee]
                    flows = callee_summary.tainted_param_to_return & callee_tainted
                    if (flows or edge.callee in returns_taint) and \
                       edge.result_var not in caller_tainted:
                        caller_tainted.add(edge.result_var)
                        changed = True
                        # If a function returns taint, mark it
                        if edge.callee in returns_taint:
                            returns_taint.add(edge.caller)

        self._tainted_vars = tainted_vars
        self._returns_taint = returns_taint

    def _arg_is_tainted(
        self, arg: ast.expr, caller_tainted: set[str], returns_taint: set[str]
    ) -> bool:
        """Check if an argument expression carries taint at the call site."""
        # Direct source
        if self._expr_contains_source(arg):
            return True

        # Tainted variable reference
        for node in ast.walk(arg):
            if isinstance(node, ast.Name) and node.id in caller_tainted:
                return True
            # Call to a tainted-returning function
            if isinstance(node, ast.Call):
                callee = self._call_name(node)
                if callee in returns_taint:
                    return True

        return False

    # ─── Phase 5: Reporting ──────────────────────────────────────────────────

    def _report_findings(self, file_path: str) -> None:
        """Report findings where tainted data reaches sinks cross-function."""
        for fn, summary in self._summaries.items():
            tainted = self._tainted_vars.get(fn, set())

            # Which of this function's params are tainted at runtime?
            tainted_params = tainted & set(summary.params)

            for param, sink_type in summary.tainted_param_to_sink.items():
                if param in tainted_params:
                    # This param is tainted by a caller AND reaches a sink
                    source = TaintSource(
                        name=f"<cross-function via param '{param}'>",
                        line=summary.line,
                        source_type="cross_function",
                        variable=param,
                    )
                    sink = TaintSink(
                        name=f"{fn}() sink",
                        line=summary.line,
                        sink_type=sink_type,
                        arguments=[param],
                    )
                    self._findings.append(TaintFinding(
                        source=source,
                        sink=sink,
                        severity="CRITICAL",
                        message=(
                            f"Inter-procedural taint: parameter '{param}' of "
                            f"'{fn}()' carries tainted data to a {sink_type} sink"
                        ),
                        taint_path=[
                            f"param '{param}' (tainted by caller)",
                            f"-> {sink_type} sink in {fn}()",
                        ],
                    ))

            # Also report sinks that consume a tainted LOCAL variable
            # (e.g. data = get_input(); os.system(data) — data tainted via return)
            self._report_local_var_sinks(fn, tainted, file_path)

    def _report_local_var_sinks(
        self, fn: str, tainted: set[str], file_path: str
    ) -> None:
        """Report sinks within a function that use tainted local variables.

        Catches the pattern where a variable is tainted via a function's
        return value (cross-function) and then flows to a sink locally.
        """
        func = self._functions.get(fn)
        if not func:
            return

        for node in ast.walk(func):
            if not isinstance(node, ast.Call):
                continue
            sink_type = self._sink_type(node)
            if not sink_type:
                continue

            # Check positional args for tainted var references
            for arg in node.args:
                if self._refs_tainted_var(arg, tainted):
                    source = TaintSource(
                        name="<cross-function return taint>",
                        line=node.lineno,
                        source_type="cross_function",
                    )
                    sink = TaintSink(
                        name=self._call_name(node),
                        line=node.lineno,
                        sink_type=sink_type,
                        arguments=[self._expr_name(arg) or "?"],
                    )
                    self._findings.append(TaintFinding(
                        source=source,
                        sink=sink,
                        severity="CRITICAL",
                        message=(
                            f"Inter-procedural taint: tainted value reaches "
                            f"{sink_type} sink '{self._call_name(node)}' in '{fn}()'"
                        ),
                        taint_path=[
                            f"tainted local var (via function return)",
                            f"-> {sink_type} sink at L{node.lineno}",
                        ],
                    ))
                    break

    def _refs_tainted_var(self, expr: ast.expr, tainted: set[str]) -> bool:
        """Check if an expression references a tainted variable (not via source)."""
        for node in ast.walk(expr):
            if isinstance(node, ast.Name) and node.id in tainted:
                return True
        return False

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _sink_type(self, call: ast.Call) -> Optional[str]:
        """Return sink type if call is a sink, else None."""
        name = self._call_name(call)
        for pattern, stype in self.taint_sinks.items():
            if name == pattern or name.endswith("." + pattern):
                return stype
        return None

    def _is_sanitizer(self, call: ast.Call) -> bool:
        name = self._call_name(call)
        for s in self.sanitizers:
            if name == s or name.endswith("." + s):
                return True
        return False

    def _call_name(self, call: ast.Call) -> str:
        return self._expr_name(call.func)

    def _expr_name(self, node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            base = self._expr_name(node.value)
            return f"{base}.{node.attr}" if base else node.attr
        elif isinstance(node, ast.Subscript):
            return self._expr_name(node.value)
        return ""

    def _target_name(self, target: ast.expr) -> Optional[str]:
        if isinstance(target, ast.Name):
            return target.id
        elif isinstance(target, ast.Attribute):
            return self._expr_name(target)
        elif isinstance(target, ast.Tuple) and target.elts:
            return self._target_name(target.elts[0])
        return None


def analyze_combined(content: str, file_path: str = "") -> list[TaintFinding]:
    """Run both intra- and inter-procedural taint analysis, merged.

    Convenience function combining DataFlowAnalyzer (intra) with
    InterproceduralTaintAnalyzer (cross-function) and de-duplicating.

    Args:
        content: Python source code
        file_path: Path for reporting

    Returns:
        Combined, de-duplicated list of taint findings
    """
    from src.infrastructure.analysis.data_flow import DataFlowAnalyzer

    intra = DataFlowAnalyzer().analyze(content, file_path)
    inter = InterproceduralTaintAnalyzer().analyze(content, file_path)

    # De-duplicate by (sink line, sink type)
    seen: set[tuple[int, str]] = set()
    combined: list[TaintFinding] = []

    for finding in intra + inter:
        key = (finding.sink.line, finding.sink.sink_type)
        if key not in seen:
            seen.add(key)
            combined.append(finding)

    return combined

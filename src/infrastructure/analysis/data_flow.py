"""Data flow analysis for taint tracking.

This module provides taint analysis to track how user input flows through
the program to identify potential security vulnerabilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Set, List, Dict
import ast


@dataclass
class TaintSource:
    """A source of tainted data."""

    name: str
    line: int
    source_type: str


@dataclass
class TaintSink:
    """A sink where tainted data is dangerous."""

    name: str
    line: int
    sink_type: str


@dataclass
class TaintFinding:
    """A finding from taint analysis."""

    source: TaintSource
    sink: TaintSink
    severity: str = "CRITICAL"
    message: str = ""


class DataFlowAnalyzer:
    """Analyze data flow to detect taint propagation.

    Tracks how user input flows through the program to identify
    potential security vulnerabilities.
    """

    TAINT_SOURCES = {
        'input(': 'user_input',
        'request.args': 'user_input',
        'request.form': 'user_input',
        'request.json': 'user_input',
        'request.data': 'user_input',
        'sys.argv': 'user_input',
        'os.environ': 'env',
        'open(': 'file',
    }

    TAINT_SINKS = {
        'exec(': 'execute',
        'eval(': 'eval',
        'open(': 'open',
        'cursor.execute(': 'sql',
        'execute(': 'sql',
        'render_template_string(': 'html',
        '.format(': 'format',
    }

    def __init__(self) -> None:
        self.tainted_vars: Set[str] = set()
        self.sources: List[TaintSource] = []
        self.sinks: List[TaintSink] = []

    def analyze(self, content: str, file_path: str = "") -> List[TaintFinding]:
        """Analyze content for taint flow vulnerabilities.

        Args:
            content: Source code content
            file_path: Path to source file

        Returns:
            List of taint findings
        """
        findings = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return findings

        self.sources = []
        self.sinks = []
        self.tainted_vars = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                source_type = self._is_taint_source(node)
                if source_type:
                    name = self._get_call_name(node)
                    self.sources.append(TaintSource(
                        name=name,
                        line=node.lineno,
                        source_type=source_type,
                    ))
                    self.tainted_vars.add(f"_taint_{node.lineno}")

                sink_type = self._is_taint_sink(node)
                if sink_type:
                    name = self._get_call_name(node)
                    self.sinks.append(TaintSink(
                        name=name,
                        line=node.lineno,
                        sink_type=sink_type,
                    ))

        for source in self.sources:
            for sink in self.sinks:
                if sink.line > source.line:
                    if self._is_connected(source, sink):
                        findings.append(TaintFinding(
                            source=source,
                            sink=sink,
                            message=f"Taint flow: {source.source_type} -> {sink.sink_type}",
                        ))

        return findings

    def _is_taint_source(self, node: ast.Call) -> Optional[str]:
        """Check if call is a taint source."""
        name = self._get_call_name(node)
        for pattern, source_type in self.TAINT_SOURCES.items():
            base = pattern.rstrip('(')
            if name == base or name.startswith(base + '.'):
                return source_type
        return None

    def _is_taint_sink(self, node: ast.Call) -> Optional[str]:
        """Check if call is a taint sink."""
        name = self._get_call_name(node)
        for pattern, sink_type in self.TAINT_SINKS.items():
            base = pattern.rstrip('(')
            if name == base or name.startswith(base + '.'):
                return sink_type
        return None

    def _get_call_name(self, node: ast.Call) -> str:
        """Get the name of a call."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            if isinstance(node.func.value, ast.Name):
                return f"{node.func.value.id}.{attr}"
            return attr
        return ""

    def _is_connected(self, source: TaintSource, sink: TaintSink) -> bool:
        """Check if sink uses source result (simplified)."""
        return True


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

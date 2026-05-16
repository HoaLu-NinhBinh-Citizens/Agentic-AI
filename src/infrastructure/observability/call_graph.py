"""
Tool Call Graph Visualization

Provides tool execution tracking and graph visualization for debugging
and analyzing tool call patterns in src.

Features:
- Tool call graph tracking
- Execution timeline
- Dependency visualization
- Performance metrics
- HTML/JSON export

Usage:
    from src.infrastructure.observability.call_graph import CallGraph, CallNode

    graph = CallGraph()
    graph.start_span("root")
    graph.start_span("tool_call")
    # ... tool execution ...
    graph.end_span("tool_call")
    graph.end_span("root")

    # Export visualization
    html = graph.to_html()
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import uuid4

logger = logging.getLogger(__name__)


class NodeStatus(Enum):
    """Status of a call graph node."""
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class CallNode:
    """A node in the call graph."""
    id: str
    name: str
    tool_name: Optional[str] = None
    parent_id: Optional[str] = None
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    status: NodeStatus = NodeStatus.RUNNING
    depth: int = 0
    children: List[str] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    result_size: int = 0

    @property
    def duration_ms(self) -> float:
        """Get duration in milliseconds."""
        if self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time).total_seconds() * 1000

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "tool_name": self.tool_name,
            "parent_id": self.parent_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "status": self.status.value,
            "depth": self.depth,
            "children": self.children,
            "attributes": self.attributes,
            "error": self.error,
            "result_size": self.result_size,
        }


class CallGraph:
    """
    Tool call graph tracker for visualization.

    Tracks tool execution as a hierarchical graph that can be
    exported as HTML, JSON, or DOT format.

    Usage:
        graph = CallGraph()

        with graph.span("workflow") as root:
            with graph.span("tool_read"):
                # read file
                pass
            with graph.span("tool_write"):
                # write file
                pass

        # Get visualization
        html = graph.to_html()
    """

    def __init__(self, max_nodes: int = 10000):
        self.max_nodes = max_nodes
        self._nodes: Dict[str, CallNode] = {}
        self._root_id: Optional[str] = None
        self._current_span_id: Optional[str] = None
        self._span_stack: List[str] = []
        self._start_time = datetime.now()

        # Statistics
        self._stats = {
            "total_calls": 0,
            "total_errors": 0,
            "total_duration_ms": 0.0,
        }

    @property
    def root(self) -> Optional[CallNode]:
        """Get the root node."""
        if self._root_id:
            return self._nodes.get(self._root_id)
        return None

    @property
    def current_span(self) -> Optional[CallNode]:
        """Get the current active span."""
        if self._current_span_id:
            return self._nodes.get(self._current_span_id)
        return None

    def start_span(
        self,
        name: str,
        tool_name: Optional[str] = None,
        parent_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Start a new span.

        Args:
            name: Span name
            tool_name: Optional tool name
            parent_id: Parent span ID (default: current)
            attributes: Initial attributes

        Returns:
            Span ID
        """
        if len(self._nodes) >= self.max_nodes:
            logger.warning(f"Max nodes ({self.max_nodes}) reached, ignoring span")
            return ""

        span_id = str(uuid4())[:8]

        # Determine parent
        if parent_id is None and self._current_span_id:
            parent_id = self._current_span_id

        depth = 0
        if parent_id and parent_id in self._nodes:
            depth = self._nodes[parent_id].depth + 1
            self._nodes[parent_id].children.append(span_id)

        node = CallNode(
            id=span_id,
            name=name,
            tool_name=tool_name,
            parent_id=parent_id,
            depth=depth,
            attributes=attributes or {},
        )

        self._nodes[span_id] = node
        self._current_span_id = span_id
        self._span_stack.append(span_id)

        # Set root if first node
        if self._root_id is None:
            self._root_id = span_id

        self._stats["total_calls"] += 1

        logger.debug(f"Started span: {name} (id={span_id}, parent={parent_id})")
        return span_id

    def end_span(
        self,
        span_id: Optional[str] = None,
        status: NodeStatus = NodeStatus.SUCCESS,
        error: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Optional[CallNode]:
        """
        End a span.

        Args:
            span_id: Span ID to end (default: current)
            status: Final status
            error: Error message if failed
            attributes: Additional attributes

        Returns:
            The ended node
        """
        if span_id is None:
            span_id = self._current_span_id

        if span_id is None or span_id not in self._nodes:
            logger.warning(f"Unknown span_id: {span_id}")
            return None

        node = self._nodes[span_id]
        node.end_time = datetime.now()
        node.status = status
        node.error = error

        if attributes:
            node.attributes.update(attributes)

        # Update stats
        self._stats["total_duration_ms"] += node.duration_ms
        if status == NodeStatus.FAILED:
            self._stats["total_errors"] += 1

        # Pop stack
        if self._span_stack and self._span_stack[-1] == span_id:
            self._span_stack.pop()

        # Move to parent
        if self._span_stack:
            self._current_span_id = self._span_stack[-1]
        else:
            self._current_span_id = None

        logger.debug(f"Ended span: {node.name} (duration={node.duration_ms:.2f}ms)")
        return node

    def add_attribute(self, span_id: Optional[str], key: str, value: Any) -> None:
        """Add attribute to a span."""
        if span_id is None:
            span_id = self._current_span_id

        if span_id and span_id in self._nodes:
            self._nodes[span_id].attributes[key] = value

    def get_stats(self) -> Dict[str, Any]:
        """Get execution statistics."""
        return {
            **self._stats,
            "node_count": len(self._nodes),
            "max_depth": max((n.depth for n in self._nodes.values()), default=0),
            "total_time_ms": (datetime.now() - self._start_time).total_seconds() * 1000,
            "error_rate": (
                self._stats["total_errors"] / self._stats["total_calls"] * 100
                if self._stats["total_calls"] > 0 else 0
            ),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Export as dictionary."""
        return {
            "root_id": self._root_id,
            "nodes": {k: v.to_dict() for k, v in self._nodes.items()},
            "stats": self.get_stats(),
        }

    def to_json(self) -> str:
        """Export as JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    def to_html(self) -> str:
        """Export as interactive HTML visualization."""
        nodes_data = json.dumps([
            {
                "id": n.id,
                "name": n.name,
                "tool": n.tool_name or "",
                "parent": n.parent_id or "",
                "duration": n.duration_ms,
                "status": n.status.value,
                "depth": n.depth,
                "error": n.error or "",
            }
            for n in self._nodes.values()
        ])

        stats = self.get_stats()

        return f"""<!DOCTYPE html>
<html>
<head>
    <title>Tool Call Graph</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; padding: 20px; background: #1a1a2e; color: #eee; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }}
        h1 {{ color: #00d4ff; margin: 0; }}
        .stats {{ display: flex; gap: 20px; }}
        .stat {{ background: #16213e; padding: 10px 20px; border-radius: 8px; }}
        .stat-value {{ font-size: 24px; font-weight: bold; color: #00d4ff; }}
        .stat-label {{ font-size: 12px; color: #888; }}
        .graph {{ background: #16213e; border-radius: 12px; padding: 20px; overflow-x: auto; }}
        .node {{ 
            display: inline-block; padding: 8px 16px; margin: 4px; border-radius: 6px;
            font-family: monospace; font-size: 12px; white-space: nowrap;
        }}
        .success {{ background: #0f5132; border-left: 4px solid #00ff88; }}
        .failed {{ background: #842029; border-left: 4px solid #ff4444; }}
        .running {{ background: #66401d; border-left: 4px solid #ffaa00; }}
        .depth-0 {{ margin-left: 0; }}
        .depth-1 {{ margin-left: 20px; }}
        .depth-2 {{ margin-left: 40px; }}
        .depth-3 {{ margin-left: 60px; }}
        .depth-4 {{ margin-left: 80px; }}
        .depth-5 {{ margin-left: 100px; }}
        .depth {{ padding-left: 10px; border-left: 2px solid #333; }}
        .tool {{ color: #00d4ff; font-weight: bold; }}
        .duration {{ color: #888; margin-left: 8px; }}
        .error {{ color: #ff4444; font-size: 10px; }}
        #tree {{ line-height: 1.8; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Tool Call Graph</h1>
        <div class="stats">
            <div class="stat">
                <div class="stat-value">{stats['total_calls']}</div>
                <div class="stat-label">Total Calls</div>
            </div>
            <div class="stat">
                <div class="stat-value">{stats['total_errors']}</div>
                <div class="stat-label">Errors</div>
            </div>
            <div class="stat">
                <div class="stat-value">{stats['total_duration_ms']:.0f}ms</div>
                <div class="stat-label">Total Duration</div>
            </div>
            <div class="stat">
                <div class="stat-value">{stats['max_depth']}</div>
                <div class="stat-label">Max Depth</div>
            </div>
        </div>
    </div>
    <div class="graph">
        <div id="tree"></div>
    </div>
    <script>
        const nodes = {nodes_data};
        const tree = document.getElementById('tree');
        
        // Build tree structure
        const nodeMap = {{}};
        nodes.forEach(n => {{ nodeMap[n.id] = n; }});
        
        // Find root(s)
        const roots = nodes.filter(n => !n.parent);
        
        function renderNode(node, depth) {{
            const div = document.createElement('div');
            div.className = `node ${{node.status}} depth-${{Math.min(depth, 5)}}`;
            
            const tool = node.tool ? `<span class="tool">[{{node.tool}}]</span> ` : '';
            const duration = `<span class="duration">{{node.duration.toFixed(2)}}ms</span>`;
            const error = node.error ? `<div class="error">{{node.error}}</div>` : '';
            
            div.innerHTML = `${{tool}}${{node.name}}${{duration}}${{error}}`;
            return div;
        }}
        
        function renderTree(nodes, parentId, depth) {{
            const children = nodes.filter(n => n.parent === parentId);
            children.forEach(child => {{
                const el = renderNode(child, depth);
                tree.appendChild(el);
                renderTree(nodes, child.id, depth + 1);
            }});
        }}
        
        roots.forEach(root => {{
            const el = renderNode(root, 0);
            tree.appendChild(el);
            renderTree(nodes, root.id, 1);
        }});
    </script>
</body>
</html>"""

    def to_dot(self) -> str:
        """Export as DOT format for Graphviz."""
        lines = ["digraph call_graph {", "  rankdir=TB;"]

        for node in self._nodes.values():
            color = {
                NodeStatus.SUCCESS: "#00ff88",
                NodeStatus.FAILED: "#ff4444",
                NodeStatus.RUNNING: "#ffaa00",
                NodeStatus.CANCELLED: "#888888",
            }.get(node.status, "#888888")

            label = f'"{node.name}"'
            if node.tool_name:
                label = f'"{node.name}\\n[{node.tool_name}]"'

            lines.append(
                f'  {node.id} [label={label}, color="{color}", '
                f'style=filled, fillcolor="{color}33"];'
            )

            if node.parent_id:
                lines.append(f"  {node.parent_id} -> {node.id};")

        lines.append("}")
        return "\n".join(lines)

    def get_timeline(self) -> List[Dict[str, Any]]:
        """Get execution timeline for visualization."""
        return sorted(
            [
                {
                    "name": n.name,
                    "tool": n.tool_name,
                    "start": n.start_time.timestamp() * 1000,
                    "end": n.end_time.timestamp() * 1000 if n.end_time else None,
                    "duration": n.duration_ms,
                    "depth": n.depth,
                    "status": n.status.value,
                    "error": n.error,
                }
                for n in self._nodes.values()
            ],
            key=lambda x: x["start"]
        )

    def clear(self) -> None:
        """Clear the graph."""
        self._nodes.clear()
        self._root_id = None
        self._current_span_id = None
        self._span_stack.clear()
        self._stats = {
            "total_calls": 0,
            "total_errors": 0,
            "total_duration_ms": 0.0,
        }


class SpanContext:
    """Context manager for spans."""

    def __init__(
        self,
        graph: CallGraph,
        name: str,
        tool_name: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ):
        self.graph = graph
        self.name = name
        self.tool_name = tool_name
        self.attributes = attributes
        self.span_id: Optional[str] = None
        self.exception: Optional[Exception] = None

    def __enter__(self) -> "SpanContext":
        self.span_id = self.graph.start_span(
            self.name,
            self.tool_name,
            attributes=self.attributes,
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val is not None:
            self.graph.end_span(
                self.span_id,
                status=NodeStatus.FAILED,
                error=str(exc_val),
            )
        else:
            self.graph.end_span(self.span_id, status=NodeStatus.SUCCESS)
        return False

    def add_attribute(self, key: str, value: Any) -> None:
        """Add attribute to the span."""
        if self.span_id:
            self.graph.add_attribute(self.span_id, key, value)

"""Fault Propagation Graph - tracking hardware fault relationships.

Phase 6.1: Graph model for understanding how faults propagate through
hardware components (e.g., clock fail → UART timeout → watchdog reset).
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================================
# Fault Types
# ============================================================================


class FaultSeverity(Enum):
    """Severity of a fault."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    FATAL = "fatal"


class FaultDomain(Enum):
    """Domain where fault originated."""

    POWER = "power"
    CLOCK = "clock"
    MEMORY = "memory"
    PERIPHERAL = "peripheral"
    INTERRUPT = "interrupt"
    DMA = "dma"
    SECURITY = "security"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


# ============================================================================
# Fault Node
# ============================================================================


@dataclass
class FaultNode:
    """A node in the fault propagation graph.

    Represents a hardware component or subsystem that can fail.
    """

    # Identity
    node_id: str
    name: str
    category: str  # e.g., "clock", "uart", "flash"

    # Relationships
    fault_type: str = ""  # e.g., "clock_failure", "timeout", "crc_error"
    severity: FaultSeverity = FaultSeverity.ERROR
    domain: FaultDomain = FaultDomain.UNKNOWN

    # Detection
    can_detect: bool = True
    detection_method: str = ""
    detection_register: str = ""

    # Effects
    causes: list[str] = field(default_factory=list)  # Node IDs this node causes
    propagates_to: list[str] = field(default_factory=list)  # Node IDs this propagates to
    mitigated_by: list[str] = field(default_factory=list)  # Node IDs that can mitigate
    prevented_by: list[str] = field(default_factory=list)  # Node IDs that prevent this

    # Recovery
    self_recovering: bool = False
    recovery_timeout_ms: int = 0

    # Symptoms
    symptoms: list[str] = field(default_factory=list)  # Observable symptoms
    error_patterns: list[str] = field(default_factory=list)  # Known error patterns

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "node_id": self.node_id,
            "name": self.name,
            "category": self.category,
            "fault_type": self.fault_type,
            "severity": self.severity.value,
            "domain": self.domain.value,
            "causes": self.causes,
            "propagates_to": self.propagates_to,
            "mitigated_by": self.mitigated_by,
            "symptoms": self.symptoms,
        }


# ============================================================================
# Fault Propagation Graph
# ============================================================================


class FaultPropagationGraph:
    """Graph model for fault propagation through hardware.

    Nodes represent hardware components/subsystems.
    Edges represent fault propagation relationships.

    Example:
        graph = FaultPropagationGraph()

        # Add fault relationships
        graph.add_edge("PLL", "UART", relation="causes", fault_type="clock_loss")
        graph.add_edge("UART", "Watchdog", relation="causes", fault_type="timeout")

        # Query propagation path
        path = graph.get_propagation_path("PLL", "Watchdog")
        # Returns: ["PLL", "UART", "Watchdog"]
    """

    def __init__(self) -> None:
        """Initialize fault propagation graph."""
        self._nodes: dict[str, FaultNode] = {}
        self._edges: dict[str, list[tuple[str, str]]] = {  # source -> (target, relation)
            "causes": [],
            "propagates_to": [],
            "mitigated_by": [],
            "prevented_by": [],
        }
        self._index: dict[str, list[str]] = {  # category -> node_ids
            "clock": [],
            "power": [],
            "memory": [],
            "peripheral": [],
        }

        # Load default fault relationships
        self._load_default_faults()

    def _load_default_faults(self) -> None:
        """Load default fault relationships."""
        # Clock failures
        self.add_node(FaultNode(
            node_id="pll",
            name="PLL Clock",
            category="clock",
            fault_type="pll_loss",
            severity=FaultSeverity.CRITICAL,
            domain=FaultDomain.CLOCK,
            causes=["uart", "timer"],
            symptoms=["no_clock_output", "frequency_drift"],
        ))

        self.add_node(FaultNode(
            node_id="hse",
            name="HSE Oscillator",
            category="clock",
            fault_type="hse_failure",
            severity=FaultSeverity.CRITICAL,
            domain=FaultDomain.CLOCK,
            causes=["pll"],
            symptoms=["system_clock_switch"],
        ))

        # UART failures
        self.add_node(FaultNode(
            node_id="uart",
            name="UART Peripheral",
            category="peripheral",
            fault_type="uart_timeout",
            severity=FaultSeverity.WARNING,
            domain=FaultDomain.PERIPHERAL,
            causes=["watchdog"],
            mitigated_by=["dma"],
            symptoms=["no_data_received", "framing_error"],
        ))

        # Watchdog
        self.add_node(FaultNode(
            node_id="watchdog",
            name="Watchdog Timer",
            category="peripheral",
            fault_type="watchdog_reset",
            severity=FaultSeverity.CRITICAL,
            domain=FaultDomain.PERIPHERAL,
            symptoms=["system_reset", "boot_loop"],
        ))

        # Memory failures
        self.add_node(FaultNode(
            node_id="flash",
            name="Flash Memory",
            category="memory",
            fault_type="read_error",
            severity=FaultSeverity.ERROR,
            domain=FaultDomain.MEMORY,
            causes=["memory_controller"],
            symptoms=["data_corruption", "hang"],
        ))

        self.add_node(FaultNode(
            node_id="sram",
            name="SRAM",
            category="memory",
            fault_type="sram_error",
            severity=FaultSeverity.ERROR,
            domain=FaultDomain.MEMORY,
            causes=["memory_controller"],
            symptoms=["data_corruption", "hard_fault"],
        ))

        self.add_node(FaultNode(
            node_id="memory_controller",
            name="Memory Controller",
            category="peripheral",
            fault_type="memctrl_error",
            severity=FaultSeverity.ERROR,
            domain=FaultDomain.MEMORY,
            causes=["flash", "sram"],
            symptoms=["bus_fault"],
        ))

        # Power failures
        self.add_node(FaultNode(
            node_id="vdd",
            name="VDD Supply",
            category="power",
            fault_type="undervoltage",
            severity=FaultSeverity.CRITICAL,
            domain=FaultDomain.POWER,
            causes=["regulator"],
            symptoms=["brownout_reset", "unpredictable_behavior"],
        ))

        self.add_node(FaultNode(
            node_id="regulator",
            name="Voltage Regulator",
            category="power",
            fault_type="regulator_failure",
            severity=FaultSeverity.FATAL,
            domain=FaultDomain.POWER,
            causes=["vdd"],
            symptoms=["no_power", "dead"],
        ))

        # DMA failures
        self.add_node(FaultNode(
            node_id="dma",
            name="DMA Controller",
            category="peripheral",
            fault_type="dma_error",
            severity=FaultSeverity.WARNING,
            domain=FaultDomain.DMA,
            causes=["memory_controller"],
            symptoms=["data_loss", "stall"],
        ))

        # Add edges
        self.add_edge("pll", "uart", "causes", "clock_loss")
        self.add_edge("hse", "pll", "causes", "clock_source_lost")
        self.add_edge("uart", "watchdog", "causes", "communication_timeout")
        self.add_edge("memory_controller", "flash", "causes", "memory_error")
        self.add_edge("memory_controller", "sram", "causes", "memory_error")
        self.add_edge("vdd", "regulator", "causes", "power_failure")
        self.add_edge("dma", "uart", "mitigated_by", "data_transfer")

    def add_node(self, node: FaultNode) -> None:
        """Add a fault node to the graph.

        Args:
            node: FaultNode to add
        """
        self._nodes[node.node_id] = node

        # Update index
        if node.category not in self._index:
            self._index[node.category] = []
        self._index[node.category].append(node.node_id)

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        relation: str = "causes",
        fault_type: str = "",
    ) -> None:
        """Add an edge between fault nodes.

        Args:
            source_id: Source node ID
            target_id: Target node ID
            relation: Edge type ("causes", "propagates_to", "mitigated_by", "prevented_by")
            fault_type: Specific fault type for this edge
        """
        if source_id not in self._nodes or target_id not in self._nodes:
            logger.warning(f"Cannot add edge: node not found ({source_id} or {target_id})")
            return

        if relation not in self._edges:
            self._edges[relation] = []

        self._edges[relation].append((source_id, target_id))

        # Also update node relationships
        if relation == "causes":
            self._nodes[source_id].causes.append(target_id)
            self._nodes[target_id].propagates_to.append(source_id)
        elif relation == "mitigated_by":
            self._nodes[source_id].mitigated_by.append(target_id)

    def get_node(self, node_id: str) -> FaultNode | None:
        """Get a fault node by ID."""
        return self._nodes.get(node_id)

    def get_propagation_path(
        self,
        source_id: str,
        target_id: str,
    ) -> list[str]:
        """Find shortest propagation path from source to target.

        Uses BFS to find the path.

        Args:
            source_id: Starting node ID
            target_id: Target node ID

        Returns:
            List of node IDs in path, or empty if no path
        """
        if source_id == target_id:
            return [source_id]

        if source_id not in self._nodes or target_id not in self._nodes:
            return []

        # BFS
        queue = deque([(source_id, [source_id])])
        visited = {source_id}

        while queue:
            current, path = queue.popleft()

            for _, next_id in self._edges.get("causes", []):
                if _ != current:
                    continue
                if next_id not in visited:
                    if next_id == target_id:
                        return path + [target_id]
                    visited.add(next_id)
                    queue.append((next_id, path + [next_id]))

            # Also follow propagation edges
            for next_id in self._nodes[current].causes:
                if next_id not in visited:
                    if next_id == target_id:
                        return path + [target_id]
                    visited.add(next_id)
                    queue.append((next_id, path + [next_id]))

        return []

    def get_root_causes(self, node_id: str) -> list[FaultNode]:
        """Find root causes that can lead to the given node.

        Args:
            node_id: Target node ID

        Returns:
            List of root cause fault nodes
        """
        root_causes: list[FaultNode] = []
        visited: set[str] = set()

        def dfs(nid: str) -> None:
            if nid in visited:
                return
            visited.add(nid)

            node = self._nodes.get(nid)
            if not node:
                return

            # Check if this is a root cause (no causes)
            if not node.propagates_to or all(p in visited for p in node.propagates_to):
                if node not in root_causes:
                    root_causes.append(node)

            for cause_id in node.propagates_to:
                dfs(cause_id)

        dfs(node_id)
        return root_causes

    def get_effects(self, node_id: str, depth: int = 10) -> list[FaultNode]:
        """Get all effects that can result from this node failing.

        Args:
            node_id: Starting node ID
            depth: Maximum depth to traverse

        Returns:
            List of affected fault nodes
        """
        effects: list[FaultNode] = []
        visited: set[str] = set()

        def dfs(nid: str, current_depth: int) -> None:
            if nid in visited or current_depth >= depth:
                return
            visited.add(nid)

            node = self._nodes.get(nid)
            if not node:
                return

            for cause_id in node.causes:
                if cause_id not in visited:
                    effects.append(self._nodes[cause_id])
                    dfs(cause_id, current_depth + 1)

        dfs(node_id, 0)
        return effects

    def get_mitigations(self, node_id: str) -> list[FaultNode]:
        """Get nodes that can mitigate the given fault.

        Args:
            node_id: Target node ID

        Returns:
            List of mitigating fault nodes
        """
        node = self._nodes.get(node_id)
        if not node:
            return []

        return [self._nodes[mid] for mid in node.mitigated_by if mid in self._nodes]

    def get_nodes_by_category(self, category: str) -> list[FaultNode]:
        """Get all nodes in a category.

        Args:
            category: Category name

        Returns:
            List of fault nodes
        """
        node_ids = self._index.get(category, [])
        return [self._nodes[nid] for nid in node_ids if nid in self._nodes]

    def get_fault_sequence(
        self,
        observed_symptoms: list[str],
    ) -> list[FaultNode]:
        """Infer likely fault sequence from observed symptoms.

        Args:
            observed_symptoms: List of observed symptoms

        Returns:
            Ordered list of likely fault nodes
        """
        candidates: list[tuple[int, FaultNode]] = []

        for node in self._nodes.values():
            matches = sum(1 for s in observed_symptoms if s in node.symptoms)
            if matches > 0:
                candidates.append((matches, node))

        # Sort by match count (descending) and severity
        candidates.sort(key=lambda x: (-x[0], x[1].severity.value))

        return [node for _, node in candidates]

    def explain_fault(
        self,
        node_id: str,
    ) -> dict[str, Any]:
        """Explain a fault in human-readable format.

        Args:
            node_id: Node ID

        Returns:
            Dictionary with fault explanation
        """
        node = self._nodes.get(node_id)
        if not node:
            return {"error": f"Unknown node: {node_id}"}

        root_causes = self.get_root_causes(node_id)
        effects = self.get_effects(node_id)
        mitigations = self.get_mitigations(node_id)

        return {
            "fault": node.to_dict(),
            "root_causes": [n.name for n in root_causes],
            "propagates_to": [n.name for n in effects],
            "can_be_mitigated_by": [n.name for n in mitigations],
            "recommended_actions": self._get_recommended_actions(node),
        }

    def _get_recommended_actions(self, node: FaultNode) -> list[str]:
        """Get recommended actions for a fault."""
        actions = []

        if node.fault_type == "clock_loss":
            actions.append("Check oscillator connections")
            actions.append("Verify PLL configuration")
            actions.append("Check decoupling capacitors")
        elif node.fault_type == "uart_timeout":
            actions.append("Increase timeout threshold")
            actions.append("Check baud rate configuration")
            actions.append("Verify TX/RX connections")
        elif node.fault_type == "watchdog_reset":
            actions.append("Increase watchdog timeout")
            actions.append("Check main loop execution time")
            actions.append("Ensure watchdog is being kicked")
        elif node.fault_type == "read_error":
            actions.append("Verify flash integrity")
            actions.append("Check memory timings")
            actions.append("Consider ECC if available")

        if node.mitigated_by:
            actions.append(f"Consider adding {node.mitigated_by[0]} for mitigation")

        return actions

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "node_count": len(self._nodes),
            "edge_counts": {rel: len(edges) for rel, edges in self._edges.items()},
            "categories": list(self._index.keys()),
            "nodes": {nid: node.to_dict() for nid, node in self._nodes.items()},
        }


# ============================================================================
# Global Instance
# ============================================================================


_default_graph: FaultPropagationGraph | None = None


def get_default_fault_graph() -> FaultPropagationGraph:
    """Get the default fault propagation graph instance."""
    global _default_graph
    if _default_graph is None:
        _default_graph = FaultPropagationGraph()
    return _default_graph

"""Causal reasoning engine (Phase 13b.2).

Provides causal reasoning for error analysis:
- Root cause graph construction
- Causal chain analysis
- Effect propagation
- Counterfactual reasoning
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class CausalType(Enum):
    """Causal relationship types."""
    CAUSES = "causes"
    ENABLES = "enables"
    INHIBITS = "inhibits"
    CORRELATES = "correlates"


@dataclass
class CausalNode:
    """Causal graph node."""
    node_id: str
    event: str  # The event or state
    event_type: str  # "error", "action", "state"
    
    # Properties
    probability: float = 1.0
    severity: str = "medium"
    
    # Evidence
    evidence: list[str] = field(default_factory=list)


@dataclass
class CausalEdge:
    """Causal relationship edge."""
    source_id: str
    target_id: str
    causal_type: CausalType
    
    # Strength
    strength: float = 1.0  # 0.0 - 1.0
    
    # Latency
    latency_ms: int = 0
    
    # Conditions
    conditions: list[str] = field(default_factory=list)


@dataclass
class RootCause:
    """Identified root cause."""
    cause_id: str
    node: CausalNode
    confidence: float
    chain: list[str]  # chain of nodes from effect to cause
    
    # Evidence
    supporting_evidence: list[str] = field(default_factory=list)
    
    # Recommendations
    fixes: list[str] = field(default_factory=list)


class CausalGraph:
    """Causal dependency graph."""
    
    def __init__(self) -> None:
        self._nodes: dict[str, CausalNode] = {}
        self._edges: list[CausalEdge] = []
        self._adjacency: dict[str, list[str]] = {}  # node -> [children]
        self._reverse_adjacency: dict[str, list[str]] = {}  # node -> [parents]
    
    def add_node(self, node: CausalNode) -> None:
        """Add node to graph."""
        self._nodes[node.node_id] = node
        if node.node_id not in self._adjacency:
            self._adjacency[node.node_id] = []
        if node.node_id not in self._reverse_adjacency:
            self._reverse_adjacency[node.node_id] = []
    
    def add_edge(self, edge: CausalEdge) -> None:
        """Add causal edge."""
        self._edges.append(edge)
        
        if edge.source_id not in self._adjacency:
            self._adjacency[edge.source_id] = []
        self._adjacency[edge.source_id].append(edge.target_id)
        
        if edge.target_id not in self._reverse_adjacency:
            self._reverse_adjacency[edge.target_id] = []
        self._reverse_adjacency[edge.target_id].append(edge.source_id)
    
    def get_ancestors(self, node_id: str) -> list[str]:
        """Get all ancestors (causes) of a node."""
        visited = set()
        queue = [node_id]
        
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            
            for parent in self._reverse_adjacency.get(current, []):
                queue.append(parent)
        
        visited.discard(node_id)
        return list(visited)
    
    def get_descendants(self, node_id: str) -> list[str]:
        """Get all descendants (effects) of a node."""
        visited = set()
        queue = [node_id]
        
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            
            for child in self._adjacency.get(current, []):
                queue.append(child)
        
        visited.discard(node_id)
        return list(visited)


class CausalReasoner:
    """Causal reasoning engine.
    
    Phase 13b.2: Causal reasoning - Lỗi → root cause graph
    """
    
    def __init__(self) -> None:
        self._graph = CausalGraph()
        self._patterns: dict[str, list[str]] = {}  # error_pattern -> [potential_causes]
    
    def add_observation(self, event: str, event_type: str) -> str:
        """Add observation to causal graph."""
        import hashlib
        node_id = hashlib.md5(event.encode()).hexdigest()[:8]
        
        node = CausalNode(
            node_id=node_id,
            event=event,
            event_type=event_type,
        )
        
        self._graph.add_node(node)
        return node_id
    
    def add_causal_link(
        self,
        cause_event: str,
        effect_event: str,
        causal_type: CausalType = CausalType.CAUSES,
    ) -> None:
        """Add causal link between events."""
        # Find or create nodes
        cause_id = None
        effect_id = None
        
        for node_id, node in self._graph._nodes.items():
            if node.event == cause_event:
                cause_id = node_id
            if node.event == effect_event:
                effect_id = node_id
        
        if not cause_id:
            cause_id = self.add_observation(cause_event, "unknown")
        if not effect_id:
            effect_id = self.add_observation(effect_event, "error")
        
        edge = CausalEdge(
            source_id=cause_id,
            target_id=effect_id,
            causal_type=causal_type,
        )
        
        self._graph.add_edge(edge)
    
    def find_root_causes(
        self,
        effect_event: str,
        max_depth: int = 5,
    ) -> list[RootCause]:
        """Find root causes of an effect."""
        # Find effect node
        effect_id = None
        for node_id, node in self._graph._nodes.items():
            if node.event == effect_event:
                effect_id = node_id
                break
        
        if not effect_id:
            return []
        
        # BFS to find root causes
        root_causes = []
        visited = set()
        queue = [(effect_id, [effect_id])]
        
        while queue:
            current_id, chain = queue.pop(0)
            
            if len(chain) > max_depth:
                continue
            
            parents = self._graph._reverse_adjacency.get(current_id, [])
            
            if not parents:
                # This is a root cause
                node = self._graph._nodes[current_id]
                root_cause = RootCause(
                    cause_id=current_id,
                    node=node,
                    confidence=0.8 ** len(chain),  # Confidence decreases with depth
                    chain=list(reversed(chain)),
                )
                root_causes.append(root_cause)
            else:
                for parent_id in parents:
                    if parent_id not in visited:
                        visited.add(parent_id)
                        queue.append((parent_id, chain + [parent_id]))
        
        # Sort by confidence
        root_causes.sort(key=lambda rc: rc.confidence, reverse=True)
        return root_causes
    
    def explain_effect(
        self,
        effect_event: str,
    ) -> dict[str, Any]:
        """Explain an effect with causal chain."""
        root_causes = self.find_root_causes(effect_event)
        
        # Build explanation
        chains = []
        for rc in root_causes[:3]:  # Top 3
            chain_events = [self._graph._nodes[n].event for n in rc.chain]
            chains.append({
                "chain": chain_events,
                "confidence": rc.confidence,
            })
        
        return {
            "effect": effect_event,
            "root_causes": len(root_causes),
            "chains": chains,
        }
    
    def suggest_fixes(self, root_cause: RootCause) -> list[str]:
        """Suggest fixes for a root cause."""
        fixes = []
        
        cause_event = root_cause.node.event.lower()
        
        if "null" in cause_event or "pointer" in cause_event:
            fixes.append("Add null pointer check")
            fixes.append("Use safe pointer wrapper")
        
        if "memory" in cause_event or "leak" in cause_event:
            fixes.append("Add memory leak detection")
            fixes.append("Review allocation/deallocation pairs")
        
        if "overflow" in cause_event:
            fixes.append("Add bounds checking")
            fixes.append("Use safe integer operations")
        
        if "race" in cause_event or "concurrent" in cause_event:
            fixes.append("Add proper synchronization")
            fixes.append("Review critical sections")
        
        # Default
        if not fixes:
            fixes.append("Review code at this location")
            fixes.append("Add defensive checks")
        
        return fixes
    
    def get_causal_graph(self) -> CausalGraph:
        """Get the causal graph."""
        return self._graph


# Global reasoner
_causal_reasoner: CausalReasoner | None = None


def get_causal_reasoner() -> CausalReasoner:
    """Get global causal reasoner."""
    global _causal_reasoner
    if _causal_reasoner is None:
        _causal_reasoner = CausalReasoner()
    return _causal_reasoner


if __name__ == "__main__":
    reasoner = get_causal_reasoner()
    
    print("Causal Reasoning Engine")
    print("=" * 40)
    
    # Add causal chain
    reasoner.add_observation("memory_alloc_fail", "error")
    reasoner.add_observation("heap_corruption", "error")
    reasoner.add_observation("hardfault", "error")
    
    reasoner.add_causal_link("memory_alloc_fail", "heap_corruption")
    reasoner.add_causal_link("heap_corruption", "hardfault")
    
    # Explain effect
    explanation = reasoner.explain_effect("hardfault")
    print(f"Effect: {explanation['effect']}")
    print(f"Root causes: {explanation['root_causes']}")
    
    for chain in explanation['chains']:
        print(f"  Chain: {' -> '.join(chain['chain'])} ({chain['confidence']:.2f})")

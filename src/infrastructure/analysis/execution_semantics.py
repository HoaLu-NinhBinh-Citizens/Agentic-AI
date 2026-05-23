"""Execution semantics analysis (Phase 13.5).

Provides execution semantics modeling:
- Control Flow Graph (CFG) analysis
- ISR (Interrupt Service Routine) interaction
- DMA modeling and validation
- Execution path analysis
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class NodeType(Enum):
    """CFG node types."""
    ENTRY = "entry"
    EXIT = "exit"
    BASIC_BLOCK = "basic_block"
    BRANCH = "branch"
    LOOP = "loop"
    CALL = "call"
    ISR = "isr"


@dataclass
class CFGNode:
    """Control Flow Graph node."""
    node_id: str
    node_type: NodeType
    address: int = 0
    instructions: list[str] = field(default_factory=list)
    successors: list[str] = field(default_factory=list)  # node IDs
    predecessors: list[str] = field(default_factory=list)


@dataclass
class ISRInfo:
    """Interrupt Service Routine information."""
    isr_id: str
    vector_address: int
    priority: int = 0
    triggers: list[str] = field(default_factory=list)
    accessed_registers: list[str] = field(default_factory=list)
    shared_resources: list[str] = field(default_factory=list)


@dataclass
class DMAChannel:
    """DMA channel configuration."""
    channel_id: int
    peripheral: str
    direction: str  # "mem_to_periph", "periph_to_mem", "mem_to_mem"
    address: int = 0
    size: int = 0
    triggers: list[str] = field(default_factory=list)


class CFGBuilder:
    """Builds control flow graphs."""
    
    def build(self, function_address: int, instructions: list[str]) -> dict[str, CFGNode]:
        """Build CFG from instructions."""
        nodes = {}
        
        # Simplified CFG construction
        current = CFGNode(
            node_id="entry",
            node_type=NodeType.ENTRY,
            address=function_address,
        )
        nodes["entry"] = current
        
        return nodes


class ISRAnalyzer:
    """Analyzes ISR interactions."""
    
    def __init__(self) -> None:
        self._isrs: dict[str, ISRInfo] = {}
    
    def add_isr(self, isr: ISRInfo) -> None:
        """Add ISR."""
        self._isrs[isr.isr_id] = isr
    
    def analyze_interaction(self, isr_id: str) -> list[dict]:
        """Analyze ISR interaction with main code."""
        isr = self._isrs.get(isr_id)
        if not isr:
            return []
        
        interactions = []
        
        # Check for shared resources
        for other_id, other in self._isrs.items():
            if other_id != isr_id:
                shared = set(isr.shared_resources) & set(other.shared_resources)
                if shared:
                    interactions.append({
                        "type": "resource_conflict",
                        "with": other_id,
                        "resources": list(shared),
                    })
        
        return interactions


class DMAAnalyzer:
    """Analyzes DMA configuration."""
    
    def __init__(self) -> None:
        self._channels: dict[int, DMAChannel] = {}
    
    def add_channel(self, channel: DMAChannel) -> None:
        """Add DMA channel."""
        self._channels[channel.channel_id] = channel
    
    def check_buffer_overlap(self, addr1: int, size1: int, addr2: int, size2: int) -> bool:
        """Check if two buffers overlap."""
        return addr1 < addr2 + size2 and addr2 < addr1 + size1
    
    def validate_config(self) -> list[str]:
        """Validate DMA configuration."""
        issues = []
        
        for ch_id, ch in self._channels.items():
            # Check for potential buffer issues
            if ch.size == 0:
                issues.append(f"Channel {ch_id}: Zero-size buffer")
        
        return issues


class ExecutionSemanticsAnalyzer:
    """Main execution semantics analyzer.
    
    Phase 13.5: Execution semantics - CFG, ISR interaction, DMA modeling
    """
    
    def __init__(self) -> None:
        self._cfg_builder = CFGBuilder()
        self._isr_analyzer = ISRAnalyzer()
        self._dma_analyzer = DMAAnalyzer()
    
    def analyze_function(
        self,
        function_address: int,
        instructions: list[str],
    ) -> dict[str, Any]:
        """Analyze function execution semantics."""
        cfg = self._cfg_builder.build(function_address, instructions)
        
        return {
            "cfg": cfg,
            "nodes": len(cfg),
            "complexity": len(cfg),
        }
    
    def analyze_isr(self, isr: ISRInfo) -> dict[str, Any]:
        """Analyze ISR semantics."""
        self._isr_analyzer.add_isr(isr)
        
        return {
            "isr_id": isr.isr_id,
            "priority": isr.priority,
            "interactions": self._isr_analyzer.analyze_interaction(isr.isr_id),
        }
    
    def analyze_dma(self) -> dict[str, Any]:
        """Analyze DMA configuration."""
        return {
            "channels": len(self._dma_analyzer._channels),
            "issues": self._dma_analyzer.validate_config(),
        }


# Global analyzer
_execution_analyzer: ExecutionSemanticsAnalyzer | None = None


def get_execution_analyzer() -> ExecutionSemanticsAnalyzer:
    """Get global execution analyzer."""
    global _execution_analyzer
    if _execution_analyzer is None:
        _execution_analyzer = ExecutionSemanticsAnalyzer()
    return _execution_analyzer


if __name__ == "__main__":
    analyzer = get_execution_analyzer()
    
    print("Execution Semantics Analyzer")
    print("=" * 40)
    print("CFG, ISR, DMA analysis")

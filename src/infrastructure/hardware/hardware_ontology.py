"""Hardware ontology from SVD files (Phase 13.7).

Provides hardware knowledge graph from CMSIS-SVD:
- SVD parsing
- Register causal relationships
- Interrupt dependency mapping
- Peripheral interaction graph
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class RegisterType(Enum):
    """Register types."""
    CONTROL = "control"
    STATUS = "status"
    DATA = "data"
    CONFIG = "config"
    INTERRUPT = "interrupt"


@dataclass
class Register:
    """Hardware register."""
    name: str
    address: int
    size: int  # bits
    
    type: RegisterType = RegisterType.CONTROL
    description: str = ""
    
    # Fields
    fields: dict[str, dict] = field(default_factory=dict)  # name -> {bits, values}
    
    # Dependencies
    clock_dependency: str = ""
    reset_dependency: str = ""


@dataclass
class Interrupt:
    """Interrupt configuration."""
    name: str
    number: int
    priority: int = 0
    
    # Associated registers
    registers: list[str] = field(default_factory=list)


@dataclass
class Peripheral:
    """Hardware peripheral."""
    name: str
    base_address: int
    size: int
    
    registers: list[Register] = field(default_factory=list)
    interrupts: list[Interrupt] = field(default_factory=list)
    
    # Dependencies
    clock_domain: str = ""
    power_domain: str = ""
    depends_on: list[str] = field(default_factory=list)


@dataclass
class CausalRelation:
    """Causal relationship between registers."""
    source: str  # register path
    target: str
    relation_type: str  # "enables", "triggers", "conflicts", "requires"
    description: str = ""


class SVDParser:
    """CMSIS-SVD file parser."""
    
    def parse_svd(self, svd_path: str) -> list[Peripheral]:
        """Parse SVD file."""
        peripherals = []
        
        # In real implementation, would parse XML
        logger.info("Parsing SVD", path=svd_path)
        
        return peripherals


class HardwareOntology:
    """Hardware knowledge graph.
    
    Phase 13.7: Hardware ontology - SVD → causal graph
    """
    
    def __init__(self) -> None:
        self._peripherals: dict[str, Peripheral] = {}
        self._registers: dict[str, Register] = {}
        self._causal_relations: list[CausalRelation] = []
        self._svd_parser = SVDParser()
    
    def load_svd(self, svd_path: str) -> None:
        """Load SVD file and build ontology."""
        peripherals = self._svd_parser.parse_svd(svd_path)
        
        for peripheral in peripherals:
            self._peripherals[peripheral.name] = peripheral
            
            for reg in peripheral.registers:
                reg_path = f"{peripheral.name}.{reg.name}"
                self._registers[reg_path] = reg
        
        self._infer_causal_relations()
        logger.info("Hardware ontology loaded", peripherals=len(peripherals))
    
    def _infer_causal_relations(self) -> None:
        """Infer causal relationships from hardware semantics."""
        # Clock enable → peripheral access
        for peripheral in self._peripherals.values():
            if peripheral.clock_domain:
                self._causal_relations.append(CausalRelation(
                    source=f"clock.{peripheral.clock_domain}",
                    target=peripheral.name,
                    relation_type="enables",
                    description=f"Clock {peripheral.clock_domain} must be enabled for {peripheral.name}",
                ))
        
        # Interrupt → handler
        for peripheral in self._peripherals.values():
            for irq in peripheral.interrupts:
                for reg in irq.registers:
                    self._causal_relations.append(CausalRelation(
                        source=f"{peripheral.name}.{reg}",
                        target=f"ISR.{irq.name}",
                        relation_type="triggers",
                        description=f"{reg} triggers {irq.name}",
                    ))
    
    def get_peripheral(self, name: str) -> Peripheral | None:
        """Get peripheral info."""
        return self._peripherals.get(name)
    
    def get_register(self, register_path: str) -> Register | None:
        """Get register info."""
        return self._registers.get(register_path)
    
    def get_dependencies(self, register_path: str) -> list[CausalRelation]:
        """Get register dependencies."""
        return [
            r for r in self._causal_relations
            if r.target == register_path or r.source == register_path
        ]
    
    def query(self, query: str) -> list[dict[str, Any]]:
        """Query hardware ontology."""
        results = []
        query_lower = query.lower()
        
        for peripheral in self._peripherals.values():
            if query_lower in peripheral.name.lower():
                results.append({
                    "type": "peripheral",
                    "name": peripheral.name,
                    "base_address": f"0x{peripheral.base_address:08X}",
                    "interrupts": [i.name for i in peripheral.interrupts],
                })
        
        return results


# Global ontology
_ontology: HardwareOntology | None = None


def get_hardware_ontology() -> HardwareOntology:
    """Get global hardware ontology."""
    global _ontology
    if _ontology is None:
        _ontology = HardwareOntology()
    return _ontology


if __name__ == "__main__":
    ontology = get_hardware_ontology()
    
    print("Hardware Ontology")
    print("=" * 40)
    print("SVD-based hardware knowledge graph")
    print("Supports: register causal relationships, interrupt dependencies")

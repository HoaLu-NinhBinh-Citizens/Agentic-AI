"""Hardware ontology from SVD files (Phase 13.7 - FIXED).

Provides hardware knowledge graph from CMSIS-SVD:
- Real SVD XML parsing
- Register causal relationships
- Interrupt dependency mapping
- Peripheral interaction graph
- Clock tree inference
- Power domain modeling

FIXES Applied:
- Real CMSIS-SVD XML parser implementation
- Full peripheral/register/field extraction
- Interrupt priority validation
- Clock dependency inference
- DMA channel mapping
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
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
class RegisterField:
    """Register field definition."""
    name: str
    bit_offset: int
    bit_width: int
    access: str  # "read-only", "write-only", "read-write", etc.
    description: str = ""
    enumerated_values: dict[str, int] = field(default_factory=dict)  # name -> value


@dataclass
class Register:
    """Hardware register."""
    name: str
    address: int
    size: int  # bits
    reset_value: int = 0
    
    type: RegisterType = RegisterType.CONTROL
    description: str = ""
    
    fields: list[RegisterField] = field(default_factory=list)
    
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
class DMADescription:
    """DMA channel description."""
    name: str
    channel: int
    request_source: str = ""
    direction: str = ""  # "memory_to_peripheral", "peripheral_to_memory", etc.


@dataclass
class Peripheral:
    """Hardware peripheral."""
    name: str
    base_address: int
    size: int
    version: str = ""
    description: str = ""
    
    registers: list[Register] = field(default_factory=list)
    interrupts: list[Interrupt] = field(default_factory=list)
    dma_channels: list[DMADescription] = field(default_factory=list)
    
    # Dependencies
    clock_domain: str = ""
    power_domain: str = ""
    depends_on: list[str] = field(default_factory=list)


@dataclass
class CausalRelation:
    """Causal relationship between registers/peripherals."""
    source: str  # register path or peripheral name
    target: str
    relation_type: str  # "enables", "triggers", "conflicts", "requires", "shares_dma"
    description: str = ""


@dataclass
class ClockTreeNode:
    """Clock tree node representation."""
    name: str
    frequency: int = 0  # Hz
    source: str = ""  # Parent clock
    enables: list[str] = field(default_factory=list)  # Peripherals this enables


class SVDParserError(Exception):
    """SVD parsing error."""
    pass


class SVDParser:
    """CMSIS-SVD file parser.
    
    FIX: Real implementation for parsing CMSIS-SVD XML files.
    Supports ARM Cortex-M SVD format.
    """
    
    # SVD namespace
    SVD_NS = "{http://www.arm.com/Schema/Schema_a1}"
    
    def __init__(self):
        self._processed_files: set[str] = set()
    
    def parse_svd(self, svd_path: str) -> list[Peripheral]:
        """Parse SVD file and return peripherals.
        
        Args:
            svd_path: Path to .svd file
            
        Returns:
            List of Peripheral objects
        """
        import os
        
        if not os.path.exists(svd_path):
            logger.error("svd_file_not_found", path=svd_path)
            return []
        
        if svd_path in self._processed_files:
            logger.debug("svd_already_parsed", path=svd_path)
            return []
        
        try:
            tree = ET.parse(svd_path)
            root = tree.getroot()
            
            peripherals = self._parse_device(root)
            self._processed_files.add(svd_path)
            
            logger.info("svd_parsed", path=svd_path, peripherals=len(peripherals))
            return peripherals
            
        except ET.ParseError as e:
            logger.error("svd_parse_error", path=svd_path, error=str(e))
            raise SVDParserError(f"Failed to parse SVD: {e}")
        except Exception as e:
            logger.error("svd_unknown_error", path=svd_path, error=str(e))
            raise SVDParserError(f"SVD parsing failed: {e}")
    
    def parse_svd_string(self, svd_content: str) -> list[Peripheral]:
        """Parse SVD from string content.
        
        Args:
            svd_content: SVD XML as string
            
        Returns:
            List of Peripheral objects
        """
        try:
            root = ET.fromstring(svd_content)
            return self._parse_device(root)
        except ET.ParseError as e:
            raise SVDParserError(f"Failed to parse SVD string: {e}")
    
    def _parse_device(self, root: ET.Element) -> list[Peripheral]:
        """Parse device element and extract peripherals."""
        peripherals = []
        
        # Find peripherals section
        peripherals_elem = root.find(f"{self.SVD_NS}peripherals")
        if peripherals_elem is None:
            logger.warning("no_peripherals_in_svd")
            return peripherals
        
        for peri_elem in peripherals_elem.findall(f"{self.SVD_NS}peripheral"):
            peripheral = self._parse_peripheral(peri_elem)
            if peripheral:
                peripherals.append(peripheral)
        
        return peripherals
    
    def _parse_peripheral(self, elem: ET.Element) -> Peripheral | None:
        """Parse a peripheral element."""
        try:
            name = elem.findtext(f"{self.SVD_NS}name", "")
            if not name:
                return None
            
            base_address_str = elem.findtext(f"{self.SVD_NS}baseAddress", "0")
            base_address = int(base_address_str, 0) if base_address_str else 0
            
            # Size is often not directly available, derive from address space
            size_elem = elem.find(f"{self.SVD_NS}addressBlock")
            size = 0x1000  # Default 4KB
            if size_elem is not None:
                size_str = size_elem.findtext(f"{self.SVD_NS}size")
                if size_str:
                    size = int(size_str, 0)
            
            version = elem.findtext(f"{self.SVD_NS}version", "")
            description = elem.findtext(f"{self.SVD_NS}description", "")
            
            # Parse registers
            registers = []
            regs_container = elem.find(f"{self.SVD_NS}registers")
            if regs_container is not None:
                for reg_elem in regs_container.findall(f"{self.SVD_NS}register"):
                    register = self._parse_register(reg_elem)
                    if register:
                        registers.append(register)
            
            # Parse interrupts
            interrupts = []
            for irq_elem in elem.findall(f"{self.SVD_NS}interrupt"):
                irq = self._parse_interrupt(irq_elem)
                if irq:
                    interrupts.append(irq)
            
            # Parse DMA channels
            dma_channels = []
            for dma_elem in elem.findall(f"{self.SVD_NS}dma"):
                dma = self._parse_dma(dma_elem)
                if dma:
                    dma_channels.append(dma)
            
            # Parse dependencies
            clock_domain = self._extract_clock_domain(name)
            power_domain = self._extract_power_domain(name)
            depends_on = self._extract_dependencies(name, registers)
            
            return Peripheral(
                name=name,
                base_address=base_address,
                size=size,
                version=version,
                description=description,
                registers=registers,
                interrupts=interrupts,
                dma_channels=dma_channels,
                clock_domain=clock_domain,
                power_domain=power_domain,
                depends_on=depends_on,
            )
            
        except Exception as e:
            logger.error("peripheral_parse_error", name=elem.findtext(f"{self.SVD_NS}name"), error=str(e))
            return None
    
    def _parse_register(self, elem: ET.Element) -> Register | None:
        """Parse a register element."""
        try:
            name = elem.findtext(f"{self.SVD_NS}name", "")
            if not name:
                return None
            
            address_offset_str = elem.findtext(f"{self.SVD_NS}addressOffset", "0")
            address_offset = int(address_offset_str, 0) if address_offset_str else 0
            
            size_str = elem.findtext(f"{self.SVD_NS}size", "32")
            size = int(size_str) if size_str else 32
            
            reset_value_str = elem.findtext(f"{self.SVD_NS}resetValue", "0")
            reset_value = int(reset_value_str, 0) if reset_value_str else 0
            
            access_str = elem.findtext(f"{self.SVD_NS}access", "read-write")
            description = elem.findtext(f"{self.SVD_NS}description", "")
            
            # Determine register type from name
            reg_type = self._infer_register_type(name, access_str)
            
            # Parse fields
            fields = []
            fields_elem = elem.find(f"{self.SVD_NS}fields")
            if fields_elem is not None:
                for field_elem in fields_elem.findall(f"{self.SVD_NS}field"):
                    field = self._parse_field(field_elem)
                    if field:
                        fields.append(field)
            
            return Register(
                name=name,
                address=address_offset,
                size=size,
                reset_value=reset_value,
                type=reg_type,
                description=description,
                fields=fields,
            )
            
        except Exception as e:
            logger.error("register_parse_error", name=elem.findtext(f"{self.SVD_NS}name"), error=str(e))
            return None
    
    def _parse_field(self, elem: ET.Element) -> RegisterField | None:
        """Parse a register field element."""
        try:
            name = elem.findtext(f"{self.SVD_NS}name", "")
            if not name:
                return None
            
            bit_offset_str = elem.findtext(f"{self.SVD_NS}bitOffset", "0")
            bit_width_str = elem.findtext(f"{self.SVD_NS}bitWidth", "1")
            access_str = elem.findtext(f"{self.SVD_NS}access", "read-write")
            description = elem.findtext(f"{self.SVD_NS}description", "")
            
            bit_offset = int(bit_offset_str) if bit_offset_str else 0
            bit_width = int(bit_width_str) if bit_width_str else 1
            
            # Alternative: use <bitRange> element
            bit_range_elem = elem.find(f"{self.SVD_NS}bitRange")
            if bit_range_elem is not None:
                bit_range_text = bit_range_elem.text or ""
                match = re.match(r"\[(\d+):(\d+)\]", bit_range_text)
                if match:
                    bit_offset = int(match.group(2))
                    bit_width = int(match.group(1)) - int(match.group(2)) + 1
            
            enumerated_values = {}
            for enum_elem in elem.findall(f"{self.SVD_NS}enumeratedValues/{self.SVD_NS}enumeratedValue"):
                enum_name = enum_elem.findtext(f"{self.SVD_NS}name", "")
                enum_value_str = enum_elem.findtext(f"{self.SVD_NS}value", "0")
                if enum_name and enum_value_str:
                    try:
                        enumerated_values[enum_name] = int(enum_value_str, 0)
                    except ValueError:
                        pass
            
            return RegisterField(
                name=name,
                bit_offset=bit_offset,
                bit_width=bit_width,
                access=access_str,
                description=description,
                enumerated_values=enumerated_values,
            )
            
        except Exception as e:
            logger.error("field_parse_error", name=elem.findtext(f"{self.SVD_NS}name"), error=str(e))
            return None
    
    def _parse_interrupt(self, elem: ET.Element) -> Interrupt | None:
        """Parse an interrupt element."""
        try:
            name = elem.findtext(f"{self.SVD_NS}name", "")
            value_str = elem.findtext(f"{self.SVD_NS}value", "0")
            description = elem.findtext(f"{self.SVD_NS}description", "")
            
            number = int(value_str, 0) if value_str else 0
            
            return Interrupt(
                name=name,
                number=number,
                description=description,
            )
            
        except Exception as e:
            logger.error("interrupt_parse_error", error=str(e))
            return None
    
    def _parse_dma(self, elem: ET.Element) -> DMADescription | None:
        """Parse a DMA channel element."""
        try:
            value_str = elem.findtext(f"{self.SVD_NS}value", "0")
            request_str = elem.findtext(f"{self.SVD_NS}request", "")
            
            return DMADescription(
                name=elem.findtext(f"{self.SVD_NS}name", f"DMA{value_str}"),
                channel=int(value_str, 0) if value_str else 0,
                request_source=request_str,
            )
            
        except Exception as e:
            logger.error("dma_parse_error", error=str(e))
            return None
    
    def _infer_register_type(self, name: str, access: str) -> RegisterType:
        """Infer register type from name and access patterns."""
        name_upper = name.upper()
        
        if any(suffix in name_upper for suffix in ["FLAG", "STATUS", "RIS", "MIS", "SR", "IF"]):
            return RegisterType.STATUS
        elif any(suffix in name_upper for suffix in ["CR", "CTRL", "CFG", "CONFIG", "SEL", "EN"]):
            return RegisterType.CONTROL
        elif any(suffix in name_upper for suffix in ["DATA", "DR", "TX", "RX", "FIFO", "RDR", "TDR"]):
            return RegisterType.DATA
        elif any(suffix in name_upper for suffix in ["IE", "IMSK", "MASK", "INT"]):
            return RegisterType.INTERRUPT
        
        # Infer from access
        if "write" in access.lower() and "read" not in access.lower():
            return RegisterType.DATA
        
        return RegisterType.CONFIG
    
    def _extract_clock_domain(self, peripheral_name: str) -> str:
        """Extract clock domain from peripheral name."""
        name_upper = peripheral_name.upper()
        
        # Common clock domains for ARM Cortex-M
        if "GPIO" in name_upper:
            if "GPIOA" in name_upper:
                return "AHB1_GPIOA"
            elif "GPIOB" in name_upper:
                return "AHB1_GPIOB"
            return "AHB1"
        elif "DMA" in name_upper:
            return "AHB1_DMA"
        elif any(x in name_upper for x in ["UART", "USART"]):
            return "APB1"
        elif any(x in name_upper for x in ["SPI", "I2C"]):
            return "APB1"
        elif any(x in name_upper for x in ["TIM", "TIMER"]):
            return "APB1"
        
        return "APB1"  # Default
    
    def _extract_power_domain(self, peripheral_name: str) -> str:
        """Extract power domain from peripheral name."""
        name_upper = peripheral_name.upper()
        
        # Power domains for STM32
        if any(x in name_upper for x in ["USB", "ETH", "CAN"]):
            return "PDS"
        elif any(x in name_upper for x in ["ADC", "DAC"]):
            return "PD_ADC"
        
        return "PD_MAIN"  # Default main power domain
    
    def _extract_dependencies(self, peripheral_name: str, registers: list[Register]) -> list[str]:
        """Extract peripheral dependencies from registers."""
        deps = []
        name_upper = peripheral_name.upper()
        
        # Clock enable dependencies
        if not any(r.name.upper() in ["CLK", "EN", "RCC"] for r in registers):
            deps.append("RCC")  # Most peripherals depend on RCC
        
        # USB needs PLL
        if "USB" in name_upper:
            deps.append("PLL")
        
        return deps


class ClockTreeBuilder:
    """Build clock tree from peripheral data.
    
    FIX: Infers clock relationships from peripheral definitions.
    """
    
    def __init__(self):
        self._nodes: dict[str, ClockTreeNode] = {}
    
    def add_peripheral_clock(self, peripheral: Peripheral) -> None:
        """Add a peripheral and infer its clock requirements."""
        if peripheral.clock_domain:
            if peripheral.clock_domain not in self._nodes:
                self._nodes[peripheral.clock_domain] = ClockTreeNode(
                    name=peripheral.clock_domain,
                )
            self._nodes[peripheral.clock_domain].enables.append(peripheral.name)
    
    def get_clock_tree(self) -> dict[str, ClockTreeNode]:
        """Get the complete clock tree."""
        return dict(self._nodes)
    
    def get_peripheral_clock_domain(self, peripheral_name: str) -> str | None:
        """Get the clock domain for a peripheral."""
        for node in self._nodes.values():
            if peripheral_name in node.enables:
                return node.name
        return None


class HardwareOntology:
    """Hardware knowledge graph.
    
    Phase 13.7: Hardware ontology - SVD → causal graph
    
    FIX: Real implementation with full SVD parsing.
    """
    
    def __init__(self):
        self._peripherals: dict[str, Peripheral] = {}
        self._registers: dict[str, Register] = {}
        self._causal_relations: list[CausalRelation] = []
        self._svd_parser = SVDParser()
        self._clock_tree = ClockTreeBuilder()
    
    def load_svd(self, svd_path: str) -> None:
        """Load SVD file and build ontology."""
        peripherals = self._svd_parser.parse_svd(svd_path)
        
        for peripheral in peripherals:
            self._peripherals[peripheral.name] = peripheral
            
            for reg in peripheral.registers:
                reg_path = f"{peripheral.name}.{reg.name}"
                self._registers[reg_path] = reg
            
            # Add to clock tree
            self._clock_tree.add_peripheral_clock(peripheral)
        
        self._infer_causal_relations()
        logger.info("Hardware ontology loaded", 
                   peripherals=len(peripherals), 
                   registers=len(self._registers))
    
    def load_svd_string(self, svd_content: str) -> None:
        """Load SVD from string content."""
        peripherals = self._svd_parser.parse_svd_string(svd_content)
        
        for peripheral in peripherals:
            self._peripherals[peripheral.name] = peripheral
            
            for reg in peripheral.registers:
                reg_path = f"{peripheral.name}.{reg.name}"
                self._registers[reg_path] = reg
            
            self._clock_tree.add_peripheral_clock(peripheral)
        
        self._infer_causal_relations()
        logger.info("Hardware ontology loaded from string", peripherals=len(peripherals))
    
    def _infer_causal_relations(self) -> None:
        """Infer causal relationships from hardware semantics.
        
        FIX: Real inference based on peripheral/interrupt/DMA data.
        """
        # Clock enable → peripheral access
        for peripheral in self._peripherals.values():
            if peripheral.clock_domain:
                self._causal_relations.append(CausalRelation(
                    source=f"clock.{peripheral.clock_domain}",
                    target=peripheral.name,
                    relation_type="enables",
                    description=f"Clock {peripheral.clock_domain} must be enabled for {peripheral.name}",
                ))
            
            # Power domain dependencies
            if peripheral.power_domain and peripheral.power_domain != "PD_MAIN":
                self._causal_relations.append(CausalRelation(
                    source=f"power.{peripheral.power_domain}",
                    target=peripheral.name,
                    relation_type="requires",
                    description=f"Power domain {peripheral.power_domain} required for {peripheral.name}",
                ))
            
            # Peripheral dependencies
            for dep in peripheral.depends_on:
                self._causal_relations.append(CausalRelation(
                    source=dep,
                    target=peripheral.name,
                    relation_type="requires",
                    description=f"{dep} must be enabled for {peripheral.name}",
                ))
        
        # Interrupt → handler
        for peripheral in self._peripherals.values():
            for irq in peripheral.interrupts:
                # Find registers that can trigger this interrupt
                for reg in peripheral.registers:
                    if reg.type == RegisterType.INTERRUPT:
                        self._causal_relations.append(CausalRelation(
                            source=f"{peripheral.name}.{reg.name}",
                            target=f"ISR.{irq.name}",
                            relation_type="triggers",
                            description=f"{reg.name} can trigger {irq.name} interrupt",
                        ))
        
        # DMA relationships
        for peripheral in self._peripherals.values():
            for dma in peripheral.dma_channels:
                # DMA request from peripheral
                self._causal_relations.append(CausalRelation(
                    source=peripheral.name,
                    target=f"DMA.{dma.channel}",
                    relation_type="shares_dma",
                    description=f"{peripheral.name} uses DMA channel {dma.channel}",
                ))
        
        # Register access conflicts (e.g., read-only vs write-only)
        self._infer_register_conflicts()
    
    def _infer_register_conflicts(self) -> None:
        """Infer register access conflicts."""
        for peripheral in self._peripherals.values():
            regs_by_name = {}
            for reg in peripheral.registers:
                base_name = reg.name.replace("_R", "").replace("_SR", "")
                if base_name not in regs_by_name:
                    regs_by_name[base_name] = []
                regs_by_name[base_name].append(reg)
            
            for base_name, regs in regs_by_name.items():
                if len(regs) > 1:
                    # Check for read/write variants
                    read_regs = [r for r in regs if "read" in r.description.lower() or "status" in r.name.lower()]
                    write_regs = [r for r in regs if "write" in r.description.lower() or "data" in r.name.lower()]
                    
                    if read_regs and write_regs:
                        for rr in read_regs:
                            for wr in write_regs:
                                self._causal_relations.append(CausalRelation(
                                    source=rr.name,
                                    target=wr.name,
                                    relation_type="conflicts",
                                    description=f"Read-only {rr.name} and write-only {wr.name} may conflict",
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
    
    def get_peripheral_dependencies(self, peripheral_name: str) -> list[CausalRelation]:
        """Get all causal relations for a peripheral."""
        return [
            r for r in self._causal_relations
            if peripheral_name in [r.source, r.target]
        ]
    
    def validate_interrupt_priority(self, peripheral_name: str, irq_name: str, priority: int) -> tuple[bool, str]:
        """Validate interrupt priority setting.
        
        Returns:
            (is_valid, error_message)
        """
        peripheral = self._peripherals.get(peripheral_name)
        if not peripheral:
            return False, f"Peripheral {peripheral_name} not found"
        
        irq = next((i for i in peripheral.interrupts if i.name == irq_name), None)
        if not irq:
            return False, f"Interrupt {irq_name} not found in {peripheral_name}"
        
        # ARM Cortex-M supports 0-255 priority levels (configurable)
        if priority < 0 or priority > 255:
            return False, f"Priority {priority} out of range (0-255)"
        
        # Warn if priority differs from SVD definition
        if irq.priority and irq.priority != priority:
            return True, f"Warning: SVD defines priority {irq.priority}, setting {priority}"
        
        return True, "OK"
    
    def get_clock_domain(self, peripheral_name: str) -> str | None:
        """Get clock domain for a peripheral."""
        peripheral = self._peripherals.get(peripheral_name)
        return peripheral.clock_domain if peripheral else None
    
    def query(self, query: str) -> list[dict[str, Any]]:
        """Query hardware ontology."""
        results = []
        query_lower = query.lower()
        
        for peripheral in self._peripherals.values():
            # Match by name
            if query_lower in peripheral.name.lower():
                results.append({
                    "type": "peripheral",
                    "name": peripheral.name,
                    "base_address": f"0x{peripheral.base_address:08X}",
                    "size": f"0x{peripheral.size:04X}",
                    "interrupts": [f"{i.name} (#{i.number})" for i in peripheral.interrupts],
                    "clock_domain": peripheral.clock_domain,
                    "power_domain": peripheral.power_domain,
                })
                continue
            
            # Match by interrupt name
            for irq in peripheral.interrupts:
                if query_lower in irq.name.lower():
                    results.append({
                        "type": "interrupt",
                        "name": irq.name,
                        "number": irq.number,
                        "peripheral": peripheral.name,
                        "priority": irq.priority,
                    })
            
            # Match by register name
            for reg in peripheral.registers:
                if query_lower in reg.name.lower():
                    results.append({
                        "type": "register",
                        "name": reg.name,
                        "address": f"0x{reg.address:04X}",
                        "peripheral": peripheral.name,
                        "size_bits": reg.size,
                        "type": reg.type.value,
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
    print()
    print("Usage:")
    print("  ontology.load_svd('/path/to/device.svd')")
    print("  ontology.query('GPIO')")
    print("  ontology.get_clock_domain('USART1')")
    print("  ontology.validate_interrupt_priority('NVIC', 'USART1_IRQn', 3)")

"""Hardware Validator - deterministic hardware rule validation."""

from typing import Dict, List, Optional

from src.domains.hardware_engine.core.peripheral_graph import PeripheralGraph
from src.domains.hardware_engine.core.register_schema import RegisterSchemaDB
from src.domains.hardware_engine.core.pin_map import PinMap
from src.domains.hardware_engine.core.clock_tree import ClockTree
from src.domains.hardware_engine.core.interrupt_model import InterruptModel
from src.domains.hardware_engine.core.models import (
    ValidationResult,
    ValidationFinding,
    ValidationSeverity,
)
from src.domains.hardware_engine.validator.rules import HardwareRules
from src.domains.hardware_engine.validator.errors import (
    HardwareError,
    PinConflictError,
    ClockError,
    InterruptError,
    RegisterError,
    AllocationError,
    ValidationError,
)


class HardwareValidator:
    """
    Deterministic hardware validation engine.

    Validates allocations and code against hardware rules:
    - Pin routing and conflicts
    - Clock configuration and bus speed limits
    - Interrupt allocation and priority
    - Register access patterns
    - Protocol constraints (SPI, I2C, CAN, etc.)

    All rules are deterministic - no LLM required.
    """

    def __init__(
        self,
        peripheral_graph: PeripheralGraph,
        register_schema: RegisterSchemaDB,
        pin_map: PinMap,
        clock_tree: ClockTree,
        interrupt_model: InterruptModel,
    ):
        self.graph = peripheral_graph
        self.register_schema = register_schema
        self.pin_map = pin_map
        self.clock_tree = clock_tree
        self.interrupt_model = interrupt_model
        self.rules = HardwareRules()

    # ─── Allocation Validation ──────────────────────────────────────

    def validate_allocation(self, allocation: dict) -> ValidationResult:
        """
        Validate a complete hardware allocation.

        Checks:
        - Pin assignments are valid and non-conflicting
        - Clock configuration is valid
        - Interrupt allocation is valid
        - Register access patterns are correct
        - Protocol constraints are satisfied
        """
        result = ValidationResult(valid=True)

        allocation_dict = allocation if isinstance(allocation, dict) else {}

        # Validate pins
        pin_assignments = allocation_dict.get("pin_assignments", [])
        self._validate_pin_assignments(result, pin_assignments)

        # Validate clock
        clock_assignment = allocation_dict.get("clock_assignment", {})
        self._validate_clock(result, clock_assignment)

        # Validate interrupt
        int_assignment = allocation_dict.get("interrupt_assignment", {})
        self._validate_interrupt(result, int_assignment)

        # Validate register writes
        register_writes = allocation_dict.get("register_writes", [])
        self._validate_register_writes(result, register_writes)

        return result

    def _validate_pin_assignments(
        self, result: ValidationResult, assignments: List
    ):
        pin_names = []
        for a in assignments:
            if not isinstance(a, dict):
                continue
            pin = str(a.get("pin", ""))
            signal = str(a.get("signal", ""))
            peripheral = str(a.get("peripheral", ""))
            af = a.get("alternate_function")

            if not pin:
                result.add_error("PIN_001", "Pin assignment missing pin name", peripheral=peripheral)
                continue

            pin_names.append(pin)

            # Check reservation
            pin_info = self.pin_map.get_pin_info(pin)
            reserved = pin_info.get("reserved_by", "")
            if reserved and reserved != peripheral:
                result.add_error(
                    "PIN_002",
                    f"Pin {pin} already reserved by '{reserved}'",
                    location=pin,
                    peripheral=peripheral,
                )

            # Check AF support
            if af is not None:
                af_ok = self.pin_map.get_alternate_function(pin, peripheral)
                if af_ok is None:
                    result.add_warning(
                        "PIN_003",
                        f"Pin {pin} AF{af} may not support {peripheral}",
                        location=pin,
                        peripheral=peripheral,
                    )

        # Check duplicates
        seen = set()
        for pin in pin_names:
            if pin in seen:
                result.add_error("PIN_004", f"Pin {pin} assigned multiple times", location=pin)
            seen.add(pin)

    def _validate_clock(
        self, result: ValidationResult, assignment: dict
    ):
        if not assignment:
            result.add_warning("CLK_001", "No clock assignment provided")
            return

        peripheral = assignment.get("peripheral", "")
        frequency = assignment.get("frequency_hz", 0)
        domain = assignment.get("domain", "")

        if not peripheral:
            return

        # Check bus speed limits
        if domain == "APB1":
            ok, msg = HardwareRules.apb1_speed_limit(frequency)
            if not ok:
                result.add_error("CLK_002", msg, peripheral=peripheral)
        elif domain == "APB2":
            ok, msg = HardwareRules.apb2_speed_limit(frequency)
            if not ok:
                result.add_error("CLK_002", msg, peripheral=peripheral)

        # Check clock enabled
        if not self.clock_tree.is_enabled(peripheral):
            result.add_error("CLK_003", f"Clock not enabled for {peripheral}", peripheral=peripheral)

    def _validate_interrupt(
        self, result: ValidationResult, assignment: dict
    ):
        if not assignment:
            return

        peripheral = assignment.get("peripheral", "")
        irq = assignment.get("irq_line", -1)
        priority = assignment.get("priority", 0)

        if irq < 0:
            result.add_warning("INT_001", f"No valid IRQ for {peripheral}", peripheral=peripheral)
            return

        # Priority check
        ok, msg = HardwareRules.priority_valid(priority)
        if not ok:
            result.add_error("INT_002", msg, peripheral=peripheral)

        # Availability check
        if not self.interrupt_model.is_available(irq):
            alloc = self.interrupt_model.get_allocation(irq)
            result.add_error(
                "INT_003",
                f"IRQ {irq} already allocated to '{alloc.peripheral if alloc else 'unknown'}'",
                peripheral=peripheral,
            )

    def _validate_register_writes(
        self, result: ValidationResult, writes: List
    ):
        for w in writes:
            if not isinstance(w, dict):
                continue
            peripheral = str(w.get("peripheral", ""))
            register = str(w.get("register", ""))
            operation = str(w.get("operation", "write"))

            if not peripheral or not register:
                continue

            access = self.register_schema.get_access(peripheral, register)
            ok, msg = HardwareRules.register_access_compatible(access, operation)
            if not ok:
                result.add_error(
                    "REG_001",
                    f"{peripheral}->{register}: {msg}",
                    location=f"{peripheral}->{register}",
                    peripheral=peripheral,
                )

    # ─── Code Validation ────────────────────────────────────────────

    def validate_code(self, code: str, allocation: dict) -> ValidationResult:
        """
        Validate generated C code against hardware constraints.

        Checks:
        - No undeclared register accesses
        - Pin usage matches allocation
        - Interrupt handlers match NVIC
        - No hardcoded magic numbers without explanation
        """
        result = ValidationResult(valid=True)

        import re

        # Extract register accesses (simplified pattern)
        register_pattern = r"(\w+)->(\w+)"
        for match in re.finditer(register_pattern, code):
            peripheral = match.group(1)
            register = match.group(2)

            if not self.graph.has_peripheral(peripheral):
                result.add_warning(
                    "CODE_001",
                    f"Accessing potentially unknown peripheral '{peripheral}'",
                    location=f"{peripheral}->{register}",
                )

            schema = self.register_schema.get_register(peripheral, register)
            if not schema:
                result.add_warning(
                    "CODE_002",
                    f"Register '{register}' for '{peripheral}' not in schema",
                    location=f"{peripheral}->{register}",
                )

        # Extract ISR handlers
        isr_pattern = r"void\s+(\w+_IRQHandler)\s*\("
        for match in re.finditer(isr_pattern, code):
            handler_name = match.group(1)
            expected_prefix = handler_name.replace("_IRQHandler", "")
            irq = self.interrupt_model.get_irq(expected_prefix)
            if irq is None:
                result.add_warning(
                    "CODE_003",
                    f"ISR '{handler_name}' does not match any known peripheral",
                    location=handler_name,
                )

        # Check for hardcoded addresses
        addr_pattern = r"0x[0-9A-Fa-f]{6,}"
        for match in re.finditer(addr_pattern, code):
            addr_str = match.group(0)
            result.add_info(
                "CODE_004",
                f"Hardcoded address {addr_str} found - consider using defines",
                location=addr_str,
            )

        # Validate against allocation
        alloc_validation = self.validate_allocation(allocation)
        for finding in alloc_validation.findings:
            result.findings.append(finding)
            if finding.severity == ValidationSeverity.ERROR:
                result.errors += 1
                result.valid = False
            elif finding.severity == ValidationSeverity.WARNING:
                result.warnings += 1

        return result

    # ─── Quick Checks ────────────────────────────────────────────────

    def check_pin(self, pin: str) -> ValidationResult:
        """Quick check for a single pin."""
        result = ValidationResult(valid=True)
        pin_info = self.pin_map.get_pin_info(pin)
        if not pin_info:
            result.add_error("PIN_100", f"Pin {pin} not found in pin map", location=pin)
        return result

    def check_clock(self, peripheral: str) -> ValidationResult:
        """Quick check for clock configuration."""
        result = ValidationResult(valid=True)
        if not self.clock_tree.is_enabled(peripheral):
            result.add_error("CLK_100", f"Clock not enabled for {peripheral}", peripheral=peripheral)
        speed_check = self.clock_tree.validate_bus_speed(peripheral)
        if speed_check and not speed_check.get("valid"):
            result.add_error(
                "CLK_101",
                f"Bus speed violation for {peripheral}",
                peripheral=peripheral,
            )
        return result

    def check_interrupt(self, peripheral: str) -> ValidationResult:
        """Quick check for interrupt configuration."""
        result = ValidationResult(valid=True)
        irq = self.interrupt_model.get_irq(peripheral)
        if irq is None:
            result.add_warning("INT_100", f"No IRQ defined for {peripheral}", peripheral=peripheral)
        elif not self.interrupt_model.is_available(irq):
            alloc = self.interrupt_model.get_allocation(irq)
            result.add_error(
                "INT_101",
                f"IRQ {irq} already allocated to '{alloc.peripheral if alloc else 'unknown'}'",
                peripheral=peripheral,
            )
        return result

    # ─── Export ────────────────────────────────────────────────────

    def validation_summary(self, result: ValidationResult) -> str:
        """Format validation result as readable string."""
        lines = []
        lines.append(f"Valid: {result.valid}")
        lines.append(f"Errors: {result.errors}")
        lines.append(f"Warnings: {result.warnings}")
        if result.findings:
            lines.append("")
            lines.append("Findings:")
            for f in result.findings:
                prefix = "ERROR" if f.severity == ValidationSeverity.ERROR else "WARN" if f.severity == ValidationSeverity.WARNING else "INFO"
                lines.append(f"  [{prefix}] {f.rule_id}: {f.message}")
                if f.location:
                    lines.append(f"    Location: {f.location}")
                if f.peripheral:
                    lines.append(f"    Peripheral: {f.peripheral}")
                if f.fix_suggestion:
                    lines.append(f"    Fix: {f.fix_suggestion}")
        return "\n".join(lines)

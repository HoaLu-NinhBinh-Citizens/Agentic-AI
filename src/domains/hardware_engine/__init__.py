"""Hardware Semantic Engine for CARV.

Provides deterministic hardware reasoning for embedded firmware generation.
Architectural layers:
- core/       : Data models (PeripheralGraph, RegisterSchema, PinMap, ClockTree, InterruptModel)
- engine/     : Reasoning engines (PinMux, Clock, Interrupt, Register, Allocator)
- validator/  : Deterministic rule-based validation
- parser/     : RM PDF / SVD extraction to RegisterSchema
- codegen/    : Hardware-constrained code generation
- integration/: Multi-agent integration (HardwareAgent)

Usage:
    from src.domains.hardware_engine import HardwareSemanticEngine

    engine = HardwareSemanticEngine(chip="STM32F407")
    engine.load_rm("STM32F407_RM.pdf")

    result = engine.allocate(
        peripheral="CAN1",
        mode="loopback",
        baudrate=500000,
    )

    if result.valid:
        code = engine.generate_init_code(result.allocation)
"""

from src.domains.hardware_engine.core.models import (
    Chip,
    Peripheral,
    Register,
    Bitfield,
    Pin,
    Signal,
    ClockDomain,
    NVICConfig,
    AllocationResult,
    AllocationContext,
    HardwareConstraint,
    ValidationResult,
    ValidationSeverity,
    ValidationFinding,
)

from src.domains.hardware_engine.core.peripheral_graph import PeripheralGraph
from src.domains.hardware_engine.core.register_schema import RegisterSchemaDB
from src.domains.hardware_engine.core.pin_map import PinMap
from src.domains.hardware_engine.core.clock_tree import ClockTree
from src.domains.hardware_engine.core.interrupt_model import InterruptModel

from src.domains.hardware_engine.engine.pinmux_engine import PinMuxEngine
from src.domains.hardware_engine.engine.clock_engine import ClockEngine
from src.domains.hardware_engine.engine.interrupt_engine import InterruptEngine
from src.domains.hardware_engine.engine.register_engine import RegisterEngine
from src.domains.hardware_engine.engine.allocator import ResourceAllocator

from src.domains.hardware_engine.validator.hw_validator import HardwareValidator
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

from src.domains.hardware_engine.parser.rm_parser import RMParser
from src.domains.hardware_engine.parser.svd_parser import SVDParser
from src.domains.hardware_engine.parser.extractor import SchemaExtractor

from src.domains.hardware_engine.codegen.hw_constrained_gen import HardwareConstrainedGenerator
from src.domains.hardware_engine.codegen.templates import RegisterAccessTemplates
from src.domains.hardware_engine.codegen.assertions import HardwareAssertions

from src.domains.hardware_engine.integration.hw_agent import HardwareAgent
from src.domains.hardware_engine.integration.adapter import HardwareEngineAdapter


class HardwareSemanticEngine:
    """
    Main entry point for the Hardware Semantic Engine.

    Provides a unified API over the peripheral graph, resource allocator,
    and code generator.

    Example:
        engine = HardwareSemanticEngine(chip="STM32F407")
        engine.load_rm("path/to/STM32F407_RM.pdf")

        result = engine.allocate(
            peripheral="USART2",
            mode="interrupt",
            baudrate=115200,
        )

        if result.valid:
            code = engine.generate_code(result.allocation)
    """

    def __init__(self, chip: str = "STM32F407"):
        self.chip = chip
        self.peripheral_graph = PeripheralGraph()
        self.register_schema = RegisterSchemaDB()
        self.pin_map = PinMap()
        self.clock_tree = ClockTree()
        self.interrupt_model = InterruptModel()

        self.pinmux_engine = PinMuxEngine(self.pin_map, self.peripheral_graph)
        self.clock_engine = ClockEngine(self.clock_tree, self.register_schema)
        self.interrupt_engine = InterruptEngine(
            self.interrupt_model, self.peripheral_graph
        )
        self.register_engine = RegisterEngine(self.register_schema)
        self.allocator = ResourceAllocator(
            self.pinmux_engine,
            self.clock_engine,
            self.interrupt_engine,
            self.register_engine,
        )
        self.validator = HardwareValidator(
            self.peripheral_graph,
            self.register_schema,
            self.pin_map,
            self.clock_tree,
            self.interrupt_model,
        )
        self.codegen = HardwareConstrainedGenerator(
            self.register_schema,
            self.peripheral_graph,
            self.pin_map,
            self.clock_tree,
            self.interrupt_model,
        )
        self._loaded = False

    def load_defaults(self):
        """Load default clock tree and interrupt model for the chip family."""
        if "F407" in self.chip.upper() or "F4" in self.chip.upper():
            self.clock_tree.load_default_stm32f4()
            self.interrupt_model.load_default_stm32f4()
        elif "F103" in self.chip.upper() or "F1" in self.chip.upper():
            self.clock_tree.load_default_stm32f4()
            self.interrupt_model.load_default_stm32f4()
        self._loaded = True

    # ─── Data Loading ───────────────────────────────────────────────

    def load_rm(self, pdf_path: str) -> bool:
        """Load register definitions from a Reference Manual PDF."""
        from pathlib import Path

        if not Path(pdf_path).exists():
            return False
        parser = RMParser()
        schema = parser.parse(pdf_path)
        if schema:
            self.register_schema.load(schema)
            self._apply_schema_to_graph(schema)
            self._loaded = True
            return True
        return False

    def load_svd(self, svd_path: str) -> bool:
        """Load register definitions from an SVD file."""
        from pathlib import Path

        if not Path(svd_path).exists():
            return False
        parser = SVDParser()
        schema = parser.parse(svd_path)
        if schema:
            self.register_schema.load(schema)
            self._apply_schema_to_graph(schema)
            self._loaded = True
            return True
        return False

    def load_json_schema(self, schema: dict) -> bool:
        """Load register schema from a JSON dict."""
        self.register_schema.load(schema)
        self._apply_schema_to_graph(schema)
        self._loaded = True
        return True

    def _apply_schema_to_graph(self, schema: dict):
        """Populate peripheral graph and related models from register schema."""
        chip = Chip(
            name=self.chip,
            family=self._infer_family(self.chip),
            core="Cortex-M4",
            vendor="STMicroelectronics",
        )
        self.peripheral_graph.set_chip(chip)

        for entry in schema.get("entries", []):
            peripheral_name = entry.get("peripheral", "")
            if not peripheral_name:
                continue

            registers = []
            for reg_entry in entry.get("registers", []):
                bitfields = []
                for bf in reg_entry.get("bitfields", []):
                    bitfields.append(
                        Bitfield(
                            name=bf.get("name", ""),
                            offset=int(bf.get("offset", 0)),
                            width=int(bf.get("width", 1)),
                            access=bf.get("access", "RW"),
                            description=bf.get("description", ""),
                            values=bf.get("values", {}),
                        )
                    )
                registers.append(
                    Register(
                        name=reg_entry.get("register", ""),
                        offset=int(reg_entry.get("offset", 0)),
                        access=reg_entry.get("access", "RW"),
                        description=reg_entry.get("description", ""),
                        bitfields=bitfields,
                        reset_value=reg_entry.get("reset_value"),
                    )
                )

            peripheral = Peripheral(
                name=peripheral_name,
                base_address=int(entry.get("base_address", 0), 16)
                if isinstance(entry.get("base_address"), str)
                else entry.get("base_address", 0),
                description=entry.get("description", peripheral_name),
                registers=registers,
                clock_enable_bit=entry.get("clock_enable_bit"),
                reset_bit=entry.get("reset_bit"),
                interrupts=entry.get("interrupts", []),
            )
            self.peripheral_graph.add_peripheral(peripheral)

    def _infer_family(self, chip: str) -> str:
        """Infer chip family from chip name."""
        chip = chip.upper()
        if "F407" in chip:
            return "STM32F4"
        if "F103" in chip:
            return "STM32F1"
        if "F401" in chip or "F411" in chip:
            return "STM32F4"
        if "F051" in chip:
            return "STM32F0"
        return "STM32"

    # ─── Allocation ─────────────────────────────────────────────────

    def allocate(self, peripheral: str, **kwargs) -> AllocationResult:
        """
        Allocate hardware resources for a peripheral configuration.

        Args:
            peripheral: Peripheral name (e.g., "USART2", "CAN1")
            **kwargs: Configuration parameters (mode, baudrate, pins, etc.)

        Returns:
            AllocationResult with valid flag and allocation details
        """
        if not self._loaded:
            return AllocationResult(
                valid=False,
                errors=["Hardware Semantic Engine not loaded. Call load_rm() or load_svd() first."],
                peripheral=peripheral,
                constraints=[],
            )

        context = AllocationContext(
            peripheral=peripheral,
            mode=kwargs.get("mode", "default"),
            parameters=kwargs,
        )

        return self.allocator.allocate(context)

    def validate_allocation(self, allocation: dict) -> ValidationResult:
        """Validate a hardware allocation against hardware rules."""
        return self.validator.validate_allocation(allocation)

    # ─── Code Generation ────────────────────────────────────────────

    def generate_code(self, allocation: dict) -> dict:
        """
        Generate hardware-constrained C code from an allocation.

        Returns dict with:
            - headers: list of required #include headers
            - defines: #define statements for pins/clocks
            - init_sequence: register initialization sequence
            - isr_handlers: interrupt handler stubs
            - assertions: embedded hardware assertions
        """
        return self.codegen.generate(allocation)

    def generate_init_code(self, allocation: dict) -> str:
        """Generate complete peripheral initialization C code."""
        code = self.codegen.generate(allocation)
        return self._format_init_code(code)

    def generate_interrupt_handlers(self, allocation: dict) -> str:
        """Generate interrupt handler stubs."""
        code = self.codegen.generate(allocation)
        return code.get("isr_handlers", "")

    def generate_register_sequence(
        self, peripheral: str, operation: str
    ) -> list:
        """
        Generate deterministic register initialization sequence.

        Args:
            peripheral: Peripheral name
            operation: "init", "deinit", "enable", "disable"

        Returns:
            List of register write operations
        """
        return self.register_engine.build_sequence(peripheral, operation)

    # ─── Validation ─────────────────────────────────────────────────

    def validate_code(self, code: str, allocation: dict) -> ValidationResult:
        """Validate generated code against hardware constraints."""
        return self.validator.validate_code(code, allocation)

    def check_pin_conflict(self, pin: str) -> list:
        """Check if a pin is already allocated."""
        return self.pin_map.find_conflicts(pin)

    def check_clock_configuration(self, peripheral: str) -> ValidationResult:
        """Validate clock configuration for a peripheral."""
        return self.clock_engine.validate(peripheral)

    def check_interrupt_availability(self, irq_line: int) -> bool:
        """Check if an IRQ line is available."""
        return self.interrupt_model.is_available(irq_line)

    # ─── Utility ────────────────────────────────────────────────────

    def get_peripheral_info(self, peripheral: str) -> dict:
        """Get information about a peripheral."""
        peri = self.peripheral_graph.get_peripheral(peripheral)
        if not peri:
            return {}
        return {
            "name": peri.name,
            "base_address": f"0x{peri.base_address:08X}",
            "registers": [
                {"name": r.name, "offset": f"0x{r.offset:04X}", "access": r.access}
                for r in peri.registers
            ],
            "interrupts": peri.interrupts,
            "clock_enable_bit": peri.clock_enable_bit,
        }

    def list_peripherals(self) -> list:
        """List all available peripherals."""
        return self.peripheral_graph.list_peripherals()

    def get_register_schema(self, peripheral: str) -> dict:
        """Get full register schema for a peripheral."""
        return self.register_schema.get_peripheral_schema(peripheral)

    def _format_init_code(self, code: dict) -> str:
        """Format generated code into readable C code."""
        lines = []

        headers = code.get("headers", [])
        if headers:
            for h in headers:
                lines.append(f"#include <{h}>")
            lines.append("")

        defines = code.get("defines", [])
        if defines:
            for d in defines:
                lines.append(f"#define {d}")
            lines.append("")

        lines.append("/* === Hardware Initialization === */")
        lines.append("")
        for stmt in code.get("init_sequence", []):
            lines.append(f"    {stmt};")
        lines.append("")

        isr = code.get("isr_handlers", "")
        if isr:
            lines.append("/* === Interrupt Handlers === */")
            lines.append(isr)

        assertions = code.get("assertions", [])
        if assertions:
            lines.append("")
            lines.append("/* === Hardware Assertions === */")
            for a in assertions:
                lines.append(f"    /* {a['description']} */")
                lines.append(f"    {a['expression']};")

        return "\n".join(lines)

    def summary(self) -> dict:
        """Return a summary of the loaded hardware model."""
        return {
            "chip": self.chip,
            "loaded": self._loaded,
            "peripherals": len(self.peripheral_graph.list_peripherals()),
            "pins": self.pin_map.count(),
            "clock_domains": len(self.clock_tree.list_domains()),
            "interrupt_lines": len(self.interrupt_model.list_allocations()),
        }

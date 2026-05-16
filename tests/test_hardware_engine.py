"""Unit tests for Hardware Semantic Engine."""

import pytest

from src.hardware_engine import HardwareSemanticEngine
from src.hardware_engine.core.models import (
    Peripheral,
    Register,
    Bitfield,
    Interrupt,
    Signal,
    Chip,
    PinAssignment,
    ClockAssignment,
    InterruptAssignment,
    RegisterWrite,
    ResourceAllocation,
    AllocationContext,
    ValidationResult,
    ValidationSeverity,
    HardwareConstraint,
)
from src.hardware_engine.core.peripheral_graph import PeripheralGraph
from src.hardware_engine.core.register_schema import RegisterSchemaDB
from src.hardware_engine.core.pin_map import PinMap
from src.hardware_engine.core.clock_tree import ClockTree
from src.hardware_engine.core.interrupt_model import InterruptModel
from src.hardware_engine.engine.pinmux_engine import PinMuxEngine
from src.hardware_engine.engine.clock_engine import ClockEngine
from src.hardware_engine.engine.interrupt_engine import InterruptEngine
from src.hardware_engine.engine.register_engine import RegisterEngine
from src.hardware_engine.engine.allocator import ResourceAllocator
from src.hardware_engine.validator.hw_validator import HardwareValidator
from src.hardware_engine.validator.rules import HardwareRules
from src.hardware_engine.codegen.templates import RegisterAccessTemplates
from src.hardware_engine.codegen.assertions import HardwareAssertions
from src.hardware_engine.integration.hw_agent import HardwareAgent


# ═══════════════════════════════════════════════════════════════
# Core Models
# ═══════════════════════════════════════════════════════════════

class TestCoreModels:
    def test_validation_result_add_error(self):
        r = ValidationResult(valid=True)
        r.add_error("TEST_001", "Test error", peripheral="USART2")
        assert r.valid is False
        assert r.errors == 1
        assert len(r.findings) == 1
        assert r.findings[0].severity == ValidationSeverity.ERROR

    def test_validation_result_add_warning(self):
        r = ValidationResult(valid=True)
        r.add_warning("TEST_001", "Test warning")
        assert r.valid is True
        assert r.warnings == 1

    def test_validation_result_add_info(self):
        r = ValidationResult(valid=True)
        r.add_info("TEST_001", "Test info")
        assert r.valid is True
        assert len(r.findings) == 1

    def test_resource_allocation_dataclass(self):
        alloc = ResourceAllocation(
            peripheral="USART2",
            mode="interrupt",
            pin_assignments=[
                PinAssignment(signal="TX", pin="PA2", alternate_function=7, direction="output")
            ],
            clock_assignment=ClockAssignment(
                peripheral="USART2", domain="APB1", source="APB1",
                frequency_hz=42000000, prescaler=1
            ),
            interrupt_assignment=InterruptAssignment(
                peripheral="USART2", signal="", irq_line=38,
                handler_name="USART2_IRQHandler", priority=5
            ),
            register_writes=[
                RegisterWrite(peripheral="USART2", register="CR1",
                              field_name="UE", value=1, operation="set_bit")
            ],
        )
        assert alloc.peripheral == "USART2"
        assert alloc.mode == "interrupt"
        assert len(alloc.pin_assignments) == 1
        assert alloc.clock_assignment.domain == "APB1"
        assert alloc.interrupt_assignment.irq_line == 38

    def test_allocation_context(self):
        ctx = AllocationContext(
            peripheral="USART2",
            mode="interrupt",
            parameters={"baudrate": 115200, "priority": 5},
            pin_assignments={"TX": "PA2", "RX": "PA3"},
        )
        assert ctx.peripheral == "USART2"
        assert ctx.parameters["baudrate"] == 115200
        assert ctx.pin_assignments["TX"] == "PA2"


# ═══════════════════════════════════════════════════════════════
# PeripheralGraph
# ═══════════════════════════════════════════════════════════════

class TestPeripheralGraph:
    def setup_method(self):
        self.graph = PeripheralGraph()
        self.graph.set_chip(Chip(
            name="STM32F407", family="STM32F4",
            core="Cortex-M4", vendor="STMicroelectronics"
        ))

    def test_add_peripheral(self):
        peri = Peripheral(name="USART2", base_address=0x40004400)
        peri.interrupts = [Interrupt(name="USART2_IRQ", irq_line=38)]
        self.graph.add_peripheral(peri)

        assert self.graph.has_peripheral("USART2")
        assert self.graph.get_peripheral("USART2").name == "USART2"
        assert len(self.graph.list_peripherals()) == 1

    def test_get_interrupt(self):
        peri = Peripheral(name="USART2", base_address=0x40004400)
        peri.interrupts = [Interrupt(name="USART2_IRQ", irq_line=38)]
        self.graph.add_peripheral(peri)

        irq = self.graph.get_interrupt(38)
        assert irq is not None
        assert irq.name == "USART2_IRQ"
        assert irq.irq_line == 38

    def test_get_clock_domain(self):
        # Test clock domain inference based on peripheral name conventions
        # These peripherals need to be added for the inference to work
        peri = Peripheral(name="USART2", base_address=0x40004400)
        self.graph.add_peripheral(peri)
        assert self.graph.get_clock_domain("USART2") == "APB1"

        peri2 = Peripheral(name="SPI1", base_address=0x40013000)
        self.graph.add_peripheral(peri2)
        assert self.graph.get_clock_domain("SPI1") == "APB2"

        peri3 = Peripheral(name="CAN1", base_address=0x40006400)
        self.graph.add_peripheral(peri3)
        assert self.graph.get_clock_domain("CAN1") == "APB1"

        # I2C uses APB1
        peri4 = Peripheral(name="I2C1", base_address=0x40005400)
        self.graph.add_peripheral(peri4)
        assert self.graph.get_clock_domain("I2C1") == "APB1"

        # ADC uses APB2
        peri5 = Peripheral(name="ADC1", base_address=0x40012000)
        self.graph.add_peripheral(peri5)
        assert self.graph.get_clock_domain("ADC1") == "APB2"

    def test_add_dependency(self):
        peri1 = Peripheral(name="USART2", base_address=0x40004400)
        peri2 = Peripheral(name="USART3", base_address=0x40004800)
        self.graph.add_peripheral(peri1)
        self.graph.add_peripheral(peri2)
        self.graph.add_dependency("USART3", "USART2")

        deps = self.graph.get_dependencies("USART3")
        assert "USART2" in deps

    def test_to_dict(self):
        peri = Peripheral(name="USART2", base_address=0x40004400)
        self.graph.add_peripheral(peri)
        d = self.graph.to_dict()
        assert d["chip"]["name"] == "STM32F407"
        assert "USART2" in d["peripherals"]


# ═══════════════════════════════════════════════════════════════
# RegisterSchemaDB
# ═══════════════════════════════════════════════════════════════

class TestRegisterSchemaDB:
    def setup_method(self):
        self.db = RegisterSchemaDB()
        self.db.load({
            "chip": "STM32F407",
            "entries": [{
                "peripheral": "USART2",
                "base_address": 0x40004400,
                "registers": [
                    {
                        "register": "CR1",
                        "offset": 0x0C,
                        "access": "RW",
                        "description": "Control register 1",
                        "bitfields": [
                            {"name": "UE", "offset": 0, "width": 1, "access": "RW",
                             "description": "USART enable"},
                            {"name": "TE", "offset": 1, "width": 1, "access": "RW",
                             "description": "Transmitter enable"},
                        ]
                    },
                    {
                        "register": "SR",
                        "offset": 0x00,
                        "access": "RO",
                        "description": "Status register",
                        "bitfields": [
                            {"name": "TXE", "offset": 5, "width": 1, "access": "RO",
                             "description": "Transmit data register empty"},
                        ]
                    },
                ]
            }]
        })

    def test_get_peripheral_schema(self):
        schema = self.db.get_peripheral_schema("USART2")
        assert schema["peripheral"] == "USART2"
        assert len(schema["registers"]) == 2

    def test_get_register(self):
        reg = self.db.get_register("USART2", "CR1")
        assert reg is not None
        assert reg.register == "CR1"
        assert reg.offset == 0x0C
        assert reg.access == "RW"

    def test_get_by_address(self):
        entry = self.db.get_by_address(0x4000440C)
        assert entry is not None
        assert entry.register == "CR1"

    def test_find_registers(self):
        results = self.db.find_registers("control")
        assert len(results) == 1
        assert results[0].register == "CR1"

    def test_get_bitfield(self):
        bf = self.db.get_bitfield("USART2", "CR1", "UE")
        assert bf is not None
        assert bf["name"] == "UE"
        assert bf["offset"] == 0

    def test_validate_register_access(self):
        assert self.db.validate_register_access("USART2", "CR1", "write") is True
        assert self.db.validate_register_access("USART2", "SR", "write") is False
        assert self.db.validate_register_access("USART2", "SR", "read") is True

    def test_get_address(self):
        addr = self.db.get_address("USART2", "CR1")
        assert addr == 0x4000440C


# ═══════════════════════════════════════════════════════════════
# PinMap
# ═══════════════════════════════════════════════════════════════

class TestPinMap:
    def setup_method(self):
        self.pin_map = PinMap()
        self.pin_map.add_pin("PA9", "A", 9, af7="USART1", af8="OTG_FS")
        self.pin_map.add_pin("PA10", "A", 10, af7="USART1")
        self.pin_map.add_pin("PA2", "A", 2, af7="USART2")
        self.pin_map.add_pin("PA3", "A", 3, af7="USART2")
        self.pin_map.add_pin("PB6", "B", 6, af4="I2C1", af7="USART1")

    def test_add_and_find_pins(self):
        assert self.pin_map.count() == 5
        assert self.pin_map.count_available() == 5

    def test_get_alternate_function(self):
        af = self.pin_map.get_alternate_function("PA9", "USART1")
        assert af == 7
        af = self.pin_map.get_alternate_function("PB6", "I2C1")
        assert af == 4

    def test_pin_reservation(self):
        assert self.pin_map.is_available("PA9")
        self.pin_map.reserve_pin("PA9", "USART1", "TX")
        assert not self.pin_map.is_available("PA9")
        conflicts = self.pin_map.find_conflicts("PA9")
        assert len(conflicts) == 1
        self.pin_map.release_pin("PA9")
        assert self.pin_map.is_available("PA9")

    def test_find_pins_for_signal(self):
        pins = self.pin_map.find_pins_for_signal("USART1")
        assert "PA9" in pins
        assert "PA10" in pins
        assert "PB6" in pins

    def test_assign(self):
        result = self.pin_map.assign("PA9", "USART1", "TX")
        assert result is True
        assert not self.pin_map.is_available("PA9")

        result = self.pin_map.assign("PA9", "USART2", "TX")
        assert result is False

    def test_reset(self):
        self.pin_map.reserve_pin("PA9", "USART1", "TX")
        self.pin_map.reset()
        assert self.pin_map.is_available("PA9")


# ═══════════════════════════════════════════════════════════════
# ClockTree
# ═══════════════════════════════════════════════════════════════

class TestClockTree:
    def setup_method(self):
        self.clock = ClockTree()
        self.clock.load_default_stm32f4()

    def test_domain_access(self):
        domain = self.clock.get_domain("APB1")
        assert domain is not None
        assert domain.frequency_hz == 42_000_000

    def test_enable_clock(self):
        assert not self.clock.is_enabled("USART2")
        self.clock.enable_clock("USART2")
        assert self.clock.is_enabled("USART2")

    def test_get_frequency(self):
        freq = self.clock.get_frequency("USART2")
        assert freq == 42_000_000
        freq = self.clock.get_frequency("SPI1")
        assert freq == 84_000_000

    def test_baudrate_prescaler(self):
        result = self.clock.calculate_baudrate_prescaler("USART2", 115200)
        assert result["brr"] > 0
        assert result["acceptable"] is True
        assert result["periph_clock"] == 42_000_000

    def test_validate_bus_speed(self):
        check = self.clock.validate_bus_speed("USART2")
        assert check["valid"] is True
        assert check["domain"] == "APB1"

    def test_clock_enable_register(self):
        reg = self.clock.get_clock_enable_register("USART2")
        assert "APB1" in reg


# ═══════════════════════════════════════════════════════════════
# InterruptModel
# ═══════════════════════════════════════════════════════════════

class TestInterruptModel:
    def setup_method(self):
        self.int_model = InterruptModel()
        self.int_model.load_default_stm32f4()

    def test_get_irq(self):
        assert self.int_model.get_irq("USART2") == 38
        assert self.int_model.get_irq("SPI1") == 35
        assert self.int_model.get_irq("CAN1_TX") == 19

    def test_allocate(self):
        success, error, irq = self.int_model.allocate("USART2", "USART2_IRQHandler", 5)
        assert success is True
        assert irq == 38
        assert self.int_model.is_available(38) is False

    def test_allocate_already_used(self):
        self.int_model.allocate("USART2", "USART2_IRQHandler")
        success, error, irq = self.int_model.allocate("USART2", "USART2_IRQHandler")
        assert success is False
        assert "already allocated" in error

    def test_allocate_unknown_peripheral(self):
        success, error, irq = self.int_model.allocate("UNKNOWN", "UNKNOWN_IRQHandler")
        assert success is False

    def test_free(self):
        self.int_model.allocate("USART2", "USART2_IRQHandler")
        assert self.int_model.free("USART2") is True
        assert self.int_model.is_available(38) is True

    def test_generate_enable_sequence(self):
        self.int_model.allocate("USART2", "USART2_IRQHandler", 5)
        seq = self.int_model.get_enable_sequence("USART2")
        assert len(seq) == 2
        assert seq[0]["action"] == "set_priority"
        assert seq[1]["action"] == "enable"


# ═══════════════════════════════════════════════════════════════
# HardwareRules
# ═══════════════════════════════════════════════════════════════

class TestHardwareRules:
    def test_pin_not_reserved(self):
        ok, msg = HardwareRules.pin_not_reserved("PA9", "")
        assert ok is True
        ok, msg = HardwareRules.pin_not_reserved("PA9", "USART1")
        assert ok is False

    def test_apb_speed_limits(self):
        ok, msg = HardwareRules.apb1_speed_limit(42_000_000)
        assert ok is True
        ok, msg = HardwareRules.apb1_speed_limit(50_000_000)
        assert ok is False

    def test_priority_valid(self):
        ok, msg = HardwareRules.priority_valid(5)
        assert ok is True
        ok, msg = HardwareRules.priority_valid(20)
        assert ok is False

    def test_register_access_compatible(self):
        ok, msg = HardwareRules.register_access_compatible("RW", "write")
        assert ok is True
        ok, msg = HardwareRules.register_access_compatible("RO", "write")
        assert ok is False
        ok, msg = HardwareRules.register_access_compatible("WO", "read")
        assert ok is False

    def test_can_baudrate_valid(self):
        ok, msg = HardwareRules.can_baudrate_valid(500_000)
        assert ok is True
        ok, msg = HardwareRules.can_baudrate_valid(333_333)
        assert ok is False

    def test_bitfield_width_valid(self):
        ok, msg = HardwareRules.bitfield_width_valid(0, 1)
        assert ok is True
        ok, msg = HardwareRules.bitfield_width_valid(28, 8)
        assert ok is False

    def test_no_priority_conflict(self):
        allocated = [{"priority": 5, "peripheral": "USART2", "irq": 38}]
        ok, msg = HardwareRules.no_priority_conflict(10, allocated)
        assert ok is True
        ok, msg = HardwareRules.no_priority_conflict(5, allocated)
        assert ok is False


# ═══════════════════════════════════════════════════════════════
# HardwareValidator
# ═══════════════════════════════════════════════════════════════

class TestHardwareValidator:
    def setup_method(self):
        self.graph = PeripheralGraph()
        self.db = RegisterSchemaDB()
        self.pin_map = PinMap()
        self.clock = ClockTree()
        self.int_model = InterruptModel()
        self.clock.load_default_stm32f4()
        self.int_model.load_default_stm32f4()

        self.validator = HardwareValidator(
            self.graph, self.db, self.pin_map, self.clock, self.int_model
        )

    def test_validate_empty_allocation(self):
        result = self.validator.validate_allocation({})
        assert result.valid is True

    def test_check_pin_not_found(self):
        result = self.validator.check_pin("PA99")
        assert result.valid is False
        assert result.errors == 1

    def test_check_clock_enabled(self):
        result = self.validator.check_clock("USART2")
        assert result.errors == 1  # Clock not yet enabled

    def test_validation_summary(self):
        result = ValidationResult(valid=False)
        result.add_error("TEST", "Test error", location="USART2->CR1", peripheral="USART2")
        summary = self.validator.validation_summary(result)
        assert "Valid: False" in summary
        assert "TEST" in summary


# ═══════════════════════════════════════════════════════════════
# HardwareConstrainedGenerator
# ═══════════════════════════════════════════════════════════════

class TestHardwareConstrainedGenerator:
    def setup_method(self):
        from src.hardware_engine.codegen.hw_constrained_gen import HardwareConstrainedGenerator
        self.graph = PeripheralGraph()
        self.db = RegisterSchemaDB()
        self.pin_map = PinMap()
        self.clock = ClockTree()
        self.int_model = InterruptModel()
        self.gen = HardwareConstrainedGenerator(
            self.db, self.graph, self.pin_map, self.clock, self.int_model
        )

    def test_generate_with_clock(self):
        allocation = {
            "peripheral": "USART2",
            "mode": "default",
            "pin_assignments": [],
            "clock_assignment": ClockAssignment(
                peripheral="USART2", domain="APB1", source="APB1",
                frequency_hz=42_000_000, prescaler=1
            ).__dict__,
            "interrupt_assignment": {},
            "register_writes": [],
        }
        result = self.gen.generate(allocation)
        assert "<stdint.h>" in result["headers"]
        defines_str = " ".join(result["defines"])
        assert "HW_USART2_CLOCK_HZ" in defines_str
        assert len(result["init_sequence"]) > 0


# ═══════════════════════════════════════════════════════════════
# HardwareAgent
# ═══════════════════════════════════════════════════════════════

class TestHardwareAgent:
    def setup_method(self):
        self.agent = HardwareAgent(chip="STM32F407")
        self.agent.configure({"schema": {"chip": "STM32F407", "entries": []}})

    def test_configure(self):
        assert self.agent._chip == "STM32F407"
        assert self.agent._loaded is True

    def test_process_request_without_peripheral(self):
        result = self.agent.process_request({})
        assert result["success"] is False
        assert "No peripheral" in result["error"]

    def test_get_tool_definitions(self):
        tools = self.agent.get_tool_definitions()
        assert len(tools) == 6
        names = [t["name"] for t in tools]
        assert "hw_allocate" in names
        assert "hw_validate" in names
        assert "hw_info" in names

    def test_list_peripherals(self):
        self.agent.engine.peripheral_graph.add_peripheral(
            Peripheral(name="USART1", base_address=0x40011000)
        )
        assert "USART1" in self.agent.list_peripherals()

    def test_get_summary(self):
        summary = self.agent.get_summary()
        assert summary["chip"] == "STM32F407"


# ═══════════════════════════════════════════════════════════════
# HardwareAssertions
# ═══════════════════════════════════════════════════════════════

class TestHardwareAssertions:
    def test_static_assert(self):
        code = HardwareAssertions.static_assert("X", "Test message")
        assert "STATIC_ASSERT" in code
        assert "Test message" in code

    def test_runtime_check(self):
        code = HardwareAssertions.runtime_check("x > 0", "x must be positive")
        assert "HW_ASSERT_FAIL" in code

    def test_generate_baudrate_check(self):
        lines = HardwareAssertions.generate_baudrate_check("USART2", 115200, 500)
        assert len(lines) == 3
        assert "115200" in " ".join(lines)

    def test_generate_interrupt_priority_check(self):
        lines = HardwareAssertions.generate_interrupt_priority_check("USART2", 38, 5)
        assert len(lines) == 2


# ═══════════════════════════════════════════════════════════════
# Integration / End-to-End
# ═══════════════════════════════════════════════════════════════

class TestHardwareSemanticEngine:
    def setup_method(self):
        self.engine = HardwareSemanticEngine(chip="STM32F407")
        self.engine.load_defaults()
        peri = Peripheral(name="USART2", base_address=0x40004400)
        peri.interrupts = [Interrupt(name="USART2_IRQ", irq_line=38)]
        self.engine.peripheral_graph.add_peripheral(peri)

    def test_load_defaults(self):
        assert self.engine.summary()["loaded"] is True
        assert self.engine.summary()["clock_domains"] == 8

    def test_allocate_usart2_interrupt(self):
        result = self.engine.allocate(
            peripheral="USART2",
            mode="interrupt",
            baudrate=115200,
        )
        assert result.valid is True
        assert len(result.errors) == 0
        assert result.allocation is not None
        assert result.allocation.clock_assignment.domain == "APB1"
        assert result.allocation.interrupt_assignment.irq_line == 38

    def test_allocate_unknown_peripheral(self):
        result = self.engine.allocate(peripheral="UNKNOWN_PERI")
        assert result.valid is False
        assert len(result.errors) > 0

    def test_generate_code(self):
        result = self.engine.allocate(peripheral="USART2", mode="interrupt")
        code = self.engine.generate_code(result.allocation.__dict__)
        assert "<stdint.h>" in code["headers"]
        assert len(code["init_sequence"]) > 0
        assert "USART2_IRQHandler" in code["isr_handlers"]

    def test_generate_init_code(self):
        result = self.engine.allocate(peripheral="USART2", mode="interrupt")
        code_str = self.engine.generate_init_code(result.allocation.__dict__)
        assert "#include" in code_str
        assert "USART2" in code_str
        assert "RCC->APB1ENR" in code_str

    def test_get_peripheral_info(self):
        info = self.engine.get_peripheral_info("USART2")
        assert info["name"] == "USART2"
        assert "0x40004400" in info["base_address"]

    def test_list_peripherals(self):
        peris = self.engine.list_peripherals()
        assert "USART2" in peris

    def test_check_interrupt_availability(self):
        assert self.engine.check_interrupt_availability(38) is True
        result = self.engine.allocate(peripheral="USART2", mode="interrupt")
        assert self.engine.check_interrupt_availability(38) is False

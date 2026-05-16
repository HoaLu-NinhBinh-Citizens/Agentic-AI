"""Resource Allocator - orchestrates PinMux + Clock + Interrupt + Register engines."""

from typing import Dict, List, Optional

from src.domains.hardware_engine.engine.pinmux_engine import PinMuxEngine
from src.domains.hardware_engine.engine.clock_engine import ClockEngine
from src.domains.hardware_engine.engine.interrupt_engine import InterruptEngine
from src.domains.hardware_engine.engine.register_engine import RegisterEngine
from src.domains.hardware_engine.core.models import (
    AllocationContext,
    AllocationResult,
    ResourceAllocation,
    PinAssignment,
    ClockAssignment,
    InterruptAssignment,
    RegisterWrite,
    HardwareConstraint,
    ValidationSeverity,
)


class ResourceAllocator:
    """
    Hardware resource allocation orchestrator.

    Coordinates PinMuxEngine, ClockEngine, InterruptEngine, and RegisterEngine
    to produce a complete ResourceAllocation for a peripheral configuration.

    Allocation order:
    1. Validate peripheral exists in graph
    2. Allocate clock
    3. Allocate pins (if not interrupt-only)
    4. Allocate interrupt (if interrupt mode)
    5. Build register sequence
    6. Collect constraints
    """

    def __init__(
        self,
        pinmux_engine: PinMuxEngine,
        clock_engine: ClockEngine,
        interrupt_engine: InterruptEngine,
        register_engine: RegisterEngine,
    ):
        self.pinmux = pinmux_engine
        self.clock = clock_engine
        self.interrupt = interrupt_engine
        self.register = register_engine

    def allocate(self, context: AllocationContext) -> AllocationResult:
        """
        Allocate all hardware resources for a peripheral configuration.

        Args:
            context: AllocationContext with peripheral, mode, and parameters

        Returns:
            AllocationResult with ResourceAllocation or errors
        """
        peripheral = context.peripheral
        mode = context.mode

        errors: List[str] = []
        warnings: List[str] = []
        constraints: List[HardwareConstraint] = []

        # 1. Validate peripheral
        if not self._validate_peripheral(peripheral):
            return AllocationResult(
                valid=False,
                peripheral=peripheral,
                constraints=constraints,
                errors=[f"Peripheral '{peripheral}' not found in hardware graph"],
            )

        # 2. Allocate clock
        clock_assignment, clock_errors, clock_warnings = self._allocate_clock(peripheral)
        errors.extend(clock_errors)
        warnings.extend(clock_warnings)

        # 3. Allocate pins
        pin_assignments: List[PinAssignment] = []
        pin_errors: List[str] = []
        if mode not in {"interrupt", "dma"}:
            pin_assignments, pin_errors = self._allocate_pins(peripheral, context.pin_assignments)
            errors.extend(pin_errors)

        # 4. Allocate interrupt
        interrupt_assignment: Optional[InterruptAssignment] = None
        int_errors: List[str] = []
        int_warnings: List[str] = []
        if mode in {"interrupt", "dma", "realtime"}:
            interrupt_assignment, int_errors, int_warnings = self._allocate_interrupt(peripheral, context.parameters)
            errors.extend(int_errors)
            warnings.extend(int_warnings)

        # 5. Build register sequence
        register_writes: List[RegisterWrite] = []
        reg_ops = self.register.build_sequence(peripheral, "init")
        register_writes.extend(reg_ops)

        # Add mode-specific register writes
        if mode == "interrupt":
            register_writes.extend(self._interrupt_enable_regs(peripheral))
        elif mode == "dma":
            register_writes.extend(self._dma_enable_regs(peripheral))
        elif mode == "loopback":
            register_writes.extend(self._loopback_enable_regs(peripheral))

        # 6. Build constraints
        constraints.extend(self._build_constraints(peripheral, mode, context))

        # 7. Determine validity
        valid = len(errors) == 0

        allocation = ResourceAllocation(
            peripheral=peripheral,
            mode=mode,
            pin_assignments=pin_assignments,
            clock_assignment=clock_assignment,
            interrupt_assignment=interrupt_assignment,
            register_writes=register_writes,
            constraints=constraints,
        )

        return AllocationResult(
            valid=valid,
            peripheral=peripheral,
            allocation=allocation,
            constraints=constraints,
            errors=errors,
            warnings=warnings,
        )

    def _validate_peripheral(self, peripheral: str) -> bool:
        graph = self.pinmux.peripheral_graph
        return graph.has_peripheral(peripheral)

    def _allocate_clock(
        self, peripheral: str
    ) -> tuple[Optional[ClockAssignment], List[str], List[str]]:
        errors = []
        warnings = []

        self.clock.clock_tree.enable_clock(peripheral)
        domain = self.clock.clock_tree._get_peripheral_domain(peripheral)
        frequency = self.clock.clock_tree.get_frequency(peripheral)

        assignment = ClockAssignment(
            peripheral=peripheral,
            domain=domain or "UNKNOWN",
            source=domain or "UNKNOWN",
            frequency_hz=frequency,
            prescaler=1,
        )

        # Validate bus speed
        speed_check = self.clock.clock_tree.validate_bus_speed(peripheral)
        if not speed_check.get("valid"):
            warnings.append(
                f"Bus speed exceeds limit: {speed_check['actual_hz'] / 1_000_000:.1f} MHz "
                f"vs {speed_check['max_hz'] / 1_000_000:.1f} MHz"
            )

        return assignment, errors, warnings

    def _allocate_pins(
        self, peripheral: str, explicit_assignments: Dict[str, str]
    ) -> tuple[List[PinAssignment], List[str]]:
        errors = []
        pin_assignments = []

        if explicit_assignments:
            pin_assignments, pin_errors = self.pinmux.allocate_pins(peripheral, explicit_assignments)
            errors.extend(pin_errors)
        else:
            pin_assignments, pin_errors = self.pinmux.auto_allocate(peripheral)
            errors.extend(pin_errors)

        return pin_assignments, errors

    def _allocate_interrupt(
        self, peripheral: str, parameters: Dict
    ) -> tuple[Optional[InterruptAssignment], List[str], List[str]]:
        errors = []
        warnings = []
        priority = parameters.get("priority", 0)
        handler_name = parameters.get("handler", "")

        success, assignment, error_msg = self.interrupt.allocate(
            peripheral, handler_name, priority
        )

        if not success:
            errors.append(f"Interrupt allocation failed: {error_msg}")
            return None, errors, warnings

        result = InterruptAssignment(
            peripheral=peripheral,
            signal="",
            irq_line=assignment.irq_line,
            handler_name=assignment.handler_name,
            priority=priority,
        )
        return result, errors, warnings

    def _build_constraints(
        self, peripheral: str, mode: str, context: AllocationContext
    ) -> List[HardwareConstraint]:
        constraints = []

        constraints.append(
            HardwareConstraint(
                type="mode",
                peripheral=peripheral,
                description=f"Peripheral {peripheral} must be configured in {mode} mode",
                parameter="mode",
                value=mode,
                severity=ValidationSeverity.ERROR,
            )
        )

        if context.parameters.get("baudrate"):
            constraints.append(
                HardwareConstraint(
                    type="timing",
                    peripheral=peripheral,
                    description="Baudrate/timing constraints must be respected",
                    parameter="baudrate",
                    value=context.parameters.get("baudrate"),
                    severity=ValidationSeverity.ERROR,
                )
            )

        return constraints

    def _interrupt_enable_regs(self, peripheral: str) -> List[RegisterWrite]:
        """Add interrupt enable register writes."""
        ops = []
        ptype = peripheral.upper()

        if "USART" in ptype:
            ops.append(RegisterWrite(
                peripheral=peripheral,
                register="CR1",
                field_name="RXNEIE",
                value=1,
                operation="set_bit",
                description="USART RX interrupt enable",
            ))
        elif "CAN" in ptype:
            ops.append(RegisterWrite(
                peripheral=peripheral,
                register="IER",
                field_name="FMPIE0",
                value=1,
                operation="set_bit",
                description="CAN FIFO message pending interrupt enable",
            ))
        elif "TIM" in ptype:
            ops.append(RegisterWrite(
                peripheral=peripheral,
                register="DIER",
                field_name="UIE",
                value=1,
                operation="set_bit",
                description="Timer update interrupt enable",
            ))

        return ops

    def _dma_enable_regs(self, peripheral: str) -> List[RegisterWrite]:
        """Add DMA enable register writes for STM32F4.

        Maps peripheral to DMA stream/channel and generates the configuration
        sequence for the DMA stream associated with the given peripheral.
        """
        ops = []
        ptype = peripheral.upper()

        # STM32F4 DMA request mapping for common peripherals
        dma_map = {
            # USART DMA requests
            "USART1_RX": {"dma": "DMA2", "stream": 2, "channel": 4, "periph_addr": "USART1_BASE + 0x04"},
            "USART1_TX": {"dma": "DMA2", "stream": 7, "channel": 4, "periph_addr": "USART1_BASE + 0x04"},
            "USART2_RX": {"dma": "DMA1", "stream": 5, "channel": 4, "periph_addr": "USART2_BASE + 0x04"},
            "USART2_TX": {"dma": "DMA1", "stream": 6, "channel": 4, "periph_addr": "USART2_BASE + 0x04"},
            "USART3_RX": {"dma": "DMA1", "stream": 1, "channel": 4, "periph_addr": "USART3_BASE + 0x04"},
            "USART3_TX": {"dma": "DMA1", "stream": 3, "channel": 4, "periph_addr": "USART3_BASE + 0x04"},
            # SPI DMA requests
            "SPI1_RX": {"dma": "DMA2", "stream": 0, "channel": 3, "periph_addr": "SPI1_BASE + 0x0C"},
            "SPI1_TX": {"dma": "DMA2", "stream": 3, "channel": 3, "periph_addr": "SPI1_BASE + 0x0C"},
            "SPI2_RX": {"dma": "DMA1", "stream": 3, "channel": 0, "periph_addr": "SPI2_BASE + 0x0C"},
            "SPI2_TX": {"dma": "DMA1", "stream": 4, "channel": 0, "periph_addr": "SPI2_BASE + 0x0C"},
            # ADC DMA requests
            "ADC1": {"dma": "DMA2", "stream": 0, "channel": 0, "periph_addr": "ADC1_BASE + 0x4C"},
            # I2C DMA requests
            "I2C1_RX": {"dma": "DMA1", "stream": 0, "channel": 1, "periph_addr": "I2C1_BASE + 0x14"},
            "I2C1_TX": {"dma": "DMA1", "stream": 6, "channel": 1, "periph_addr": "I2C1_BASE + 0x14"},
            "I2C2_RX": {"dma": "DMA1", "stream": 2, "channel": 7, "periph_addr": "I2C2_BASE + 0x14"},
            "I2C2_TX": {"dma": "DMA1", "stream": 7, "channel": 7, "periph_addr": "I2C2_BASE + 0x14"},
            # TIM DMA requests
            "TIM1_UP": {"dma": "DMA2", "stream": 5, "channel": 6, "periph_addr": "TIM1_BASE + 0x2C"},
            "TIM2_UP": {"dma": "DMA1", "stream": 5, "channel": 3, "periph_addr": "TIM2_BASE + 0x2C"},
            "TIM3_UP": {"dma": "DMA1", "stream": 2, "channel": 5, "periph_addr": "TIM3_BASE + 0x2C"},
            "TIM4_UP": {"dma": "DMA1", "stream": 6, "channel": 2, "periph_addr": "TIM4_BASE + 0x2C"},
        }

        # Determine which DMA request key to look up
        request_key = peripheral.upper()
        if request_key.endswith("_RX") or request_key.endswith("_TX"):
            pass  # Already has RX/TX suffix
        else:
            # Default to RX for bidirectional peripherals
            request_key_rx = request_key + "_RX"
            if request_key_rx in dma_map:
                request_key = request_key_rx

        if request_key not in dma_map:
            ops.append(RegisterWrite(
                peripheral=peripheral,
                register="DMAR",
                field_name="",
                value=0,
                operation="write",
                description=f"DMA request for {peripheral} - no automatic mapping defined",
            ))
            return ops

        dma_info = dma_map[request_key]
        dma_unit = dma_info["dma"]
        stream = dma_info["stream"]
        channel = dma_info["channel"]

        # Determine if high (DMA2) or low (DMA1) register set
        if dma_unit == "DMA2":
            dma_base = "DMA2_Stream"
        else:
            dma_base = "DMA1_Stream"

        # CR register bit positions
        # EN=0, DMEIE=1, TEIE=2, HTIE=3, TCIE=4, PFCTRL=5, DIR=6:7, CIRC=8, PINC=9, MINC=10,
        # PSIZE=11:12, MSIZE=13:14, PINCOS=15, PL=16:17, DBM=18, CT=19, PB=20, MB=21, L=22
        # CR register bit positions
        # CHSEL bits for channel selection (bits 25-27 in CR)
        ops.append(RegisterWrite(
            peripheral=dma_unit,
            register=f"{dma_base}{stream}",
            field_name="CR",
            value=0,
            operation="write",
            description=f"Disable DMA stream {stream} before configuring",
        ))

        ops.append(RegisterWrite(
            peripheral=dma_unit,
            register=f"{dma_base}{stream}",
            field_name="CHSEL",
            value=channel,
            operation="write_bits",
            description=f"Select DMA channel {channel} for {peripheral}",
        ))

        ops.append(RegisterWrite(
            peripheral=dma_unit,
            register=f"{dma_base}{stream}",
            field_name="NDTR",
            value=0,
            operation="write",
            description="DMA number of data to transfer (set at runtime before enabling)",
        ))

        ops.append(RegisterWrite(
            peripheral=dma_unit,
            register=f"{dma_base}{stream}",
            field_name="PAR",
            value=0,
            operation="write",
            description=f"DMA peripheral address (set {peripheral} DR register at runtime)",
        ))

        ops.append(RegisterWrite(
            peripheral=dma_unit,
            register=f"{dma_base}{stream}",
            field_name="M0AR",
            value=0,
            operation="write",
            description="DMA memory 0 address (set buffer address at runtime)",
        ))

        ops.append(RegisterWrite(
            peripheral=dma_unit,
            register=f"{dma_unit}_IFCR",
            field_name="",
            value=(1 << (stream * 4)),
            operation="write",
            description=f"Clear all flags for stream {stream} before enabling",
        ))

        return ops

    def _loopback_enable_regs(self, peripheral: str) -> List[RegisterWrite]:
        """Add loopback mode register writes."""
        ops = []
        ptype = peripheral.upper()

        if "CAN" in ptype:
            ops.append(RegisterWrite(
                peripheral=peripheral,
                register="BTR",
                field_name="LBKM",
                value=1,
                operation="set_bit",
                description="CAN loopback mode enable",
            ))
        elif "SPI" in ptype:
            ops.append(RegisterWrite(
                peripheral=peripheral,
                register="CR2",
                field_name="RXDMAEN",
                value=1,
                operation="set_bit",
                description="SPI RX DMA enable",
            ))

        return ops

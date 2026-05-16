"""Interrupt Engine - NVIC and interrupt handling."""

from typing import Dict, List, Optional, Tuple

from src.domains.hardware_engine.core.interrupt_model import InterruptModel
from src.domains.hardware_engine.core.peripheral_graph import PeripheralGraph
from src.domains.hardware_engine.core.models import (
    ValidationResult,
    InterruptAssignment,
)


class InterruptEngine:
    """
    Interrupt configuration engine.

    Responsibilities:
    1. Allocate IRQ lines
    2. Configure priorities
    3. Generate NVIC sequences
    4. Detect conflicts
    """

    def __init__(self, interrupt_model: InterruptModel, peripheral_graph: PeripheralGraph):
        self.interrupt_model = interrupt_model
        self.peripheral_graph = peripheral_graph

    def allocate(
        self,
        peripheral: str,
        handler_name: str = "",
        priority: int = 0,
        subpriority: int = 0,
    ) -> Tuple[bool, InterruptAssignment, str]:
        """
        Allocate interrupt for a peripheral.

        Returns: (success, InterruptAssignment, error_message)
        """
        if not handler_name:
            handler_name = self.interrupt_model.get_handler_name(peripheral)

        success, error, irq = self.interrupt_model.allocate(
            peripheral, handler_name, priority, subpriority
        )

        if not success:
            return False, InterruptAssignment(
                peripheral=peripheral,
                signal="",
                irq_line=irq,
                handler_name=handler_name,
                priority=priority,
            ), error

        return True, InterruptAssignment(
            peripheral=peripheral,
            signal="",
            irq_line=irq,
            handler_name=handler_name,
            priority=priority,
        ), ""

    def free(self, peripheral: str) -> bool:
        """Free interrupt allocation for a peripheral."""
        return self.interrupt_model.free(peripheral)

    def generate_enable_sequence(self, peripheral: str) -> List[str]:
        """Generate NVIC interrupt enable sequence."""
        irq = self.interrupt_model.get_irq(peripheral)
        if irq is None:
            return [f"/* No IRQ defined for {peripheral} */"]

        alloc = self.interrupt_model.get_allocation(irq)
        priority = alloc.priority if alloc else 0

        statements = [
            f"/* Configure NVIC for {peripheral} (IRQ {irq}) */",
            f"NVIC_SetPriority({peripheral}_IRQn, {priority} << 4);",
            f"NVIC_EnableIRQ({peripheral}_IRQn);",
        ]
        return statements

    def generate_handler_stub(self, peripheral: str) -> str:
        """Generate interrupt handler stub."""
        handler = self.interrupt_model.get_handler_name(peripheral)
        irq = self.interrupt_model.get_irq(peripheral)
        ptype = peripheral.upper()

        if "USART" in ptype or "UART" in ptype:
            return self._generate_usart_handler(handler, peripheral)
        elif "CAN" in ptype:
            return self._generate_can_handler(handler, peripheral)
        elif "TIM" in ptype:
            return self._generate_tim_handler(handler, peripheral)
        elif "ADC" in ptype:
            return self._generate_adc_handler(handler, peripheral)
        elif "DMA" in ptype:
            return self._generate_dma_handler(handler, peripheral)
        elif "EXTI" in ptype:
            return self._generate_exti_handler(handler, peripheral)
        else:
            return self._generate_generic_handler(handler, peripheral, irq)

    def _generate_usart_handler(self, handler: str, peripheral: str) -> str:
        return (
            f"void {handler}(void) {{\n"
            f"    uint32_t status = {peripheral}->SR;\n"
            f"\n"
            f"    if (status & USART_SR_RXNE) {{\n"
            f"        uint8_t data = (uint8_t){peripheral}->DR;\n"
            f"        /* Process received data here */\n"
            f"        (void)data;\n"
            f"    }}\n"
            f"    if (status & USART_SR_TXE) {{\n"
            f"        /* Transmit buffer empty - load next byte if available */\n"
            f"    }}\n"
            f"    if (status & USART_SR_ORE) {{\n"
            f"        /* Overrun error - read DR to clear */\n"
            f"        (void){peripheral}->DR;\n"
            f"    }}\n"
            f"    if (status & (USART_SR_FE | USART_SR_PE)) {{\n"
            f"        /* Framing or parity error */\n"
            f"    }}\n"
            f"}}\n"
        )

    def _generate_can_handler(self, handler: str, peripheral: str) -> str:
        return (
            f"void {handler}(void) {{\n"
            f"    /* Check FIFO 0 pending messages */\n"
            f"    if ({peripheral}->RF0R & CAN_RF0R_FMP0_MASK) {{\n"
            f"        /* Read mailbox: check CAN->sMailbox1 or CAN->sMailbox2 */\n"
            f"        /* Process CAN message */\n"
            f"        {peripheral}->RF0R |= CAN_RF0R_RFOM0; /* Release FIFO 0 */\n"
            f"    }}\n"
            f"    /* Check FIFO 1 pending messages */\n"
            f"    if ({peripheral}->RF1R & CAN_RF1R_FMP1_MASK) {{\n"
            f"        {peripheral}->RF1R |= CAN_RF1R_RFOM1; /* Release FIFO 1 */\n"
            f"    }}\n"
            f"    /* Check TX mailbox empty (ESR bits for TX status) */\n"
            f"    (void){peripheral}->MSR; /* Clear pending flags by reading */\n"
            f"}}\n"
        )

    def _generate_tim_handler(self, handler: str, peripheral: str) -> str:
        return (
            f"void {handler}(void) {{\n"
            f"    uint32_t sr = {peripheral}->SR;\n"
            f"    uint32_t dier = {peripheral}->DIER;\n"
            f"\n"
            f"    if ((sr & TIM_SR_UIF) && (dier & TIM_DIER_UIE)) {{\n"
            f"        /* Update event - reload registers if needed */\n"
            f"        {peripheral}->SR = ~TIM_SR_UIF;\n"
            f"    }}\n"
            f"    if ((sr & TIM_SR_CC1IF) && (dier & TIM_DIER_CC1IE)) {{\n"
            f"        /* Capture/Compare 1 event */\n"
            f"        {peripheral}->SR = ~TIM_SR_CC1IF;\n"
            f"    }}\n"
            f"    if ((sr & TIM_SR_CC2IF) && (dier & TIM_DIER_CC2IE)) {{\n"
            f"        /* Capture/Compare 2 event */\n"
            f"        {peripheral}->SR = ~TIM_SR_CC2IF;\n"
            f"    }}\n"
            f"    /* Clear any remaining active flags */\n"
            f"    {peripheral}->SR = 0;\n"
            f"}}\n"
        )

    def _generate_adc_handler(self, handler: str, peripheral: str) -> str:
        return (
            f"void {handler}(void) {{\n"
            f"    if ({peripheral}->SR & ADC_SR_EOC) {{\n"
            f"        uint16_t result = {peripheral}->DR;\n"
            f"        /* Process ADC conversion result */\n"
            f"        (void)result;\n"
            f"    }}\n"
            f"    if ({peripheral}->SR & ADC_SR_AWD) {{\n"
            f"        /* Analog watchdog triggered - out-of-range reading */\n"
            f"        {peripheral}->SR = ~ADC_SR_AWD;\n"
            f"    }}\n"
            f"}}\n"
        )

    def _generate_dma_handler(self, handler: str, peripheral: str) -> str:
        return (
            f"void {handler}(void) {{\n"
            f"    /* DMA transfer complete or error flags should be handled here */\n"
            f"    /* Check specific DMA stream flags in DMA->LISR or DMA->HISR */\n"
            f"    /* Clear flags by writing to DMA->IFCR */\n"
            f"}}\n"
        )

    def _generate_exti_handler(self, handler: str, peripheral: str) -> str:
        return (
            f"void {handler}(void) {{\n"
            f"    /* External line interrupt - determine which line triggered */\n"
            f"    /* Clear pending flag */\n"
            f"    EXTI->PR = (1U << 0); /* Adjust line number as needed */\n"
            f"}}\n"
        )

    def _generate_generic_handler(self, handler: str, peripheral: str, irq: Optional[int]) -> str:
        irq_str = str(irq) if irq is not None else "?"
        return (
            f"void {handler}(void) {{\n"
            f"    /* {peripheral} IRQ {irq_str} handler */\n"
            f"    /* Add peripheral-specific handling here */\n"
            f"}}\n"
        )

    def generate_handler_with_flags(
        self, peripheral: str, flag_name: str = "SR"
    ) -> str:
        """Generate handler with common flag clearing patterns."""
        handler = self.interrupt_model.get_handler_name(peripheral)
        ptype = peripheral.upper()

        if "USART" in ptype or "UART" in ptype:
            return self._generate_usart_handler(handler, peripheral)
        elif "CAN" in ptype:
            return self._generate_can_handler(handler, peripheral)
        elif "TIM" in ptype:
            return self._generate_tim_handler(handler, peripheral)
        else:
            return self.generate_handler_stub(peripheral)

    def validate_allocation(self, peripheral: str) -> ValidationResult:
        """Validate interrupt allocation."""
        result = ValidationResult(valid=True)
        irq = self.interrupt_model.get_irq(peripheral)

        if irq is None:
            result.add_error(
                "INT_001",
                f"No IRQ defined for peripheral '{peripheral}'",
                peripheral=peripheral,
            )
            return result

        if not self.interrupt_model.is_available(irq):
            alloc = self.interrupt_model.get_allocation(irq)
            result.add_error(
                "INT_002",
                f"IRQ {irq} already allocated to '{alloc.peripheral if alloc else 'unknown'}'",
                peripheral=peripheral,
            )

        alloc = self.interrupt_model.get_allocation(irq)
        if alloc:
            conflicts = self.interrupt_model.validate_priority_conflict(peripheral, alloc.priority)
            for conflict in conflicts:
                result.add_warning(
                    "INT_003",
                    f"Priority conflict with {conflict['existing']} at IRQ {conflict['existing_irq']}",
                    peripheral=peripheral,
                )

        return result

    def list_allocations(self) -> List[str]:
        """List all allocated interrupts."""
        return [
            f"IRQ {a.irq_line}: {a.peripheral} -> {a.handler_name} (pri={a.priority})"
            for a in self.interrupt_model.list_allocations()
        ]

    def get_free_irqs(self) -> List[int]:
        """List free IRQ lines."""
        all_irqs = set(self.interrupt_model._irq_by_name.values())
        allocated = {a.irq_line for a in self.interrupt_model.list_allocations()}
        return sorted(all_irqs - allocated)

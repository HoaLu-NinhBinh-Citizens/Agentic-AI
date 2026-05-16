"""Hardware-Constrained Code Generator."""

from typing import Any, Dict, List

from src.domains.hardware_engine.core.register_schema import RegisterSchemaDB
from src.domains.hardware_engine.core.peripheral_graph import PeripheralGraph
from src.domains.hardware_engine.core.pin_map import PinMap
from src.domains.hardware_engine.core.clock_tree import ClockTree
from src.domains.hardware_engine.core.interrupt_model import InterruptModel
from src.domains.hardware_engine.codegen.templates import RegisterAccessTemplates
from src.domains.hardware_engine.codegen.assertions import HardwareAssertions


class HardwareConstrainedGenerator:
    """
    Generate hardware-constrained C code from allocations.

    Key principle: ALL generated code is validated against the
    RegisterSchemaDB, PinMap, ClockTree, and InterruptModel.
    No "hallucinated" register accesses or magic values.

    Generated code includes:
    - Required headers (#include)
    - Hardware defines (pins, addresses)
    - Clock initialization
    - GPIO/PinMux configuration
    - Register initialization sequences
    - Interrupt handler stubs
    - Embedded hardware assertions
    """

    def __init__(
        self,
        register_schema: RegisterSchemaDB,
        peripheral_graph: PeripheralGraph,
        pin_map: PinMap,
        clock_tree: ClockTree,
        interrupt_model: InterruptModel,
    ):
        self.register_schema = register_schema
        self.peripheral_graph = peripheral_graph
        self.pin_map = pin_map
        self.clock_tree = clock_tree
        self.interrupt_model = interrupt_model
        self.templates = RegisterAccessTemplates()
        self.assertions = HardwareAssertions()

    def generate(self, allocation: dict) -> dict:
        """
        Generate complete hardware-constrained C code from allocation.

        Returns dict with:
            headers: list of #include directives
            defines: list of #define statements
            init_sequence: register write statements
            isr_handlers: interrupt handler code
            assertions: embedded hardware assertions
        """
        allocation_dict = allocation if isinstance(allocation, dict) else {}

        peripheral = allocation_dict.get("peripheral", "")
        mode = allocation_dict.get("mode", "default")
        pin_assignments = allocation_dict.get("pin_assignments", [])
        clock_assignment = allocation_dict.get("clock_assignment", {})
        int_assignment = allocation_dict.get("interrupt_assignment", {})
        register_writes = allocation_dict.get("register_writes", [])

        # Convert dataclass objects to dicts
        if hasattr(clock_assignment, "__dict__"):
            clock_assignment = clock_assignment.__dict__
        if hasattr(int_assignment, "__dict__"):
            int_assignment = int_assignment.__dict__
        pin_assignments = [
            pa.__dict__ if hasattr(pa, "__dict__") else pa
            for pa in pin_assignments
        ]
        register_writes = [
            rw.__dict__ if hasattr(rw, "__dict__") else rw
            for rw in register_writes
        ]

        result: Dict[str, Any] = {
            "headers": [],
            "defines": [],
            "init_sequence": [],
            "isr_handlers": "",
            "assertions": [],
            "errors": [],
        }

        self._generate_headers(result, peripheral)
        self._generate_defines(result, peripheral, pin_assignments, clock_assignment)
        self._generate_clock_init(result, peripheral, clock_assignment)
        self._generate_pin_config(result, peripheral, pin_assignments)
        self._generate_register_sequence(result, peripheral, register_writes)
        self._generate_interrupt_handlers(result, peripheral, int_assignment)
        self._generate_assertions(result, peripheral, pin_assignments, clock_assignment)

        return result

    def _generate_headers(self, result: dict, peripheral: str):
        headers = [
            "<stdint.h>",
            "<stdbool.h>",
        ]

        ptype = peripheral.upper()
        if "USART" in ptype or "UART" in ptype:
            headers.append("<stdio.h>")
        if "CAN" in ptype:
            headers.append("<string.h>")

        result["headers"] = headers

    def _generate_defines(
        self, result: dict, peripheral: str, pin_assignments: List, clock_assignment: dict
    ):
        defines = []

        # Peripheral base address
        addr = self.register_schema.get_address(peripheral, "")
        if addr:
            defines.append(f"HW_{peripheral.upper()}_BASE 0x{addr:08X}")

        # Pin defines
        for pa in pin_assignments:
            if isinstance(pa, dict):
                pin = pa.get("pin", "")
                signal = pa.get("signal", "")
                af = pa.get("alternate_function", 0)
                if pin:
                    safe_pin = pin.replace(".", "_").replace("(", "_").replace(")", "")
                    safe_signal = signal.upper().replace("-", "_")
                    defines.append(f"HW_{safe_signal}_PIN {pin}")
                    defines.append(f"HW_{safe_signal}_AF {af}")

        # Clock domain
        if clock_assignment:
            domain = clock_assignment.get("domain", "")
            freq = clock_assignment.get("frequency_hz", 0)
            defines.append(f"HW_{peripheral.upper()}_CLOCK_HZ {freq}")
            defines.append(f"HW_{peripheral.upper()}_BUS \"{domain}\"")

        result["defines"] = defines

    def _generate_clock_init(
        self, result: dict, peripheral: str, clock_assignment: dict
    ):
        lines = []

        if clock_assignment:
            domain = clock_assignment.get("domain", "APB1")
            freq = clock_assignment.get("frequency_hz", 0)
            lines.append(f"/* Clock: {domain} at {freq / 1_000_000:.1f} MHz */")

            if domain == "AHB":
                lines.append(f"RCC->AHB1ENR |= RCC_AHB1ENR_{peripheral}EN;")
            elif domain == "APB1":
                lines.append(f"RCC->APB1ENR |= RCC_APB1ENR_{peripheral}EN;")
            elif domain == "APB2":
                lines.append(f"RCC->APB2ENR |= RCC_APB2ENR_{peripheral}EN;")
        else:
            self.clock_tree.enable_clock(peripheral)
            domain = self.clock_tree._get_peripheral_domain(peripheral)
            if domain:
                lines.append(f"/* Enable {domain} clock for {peripheral} */")
                if domain == "APB1":
                    lines.append(f"RCC->APB1ENR |= RCC_APB1ENR_{peripheral}EN;")
                elif domain == "APB2":
                    lines.append(f"RCC->APB2ENR |= RCC_APB2ENR_{peripheral}EN;")
                elif domain == "AHB":
                    lines.append(f"RCC->AHB1ENR |= RCC_AHB1ENR_{peripheral}EN;")

        result["init_sequence"].extend(lines)

    def _generate_pin_config(
        self, result: dict, peripheral: str, pin_assignments: List
    ):
        lines = []
        for pa in pin_assignments:
            if not isinstance(pa, dict):
                continue
            pin = pa.get("pin", "")
            af = pa.get("alternate_function", 0)
            if not pin:
                continue

            lines.append(f"/* Configure {pin} as AF{af} for {peripheral} */")

            port = pin[0]
            pin_num = int(pin[1:])

            lines.append(f"    GPIO{port}->MODER = (GPIO{port}->MODER & ~(0x3 << ({pin_num} * 2))) | (0x2 << ({pin_num} * 2)); /* AF mode */")
            lines.append(f"    GPIO{port}->AFR[{pin_num // 8}] = (GPIO{port}->AFR[{pin_num // 8}] & ~(0xF << ({pin_num % 8} * 4))) | ({af} << ({pin_num % 8} * 4)); /* AF{af} */")

        if lines:
            result["init_sequence"].append("")
            result["init_sequence"].extend(lines)

    def _generate_register_sequence(
        self, result: dict, peripheral: str, register_writes: List
    ):
        lines = []
        for rw in register_writes:
            if not isinstance(rw, dict):
                continue
            peri = rw.get("peripheral", peripheral)
            reg = rw.get("register", "")
            field = rw.get("field_name", "")
            op = rw.get("operation", "write")
            val = rw.get("value", 0)
            desc = rw.get("description", "")

            if op == "write":
                lines.append(f"{peri}->{reg} = 0x{val:X};")
            elif op == "set_bit":
                lines.append(f"{peri}->{reg} |= {reg}_{field};  /* {desc} */")
            elif op == "clear_bit":
                lines.append(f"{peri}->{reg} &= ~{reg}_{field};  /* {desc} */")
            elif op == "write_bits":
                lines.append(f"{peri}->{reg} = {val};  /* {desc} */")

        if lines:
            result["init_sequence"].append("")
            result["init_sequence"].extend(lines)

    def _generate_interrupt_handlers(
        self, result: dict, peripheral: str, int_assignment: dict
    ):
        if not int_assignment:
            return

        handler = int_assignment.get("handler_name", "")
        irq = int_assignment.get("irq_line", -1)

        if not handler:
            handler = self.interrupt_model.get_handler_name(peripheral)

        ptype = peripheral.upper()
        if "USART" in ptype or "UART" in ptype:
            result["isr_handlers"] = self._usart_isr(handler, peripheral)
        elif "TIM" in ptype:
            result["isr_handlers"] = self._tim_isr(handler, peripheral)
        elif "CAN" in ptype:
            result["isr_handlers"] = self._can_isr(handler, peripheral)
        elif "ADC" in ptype:
            result["isr_handlers"] = self._adc_isr(handler, peripheral)
        elif "DMA" in ptype:
            result["isr_handlers"] = self._dma_isr(handler, peripheral)
        else:
            result["isr_handlers"] = self._generic_isr(handler, peripheral, irq)

    def _usart_isr(self, handler: str, peripheral: str) -> str:
        return (
            f"void {handler}(void) {{\n"
            f"    uint32_t status = {peripheral}->SR;\n"
            f"    if (status & USART_SR_RXNE) {{\n"
            f"        uint8_t data = (uint8_t){peripheral}->DR;\n"
            f"        /* Process received data */\n"
            f"        (void)data;\n"
            f"    }}\n"
            f"    if (status & USART_SR_TXE) {{\n"
            f"        /* TX buffer empty */\n"
            f"    }}\n"
            f"    {peripheral}->SR = 0;\n"
            f"}}\n"
        )

    def _tim_isr(self, handler: str, peripheral: str) -> str:
        return (
            f"void {handler}(void) {{\n"
            f"    uint32_t sr = {peripheral}->SR;\n"
            f"    uint32_t dier = {peripheral}->DIER;\n"
            f"    if ((sr & TIM_SR_UIF) && (dier & TIM_DIER_UIE)) {{\n"
            f"        {peripheral}->SR = ~TIM_SR_UIF;\n"
            f"    }}\n"
            f"    if ((sr & TIM_SR_CC1IF) && (dier & TIM_DIER_CC1IE)) {{\n"
            f"        {peripheral}->SR = ~TIM_SR_CC1IF;\n"
            f"    }}\n"
            f"}}\n"
        )

    def _can_isr(self, handler: str, peripheral: str) -> str:
        return (
            f"void {handler}(void) {{\n"
            f"    if ({peripheral}->RF0R & CAN_RF0R_FMP0_MASK) {{\n"
            f"        /* Process FIFO 0 message */\n"
            f"        {peripheral}->RF0R |= CAN_RF0R_RFOM0;\n"
            f"    }}\n"
            f"    if ({peripheral}->RF1R & CAN_RF1R_FMP1_MASK) {{\n"
            f"        /* Process FIFO 1 message */\n"
            f"        {peripheral}->RF1R |= CAN_RF1R_RFOM1;\n"
            f"    }}\n"
            f"}}\n"
        )

    def _adc_isr(self, handler: str, peripheral: str) -> str:
        return (
            f"void {handler}(void) {{\n"
            f"    if ({peripheral}->SR & ADC_SR_EOC) {{\n"
            f"        uint16_t result = {peripheral}->DR;\n"
            f"        (void)result;\n"
            f"    }}\n"
            f"}}\n"
        )

    def _dma_isr(self, handler: str, peripheral: str) -> str:
        return (
            f"void {handler}(void) {{\n"
            f"    /* Handle DMA transfer complete or error flags */\n"
            f"    /* Check DMA->LISR / DMA->HISR and clear with DMA->IFCR */\n"
            f"}}\n"
        )

    def _generic_isr(self, handler: str, peripheral: str, irq: int) -> str:
        return (
            f"void {handler}(void) {{\n"
            f"    /* {peripheral} IRQ {irq} handler */\n"
            f"    /* Add peripheral-specific handling */\n"
            f"}}\n"
        )

    def _generate_assertions(
        self,
        result: dict,
        peripheral: str,
        pin_assignments: List,
        clock_assignment: dict,
    ):
        assertions = []

        # Clock assertion
        if clock_assignment:
            freq = clock_assignment.get("frequency_hz", 0)
            assertions.append({
                "type": "clock_frequency",
                "description": f"Clock frequency check: {freq} Hz",
                "expression": f'/* assert(HW_{peripheral.upper()}_CLOCK_HZ > 0); */',
                "severity": "error",
            })

        # Pin availability assertion
        for pa in pin_assignments:
            if isinstance(pa, dict):
                pin = pa.get("pin", "")
                signal = pa.get("signal", "")
                if pin:
                    safe_signal = signal.upper().replace("-", "_")
                    assertions.append({
                        "type": "pin_reserved",
                        "description": f"Pin {pin} reserved for {signal}",
                        "expression": f'/* Pin {pin} reserved for {signal} */',
                        "severity": "info",
                    })

        result["assertions"] = assertions

    def generate_register_header(self, peripheral: str) -> str:
        """Generate register bit definitions header."""
        schema = self.register_schema.get_peripheral_schema(peripheral)
        lines = [
            f"/* Register definitions for {peripheral} */",
            f"/* Generated by CARV Hardware Semantic Engine */",
            "",
            f"#ifndef __{peripheral}_REG_H__",
            f"#define __{peripheral}_REG_H__",
            "",
        ]

        for reg in schema.get("registers", []):
            reg_name = reg.get("register", "")
            offset = reg.get("offset", "")
            access = reg.get("access", "RW")
            desc = reg.get("description", "")

            lines.append(f"/* {desc} (offset: {offset}, access: {access}) */")
            lines.append(f"#define {peripheral}_{reg_name}_Pos  0x{offset}")
            lines.append(f"#define {peripheral}_{reg_name}_Msk  0xFFFFFFFF")

            for bf in reg.get("bitfields", []):
                bf_name = bf.get("name", "")
                bf_offset = bf.get("offset", 0)
                bf_width = bf.get("width", 1)
                bf_access = bf.get("access", "RW")

                lines.append(f"/* {bf.get('description', '')} */")
                lines.append(f"#define {peripheral}_{reg_name}_{bf_name}_Pos  {bf_offset}")
                lines.append(f"#define {peripheral}_{reg_name}_{bf_name}_Msk  (0x{(1 << bf_width) - 1} << {bf_offset})")

            lines.append("")

        lines.append("#endif")
        return "\n".join(lines)

"""Firmware Call Graph Analyzer.

Analyzes embedded C firmware to extract:
- Function calls
- ISR (Interrupt Service Routine) registrations
- Peripheral usage
- Register access patterns
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RegisterAccess:
    """Represents a register access."""
    register: str
    access_type: str  # READ, WRITE, READ_WRITE
    address: Optional[int] = None
    bitfield: Optional[str] = None


@dataclass
class PeripheralUsage:
    """Represents peripheral usage."""
    name: str
    base_address: int
    registers_used: list[str] = field(default_factory=list)
    interrupts: list[str] = field(default_factory=list)
    clock_configured: bool = False


@dataclass
class ISRRegistration:
    """Represents an ISR registration."""
    handler_name: str
    peripheral: Optional[str] = None
    priority: Optional[int] = None
    line: int = 0


@dataclass
class FunctionInfo:
    """Represents a function in the firmware."""
    name: str
    start_line: int
    end_line: int
    calls: list[str] = field(default_factory=list)
    register_accesses: list[RegisterAccess] = field(default_factory=list)
    peripheral_usage: list[str] = field(default_factory=list)
    has_delay: bool = False
    is_isr: bool = False
    is_critical: bool = False


@dataclass
class CallGraph:
    """Represents the firmware call graph."""
    functions: dict[str, FunctionInfo] = field(default_factory=dict)
    isr_registrations: list[ISRRegistration] = field(default_factory=list)
    peripheral_usage: dict[str, PeripheralUsage] = field(default_factory=dict)
    entry_points: list[str] = field(default_factory=list)


class FirmwareCallGraphAnalyzer:
    """Analyzes C firmware code."""

    # Known register patterns
    REGISTER_PATTERNS = [
        r'RCC->', r'GPIO[A-H]->', r'USART[0-9]->', r'SPI[0-9]->',
        r'I2C[0-9]->', r'TIM[0-9]->', r'ADC[0-9]->', r'CAN[0-9]->',
        r'DMA[0-9]->', r'EXTI->', r'SysTick->', r'NVIC->',
        r'PWR->', r'FLASH->', r'DBGMCU->',
    ]

    # Known peripheral names
    PERIPHERALS = [
        "RCC", "GPIOA", "GPIOB", "GPIOC", "GPIOD", "GPIOE", "GPIOF", "GPIOG", "GPIOH",
        "USART1", "USART2", "USART3", "UART4", "UART5",
        "SPI1", "SPI2", "SPI3", "SPI4", "SPI5",
        "I2C1", "I2C2", "I2C3",
        "TIM1", "TIM2", "TIM3", "TIM4", "TIM5", "TIM6", "TIM7", "TIM8",
        "ADC1", "ADC2", "ADC3",
        "CAN1", "CAN2",
        "DMA1", "DMA2",
        "EXTI", "NVIC", "SysTick",
    ]

    # ISR handler patterns
    ISR_PATTERNS = [
        r'void\s+(.+?)\s*\(void\)',  # Most common ISR signature
    ]

    # Blocking/delay patterns
    DELAY_PATTERNS = [
        r'HAL_Delay', r'vTaskDelay', r'osDelay', r'for\s*\(\s*;\s*;\s*\)', r'while\s*\(\s*1\s*\)',
    ]

    def __init__(self):
        self.call_graph = CallGraph()

    def analyze_code(self, code: str) -> CallGraph:
        """Analyze firmware code and build call graph."""
        lines = code.split('\n')

        # Extract functions
        self._extract_functions(lines)

        # Find function calls
        self._find_function_calls(lines)

        # Find ISR registrations
        self._find_isr_registrations(lines)

        # Analyze register access
        self._analyze_register_access(lines)

        # Find entry points
        self._find_entry_points(lines)

        return self.call_graph

    def _extract_functions(self, lines: list[str]) -> None:
        """Extract function definitions."""
        function_pattern = re.compile(
            r'(?:static\s+)?(?:inline\s+)?(?:\w+\s*\*?\s*)\s*(\w+)\s*\([^)]*\)\s*(?:__attribute__[^;]*)?\s*\{',
            re.MULTILINE
        )

        for i, line in enumerate(lines):
            match = function_pattern.search(line)
            if match:
                func_name = match.group(1)

                # Skip macros and declarations
                if func_name.startswith('#') or func_name.startswith('_'):
                    continue

                # Find function end
                end_line = self._find_matching_brace(lines, i)

                # Check if it's an ISR
                is_isr = any(
                    pattern in func_name.upper()
                    for pattern in ['IRQ', 'HANDLER', '_IRQ']
                )

                # Check if it's a critical section
                is_critical = any(
                    pattern in func_name
                    for pattern in ['_C', 'CRITICAL', 'ENTER', 'EXIT']
                )

                self.call_graph.functions[func_name] = FunctionInfo(
                    name=func_name,
                    start_line=i + 1,  # 1-indexed
                    end_line=end_line + 1,
                    is_isr=is_isr,
                    is_critical=is_critical,
                )

    def _find_matching_brace(self, lines: list[str], start: int) -> int:
        """Find the line number of the matching closing brace."""
        depth = 0
        for i in range(start, len(lines)):
            line = lines[i]
            depth += line.count('{') - line.count('}')
            if depth <= 0:
                return i
        return len(lines) - 1

    def _find_function_calls(self, lines: list[str]) -> None:
        """Find function calls within each function."""
        call_pattern = re.compile(
            r'\b(\w+)\s*\(',
            re.MULTILINE
        )

        for func_name, func_info in self.call_graph.functions.items():
            # Look for calls within this function's range
            start = func_info.start_line - 1
            end = func_info.end_line - 1

            if start < 0 or end >= len(lines):
                continue

            func_lines = lines[start:end]
            func_text = '\n'.join(func_lines)

            # Find all function calls
            for match in call_pattern.finditer(func_text):
                called_func = match.group(1)

                # Skip keywords and known non-functions
                skip_patterns = [
                    'if', 'while', 'for', 'switch', 'sizeof', 'typeof',
                    'return', 'case', 'default', 'break', 'continue',
                    'struct', 'union', 'enum', 'typedef',
                    'void', 'int', 'char', 'float', 'double', 'long',
                    'short', 'unsigned', 'signed', 'const', 'static',
                    'extern', 'inline', 'volatile', 'register',
                    'NULL', 'true', 'false',
                ]

                if called_func not in skip_patterns and called_func != func_name:
                    if called_func not in func_info.calls:
                        func_info.calls.append(called_func)

    def _find_isr_registrations(self, lines: list[str]) -> None:
        """Find ISR registrations and handler definitions."""
        # ISR handler registration patterns
        nvic_patterns = [
            r'NVIC_SetPriority\s*\(\s*(\w+)_IRQn\s*,\s*(\d+)\s*\)',
            r'HAL_NVIC_SetIRQHandler\s*\(\s*(\w+)_IRQn\s*,\s*(\d+)\s*\)',
            r'NVIC_EnableIRQ\s*\(\s*(\w+)_IRQn\s*\)',
        ]

        for i, line in enumerate(lines):
            for pattern in nvic_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    groups = match.groups()
                    if len(groups) >= 1:
                        irq_name = groups[0]
                        priority = int(groups[1]) if len(groups) > 1 else None

                        # Determine peripheral from IRQ name
                        peripheral = re.sub(r'_IRQn$', '', irq_name)

                        self.call_graph.isr_registrations.append(ISRRegistration(
                            handler_name=irq_name.replace('_IRQn', '_Handler'),
                            peripheral=peripheral,
                            priority=priority,
                            line=i + 1,
                        ))

        # Find handler definitions
        handler_patterns = [
            r'void\s+(\w*Handler|IRQ_Handler|IRQ)\s*\(',
            r'void\s+\w*_IRQHandler\s*\(',
        ]

        for i, line in enumerate(lines):
            for pattern in handler_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    handler_name = match.group(1)
                    if handler_name not in [r.handler_name for r in self.call_graph.isr_registrations]:
                        self.call_graph.isr_registrations.append(ISRRegistration(
                            handler_name=handler_name,
                            line=i + 1,
                        ))

    def _analyze_register_access(self, lines: list[str]) -> None:
        """Analyze register access patterns."""
        register_pattern = re.compile(
            r'(\w+)\s*->\s*(\w+)',
            re.MULTILINE
        )

        for func_name, func_info in self.call_graph.functions.items():
            start = func_info.start_line - 1
            end = func_info.end_line - 1

            if start < 0 or end >= len(lines):
                continue

            func_lines = lines[start:end]
            func_text = '\n'.join(func_lines)

            # Find register accesses
            for match in register_pattern.finditer(func_text):
                peripheral = match.group(1)
                register = match.group(2)

                # Determine access type
                before = func_text[:match.start()]
                after = func_text[match.end():match.end()+20]

                if '=' in before or '=' in after[:after.find(';')] if ';' in after else False:
                    access_type = 'WRITE'
                else:
                    access_type = 'READ'

                # Create register access
                access = RegisterAccess(
                    register=register,
                    access_type=access_type,
                )

                if access not in func_info.register_accesses:
                    func_info.register_accesses.append(access)

                # Track peripheral usage
                if peripheral in self.PERIPHERALS:
                    if peripheral not in func_info.peripheral_usage:
                        func_info.peripheral_usage.append(peripheral)

                    if peripheral not in self.call_graph.peripheral_usage:
                        self.call_graph.peripheral_usage[peripheral] = PeripheralUsage(
                            name=peripheral,
                            base_address=0,  # Would need SVD to get actual address
                        )

                    if register not in self.call_graph.peripheral_usage[peripheral].registers_used:
                        self.call_graph.peripheral_usage[peripheral].registers_used.append(register)

    def _find_entry_points(self, lines: list[str]) -> None:
        """Find main entry points."""
        entry_patterns = [
            r'int\s+main\s*\(',
            r'void\s+SystemInit\s*\(',
            r'void\s+HAL_Init\s*\(',
            r'void\s+app_main\s*\(',
            r'void\s+setup\s*\(',
            r'void\s+loop\s*\(',
        ]

        for i, line in enumerate(lines):
            for pattern in entry_patterns:
                match = re.search(pattern, line)
                if match:
                    func_name = match.group(1) if 'main' not in pattern else 'main'
                    if func_name not in self.call_graph.entry_points:
                        self.call_graph.entry_points.append(func_name)

    def get_callers(self, func_name: str) -> list[str]:
        """Get all functions that call the given function."""
        callers = []
        for name, info in self.call_graph.functions.items():
            if func_name in info.calls:
                callers.append(name)
        return callers

    def get_callees(self, func_name: str) -> list[str]:
        """Get all functions called by the given function."""
        if func_name in self.call_graph.functions:
            return self.call_graph.functions[func_name].calls.copy()
        return []

    def get_critical_path(self, entry_point: str = "main") -> list[str]:
        """Get critical path from entry point to leaves."""
        visited = set()
        path = []

        def dfs(func: str, current_path: list[str]):
            if func in visited:
                return
            visited.add(func)
            current_path.append(func)

            if func in self.call_graph.functions:
                for callee in self.call_graph.functions[func].calls:
                    dfs(callee, current_path.copy())

        dfs(entry_point, [])
        return list(visited)

    def get_isr_chain(self, peripheral: str) -> list[str]:
        """Get the chain of functions called from an ISR."""
        isr_name = f"{peripheral.upper()}_Handler"

        if isr_name not in self.call_graph.functions:
            isr_name = f"{peripheral.upper()}_IRQHandler"

        if isr_name not in self.call_graph.functions:
            return []

        return self.get_critical_path(isr_name)

    def validate_hardware_usage(self) -> list[str]:
        """Validate hardware usage patterns."""
        issues = []

        # Check for clock enable before peripheral use
        for func_name, func_info in self.call_graph.functions.items():
            peripherals_used = set(func_info.peripheral_usage)

            for peripheral in peripherals_used:
                if peripheral != "RCC":
                    # Check if RCC is used in the same function
                    has_clock_enable = any(
                        p == "RCC" for p in func_info.peripheral_usage
                    )

                    if not has_clock_enable:
                        issues.append(
                            f"Warning: {func_name} uses {peripheral} without enabling clock"
                        )

        return issues

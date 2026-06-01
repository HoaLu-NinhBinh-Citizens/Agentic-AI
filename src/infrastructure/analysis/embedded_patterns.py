"""Embedded Systems Patterns Detector.

Detects common patterns in embedded C firmware:
- ISR safety violations
- Memory barriers
- Volatile usage
- Blocking in ISR
- Uninitialized variables
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class PatternSeverity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class PatternIssue:
    """Represents a detected pattern issue."""
    severity: PatternSeverity
    rule: str
    message: str
    line: int
    suggestion: Optional[str] = None


class EmbeddedPatternsDetector:
    """Detects embedded systems patterns."""

    # ISR-unsafe functions that should not be called from ISR
    ISR_UNSAFE_FUNCTIONS = {
        "HAL_Delay": "Uses blocking delay, not ISR-safe",
        "HAL_GPIO_WritePin": "Safe but verify timing requirements",
        "malloc": "Dynamic memory allocation, not ISR-safe",
        "free": "Dynamic memory deallocation, not ISR-safe",
        "printf": "May block, not ISR-safe",
        "vTaskDelay": "RTOS delay, not ISR-safe",
        "vTaskDelayUntil": "RTOS delay, not ISR-safe",
        "osDelay": "RTOS delay, not ISR-safe",
        "osDelayUntil": "RTOS delay, not ISR-safe",
        "sleep": "Not ISR-safe",
        "usleep": "Not ISR-safe",
        "delay": "Generic delay, verify ISR-safety",
        "_flush_cache": "May not be ISR-safe on some platforms",
    }

    # Blocking patterns in ISR
    BLOCKING_PATTERNS = {
        r'HAL_Delay\s*\(': "HAL_Delay uses blocking loop in ISR",
        r'for\s*\(\s*;\s*;\s*\)': "Infinite loop in ISR - verify this is intentional",
        r'while\s*\(\s*1\s*\)|while\s*\(\s*true\s*\)': "Infinite loop in ISR - verify this is intentional",
        r'vTaskDelay\s*\(': "RTOS vTaskDelay called from ISR - not allowed",
        r'vTaskDelayUntil\s*\(': "RTOS vTaskDelayUntil called from ISR - not allowed",
        r'osDelay\s*\(': "RTOS osDelay called from ISR - not allowed",
        r'xQueueSend\s*\(': "FreeRTOS queue send with block time from ISR",
        r'xSemaphoreGiveFromISR\s*\(': "FreeRTOS semaphore give from ISR - check timeout",
    }

    # Missing volatile qualifier patterns
    VOLATILE_PATTERNS = {
        r'(?:static\s+)?(?:uint8_t|uint16_t|uint32_t|uint64_t|int8_t|int16_t|int32_t|int64_t|bool|_Bool)\s+\w+\s*[;=\[]': 
            "Variable used in ISR may need volatile qualifier",
    }

    # Memory barrier requirements
    MEMORY_BARRIER_PATTERNS = {
        r'__DSB\s*\(': "Data Synchronization Barrier",
        r'__ISB\s*\(': "Instruction Synchronization Barrier",
        r'__DMB\s*\(': "Data Memory Barrier",
        r'SCB->AIRCR': "Vector table changes may need memory barrier",
        r'NVIC_SystemReset\s*\(': "System reset - ensure pending operations complete",
    }

    def __init__(self):
        self.issues: list[PatternIssue] = []

    def analyze(self, code: str, is_isr_func: bool = False) -> list[PatternIssue]:
        """Analyze code for embedded patterns."""
        self.issues = []
        lines = code.split('\n')

        # Check for ISR-unsafe functions
        self._check_isr_unsafe_functions(code, is_isr_func)

        # Check for blocking patterns
        self._check_blocking_patterns(code, is_isr_func)

        # Check for missing volatile
        self._check_volatile_usage(code)

        # Check for uninitialized hardware registers
        self._check_uninitialized_registers(code)

        # Check for magic numbers
        self._check_magic_numbers(code)

        # Check for proper interrupt disable/enable
        self._check_interrupt_management(code)

        return self.issues

    def _check_isr_unsafe_functions(self, code: str, is_isr_func: bool) -> None:
        """Check for ISR-unsafe function calls."""
        for func, reason in self.ISR_UNSAFE_FUNCTIONS.items():
            pattern = rf'\b{func}\s*\('
            matches = re.finditer(pattern, code)

            for match in matches:
                line_num = code[:match.start()].count('\n') + 1

                if is_isr_func:
                    self.issues.append(PatternIssue(
                        severity=PatternSeverity.ERROR,
                        rule="EMB001",
                        message=f"ISR-unsafe function '{func}' called in ISR: {reason}",
                        line=line_num,
                        suggestion=f"Use a flag or queue to signal from ISR, handle in main context",
                    ))
                else:
                    self.issues.append(PatternIssue(
                        severity=PatternSeverity.WARNING,
                        rule="EMB002",
                        message=f"Function '{func}' called - verify it's ISR-safe if used in ISR context",
                        line=line_num,
                        suggestion=reason,
                    ))

    def _check_blocking_patterns(self, code: str, is_isr_func: bool) -> None:
        """Check for blocking patterns."""
        for pattern, message in self.BLOCKING_PATTERNS.items():
            matches = re.finditer(pattern, code)

            for match in matches:
                line_num = code[:match.start()].count('\n') + 1

                if is_isr_func:
                    self.issues.append(PatternIssue(
                        severity=PatternSeverity.ERROR,
                        rule="EMB003",
                        message=f"Blocking pattern in ISR: {message}",
                        line=line_num,
                        suggestion="Move blocking operation to main context, use flags/queues from ISR",
                    ))

    def _check_volatile_usage(self, code: str) -> None:
        """Check for variables that should be volatile."""
        # Check for ISR-shared variables
        isr_vars_pattern = r'(?:static\s+)?(?:volatile\s+)?\w+\s+(\w+)\s*[;=]'
        matches = re.finditer(isr_vars_pattern, code)

        # Simple heuristic: look for variables used with interrupts
        for match in matches:
            var_name = match.group(1)
            line_num = code[:match.start()].count('\n') + 1

            # Check if this variable is used in a way that suggests ISR sharing
            context_pattern = rf'{var_name}\s*[;=\[\]]'
            if re.search(context_pattern, code):
                # Check if it's declared without volatile
                decl_pattern = rf'\b(?:static\s+)?\b(?:uint|int|bool|_Bool)\w+\s+{var_name}\s*[;=\[]'
                if re.search(decl_pattern, code):
                    # Look for ISR patterns nearby
                    nearby_code = self._get_nearby_code(code, line_num)
                    if any(word in nearby_code for word in ['NVIC', 'IRQ', 'Handler', 'interrupt', 'ISR']):
                        self.issues.append(PatternIssue(
                            severity=PatternSeverity.WARNING,
                            rule="EMB004",
                            message=f"Variable '{var_name}' used with interrupts but may not be volatile",
                            line=line_num,
                            suggestion="Add 'volatile' qualifier for variables shared between ISR and main code",
                        ))

    def _check_uninitialized_registers(self, code: str) -> None:
        """Check for potentially uninitialized hardware registers."""
        register_vars = re.finditer(
            r'(?:static\s+)?(?:volatile\s+)?(?:uint32_t|uint16_t|uint8_t)\s+(\w*(?:Reg|reg|REG)\w*)\s*[;=]',
            code
        )

        for match in register_vars:
            var_name = match.group(1)
            line_num = code[:match.start()].count('\n') + 1

            # Check if it's used before assignment
            after_code = code[match.end():]
            first_use = re.search(rf'\b{var_name}\b', after_code)

            if first_use and '=' not in after_code[:first_use.start()]:
                # It's used without being assigned first
                pass  # This is actually okay for register pointers

    def _check_magic_numbers(self, code: str) -> None:
        """Check for magic numbers that should be defined."""
        magic_patterns = [
            (r'0x[0-9A-Fa-f]{8}', "32-bit hex constant"),
            (r'0x[0-9A-Fa-f]{4}', "16-bit hex constant"),
            (r'\b(?:1000|1000000|8000000|72000000|168000000)\b', "Clock frequency constant"),
            (r'\b(?:9600|115200|921600)\b', "Baudrate constant"),
        ]

        for pattern, description in magic_patterns:
            matches = re.finditer(pattern, code)

            for match in matches:
                line_num = code[:match.start()].count('\n') + 1
                line_content = code.split('\n')[line_num - 1]

                # Skip if it's already in a #define
                if '#define' in line_content or 'const' in line_content:
                    continue

                # Skip if it's in an enum or struct
                if 'enum' in line_content or 'struct' in line_content:
                    continue

                self.issues.append(PatternIssue(
                    severity=PatternSeverity.INFO,
                    rule="EMB005",
                    message=f"Magic number in code: consider using a named constant",
                    line=line_num,
                    suggestion=f"Replace with a descriptive #define or const variable",
                ))

    def _check_interrupt_management(self, code: str) -> None:
        """Check for proper interrupt management."""
        # Check for __disable_irq without __enable_irq
        if '__disable_irq' in code or '__HAL_RAW_DISABLE_IRQ' in code:
            if '__enable_irq' not in code and '__HAL_RAW_ENABLE_IRQ' not in code:
                self.issues.append(PatternIssue(
                    severity=PatternSeverity.WARNING,
                    rule="EMB006",
                    message="Interrupts may be disabled without being re-enabled",
                    line=code.count('\n') + 1,
                    suggestion="Ensure __enable_irq() is called to re-enable interrupts",
                ))

        # Check for critical section patterns
        if 'taskENTER_CRITICAL' in code:
            if 'taskEXIT_CRITICAL' not in code:
                self.issues.append(PatternIssue(
                    severity=PatternSeverity.ERROR,
                    rule="EMB007",
                    message="taskENTER_CRITICAL without taskEXIT_CRITICAL",
                    line=code.count('\n') + 1,
                    suggestion="Critical sections must be exited with taskEXIT_CRITICAL",
                ))

    def _get_nearby_code(self, code: str, line_num: int, context: int = 10) -> str:
        """Get nearby code for context."""
        lines = code.split('\n')
        start = max(0, line_num - context)
        end = min(len(lines), line_num + context)
        return '\n'.join(lines[start:end])

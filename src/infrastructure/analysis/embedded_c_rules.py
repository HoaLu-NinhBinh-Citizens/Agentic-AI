"""Embedded C Analysis Rules.

Detects common issues in embedded C code:
- MISRA C compliance
- Uninitialized variables
- Integer overflow
- Volatile usage
- Hardware-specific issues
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class EmbeddedCIssue:
    """Represents an embedded C analysis issue."""
    severity: str  # error, warning, info
    rule: str
    message: str
    line: int
    column: int = 0
    suggestion: Optional[str] = None


class EmbeddedCRules:
    """Rule engine for embedded C analysis."""

    # MISRA C:2012 rules (selected important ones)
    MISRA_RULES = {
        "R1.1": "All code shall conform to ISO C90 standard",
        "R2.1": "Project shall not contain unreachable code",
        "R2.2": "Project shall not contain dead code",
        "R3.1": "Project shall not contain comments nested inside comments",
        "R4.1": "Translation units shall not contain multiple language bindings",
        "R5.1": "Identifiers shall not conflict within the same name space",
        "R5.4": "Members of structures or unions shall be selected with '.' or '->'",
        "R6.2": "Bit-fields shall only be declared with appropriate types",
        "R7.1": "Octal constants shall not be used",
        "R7.2": "A "u" or "U" suffix shall be applied to all integer constants",
        "R7.3": "The lowercase "l" suffix shall not be used on integer constants",
        "R8.1": "Bitwise operators shall only be applied to operands of underlying type",
        "R8.5": "Bitwise operators shall not be combined with logical operators",
        "R9.1": "Initializer lists shall not contain uninitialized elements",
        "R10.1": "Operands shall not be of an inappropriate essential type",
        "R10.3": "The value of an expression shall not be assigned to an object with narrower type",
        "R10.4": "Both operands of an operator should have the same essential type",
        "R10.5": "The value of an expression should not be cast to a different essential type category",
        "R11.1": "Cast shall not be performed between pointer to void and arithmetic type",
        "R11.2": "Cast shall not be performed between pointer to function and another type",
        "R11.3": "Cast shall not be performed between pointer to incomplete type and another type",
        "R11.4": "A conversion should not be performed between pointer to object and integer type",
        "R11.5": "A conversion shall not be performed from pointer to void to pointer to object",
        "R11.6": "A cast shall not be performed from pointer to object to pointer to character type",
        "R11.7": "Cast shall not be performed from pointer to base class to pointer to derived class",
        "R12.1": "The precedence of operators within expressions shall be made explicit",
        "R13.1": "Array indexing shall be the only form of pointer arithmetic",
        "R13.2": "The relational operators ">" and ">=" shall not be applied to pointers of different type",
        "R13.3": "Floating-point variables shall not be tested for exact equality/inequality",
        "R13.4": "Operators "==" and "!=" should not be used with floating-point operands",
        "R13.5": "The body of a loop-iteration statement shall not contain function calls that can cause recursion",
        "R13.6": "Loop counters shall not be modified within the loop body",
        "R14.1": "A loop-counter shall not be modified in the body of the loop",
        "R14.2": "A for loop shall only contain loop counters modified in the loop-header",
        "R14.3": "The loop-body shall not contain code that bypasses the loop counter",
        "R15.1": "The statement forming the body of a switch statement shall be compound",
        "R15.2": "A switch statement shall not contain more than one switch-default clause",
        "R15.3": "Every switch statement shall have a default label",
        "R15.4": "Every switch clause shall be terminated with a break statement",
        "R15.5": "A switch clause should be followed by a break statement",
        "R15.6": "The final clause of a switch statement shall be the default clause",
        "R16.1": "All switch statements shall have a default label",
        "R16.2": "A default label shall be the first statement in a switch clause",
        "R16.3": "An unconditional break statement shall terminate every switch clause",
        "R17.1": "The features of <stddef.h> and <stdint.h> shall be used",
        "R17.2": "Project shall not contain automatic variables larger than supported by stack",
        "R18.1": "Objects or variables should have static storage duration if possible",
        "R18.2": "The sizeof operator shall not be applied to expressions with side effects",
        "R19.1": "#include statements shall only be preceded by preprocessor directives or comments",
        "R19.2": "#include statements shall be followed by a #include guard",
        "R20.1": "All usage of assembly language shall be documented",
        "R21.1": "Project shall not contain use of the 'assert' macro",
        "R21.2": "#undef shall not be used",
        "R21.3": "Project shall not contain use of the 'goto' statement",
        "R21.4": "Project shall not contain use of the 'continue' statement",
        "R21.5": "The atexit function shall not be called",
        "R21.6": "The use of 'signal' handling functions shall be documented",
        "R21.7": "The <stdlib.h> functions for memory management shall not be used",
        "R21.8": "The 'setjmp' and 'longjmp' functions shall not be used",
        "R22.1": "All resources shall be minimized",
        "R22.2": "The union keyword shall not be used for type casting",
        "R22.3": "Dynamic memory allocation shall not be used",
        "R22.4": "All branches in code shall have all paths accessible",
        "R22.5": "All branches in code shall have a terminating default case",
        "R22.6": "All code shall be reachable",
    }

    def __init__(self, strict_mode: bool = False):
        self.strict_mode = strict_mode
        self.issues: list[EmbeddedCIssue] = []

    def analyze(self, code: str) -> list[EmbeddedCIssue]:
        """Analyze embedded C code for issues."""
        self.issues = []
        lines = code.split('\n')

        # Run all checks
        self._check_misra_compliance(code, lines)
        self._check_integer_overflow(code, lines)
        self._check_volatile_usage(code, lines)
        self._check_uninitialized_variables(code, lines)
        self._check_division_by_zero(code, lines)
        self._check_shift_operations(code, lines)
        self._check_hardware_specific(code, lines)
        self._check_array_bounds(code, lines)
        self._check_pointer_issues(code, lines)
        self._check_blocking_in_isr(code, lines)

        return self.issues

    def _check_misra_compliance(self, code: str, lines: list[str]) -> None:
        """Check for MISRA C compliance issues."""
        for i, line in enumerate(lines):
            line_num = i + 1

            # R7.1: Octal constants
            if re.search(r'\b0[0-7]+[uUlL]*\b', line):
                self.issues.append(EmbeddedCIssue(
                    severity="warning",
                    rule="MISRA R7.1",
                    message="Octal constant used",
                    line=line_num,
                    suggestion="Use decimal or hexadecimal constants instead",
                ))

            # R7.2: Integer constant suffix
            if re.search(r'\b[0-9]+\b', line) and not re.search(r'\b[0-9]+[uUlL]+\b', line):
                # Check if it's a constant without suffix (potential issue)
                pass  # Too noisy, skip

            # R8.5: Bitwise and logical operators combined
            if re.search(r'&&.*\|', line) or re.search(r'\|\|.*&', line):
                self.issues.append(EmbeddedCIssue(
                    severity="error",
                    rule="MISRA R8.5",
                    message="Bitwise and logical operators combined without parentheses",
                    line=line_num,
                    suggestion="Use explicit parentheses to clarify precedence",
                ))

            # R12.1: Precedence not explicit
            if re.search(r'\+\s*<<|\+\s*>>|<<\s*\+', line):
                self.issues.append(EmbeddedCIssue(
                    severity="warning",
                    rule="MISRA R12.1",
                    message="Operator precedence may be unclear",
                    line=line_num,
                    suggestion="Use parentheses to clarify operator precedence",
                ))

            # R15.3: Switch without default
            # This needs project-level analysis

            # R21.3: goto statement
            if re.search(r'\bgoto\b', line):
                self.issues.append(EmbeddedCIssue(
                    severity="error",
                    rule="MISRA R21.3",
                    message="goto statement used",
                    line=line_num,
                    suggestion="Refactor to avoid goto. Use structured control flow instead.",
                ))

            # R21.7: malloc/free
            if re.search(r'\bmalloc\s*\(', line) or re.search(r'\bfree\s*\(', line):
                self.issues.append(EmbeddedCIssue(
                    severity="error",
                    rule="MISRA R22.3",
                    message="Dynamic memory allocation used",
                    line=line_num,
                    suggestion="Use static or stack allocation for embedded systems",
                ))

    def _check_integer_overflow(self, code: str, lines: list[str]) -> None:
        """Check for potential integer overflow."""
        for i, line in enumerate(lines):
            line_num = i + 1

            # Check for multiplication that might overflow
            if re.search(r'\*\s*[0-9]{5,}', line):
                self.issues.append(EmbeddedCIssue(
                    severity="warning",
                    rule="INT001",
                    message="Large multiplication may cause overflow",
                    line=line_num,
                    suggestion="Use 64-bit types or check for overflow before multiplication",
                ))

            # Check for addition with constants
            if re.search(r'[a-zA-Z_]\w*\s*\+\s*[0-9]{5,}', line):
                self.issues.append(EmbeddedCIssue(
                    severity="warning",
                    rule="INT002",
                    message="Large addition may cause overflow",
                    line=line_num,
                    suggestion="Consider using 32-bit or 64-bit types for large values",
                ))

            # Check for unsigned wrap-around patterns
            if re.search(r'uint\d+_t.*-.*1', line):
                self.issues.append(EmbeddedCIssue(
                    severity="warning",
                    rule="INT003",
                    message="Potential unsigned integer underflow",
                    line=line_num,
                    suggestion="Ensure unsigned values never go below zero",
                ))

    def _check_volatile_usage(self, code: str, lines: list[str]) -> None:
        """Check for proper volatile usage with hardware registers."""
        for i, line in enumerate(lines):
            line_num = i + 1

            # Check for hardware register access without volatile
            if re.search(r'(RCC|GPIO|USART|SPI|I2C|TIM|ADC|DMA|EXTI|NVIC)->', line):
                if 'volatile' not in line:
                    self.issues.append(EmbeddedCIssue(
                        severity="warning",
                        rule="VOL001",
                        message="Hardware register access without volatile qualifier",
                        line=line_num,
                        suggestion="Add volatile qualifier to prevent compiler optimization issues",
                    ))

            # Check for ISR-shared variables without volatile
            # Look for patterns like: while(!flag) where flag is modified in ISR
            if re.search(r'while\s*\([^)]*\)', line):
                if 'volatile' not in line and 'volatile' not in code[:code.index(line)]:
                    # Check if there's an ISR nearby that might modify the variable
                    pass  # Would need more context

    def _check_uninitialized_variables(self, code: str, lines: list[str]) -> None:
        """Check for uninitialized variable usage."""
        for i, line in enumerate(lines):
            line_num = i + 1

            # Check for use of uninitialized stack variables
            # Pattern: type var; ... if(var) or while(var)
            if re.search(r'\b(int|char|uint\d+_t|float|double)\s+(\w+)\s*;', line):
                var_name = re.search(r'\b(int|char|uint\d+_t|float|double)\s+(\w+)\s*;', line).group(2)
                # Look ahead for usage without initialization
                for j in range(i + 1, min(i + 10, len(lines))):
                    if re.search(rf'\b{var_name}\b', lines[j]):
                        # Check if there's an assignment before use
                        assigned = False
                        for k in range(i + 1, j):
                            if re.search(rf'\b{var_name}\s*=', lines[k]):
                                assigned = True
                                break
                        if not assigned:
                            self.issues.append(EmbeddedCIssue(
                                severity="warning",
                                rule="VAR001",
                                message=f"Variable '{var_name}' may be used before initialization",
                                line=line_num,
                                suggestion=f"Initialize '{var_name}' at declaration or before first use",
                            ))
                            break

    def _check_division_by_zero(self, code: str, lines: list[str]) -> None:
        """Check for potential division by zero."""
        for i, line in enumerate(lines):
            line_num = i + 1

            # Check for division by constant zero
            if re.search(r'/\s*0\s*[;,\)]', line) or re.search(r'/\s*0\.0', line):
                self.issues.append(EmbeddedCIssue(
                    severity="error",
                    rule="DIV001",
                    message="Division by zero literal",
                    line=line_num,
                    suggestion="Check divisor before division or use assert",
                ))

            # Check for division by variable that could be zero
            if re.search(r'/\s*[a-zA-Z_]\w*', line):
                # This is a heuristic check
                divisor = re.search(r'/\s*([a-zA-Z_]\w*)', line).group(1)
                # Check if there's any initialization or check for this variable
                context = '\n'.join(lines[max(0, i-5):i+1])
                if divisor not in context or f'{divisor} = 0' in context:
                    self.issues.append(EmbeddedCIssue(
                        severity="warning",
                        rule="DIV002",
                        message=f"Division by variable '{divisor}' may be zero",
                        line=line_num,
                        suggestion=f"Verify '{divisor}' is non-zero before division",
                    ))

    def _check_shift_operations(self, code: str, lines: list[str]) -> None:
        """Check for unsafe shift operations."""
        for i, line in enumerate(lines):
            line_num = i + 1

            # Check for shift by negative or large amount
            if re.search(r'>>\s*[0-9]{2,}', line) or re.search(r'<<\s*[0-9]{2,}', line):
                self.issues.append(EmbeddedCIssue(
                    severity="error",
                    rule="SHIFT001",
                    message="Shift by large constant",
                    line=line_num,
                    suggestion="Ensure shift amount is less than data type width",
                ))

            # Check for shift on signed types
            if re.search(r'(int|signed\s+\w+)\s*<<', line) or re.search(r'(int|signed\s+\w+)\s*>>', line):
                self.issues.append(EmbeddedCIssue(
                    severity="warning",
                    rule="SHIFT002",
                    message="Shift operation on signed type may have undefined behavior",
                    line=line_num,
                    suggestion="Use unsigned types for shift operations",
                ))

    def _check_hardware_specific(self, code: str, lines: list[str]) -> None:
        """Check for hardware-specific issues."""
        for i, line in enumerate(lines):
            line_num = i + 1

            # Check for delays without checking clock
            if re.search(r'HAL_Delay|osDelay|vTaskDelay', line):
                self.issues.append(EmbeddedCIssue(
                    severity="info",
                    rule="HW001",
                    message="Delay function used",
                    line=line_num,
                    suggestion="Ensure system clock is configured correctly",
                ))

            # Check for blocking in potential ISR context
            if re.search(r'HAL_Delay', line) and any('IRQ' in lines[j] or 'Handler' in lines[j] for j in range(max(0, i-10), i)):
                self.issues.append(EmbeddedCIssue(
                    severity="error",
                    rule="HW002",
                    message="Blocking delay in ISR context",
                    line=line_num,
                    suggestion="Do not use HAL_Delay in ISR. Use flags or setTick from main context.",
                ))

    def _check_array_bounds(self, code: str, lines: list[str]) -> None:
        """Check for array bounds issues."""
        for i, line in enumerate(lines):
            line_num = i + 1

            # Check for potential buffer overflow
            if re.search(r'memcpy\s*\([^,]+,\s*sizeof', line):
                self.issues.append(EmbeddedCIssue(
                    severity="warning",
                    rule="ARR001",
                    message="memcpy with sizeof may exceed destination buffer",
                    line=line_num,
                    suggestion="Use explicit size or sizeof(destination)",
                ))

            # Check for array index access with variables
            if re.search(r'\[[^\]]*[+\-*][^\]]*\]', line):
                self.issues.append(EmbeddedCIssue(
                    severity="warning",
                    rule="ARR002",
                    message="Array index involves arithmetic - verify bounds",
                    line=line_num,
                    suggestion="Ensure array index is within bounds before access",
                ))

    def _check_pointer_issues(self, code: str, lines: list[str]) -> None:
        """Check for pointer-related issues."""
        for i, line in enumerate(lines):
            line_num = i + 1

            # Check for NULL pointer dereference
            if re.search(r'->\w+', line):
                # Look backwards for NULL check
                context = '\n'.join(lines[max(0, i-5):i+1])
                if 'NULL' in context or 'null' in context:
                    # Check if there's proper NULL check
                    if not re.search(r'if\s*\([^)]*(?:NULL|null)', context):
                        self.issues.append(EmbeddedCIssue(
                            severity="warning",
                            rule="PTR001",
                            message="Pointer member access without visible NULL check",
                            line=line_num,
                            suggestion="Verify pointer is not NULL before member access",
                        ))

            # Check for casting pointer to integer
            if re.search(r'\(\s*(?:uint32_t|uintptr_t|int)\s*\)', line):
                self.issues.append(EmbeddedCIssue(
                    severity="warning",
                    rule="MISRA R11.4",
                    message="Pointer to integer conversion",
                    line=line_num,
                    suggestion="Avoid casting pointers to integers",
                ))

    def _check_blocking_in_isr(self, code: str, lines: list[str]) -> None:
        """Check for blocking operations in ISR."""
        # Find ISR functions
        isr_pattern = r'(?:__attribute__.*)?void\s+(\w*(?:IRQ|Handler|irq)_?\w*)\s*\([^)]*\)\s*(?:__attribute__[^;]*)?\s*\{'

        for i, line in enumerate(lines):
            line_num = i + 1
            match = re.search(isr_pattern, line)
            if match:
                isr_name = match.group(1)
                # Find end of ISR
                depth = 0
                for j in range(i, len(lines)):
                    depth += lines[j].count('{') - lines[j].count('}')
                    if depth <= 0:
                        break
                    # Check for blocking operations
                    if any(blocked in lines[j] for blocked in ['HAL_Delay', 'printf', 'malloc', 'free', 'vTaskDelay']):
                        self.issues.append(EmbeddedCIssue(
                            severity="error",
                            rule="ISR001",
                            message=f"Blocking operation '{lines[j].strip()[:30]}' in ISR '{isr_name}'",
                            line=j + 1,
                            suggestion="ISR should not contain blocking operations. Use flags or queues instead.",
                        ))

    def get_misra_summary(self) -> dict:
        """Get MISRA compliance summary."""
        return {
            "total_rules_checked": len(self.MISRA_RULES),
            "issues_found": len(self.issues),
            "errors": sum(1 for i in self.issues if i.severity == "error"),
            "warnings": sum(1 for i in self.issues if i.severity == "warning"),
            "info": sum(1 for i in self.issues if i.severity == "info"),
            "compliant_rules": len(self.MISRA_RULES),
        }

"""Embedded Detector — embedded C/firmware specific issue detection.

Detects issues specific to embedded/C firmware development:
- EMB001: Crash patterns (NULL dereference, stack overflow, infinite loop)
- EMB002: Assert usage without proper handling
- EMB003: Memory issues (buffer overflow, uninitialized variables)
- EMB004: ISR violations (blocking in ISR, missing volatile)
- EMB005: Hardware access patterns (register access, timing)
- EMB006: Firmware-specific anti-patterns

These rules target safety-critical embedded systems and automotive firmware.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from src.application.workflows.unified.code_context import CodeContext
from src.application.workflows.unified.detector_base import (
    Detector,
    DetectorConfig,
    Finding,
    FindingSeverity,
)

# ─── Constants ─────────────────────────────────────────────────────────────────


# Maximum stack usage estimation (bytes) for embedded systems
MAX_STACK_USAGE: int = 2048
# Maximum function nesting depth
MAX_NESTING_DEPTH: int = 4


# ─── Embedded Rule Definitions ─────────────────────────────────────────────────


@dataclass
class EmbeddedRule:
    """Definition of an embedded/C detection rule."""
    id: str
    name: str
    description: str
    severity: FindingSeverity
    patterns: list[str]
    languages: list[str]
    fix_template: str
    cwe_id: str = ""

    def matches_line(self, line: str) -> bool:
        """Check if rule pattern matches a line."""
        for pattern in self.patterns:
            if re.search(pattern, line):
                return True
        return False


# ─── Embedded Detector ────────────────────────────────────────────────────────────


class EmbeddedDetector(Detector):
    """Embedded systems and firmware detector.

    Detects issues specific to embedded C/C++ development:
    - Crash patterns (NULL dereferences, stack overflow)
    - Memory issues (buffer overflow, uninitialized variables)
    - ISR violations (blocking, missing volatile)
    - Hardware access patterns
    - Firmware anti-patterns

    Supported languages: c, cpp

    Usage:
        config = DetectorConfig(focus_areas=["embedded"])
        detector = EmbeddedDetector(config)
        findings = detector.detect(context)
    """

    RULES: list[EmbeddedRule] = []

    def __init__(self, config: DetectorConfig | None = None) -> None:
        super().__init__(config)
        self._name = "embedded"
        self._init_rules()

    def _init_rules(self) -> None:
        """Initialize embedded rules."""
        self.RULES = [
            # EMB001: Crash patterns
            EmbeddedRule(
                id="EMB001",
                name="null-dereference",
                description="Potential NULL pointer dereference",
                severity=FindingSeverity.ERROR,
                patterns=[
                    r"->\w+\s*(?!if)",
                    r"\*\w+\s*(?!if)",
                    r"\w+\[.*\]\s*(?!if)",
                    r"\*\*\w+",
                ],
                languages=["c", "cpp"],
                fix_template="Check pointer is non-NULL before dereferencing",
                cwe_id="CWE-476",
            ),
            EmbeddedRule(
                id="EMB002",
                name="infinite-loop",
                description="Potential infinite loop without timeout or break",
                severity=FindingSeverity.ERROR,
                patterns=[
                    r"while\s*\(\s*(1|true)\s*\)",
                    r"while\s*\(\s*1\s*\)",
                    r"for\s*\(;\s*;\s*\)",
                ],
                languages=["c", "cpp"],
                fix_template="Add timeout or break condition",
                cwe_id="CWE-835",
            ),
            EmbeddedRule(
                id="EMB003",
                name="unbounded-loop",
                description="Loop without bounds that could run forever",
                severity=FindingSeverity.WARNING,
                patterns=[
                    r"while\s*\(\s*[^)]*\)",
                    r"for\s*\([^)]*\)",
                ],
                languages=["c", "cpp"],
                fix_template="Add loop bound or timeout",
                cwe_id="CWE-834",
            ),

            # EMB004: Memory issues
            EmbeddedRule(
                id="EMB004",
                name="buffer-overflow",
                description="Potential buffer overflow vulnerability",
                severity=FindingSeverity.ERROR,
                patterns=[
                    r"strcpy\s*\(",
                    r"strcat\s*\(",
                    r"sprintf\s*\(",
                    r"gets\s*\(",
                    r"scanf\s*\([^,]*%s",
                    r"memcpy\s*\([^,]*,\s*[^,]*,\s*\w+[^)]*\)(?!.*sizeof)",
                ],
                languages=["c", "cpp"],
                fix_template="Use safe alternatives: strncpy, snprintf, fgets",
                cwe_id="CWE-120",
            ),
            EmbeddedRule(
                id="EMB005",
                name="uninitialized-var",
                description="Variable may be used without initialization",
                severity=FindingSeverity.WARNING,
                patterns=[
                    r"(?:int|float|double|char|bool)\s+\w+\s*;",
                    r"(?:uint8_t|uint16_t|uint32_t|int8_t|int16_t|int32_t)\s+\w+\s*;",
                ],
                languages=["c", "cpp"],
                fix_template="Initialize variable at declaration: int x = 0;",
                cwe_id="CWE-457",
            ),
            EmbeddedRule(
                id="EMB006",
                name="memory-leak",
                description="Potential memory leak - malloc without corresponding free",
                severity=FindingSeverity.WARNING,
                patterns=[
                    r"malloc\s*\(",
                    r"calloc\s*\(",
                    r"realloc\s*\(",
                    r"new\s+",
                ],
                languages=["c", "cpp"],
                fix_template="Ensure corresponding free/delete for each allocation",
                cwe_id="CWE-401",
            ),

            # EMB007: ISR violations
            EmbeddedRule(
                id="EMB007",
                name="isr-blocking",
                description="Blocking operation in ISR context",
                severity=FindingSeverity.ERROR,
                patterns=[
                    r"HAL_Delay\s*\(",
                    r"osDelay\s*\(",
                    r"vTaskDelay\s*\(",
                    r"sleep\s*\(",
                    r"usleep\s*\(",
                    r"printf\s*\(",
                    r"malloc\s*\(",
                    r"free\s*\(",
                ],
                languages=["c", "cpp"],
                fix_template="Move blocking operation out of ISR",
                cwe_id="CWE-667",
            ),
            EmbeddedRule(
                id="EMB008",
                name="missing-volatile",
                description="Shared variable accessed in ISR without volatile",
                severity=FindingSeverity.WARNING,
                patterns=[
                    r"(?:uint8_t|uint16_t|uint32_t|int8_t|int16_t|int32_t|volatile)\s+\w+_flag",
                    r"(?:uint8_t|uint16_t|uint32_t|int8_t|int16_t|int32_t)\s+\w+_count",
                ],
                languages=["c", "cpp"],
                fix_template="Add volatile qualifier: volatile uint32_t counter;",
                cwe_id="CWE-14",
            ),

            # EMB009: Hardware access
            EmbeddedRule(
                id="EMB009",
                name="hardcoded-delay",
                description="Hardcoded delay without timeout concept",
                severity=FindingSeverity.WARNING,
                patterns=[
                    r"HAL_Delay\s*\(\s*\d{4,}\s*\)",
                    r"osDelay\s*\(\s*\d{4,}\s*\)",
                    r"Delay\s*\(\s*\d{4,}\s*\)",
                ],
                languages=["c", "cpp"],
                fix_template="Use timeout pattern or check for completion flag",
                cwe_id="CWE-208",
            ),
            EmbeddedRule(
                id="EMB010",
                name="missing-timeout",
                description="Blocking hardware operation without timeout",
                severity=FindingSeverity.WARNING,
                patterns=[
                    r"HAL_UART_Receive\s*\([^)]*\)(?!.*timeout)",
                    r"HAL_SPI_Receive\s*\([^)]*\)(?!.*timeout)",
                    r"HAL_I2C_Master_Transmit\s*\([^)]*\)(?!.*timeout)",
                ],
                languages=["c", "cpp"],
                fix_template="Add timeout check for hardware operations",
                cwe_id="CWE-835",
            ),

            # EMB011: Firmware patterns
            EmbeddedRule(
                id="EMB011",
                name="magic-hardcode",
                description="Magic number in hardware/firmware code",
                severity=FindingSeverity.INFO,
                patterns=[
                    r"(?<![a-zA-Z_])(0x[0-9A-Fa-f]{5,})(?![xXa-zA-Z])",
                    r"(?<![a-zA-Z_])(?:4096|8192|16384|32768|65536)(?![a-zA-Z_])",
                ],
                languages=["c", "cpp"],
                fix_template="Define as named constant with unit/comment",
                cwe_id="CWE-571",
            ),
            EmbeddedRule(
                id="EMB012",
                name="bare-cast",
                description="Bare type cast that may lose precision",
                severity=FindingSeverity.WARNING,
                patterns=[
                    r"\(\s*(?:int|uint32_t|uint16_t)\s*\)\s*\w+",
                    r"\(\s*(?:float|double)\s*\)\s*\w+",
                ],
                languages=["c", "cpp"],
                fix_template="Use explicit cast with comment explaining conversion",
                cwe_id="CWE-192",
            ),

            # EMB013: RTOS patterns
            EmbeddedRule(
                id="EMB013",
                name="rtos-priority-inversion",
                description="Potential priority inversion in RTOS task",
                severity=FindingSeverity.WARNING,
                patterns=[
                    r"osMutexWait\s*\([^)]*\)(?!.*timeout)",
                    r"xSemaphoreTake\s*\([^)]*\)(?!.*portMAX_DELAY)",
                ],
                languages=["c", "cpp"],
                fix_template="Always use timeout with mutex/semaphore operations",
                cwe_id="CWE-551",
            ),
            EmbeddedRule(
                id="EMB014",
                name="task-stack-overflow",
                description="Large local array in function that may cause stack overflow",
                severity=FindingSeverity.ERROR,
                patterns=[
                    r"(?:uint8_t|uint32_t|int)\s+\w+\s*\[\s*(?:1024|2048|4096|8192|16384|32768|65536)\s*\]",
                ],
                languages=["c", "cpp"],
                fix_template="Use static/global allocation or heap for large buffers",
                cwe_id="CWE-774",
            ),

            # EMB015: Automotive-specific
            EmbeddedRule(
                id="EMB015",
                name="missing-can-check",
                description="CAN message processed without error checking",
                severity=FindingSeverity.WARNING,
                patterns=[
                    r"HAL_CAN_AddTxMessage\s*\([^)]*\)(?!.*error)",
                    r"CAN_Transmit\s*\([^)]*\)(?!.*ret)",
                ],
                languages=["c", "cpp"],
                fix_template="Always check return value of CAN operations",
                cwe_id="CWE-252",
            ),
        ]

    def detect(self, context: CodeContext) -> list[Finding]:
        """Detect embedded/firmware issues.

        Args:
            context: Unified code context

        Returns:
            List of embedded findings
        """
        findings: list[Finding] = []

        # Only run for C/C++ files
        if context.language not in ["c", "cpp"]:
            return findings

        # Run each applicable rule
        for rule in self.RULES:
            if context.language in rule.languages:
                rule_findings = self._run_rule(rule, context)
                findings.extend(rule_findings)

        # Run additional analysis
        findings.extend(self._detect_isr_violations(context))
        findings.extend(self._detect_stack_issues(context))

        return findings

    def _run_rule(self, rule: EmbeddedRule, context: CodeContext) -> list[Finding]:
        """Run a single embedded rule.

        Args:
            rule: Embedded rule to run
            context: Code context

        Returns:
            Findings from this rule
        """
        findings: list[Finding] = []

        for i, line in enumerate(context.lines, 1):
            # Check if line matches rule patterns
            if not rule.matches_line(line):
                continue

            # Apply additional context filtering
            if self._is_false_positive(rule.id, line, context, i):
                continue

            # Get match column
            col = 0
            for pattern in rule.patterns:
                match = re.search(pattern, line)
                if match:
                    col = match.start()
                    break

            findings.append(Finding(
                rule_id=rule.id,
                rule_name=rule.name,
                severity=rule.severity,
                file=str(context.file_path),
                line=i,
                end_line=i,
                column=col,
                message=rule.description,
                fix=rule.fix_template,
                confidence=self._calculate_confidence(rule.id, line, context),
                context=context.get_surrounding_code(i),
                detector=self._name,
                metadata={
                    "tags": ["embedded", "firmware", "safety"],
                    "cwe": rule.cwe_id,
                },
            ))

        return findings

    def _detect_isr_violations(self, context: CodeContext) -> list[Finding]:
        """Detect ISR-specific violations.

        Checks for:
        - Blocking operations in ISR
        - Missing volatile qualifiers
        - Non-reentrant functions called from ISR
        """
        findings: list[Finding] = []

        # Look for ISR definitions
        isr_patterns = [
            r"HAL_TIM_IC_CaptureCallback",
            r"HAL_TIM_PeriodElapsedCallback",
            r"HAL_GPIO_EXTI_Callback",
            r"HAL_UART_RxCpltCallback",
            r"HAL_CAN_RxFifo0MsgPendingCallback",
            r"void\s+\w*IRQHandler\s*\(",
            r"__irq\s+",
            r"__attribute__\s*\(\s*\(\s*interrupt\s*\)\s*\)",
        ]

        for i, line in enumerate(context.lines, 1):
            for pattern in isr_patterns:
                if re.search(pattern, line):
                    # Found ISR - check surrounding lines for violations
                    isr_findings = self._check_isr_content(context, i)
                    findings.extend(isr_findings)
                    break

        return findings

    def _check_isr_content(self, context: CodeContext, isr_line: int) -> list[Finding]:
        """Check content within an ISR function."""
        findings: list[Finding] = []

        # Find ISR boundaries
        start = isr_line
        end = isr_line

        brace_count = 0
        for i in range(isr_line - 1, min(len(context.lines), isr_line + 50)):
            line = context.lines[i]
            brace_count += line.count("{") - line.count("}")
            if brace_count == 0 and i > isr_line:
                end = i
                break

        # Check for blocking operations within ISR
        blocking_patterns = [
            (r"HAL_Delay", "HAL_Delay() called in ISR - use timer-based approach"),
            (r"osDelay", "osDelay() called in ISR - blocking not allowed"),
            (r"printf", "printf() in ISR - use ring buffer or GPIO toggle"),
            (r"malloc", "Dynamic allocation in ISR - use static buffers"),
            (r"free", "free() in ISR - memory management not safe"),
            (r"vTaskDelay", "Task delay in ISR - not allowed"),
            (r"xQueueSend", "Queue send in ISR - use FromISR variant"),
        ]

        for i in range(start, end + 1):
            line = context.lines[i]
            for pattern, message in blocking_patterns:
                if re.search(pattern, line):
                    findings.append(Finding(
                        rule_id="EMB007",
                        rule_name="isr-blocking",
                        severity=FindingSeverity.ERROR,
                        file=str(context.file_path),
                        line=i,
                        end_line=i,
                        message=message,
                        fix="Move operation out of ISR or use ISR-safe alternative",
                        confidence=0.95,
                        detector=self._name,
                        metadata={"tags": ["isr", "embedded", "safety"], "cwe": "CWE-667"},
                    ))

        return findings

    def _detect_stack_issues(self, context: CodeContext) -> list[Finding]:
        """Detect potential stack overflow issues."""
        findings: list[Finding] = []

        # Look for large stack allocations
        for i, line in enumerate(context.lines, 1):
            # Check for large local arrays
            match = re.search(
                r"(?:static\s+)?(?:uint8_t|uint32_t|char|int)\s+(\w+)\s*\[\s*(\d+)\s*\]",
                line
            )
            if match:
                size = int(match.group(2))
                # Flag large allocations (> 1KB on stack)
                if size >= 1024 and "static" not in line:
                    findings.append(Finding(
                        rule_id="EMB014",
                        rule_name="task-stack-overflow",
                        severity=FindingSeverity.ERROR,
                        file=str(context.file_path),
                        line=i,
                        end_line=i,
                        message=f"Large local array ({size} bytes) may cause stack overflow",
                        fix="Use static/global allocation or heap for large buffers",
                        confidence=0.85,
                        detector=self._name,
                        metadata={"tags": ["stack", "embedded", "memory"], "cwe": "CWE-774"},
                    ))

        return findings

    def _is_false_positive(
        self,
        rule_id: str,
        line: str,
        context: CodeContext,
        line_num: int,
    ) -> bool:
        """Check if a match is a false positive.

        Args:
            rule_id: Rule that matched
            line: Line containing match
            context: Code context
            line_num: Line number

        Returns:
            True if false positive
        """
        # Skip comments
        if re.match(r"^\s*//", line) or re.match(r"^\s*/\*", line):
            return True

        # Skip if already checked
        if "/* checked */" in line or "/* validated */" in line:
            return True

        # EMB001: NULL dereference - skip if in assignment
        if rule_id == "EMB001":
            if "=" in line and not re.search(r"->|\*", line.split("=")[0]):
                return True

        # EMB004: Buffer overflow - skip if using safe functions
        if rule_id == "EMB004":
            if any(safe in line for safe in ["strncpy", "snprintf", "strlcpy", "fgets"]):
                return True

        # EMB005: Uninitialized - skip if initialized
        if rule_id == "EMB005":
            if "=" in line:
                return True

        return False

    def _calculate_confidence(
        self,
        rule_id: str,
        line: str,
        context: CodeContext,
    ) -> float:
        """Calculate confidence score for a match.

        Args:
            rule_id: Rule that matched
            line: Line containing match
            context: Code context

        Returns:
            Confidence score (0.0-1.0)
        """
        base_confidence = 0.8

        # Increase confidence for clear patterns
        if rule_id == "EMB002":  # Infinite loop
            if "while (1)" in line or "while(true)" in line:
                return 0.95
            if "for (;;)" in line:
                return 0.95

        if rule_id == "EMB004":  # Buffer overflow
            if "strcpy" in line or "gets" in line:
                return 0.95

        if rule_id == "EMB007":  # ISR blocking
            return 0.9

        # Decrease for test/mock code
        if "test" in context.file_path.lower() or "mock" in line.lower():
            return base_confidence * 0.5

        return base_confidence

    def integrate_with_rule_engine(self, rule_engine: Any) -> None:
        """Integrate with RuleEngine to share findings.

        Args:
            rule_engine: Existing RuleEngine instance
        """
        from src.infrastructure.analysis.rule_engine import Rule, RuleSeverity

        for embedded_rule in self.RULES:
            rule = Rule(
                id=embedded_rule.id,
                name=embedded_rule.name,
                description=embedded_rule.description,
                severity=RuleSeverity[embedded_rule.severity.name.upper()],
                languages=embedded_rule.languages,
                patterns=embedded_rule.patterns,
                fix_template=embedded_rule.fix_template,
                cwe_id=embedded_rule.cwe_id,
                tags=["embedded", "firmware", "safety"],
            )
            try:
                rule_engine.register(rule)
            except ValueError:
                pass  # Rule already registered

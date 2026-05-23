"""Bug report parser (Phase 8.4).

Parses raw log output into structured BugReport objects with:
- Bug type classification
- Location identification
- Suspect components
- Confidence scoring
- Root cause analysis

Handles multiple log formats from different firmware sources.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class BugSeverity(Enum):
    """Bug severity classification."""
    CRITICAL = "critical"  # System halted, data loss
    HIGH = "high"          # Major feature broken
    MEDIUM = "medium"      # Degraded operation
    LOW = "low"            # Warning, non-blocking
    INFO = "info"          # Informational only


class BugStatus(Enum):
    """Bug lifecycle status."""
    NEW = "new"
    TRIAGED = "triaged"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    WONT_FIX = "wont_fix"
    VERIFIED = "verified"


class BugType(Enum):
    """Bug type classification."""
    # Fault types
    HARD_FAULT = "hard_fault"
    MEMORY_FAULT = "memory_fault"
    BUS_FAULT = "bus_fault"
    USAGE_FAULT = "usage_fault"
    
    # Timeout types
    I2C_TIMEOUT = "i2c_timeout"
    SPI_TIMEOUT = "spi_timeout"
    UART_TIMEOUT = "uart_timeout"
    CAN_TIMEOUT = "can_timeout"
    DMA_TIMEOUT = "dma_timeout"
    NETWORK_TIMEOUT = "network_timeout"
    
    # Deadlock types
    DEADLOCK = "deadlock"
    PRIORITY_INVERSION = "priority_inversion"
    RACE_CONDITION = "race_condition"
    
    # Resource types
    HEAP_EXHAUSTION = "heap_exhaustion"
    STACK_OVERFLOW = "stack_overflow"
    BUFFER_OVERFLOW = "buffer_overflow"
    QUEUE_FULL = "queue_full"
    
    # Interrupt types
    INTERRUPT_STORM = "interrupt_storm"
    NESTED_INTERRUPT_OVERFLOW = "nested_interrupt_overflow"
    
    # Watchdog types
    WATCHDOG_TIMEOUT = "watchdog_timeout"
    TASK_WATCHDOG_TIMEOUT = "task_watchdog_timeout"
    
    # Assertion types
    ASSERTION_FAILED = "assertion_failed"
    INVARIANT_VIOLATED = "invariant_violated"
    
    # Peripheral types
    PERIPHERAL_ERROR = "peripheral_error"
    GPIO_ERROR = "gpio_error"
    CLOCK_ERROR = "clock_error"
    POWER_ERROR = "power_error"
    
    # Communication types
    I2C_ERROR = "i2c_error"
    SPI_ERROR = "spi_error"
    UART_ERROR = "uart_error"
    CAN_ERROR = "can_error"
    
    # Generic
    UNKNOWN = "unknown"
    CRASH = "crash"
    HANG = "hang"
    RESET = "reset"
    CORRUPTION = "corruption"


@dataclass
class BugLocation:
    """Identified bug location."""
    file: str = ""
    line: int = 0
    function: str = ""
    module: str = ""
    component: str = ""
    register: str = ""  # For hardware bugs
    address: str = ""   # Memory address if applicable
    
    def __str__(self) -> str:
        parts = []
        if self.function:
            parts.append(f"func:{self.function}")
        if self.file:
            parts.append(f"file:{self.file}")
        if self.line:
            parts.append(f"line:{self.line}")
        if self.component:
            parts.append(f"component:{self.component}")
        return ":".join(parts) if parts else "unknown"


@dataclass
class BugSuspect:
    """Suspected cause or component."""
    name: str
    confidence: float  # 0.0 - 1.0
    reason: str = ""
    evidence: list[str] = field(default_factory=list)


@dataclass
class BugContext:
    """Surrounding context of the bug."""
    stack_trace: list[str] = field(default_factory=list)
    registers: dict[str, str] = field(default_factory=dict)
    variables: dict[str, str] = field(default_factory=dict)
    call_chain: list[str] = field(default_factory=list)
    peripheral_state: dict[str, Any] = field(default_factory=dict)


@dataclass
class BugReport:
    """Structured bug report from parsed logs."""
    # Identification
    id: str = ""
    title: str = ""
    description: str = ""
    
    # Classification
    bug_type: BugType = BugType.UNKNOWN
    severity: BugSeverity = BugSeverity.MEDIUM
    status: BugStatus = BugStatus.NEW
    
    # Location
    location: BugLocation = field(default_factory=BugLocation)
    
    # Analysis
    suspects: list[BugSuspect] = field(default_factory=list)
    root_causes: list[str] = field(default_factory=list)
    context: BugContext = field(default_factory=BugContext)
    
    # Confidence
    confidence: float = 0.5  # 0.0 - 1.0
    matched_patterns: list[str] = field(default_factory=list)
    
    # Metadata
    timestamp: datetime = field(default_factory=datetime.now)
    source_file: str = ""
    board_id: str = ""
    firmware_version: str = ""
    
    # Signature for deduplication
    signature: str = ""
    
    def compute_signature(self) -> str:
        """Compute content hash for deduplication."""
        content = f"{self.bug_type.value}:{self.location.function}:{self.location.file}:{self.title}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


# Format parsers registry
LOG_FORMATTERS: dict[str, type[LogParser]] = {}


class LogParser:
    """Base class for log format parsers."""
    
    name: str = "base"
    
    def can_parse(self, log_line: str) -> bool:
        """Check if this parser can handle the log format."""
        raise NotImplementedError
    
    def parse(self, log_lines: list[str]) -> list[BugReport]:
        """Parse log lines into bug reports."""
        raise NotImplementedError


class SeggerSystemViewParser(LogParser):
    """Parser for SEGGER SystemView logs."""
    
    name = "segger_systemview"
    
    # SystemView event patterns
    EVENT_PATTERN = re.compile(r'\[(\d+)\]\s*(\w+):\s*(.+)')
    INTERRUPT_PATTERN = re.compile(r'ISR\s+(\w+)\s+Enter|Exit')
    EXCEPTION_PATTERN = re.compile(r'Exception\s+(\d+):\s*(.+)')
    
    def can_parse(self, log_line: str) -> bool:
        return "[0]" in log_line or "SystemView" in log_line
    
    def parse(self, log_lines: list[str]) -> list[BugReport]:
        bugs = []
        for line in log_lines:
            match = self.EVENT_PATTERN.search(line)
            if match:
                timestamp, event_type, message = match.groups()
                
                # Check for exception events
                exc_match = self.EXCEPTION_PATTERN.search(message)
                if exc_match:
                    exc_num, exc_msg = exc_match.groups()
                    bug = BugReport(
                        title=f"Exception {exc_num}: {exc_msg}",
                        description=f"SystemView exception at timestamp {timestamp}",
                        bug_type=self._classify_exception(int(exc_num)),
                        severity=self._severity_from_exception(int(exc_num)),
                        confidence=0.9,
                        source_file="SystemView",
                    )
                    bug.signature = bug.compute_signature()
                    bugs.append(bug)
                
                # Check for ISR events
                if "ISR" in event_type:
                    isr_match = re.search(r'ISR\s+(\w+)', message)
                    if isr_match:
                        isr_name = isr_match.group(1)
                        bug = BugReport(
                            title=f"ISR Event: {isr_name}",
                            description=message,
                            bug_type=BugType.UNKNOWN,
                            severity=BugSeverity.INFO,
                            confidence=0.7,
                            source_file="SystemView",
                        )
                        bug.location.function = isr_name
                        bug.signature = bug.compute_signature()
                        bugs.append(bug)
        
        return bugs
    
    def _classify_exception(self, exc_num: int) -> BugType:
        """Classify exception by number (ARM Cortex-M)."""
        mapping = {
            0: BugType.HARD_FAULT,
            1: BugType.MEMORY_FAULT,
            2: BugType.BUS_FAULT,
            3: BugType.USAGE_FAULT,
            4: BugType.UNKNOWN,  # NMI
            11: BugType.HARD_FAULT,  # SVC
        }
        return mapping.get(exc_num, BugType.UNKNOWN)
    
    def _severity_from_exception(self, exc_num: int) -> BugSeverity:
        """Get severity from exception number."""
        critical = {0, 1, 2, 3, 11}  # HardFault, MemManage, Bus, Usage
        if exc_num in critical:
            return BugSeverity.CRITICAL
        return BugSeverity.HIGH


class GDBOutputParser(LogParser):
    """Parser for GDB debug output."""
    
    name = "gdb_output"
    
    # GDB patterns
    SIGNAL_PATTERN = re.compile(r'Program received signal\s+(\w+),\s*"([^"]+)"')
    ADDRESS_PATTERN = re.compile(r'0x[0-9a-fA-F]+\s+in\s+(\w+)\s+\(([^)]*)\)')
    STACK_PATTERN = re.compile(r'#(\d+)\s+0x[0-9a-fA-F]+\s+in\s+(\w+)\s*\(([^)]*)\)')
    
    def can_parse(self, log_line: str) -> bool:
        return "Program received signal" in log_line or "0x" in log_line
    
    def parse(self, log_lines: list[str]) -> list[BugReport]:
        bugs = []
        current_bug = None
        stack_trace = []
        
        for line in log_lines:
            # Signal received
            sig_match = self.SIGNAL_PATTERN.search(line)
            if sig_match:
                signal_name, signal_desc = sig_match.groups()
                current_bug = BugReport(
                    title=f"GDB Signal: {signal_name}",
                    description=signal_desc,
                    bug_type=self._classify_signal(signal_name),
                    severity=self._severity_from_signal(signal_name),
                    confidence=0.95,
                    source_file="GDB",
                )
                continue
            
            # Stack frame
            frame_match = self.STACK_PATTERN.search(line)
            if frame_match and current_bug:
                frame_num, func_name, args = frame_match.groups()
                stack_trace.append(f"#{frame_num} {func_name}({args})")
                if frame_num == "0":
                    current_bug.location.function = func_name
            
            # Address in function
            addr_match = self.ADDRESS_PATTERN.search(line)
            if addr_match and current_bug:
                func_name, args = addr_match.groups()
                if not current_bug.location.function:
                    current_bug.location.function = func_name
                stack_trace.append(f"0x... in {func_name}")
        
        if current_bug and stack_trace:
            current_bug.context.stack_trace = stack_trace
            current_bug.signature = current_bug.compute_signature()
            bugs.append(current_bug)
        
        return bugs
    
    def _classify_signal(self, signal: str) -> BugType:
        """Classify GDB signal."""
        mapping = {
            "SIGSEGV": BugType.MEMORY_FAULT,
            "SIGBUS": BugType.BUS_FAULT,
            "SIGFPE": BugType.USAGE_FAULT,
            "SIGILL": BugType.USAGE_FAULT,
            "SIGABRT": BugType.ASSERTION_FAILED,
            "SIGTRAP": BugType.UNKNOWN,
        }
        return mapping.get(signal, BugType.CRASH)
    
    def _severity_from_signal(self, signal: str) -> BugSeverity:
        """Get severity from GDB signal."""
        critical = {"SIGSEGV", "SIGBUS", "SIGFPE", "SIGILL", "SIGABRT"}
        return BugSeverity.CRITICAL if signal in critical else BugSeverity.HIGH


class OpenOCDParser(LogParser):
    """Parser for OpenOCD debug output."""
    
    name = "openocd"
    
    # OpenOCD patterns
    TARGET_PATTERN = re.compile(r'Target\s+(\w+)\s+(\w+):\s*(.+)')
    HARD_FAULT_PATTERN = re.compile(r'hard fault|HardFault|HARD_FAULT', re.I)
    WATCHDOG_PATTERN = re.compile(r'watchdog|WATCHDOG|IWDG|WWDG', re.I)
    MEMORY_PATTERN = re.compile(r'(0x[0-9a-fA-F]+):\s*([0-9a-fA-F]{8})')
    
    def can_parse(self, log_line: str) -> bool:
        return "OpenOCD" in log_line or "target" in log_line.lower()
    
    def parse(self, log_lines: list[str]) -> list[BugReport]:
        bugs = []
        
        for line in log_lines:
            # Hard fault detection
            if self.HARD_FAULT_PATTERN.search(line):
                bug = BugReport(
                    title="HardFault detected by OpenOCD",
                    description=line.strip(),
                    bug_type=BugType.HARD_FAULT,
                    severity=BugSeverity.CRITICAL,
                    confidence=0.95,
                    source_file="OpenOCD",
                )
                bug.signature = bug.compute_signature()
                bugs.append(bug)
            
            # Watchdog detection
            if self.WATCHDOG_PATTERN.search(line):
                bug = BugReport(
                    title="Watchdog event in OpenOCD",
                    description=line.strip(),
                    bug_type=BugType.WATCHDOG_TIMEOUT,
                    severity=BugSeverity.HIGH,
                    confidence=0.85,
                    source_file="OpenOCD",
                )
                bug.signature = bug.compute_signature()
                bugs.append(bug)
        
        return bugs


class GenericLogParser(LogParser):
    """Generic fallback parser for common embedded log formats."""
    
    name = "generic"
    
    # Common embedded error patterns
    ERROR_PATTERNS = [
        (re.compile(r'hard[\s_-]?fault', re.I), BugType.HARD_FAULT, BugSeverity.CRITICAL),
        (re.compile(r'mem[\s_-]?manage[\s_-]?fault', re.I), BugType.MEMORY_FAULT, BugSeverity.CRITICAL),
        (re.compile(r'bus[\s_-]?fault', re.I), BugType.BUS_FAULT, BugSeverity.CRITICAL),
        (re.compile(r'usage[\s_-]?fault', re.I), BugType.USAGE_FAULT, BugSeverity.HIGH),
        (re.compile(r'stack[\s_-]?overflow', re.I), BugType.STACK_OVERFLOW, BugSeverity.CRITICAL),
        (re.compile(r'heap[\s_-]?(out|exhaust)', re.I), BugType.HEAP_EXHAUSTION, BugSeverity.HIGH),
        (re.compile(r'watchdog[\s_-]?timeout', re.I), BugType.WATCHDOG_TIMEOUT, BugSeverity.HIGH),
        (re.compile(r'deadlock', re.I), BugType.DEADLOCK, BugSeverity.CRITICAL),
        (re.compile(r'assert(ion)?[\s_-]?fail', re.I), BugType.ASSERTION_FAILED, BugSeverity.HIGH),
        (re.compile(r'i2c.*timeout', re.I), BugType.I2C_TIMEOUT, BugSeverity.MEDIUM),
        (re.compile(r'spi.*timeout', re.I), BugType.SPI_TIMEOUT, BugSeverity.MEDIUM),
        (re.compile(r'uart.*timeout', re.I), BugType.UART_TIMEOUT, BugSeverity.LOW),
        (re.compile(r'can.*timeout', re.I), BugType.CAN_TIMEOUT, BugSeverity.HIGH),
        (re.compile(r'dma.*error', re.I), BugType.PERIPHERAL_ERROR, BugSeverity.HIGH),
        (re.compile(r'crash', re.I), BugType.CRASH, BugSeverity.CRITICAL),
        (re.compile(r'reset.*reason', re.I), BugType.RESET, BugSeverity.MEDIUM),
    ]
    
    # Location patterns
    LOCATION_PATTERNS = [
        re.compile(r'(?:in|at)\s+(\w+)\s*\(([^)]+):(\d+)\)'),  # in func(file:line)
        re.compile(r'([/\w]+\.(?:c|h)):\s*(\d+)(?::.*)?'),      # file.c: line
        re.compile(r'0x[0-9a-fA-F]+\s+in\s+(\w+)'),              # 0x... in func
    ]
    
    def can_parse(self, log_line: str) -> bool:
        return True  # Fallback parser
    
    def parse(self, log_lines: list[str]) -> list[BugReport]:
        bugs = []
        
        for i, line in enumerate(log_lines):
            for pattern, bug_type, severity in self.ERROR_PATTERNS:
                if pattern.search(line):
                    bug = BugReport(
                        title=self._extract_title(line, pattern),
                        description=line.strip(),
                        bug_type=bug_type,
                        severity=severity,
                        confidence=0.7,
                        source_file="generic",
                    )
                    
                    # Try to extract location
                    self._extract_location(line, bug)
                    
                    # Add context lines
                    start = max(0, i - 2)
                    end = min(len(log_lines), i + 3)
                    bug.description = "\n".join(log_lines[start:end])
                    
                    bug.signature = bug.compute_signature()
                    bugs.append(bug)
                    break  # One bug per line
        
        return bugs
    
    def _extract_title(self, line: str, pattern: re.Pattern) -> str:
        """Extract a readable title from the log line."""
        match = pattern.search(line)
        if match:
            return match.group(0).title()
        return "Unknown error"
    
    def _extract_location(self, line: str, bug: BugReport) -> None:
        """Extract file/line/function from log line."""
        for pattern in self.LOCATION_PATTERNS:
            match = pattern.search(line)
            if match:
                groups = match.groups()
                if len(groups) >= 1:
                    bug.location.function = groups[0]
                if len(groups) >= 2:
                    bug.location.file = groups[1]
                if len(groups) >= 3:
                    try:
                        bug.location.line = int(groups[2])
                    except ValueError:
                        pass
                break


class BugReportParser:
    """Main parser that coordinates multiple format parsers."""
    
    def __init__(self) -> None:
        self._parsers: list[LogParser] = [
            SeggerSystemViewParser(),
            GDBOutputParser(),
            OpenOCDParser(),
            GenericLogParser(),  # Fallback
        ]
    
    def parse(self, log_content: str | list[str]) -> list[BugReport]:
        """Parse log content into structured bug reports.
        
        Args:
            log_content: Raw log string or list of lines
            
        Returns:
            List of structured BugReport objects
        """
        if isinstance(log_content, str):
            log_lines = log_content.splitlines()
        else:
            log_lines = log_content
        
        all_bugs: list[BugReport] = []
        used_lines: set[int] = set()
        
        # Try each parser
        for parser in self._parsers:
            parser_bugs = parser.parse(log_lines)
            
            for bug in parser_bugs:
                # Find matching line
                for i, line in enumerate(log_lines):
                    if i not in used_lines and line.strip() in bug.description:
                        bug.source_file = f"line {i+1}"
                        used_lines.add(i)
                        break
                all_bugs.append(bug)
        
        # Remove duplicates
        return self._deduplicate(all_bugs)
    
    def _deduplicate(self, bugs: list[BugReport]) -> list[BugReport]:
        """Remove duplicate bug reports based on signature."""
        seen: set[str] = set()
        unique: list[BugReport] = []
        
        for bug in bugs:
            sig = bug.compute_signature()
            if sig not in seen:
                seen.add(sig)
                bug.signature = sig
                unique.append(bug)
        
        return unique
    
    def parse_file(self, filepath: str) -> list[BugReport]:
        """Parse a log file."""
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return self.parse(content)


# Global singleton
_bug_parser: BugReportParser | None = None


def get_bug_parser() -> BugReportParser:
    """Get global bug report parser instance."""
    global _bug_parser
    if _bug_parser is None:
        _bug_parser = BugReportParser()
    return _bug_parser


# CLI for testing
if __name__ == "__main__":
    import sys
    
    parser = get_bug_parser()
    
    # Test logs
    test_logs = [
        "[0] ISR UART1_RX Enter",
        "[1] ISR UART1_RX Exit",
        "[5] Exception 3: Usage fault - unaligned access",
        "Program received signal SIGSEGV, Segmentation fault.",
        "0x08001234 in HardFault_Handler() at stm32f4xx_it.c:142",
        "ERROR: hard_fault at 0x20001000",
        "WARN: stack_overflow in task main - stack watermark 100%",
        "INFO: watchdog timeout detected",
        "[OpenOCD] Target halted due to hardfault",
        "FATAL: deadlock detected between mutex_a and mutex_b",
    ]
    
    print("Testing bug report parser:")
    print("-" * 60)
    
    bugs = parser.parse(test_logs)
    
    for bug in bugs:
        print(f"\n[Bug] {bug.title}")
        print(f"  Type: {bug.bug_type.value}")
        print(f"  Severity: {bug.severity.value}")
        print(f"  Confidence: {bug.confidence:.0%}")
        print(f"  Location: {bug.location}")
        print(f"  Signature: {bug.signature}")

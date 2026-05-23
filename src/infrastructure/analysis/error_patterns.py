"""Error pattern library for embedded firmware (Phase 8.3).

Provides:
- HardFault pattern detection
- Timeout pattern detection
- Deadlock pattern detection
- Error classification
- Pattern versioning
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ErrorCategory(Enum):
    """Error category classification."""
    HARD_FAULT = "hard_fault"
    MEMORY_FAULT = "memory_fault"
    BUS_FAULT = "bus_fault"
    USAGE_FAULT = "usage_fault"
    TIMEOUT = "timeout"
    DEADLOCK = "deadlock"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    INTERRUPT_STORM = "interrupt_storm"
    WATCHDOG = "watchdog"
    STACK_OVERFLOW = "stack_overflow"
    ASSERTION = "assertion"
    WATCHDOG_TIMEOUT = "watchdog_timeout"
    UNKNOWN = "unknown"


class Severity(Enum):
    """Error severity level."""
    CRITICAL = "critical"    # System halted
    HIGH = "high"            # Major feature broken
    MEDIUM = "medium"        # Degraded operation
    LOW = "low"              # Warning, non-blocking


@dataclass
class ErrorPattern:
    """Error pattern definition."""
    id: str
    category: ErrorCategory
    name: str
    patterns: list[str]  # Regex patterns to match
    severity: Severity
    description: str
    root_causes: list[str] = field(default_factory=list)
    mitigation: str = ""
    version: str = "1.0"
    created_at: datetime = field(default_factory=datetime.now)
    
    def match(self, log_line: str) -> bool:
        """Check if log line matches this pattern."""
        for pattern in self.patterns:
            if re.search(pattern, log_line, re.IGNORECASE):
                return True
        return False


@dataclass
class ErrorMatch:
    """Matched error instance."""
    pattern_id: str
    category: ErrorCategory
    severity: Severity
    message: str
    line_number: int = 0
    timestamp: str = ""
    context_before: list[str] = field(default_factory=list)
    context_after: list[str] = field(default_factory=list)
    root_causes: list[str] = field(default_factory=list)
    confidence: float = 1.0  # 0.0 - 1.0


@dataclass
class CrashCluster:
    """Cluster of similar crashes for fleet analysis."""
    cluster_id: str
    error_type: ErrorCategory
    signature: str  # Hash of error pattern
    occurrences: int = 0
    affected_boards: list[str] = field(default_factory=list)
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    sample_error: ErrorMatch | None = None


class ErrorPatternLibrary:
    """Library of embedded error patterns.
    
    Phase 8.3: Error pattern library
    Phase 8.3a: Auto-learn patterns from new logs
    Phase 8.3b: Pattern versioning
    Phase 8.5: Crash clustering
    """
    
    # Built-in patterns
    BUILT_IN_PATTERNS: list[ErrorPattern] = [
        # HardFault patterns
        ErrorPattern(
            id="HF001",
            category=ErrorCategory.HARD_FAULT,
            name="HardFault",
            patterns=[
                r"HardFault",
                r"hard_fault",
                r"HARD_FAULT",
                r"\bHF\b.*fault",
            ],
            severity=Severity.CRITICAL,
            description="Unrecoverable ARM hard fault",
            root_causes=["NULL pointer dereference", "Invalid memory access", "Stack overflow", "Illegal instruction"],
            mitigation="Check PC register, analyze stack frame",
        ),
        ErrorPattern(
            id="HF002",
            category=ErrorCategory.HARD_FAULT,
            name="MemManageFault",
            patterns=[
                r"MemManageFault",
                r"MemManage fault",
                r"MEMFAULT",
            ],
            severity=Severity.CRITICAL,
            description="Memory management fault (MPU violation)",
            root_causes=["MPU configuration error", "Access to protected region"],
            mitigation="Check MPU settings, memory regions",
        ),
        ErrorPattern(
            id="HF003",
            category=ErrorCategory.HARD_FAULT,
            name="BusFault",
            patterns=[
                r"BusFault",
                r"bus fault",
                r"BUSFAULT",
            ],
            severity=Severity.CRITICAL,
            description="Bus fault (prefetch abort or data abort)",
            root_causes=["Invalid memory address", "Peripheral timeout", "Flash error"],
            mitigation="Check address, bus configuration",
        ),
        ErrorPattern(
            id="HF004",
            category=ErrorCategory.HARD_FAULT,
            name="UsageFault",
            patterns=[
                r"UsageFault",
                r"usage fault",
                r"USAGEFAULT",
                r"Unaligned memory access",
                r"Divide by zero",
            ],
            severity=Severity.HIGH,
            description="Usage fault (illegal instruction, DIVBYZERO, etc)",
            root_causes=["Unaligned access", "Invalid instruction", "Divide by zero"],
            mitigation="Check instruction alignment, enable unaligned access",
        ),
        
        # Timeout patterns
        ErrorPattern(
            id="TO001",
            category=ErrorCategory.TIMEOUT,
            name="I2CTimeout",
            patterns=[
                r"i2c.*timeout",
                r"I2C.*TIMEOUT",
                r"I2C.*stuck",
                r"I2C.*SDA.*low",
            ],
            severity=Severity.MEDIUM,
            description="I2C bus timeout",
            root_causes=["Device not responding", "Bus contention", "Clock stretch timeout"],
            mitigation="Check pull-ups, device address, bus state",
        ),
        ErrorPattern(
            id="TO002",
            category=ErrorCategory.TIMEOUT,
            name="SPITimeout",
            patterns=[
                r"spi.*timeout",
                r"SPI.*TIMEOUT",
                r"SPI.*NSS.*high",
            ],
            severity=Severity.MEDIUM,
            description="SPI transaction timeout",
            root_causes=["Device not responding", "Wrong mode", "Clock configuration"],
            mitigation="Check SPI mode, clock speed, CS signal",
        ),
        ErrorPattern(
            id="TO003",
            category=ErrorCategory.TIMEOUT,
            name="UARTTimeout",
            patterns=[
                r"uart.*timeout",
                r"UART.*IDLE",
                r"uart.*overrun",
            ],
            severity=Severity.LOW,
            description="UART receive timeout or overrun",
            root_causes=["Baud rate mismatch", "FIFO overflow", "ISR latency"],
            mitigation="Check baud rate, increase buffer size",
        ),
        ErrorPattern(
            id="TO004",
            category=ErrorCategory.TIMEOUT,
            name="CANTimeout",
            patterns=[
                r"can.*timeout",
                r"CAN.*bus.*off",
                r"CAN.*error",
                r"can.*tx.*timeout",
            ],
            severity=Severity.HIGH,
            description="CAN bus timeout or error",
            root_causes=["Bus contention", "Termination resistor", "Baud rate mismatch"],
            mitigation="Check CAN wiring, termination, baud rate",
        ),
        ErrorPattern(
            id="TO005",
            category=ErrorCategory.TIMEOUT,
            name="DMATimeout",
            patterns=[
                r"dma.*timeout",
                r"DMA.*error",
                r"DMA.*transfer.*fail",
            ],
            severity=Severity.HIGH,
            description="DMA transfer timeout",
            root_causes=["Peripheral not ready", "Bus arbitration", "Configuration error"],
            mitigation="Check DMA channel configuration, peripheral enable",
        ),
        
        # Deadlock patterns
        ErrorPattern(
            id="DL001",
            category=ErrorCategory.DEADLOCK,
            name="MutexDeadlock",
            patterns=[
                r"deadlock",
                r"mutex.*blocked.*forever",
                r"lock.*timeout",
                r"抢锁.*超时",  # Chinese
            ],
            severity=Severity.CRITICAL,
            description="Task deadlock - two or more tasks waiting on each other",
            root_causes=["Circular wait", "Lock ordering violation", "Priority inversion"],
            mitigation="Check lock order, use timeout on locks",
        ),
        ErrorPattern(
            id="DL002",
            category=ErrorCategory.DEADLOCK,
            name="PriorityInversion",
            patterns=[
                r"priority.*inversion",
                r"priority.*inheritance",
            ],
            severity=Severity.HIGH,
            description="Priority inversion detected",
            root_causes=["High priority task blocked by low priority", "Missing mutex priority inheritance"],
            mitigation="Enable priority inheritance on mutexes",
        ),
        ErrorPattern(
            id="DL003",
            category=ErrorCategory.DEADLOCK,
            name="ISRBlock",
            patterns=[
                r"isr.*blocked",
                r"interrupt.*while.*critical",
                r"basepri.*nonzero.*in.*isr",
            ],
            severity=Severity.HIGH,
            description="Blocking operation in ISR",
            root_causes=["Delay/sleep in ISR", "Mutex acquisition in ISR"],
            mitigation="Remove blocking calls from ISR, use deferred callbacks",
        ),
        
        # Resource exhaustion
        ErrorPattern(
            id="RE001",
            category=ErrorCategory.RESOURCE_EXHAUSTION,
            name="HeapExhaustion",
            patterns=[
                r"out of memory",
                r"heap.*full",
                r"malloc.*fail",
                r"pvPortMalloc.*fail",
            ],
            severity=Severity.HIGH,
            description="Heap memory exhausted",
            root_causes=["Memory leak", "Fragmentation", "Allocation too large"],
            mitigation="Profile heap usage, check for leaks",
        ),
        ErrorPattern(
            id="RE002",
            category=ErrorCategory.RESOURCE_EXHAUSTION,
            name="StackOverflow",
            patterns=[
                r"stack.*overflow",
                r"stack.*check.*fail",
                r"_ stack overflow _",
                r"task.*stack.*watermark",
            ],
            severity=Severity.CRITICAL,
            description="Stack overflow detected",
            root_causes=["Deep recursion", "Large local variables", "ISR stack too small"],
            mitigation="Increase stack size, reduce local allocations",
        ),
        ErrorPattern(
            id="RE003",
            category=ErrorCategory.RESOURCE_EXHAUSTION,
            name="FIFOFull",
            patterns=[
                r"fifo.*full",
                r"queue.*full",
                r"buffer.*overflow",
                r"xQueue.*fail",
            ],
            severity=Severity.MEDIUM,
            description="Message queue or FIFO full",
            root_causes=["Consumer task blocked/failed", "Producer rate too high"],
            mitigation="Check consumer task health, increase queue size",
        ),
        
        # Interrupt patterns
        ErrorPattern(
            id="IS001",
            category=ErrorCategory.INTERRUPT_STORM,
            name="InterruptStorm",
            patterns=[
                r"interrupt.*storm",
                r"too many.*interrupts",
                r"nested.*interrupt.*overflow",
            ],
            severity=Severity.CRITICAL,
            description="Excessive interrupt rate",
            root_causes=["Hardware issue", "External trigger misconfigured", "Level-sensitive interrupt not cleared"],
            mitigation="Check interrupt source, clear flag in handler",
        ),
        
        # Watchdog patterns
        ErrorPattern(
            id="WD001",
            category=ErrorCategory.WATCHDOG_TIMEOUT,
            name="WatchdogTimeout",
            patterns=[
                r"watchdog.*timeout",
                r"iwdg.*reset",
                r"wwdg.*reset",
                r"task.*watchdog.*timeout",
            ],
            severity=Severity.CRITICAL,
            description="Watchdog timer expired",
            root_causes=["Task stuck in loop", "Task starvation", "Deadlock"],
            mitigation="Check task watchdog kicks, analyze task state",
        ),
        
        # Assertion patterns
        ErrorPattern(
            id="AS001",
            category=ErrorCategory.ASSERTION,
            name="AssertionFailed",
            patterns=[
                r"assert.*fail",
                r"ASSERT.*failed",
                r"_assert.*failed",
                r"assertion.*failed",
            ],
            severity=Severity.HIGH,
            description="Assertion failed - invariant violated",
            root_causes=["Invalid state", "Invalid parameter", "Unexpected condition"],
            mitigation="Check assertion context, add logging before assertion",
        ),
    ]
    
    def __init__(self) -> None:
        self._patterns: dict[str, ErrorPattern] = {
            p.id: p for p in self.BUILT_IN_PATTERNS
        }
        self._learned_patterns: list[ErrorPattern] = []
        self._clusters: dict[str, CrashCluster] = {}
    
    def register_pattern(self, pattern: ErrorPattern) -> None:
        """Register a new error pattern."""
        self._patterns[pattern.id] = pattern
        logger = __import__("logging").getLogger(__name__)
        logger.info("Registered error pattern", id=pattern.id, name=pattern.name)
    
    def learn_pattern(self, log_lines: list[str], category: ErrorCategory) -> ErrorPattern | None:
        """Learn a new pattern from log lines (Phase 8.3a)."""
        if not log_lines:
            return None
        
        # Simple learning: find common error keywords
        all_text = " ".join(log_lines)
        
        # Extract potential error signatures
        import re
        signatures = re.findall(r'0x[0-9a-fA-F]+', all_text)
        addresses = set(signatures)
        
        # Find error messages (lines with error keywords)
        error_lines = [l for l in log_lines if re.search(r'error|fail|fault|timeout', l, re.I)]
        
        if error_lines:
            # Create pattern from first error line
            first_error = error_lines[0]
            
            # Generate patterns
            patterns = []
            
            # Extract non-variable parts
            pattern_str = re.sub(r'0x[0-9a-fA-F]+', '{HEX}', first_error)
            pattern_str = re.sub(r'\d+', '{NUM}', pattern_str)
            pattern_str = re.sub(r'\[.*?\]', '{BRACKET}', pattern_str)
            
            patterns.append(re.escape(pattern_str))
            
            new_pattern = ErrorPattern(
                id=f"LEARNED_{len(self._learned_patterns) + 1:03d}",
                category=category,
                name=f"Learned pattern {len(self._learned_patterns) + 1}",
                patterns=patterns,
                severity=Severity.HIGH,
                description="Auto-learned from log analysis",
            )
            
            self._learned_patterns.append(new_pattern)
            self.register_pattern(new_pattern)
            
            return new_pattern
        
        return None
    
    def match(self, log_line: str) -> list[ErrorMatch]:
        """Match log line against all patterns."""
        matches = []
        
        for pattern in self._patterns.values():
            if pattern.match(log_line):
                matches.append(ErrorMatch(
                    pattern_id=pattern.id,
                    category=pattern.category,
                    severity=pattern.severity,
                    message=log_line,
                    root_causes=pattern.root_causes,
                    confidence=1.0,
                ))
        
        return matches
    
    def analyze_logs(
        self,
        log_lines: list[str],
        context_lines: int = 3,
    ) -> list[ErrorMatch]:
        """Analyze log lines and return error matches with context."""
        errors: list[ErrorMatch] = []
        
        for i, line in enumerate(log_lines):
            matches = self.match(line)
            for match in matches:
                match.line_number = i + 1
                
                # Add context
                start = max(0, i - context_lines)
                end = min(len(log_lines), i + context_lines + 1)
                match.context_before = log_lines[start:i]
                match.context_after = log_lines[i+1:end]
                
                errors.append(match)
        
        return errors
    
    def cluster_crashes(
        self,
        errors: list[ErrorMatch],
        board_ids: list[str] | None = None,
    ) -> list[CrashCluster]:
        """Cluster similar crashes across fleet (Phase 8.5)."""
        clusters: dict[str, CrashCluster] = {}
        
        for i, error in enumerate(errors):
            # Create signature from pattern ID and category
            signature = f"{error.category.value}:{error.pattern_id}"
            
            if signature not in clusters:
                clusters[signature] = CrashCluster(
                    cluster_id=signature,
                    error_type=error.category,
                    signature=signature,
                    sample_error=error,
                )
            
            cluster = clusters[signature]
            cluster.occurrences += 1
            cluster.last_seen = datetime.now()
            
            if board_ids and i < len(board_ids):
                if board_ids[i] not in cluster.affected_boards:
                    cluster.affected_boards.append(board_ids[i])
        
        return list(clusters.values())
    
    def get_pattern(self, pattern_id: str) -> ErrorPattern | None:
        """Get pattern by ID."""
        return self._patterns.get(pattern_id)
    
    def get_patterns_by_category(self, category: ErrorCategory) -> list[ErrorPattern]:
        """Get all patterns in a category."""
        return [p for p in self._patterns.values() if p.category == category]
    
    def export_patterns(self) -> dict[str, Any]:
        """Export patterns for versioning (Phase 8.3b)."""
        return {
            "version": "1.0",
            "exported_at": datetime.now().isoformat(),
            "patterns": [
                {
                    "id": p.id,
                    "name": p.name,
                    "category": p.category.value,
                    "patterns": p.patterns,
                    "severity": p.severity.value,
                    "description": p.description,
                    "root_causes": p.root_causes,
                    "mitigation": p.mitigation,
                }
                for p in self._patterns.values()
            ],
        }
    
    def import_patterns(self, data: dict[str, Any]) -> int:
        """Import patterns with version check."""
        imported = 0
        version = data.get("version", "0.0")
        
        for p_data in data.get("patterns", []):
            try:
                pattern = ErrorPattern(
                    id=p_data["id"],
                    category=ErrorCategory(p_data["category"]),
                    name=p_data["name"],
                    patterns=p_data["patterns"],
                    severity=Severity(p_data["severity"]),
                    description=p_data["description"],
                    root_causes=p_data.get("root_causes", []),
                    mitigation=p_data.get("mitigation", ""),
                    version=version,
                )
                self.register_pattern(pattern)
                imported += 1
            except (KeyError, ValueError) as e:
                logger = __import__("logging").getLogger(__name__)
                logger.warning("Failed to import pattern", id=p_data.get("id"), error=str(e))
        
        return imported


# Global singleton
_error_pattern_library: ErrorPatternLibrary | None = None


def get_error_pattern_library() -> ErrorPatternLibrary:
    """Get global error pattern library instance."""
    global _error_pattern_library
    if _error_pattern_library is None:
        _error_pattern_library = ErrorPatternLibrary()
    return _error_pattern_library


# CLI for pattern testing
if __name__ == "__main__":
    import sys
    
    library = get_error_pattern_library()
    
    # Test patterns
    test_logs = [
        "INFO: System started",
        "ERROR: HardFault at 0x08001234",
        "WARN: I2C timeout on bus 1",
        "ERROR: Stack overflow in task main",
        "FATAL: deadlock detected",
    ]
    
    print("Testing error pattern library:")
    print("-" * 50)
    
    for log in test_logs:
        matches = library.match(log)
        if matches:
            for m in matches:
                print(f"[{m.category.value}] {m.pattern_id}: {m.severity.value}")
                print(f"  -> {m.message}")
                print(f"  Root causes: {m.root_causes}")
        else:
            print(f"[NO MATCH] {log}")
    
    print("-" * 50)
    print(f"Total patterns: {len(library._patterns)}")

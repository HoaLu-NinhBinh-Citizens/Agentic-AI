"""Closed-Loop Tool Execution with Autonomous Repair.

Real execution layer with:
- Build/test feedback loops
- Compiler error understanding
- Test failure analysis
- Autonomous fix generation
- Runtime observability
- Hardware feedback integration
"""

from __future__ import annotations

import asyncio
import logging
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# EXECUTION TYPES
# =============================================================================


class ExecutionStatus(Enum):
    """Execution status."""
    
    PENDING = auto()
    RUNNING = auto()
    SUCCESS = auto()
    FAILED = auto()
    TIMEOUT = auto()
    CANCELLED = auto()


class ErrorSeverity(Enum):
    """Error severity."""
    
    ERROR = auto()
    WARNING = auto()
    NOTE = auto()
    INFO = auto()


# =============================================================================
# DIAGNOSTIC TYPES
# =============================================================================


@dataclass
class Diagnostic:
    """A diagnostic (error, warning, note) from execution."""
    
    severity: ErrorSeverity
    message: str
    
    # Location
    file: str = ""
    line: int = 0
    column: int = 0
    
    # Categorization
    error_code: str = ""
    category: str = ""  # e.g., "syntax", "type", "linker", "undefined"
    
    # Fix suggestions
    suggestions: list[str] = field(default_factory=list)
    
    # Related
    related_diagnostics: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.name,
            "message": self.message,
            "location": f"{self.file}:{self.line}:{self.column}",
            "error_code": self.error_code,
            "category": self.category,
            "suggestions": self.suggestions,
        }


@dataclass
class ExecutionResult:
    """Result of tool execution."""
    
    command: str
    status: ExecutionStatus
    exit_code: int
    
    # Output
    stdout: str = ""
    stderr: str = ""
    
    # Diagnostics
    diagnostics: list[Diagnostic] = field(default_factory=list)
    
    # Timing
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    duration_ms: float = 0.0
    
    # Context
    working_directory: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "status": self.status.name,
            "exit_code": self.exit_code,
            "diagnostics_count": len(self.diagnostics),
            "duration_ms": self.duration_ms,
            "errors": [d.to_dict() for d in self.diagnostics if d.severity == ErrorSeverity.ERROR],
        }


# =============================================================================
# ERROR PARSER
# =============================================================================


class CompilerErrorParser:
    """Parses compiler output into structured diagnostics.
    
    Understands:
    - GCC/Clang errors
    - ARM GCC errors
    - STM32Cube errors
    - Linker errors
    - Make errors
    """
    
    # GCC/Clang pattern
    GCC_PATTERN = re.compile(
        r"(?P<file>[^:]+):(?P<line>\d+):(?P<column>\d+):\s*"
        r"(?P<severity>error|warning|note):\s*"
        r"(?P<message>.+)"
    )
    
    # ARM GCC pattern (some variations)
    ARM_PATTERN = re.compile(
        r"(?P<file>[^:]+)\((?P<line>\d+)\):\s*"
        r"(?P<severity>error|warning):\s*"
        r"(?P<code>\w+\d+):\s*"
        r"(?P<message>.+)"
    )
    
    # Linker error
    LINKER_PATTERN = re.compile(
        r"(?P<symbol>.+?):(?P<error>undefined reference to .+)"
    )
    
    def __init__(self):
        self._parsers = [
            self._parse_gcc,
            self._parse_arm,
            self._parse_linker,
        ]
    
    def parse(self, output: str, stderr: str = "") -> list[Diagnostic]:
        """Parse compiler output into diagnostics."""
        diagnostics = []
        combined = output + "\n" + stderr
        
        for parser in self._parsers:
            diagnostics.extend(parser(combined))
        
        return diagnostics
    
    def _parse_gcc(self, text: str) -> list[Diagnostic]:
        """Parse GCC/Clang style errors."""
        diagnostics = []
        
        for match in self.GCC_PATTERN.finditer(text):
            severity = ErrorSeverity.ERROR
            if "warning" in match.group("severity").lower():
                severity = ErrorSeverity.WARNING
            elif "note" in match.group("severity").lower():
                severity = ErrorSeverity.NOTE
            
            diag = Diagnostic(
                severity=severity,
                message=match.group("message").strip(),
                file=match.group("file"),
                line=int(match.group("line")),
                column=int(match.group("column")),
                category=self._categorize_error(match.group("message")),
            )
            diag.suggestions = self._generate_suggestions(diag)
            diagnostics.append(diag)
        
        return diagnostics
    
    def _parse_arm(self, text: str) -> list[Diagnostic]:
        """Parse ARM GCC style errors."""
        diagnostics = []
        
        for match in self.ARM_PATTERN.finditer(text):
            diag = Diagnostic(
                severity=ErrorSeverity.ERROR if "error" in match.group("severity") else ErrorSeverity.WARNING,
                message=match.group("message").strip(),
                file=match.group("file"),
                line=int(match.group("line")),
                error_code=match.group("code"),
                category=self._categorize_error(match.group("message")),
            )
            diag.suggestions = self._generate_suggestions(diag)
            diagnostics.append(diag)
        
        return diagnostics
    
    def _parse_linker(self, text: str) -> list[Diagnostic]:
        """Parse linker errors."""
        diagnostics = []
        
        for match in self.LINKER_PATTERN.finditer(text):
            diag = Diagnostic(
                severity=ErrorSeverity.ERROR,
                message=match.group("error").strip(),
                category="linker",
            )
            diag.suggestions = self._suggest_linker_fix(match.group("symbol"), match.group("error"))
            diagnostics.append(diag)
        
        return diagnostics
    
    def _categorize_error(self, message: str) -> str:
        """Categorize error based on message content."""
        msg_lower = message.lower()
        
        if "undefined reference" in msg_lower:
            return "linker"
        if "implicit declaration" in msg_lower:
            return "type"
        if "incompatible pointer" in msg_lower:
            return "type"
        if "syntax error" in msg_lower:
            return "syntax"
        if "undeclared" in msg_lower:
            return "undeclared"
        if "redefinition" in msg_lower:
            return "redefinition"
        if "initializer element is not compile-time constant" in msg_lower:
            return "const"
        if "warning" in msg_lower:
            return "warning"
        
        return "unknown"
    
    def _generate_suggestions(self, diag: Diagnostic) -> list[str]:
        """Generate fix suggestions based on error type."""
        suggestions = []
        msg = diag.message.lower()
        
        if "undeclared" in msg:
            suggestions.append("Check if header file is included")
            suggestions.append("Verify function/variable is defined")
        
        if "implicit declaration" in msg:
            suggestions.append("Include the header with function declaration")
            suggestions.append("Check function signature")
        
        if "incompatible pointer" in msg:
            suggestions.append("Check pointer types match")
            suggestions.append("Verify function signature")
        
        if "undefined reference" in msg:
            suggestions.append("Check if function is defined (not just declared)")
            suggestions.append("Verify linker includes the source file")
            suggestions.append("Check for missing library")
        
        if "redefinition" in msg:
            suggestions.append("Use include guards or #pragma once")
        
        if "syntax error" in msg:
            suggestions.append("Check for missing semicolons, parentheses")
            suggestions.append("Verify matching braces")
        
        return suggestions
    
    def _suggest_linker_fix(self, symbol: str, error: str) -> list[str]:
        """Generate linker-specific suggestions."""
        suggestions = []
        
        if "undefined reference" in error:
            suggestions.append(f"Check if '{symbol}' is defined in a source file")
            suggestions.append("Verify the source file is compiled and linked")
            suggestions.append("Check for static vs non-static definitions")
        
        return suggestions


# =============================================================================
# TEST RESULT PARSER
# =============================================================================


class TestResultParser:
    """Parses test output into structured results."""
    
    # pytest pattern
    PYTEST_PATTERN = re.compile(
        r"FAILED (?P<test>.+?) - (?P<message>.+)"
    )
    
    # unittest pattern
    UNittest_PATTERN = re.compile(
        r"(?P<status>FAIL|ERROR|OK): (?P<test>.+)"
    )
    
    def parse(self, output: str) -> dict[str, Any]:
        """Parse test output."""
        result = {
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "total": 0,
            "failures": [],
            "errors_list": [],
        }
        
        # Count pytest-style results
        failed = re.findall(r"(\d+) failed", output)
        passed = re.findall(r"(\d+) passed", output)
        errors = re.findall(r"(\d+) error", output)
        
        if failed:
            result["failed"] = int(failed[0])
        if passed:
            result["passed"] = int(passed[0])
        if errors:
            result["errors"] = int(errors[0])
        
        result["total"] = result["passed"] + result["failed"] + result["errors"]
        
        # Parse individual failures
        for match in self.PYTEST_PATTERN.finditer(output):
            result["failures"].append({
                "test": match.group("test"),
                "message": match.group("message").strip(),
            })
        
        return result


# =============================================================================
# TOOL EXECUTOR
# =============================================================================


class ToolExecutor:
    """Closed-loop tool executor with feedback.
    
    Features:
    - Async execution
    - Timeout handling
    - Error parsing
    - Diagnostic extraction
    - Fix suggestion generation
    - Retry with backoff
    - Environment management
    """
    
    def __init__(self):
        self._error_parser = CompilerErrorParser()
        self._test_parser = TestResultParser()
        self._execution_history: list[ExecutionResult] = []
    
    async def execute(
        self,
        command: str,
        cwd: str | None = None,
        timeout_seconds: float = 60.0,
        env: dict[str, str] | None = None,
    ) -> ExecutionResult:
        """Execute a tool command with feedback."""
        import time
        
        result = ExecutionResult(
            command=command,
            status=ExecutionStatus.RUNNING,
            exit_code=-1,
            working_directory=cwd or "",
        )
        
        start_time = time.perf_counter()
        
        try:
            # Execute command
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout_seconds,
                )
                
                result.stdout = stdout.decode("utf-8", errors="replace")
                result.stderr = stderr.decode("utf-8", errors="replace")
                result.exit_code = process.returncode
                
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                result.status = ExecutionStatus.TIMEOUT
                result.diagnostics.append(Diagnostic(
                    severity=ErrorSeverity.ERROR,
                    message=f"Command timed out after {timeout_seconds}s",
                    category="timeout",
                ))
                return result
        
        except Exception as e:
            result.status = ExecutionStatus.FAILED
            result.stderr = str(e)
            result.exit_code = -1
            result.diagnostics.append(Diagnostic(
                severity=ErrorSeverity.ERROR,
                message=f"Execution failed: {str(e)}",
                category="execution",
            ))
            return result
        
        finally:
            result.duration_ms = (time.perf_counter() - start_time) * 1000
            result.completed_at = datetime.utcnow()
        
        # Determine status
        if result.status != ExecutionStatus.TIMEOUT:
            result.status = ExecutionStatus.SUCCESS if result.exit_code == 0 else ExecutionStatus.FAILED
        
        # Parse diagnostics
        if result.stderr:
            result.diagnostics.extend(self._error_parser.parse(result.stdout, result.stderr))
        
        # Store in history
        self._execution_history.append(result)
        
        logger.info(
            "tool_executed: cmd=%s status=%s exit=%s duration=%sms diagnostics=%s",
            command[:50], result.status.name, result.exit_code,
            result.duration_ms, len(result.diagnostics),
        )
        
        return result
    
    async def build(
        self,
        build_command: str,
        cwd: str | None = None,
        timeout_seconds: float = 120.0,
    ) -> ExecutionResult:
        """Execute a build command."""
        return await self.execute(build_command, cwd, timeout_seconds)
    
    async def test(
        self,
        test_command: str,
        cwd: str | None = None,
        timeout_seconds: float = 300.0,
    ) -> dict[str, Any]:
        """Execute tests and parse results."""
        result = await self.execute(test_command, cwd, timeout_seconds)
        
        return {
            "execution": result,
            "test_results": self._test_parser.parse(result.stdout),
            "diagnostics": result.diagnostics,
        }
    
    async def flash(
        self,
        flash_command: str,
        cwd: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> ExecutionResult:
        """Execute a flash command."""
        return await self.execute(flash_command, cwd, timeout_seconds)
    
    def get_history(self) -> list[ExecutionResult]:
        """Get execution history."""
        return list(self._execution_history)
    
    def get_error_summary(self) -> dict[str, Any]:
        """Get summary of errors across executions."""
        all_errors = []
        
        for result in self._execution_history:
            all_errors.extend([
                d for d in result.diagnostics
                if d.severity == ErrorSeverity.ERROR
            ])
        
        # Group by category
        by_category: dict[str, int] = {}
        for error in all_errors:
            by_category[error.category] = by_category.get(error.category, 0) + 1
        
        return {
            "total_errors": len(all_errors),
            "by_category": by_category,
            "errors": [e.to_dict() for e in all_errors[-20:]],  # Last 20
        }


# =============================================================================
# AUTONOMOUS REPAIR ENGINE
# =============================================================================


class RepairSuggestion:
    """A repair suggestion with confidence."""
    
    def __init__(self, fix: str, confidence: float, reason: str):
        self.fix = fix
        self.confidence = confidence
        self.reason = reason


class AutonomousRepairEngine:
    """Analyzes errors and generates repair suggestions.
    
    This is the foundation for autonomous debugging.
    """
    
    def __init__(self, executor: ToolExecutor):
        self.executor = executor
        self._repair_patterns: dict[str, list[str]] = {}
        
        # Initialize common patterns
        self._init_patterns()
    
    def _init_patterns(self) -> None:
        """Initialize repair patterns."""
        self._repair_patterns = {
            "missing_include": [
                "#include <stdio.h>",
                "#include <stdlib.h>",
                "#include <string.h>",
            ],
            "missing_semicolon": [
                ";",
            ],
            "missing_brace": [
                "}",
            ],
        }
    
    def analyze_errors(self, diagnostics: list[Diagnostic]) -> list[RepairSuggestion]:
        """Analyze errors and suggest fixes."""
        suggestions = []
        
        for diag in diagnostics:
            if diag.severity != ErrorSeverity.ERROR:
                continue
            
            # Generate suggestions based on error type
            if "undeclared" in diag.message.lower():
                suggestions.extend(self._suggest_include(diag))
            
            elif "undefined reference" in diag.message.lower():
                suggestions.extend(self._suggest_linker_fix(diag))
            
            elif "incompatible" in diag.message.lower():
                suggestions.extend(self._suggest_type_fix(diag))
            
            elif "redefinition" in diag.message.lower():
                suggestions.extend(self._suggest_redefinition_fix(diag))
        
        # Deduplicate and sort by confidence
        seen = set()
        unique = []
        for s in suggestions:
            if s.fix not in seen:
                seen.add(s.fix)
                unique.append(s)
        
        unique.sort(key=lambda x: x.confidence, reverse=True)
        
        return unique
    
    def _suggest_include(self, diag: Diagnostic) -> list[RepairSuggestion]:
        """Suggest includes based on undeclared identifier."""
        suggestions = []
        
        msg = diag.message
        
        # Common functions -> header mapping
        func_to_header = {
            "printf": "#include <stdio.h>",
            "scanf": "#include <stdio.h>",
            "malloc": "#include <stdlib.h>",
            "free": "#include <stdlib.h>",
            "memcpy": "#include <string.h>",
            "memset": "#include <string.h>",
            "strlen": "#include <string.h>",
            "strcpy": "#include <string.h>",
            "HAL_": "#include \"stm32h7xx_hal.h\"",
        }
        
        for func, header in func_to_header.items():
            if func in msg:
                suggestions.append(RepairSuggestion(
                    fix=header,
                    confidence=0.9,
                    reason=f"'{func}' is declared in {header}",
                ))
        
        if not suggestions:
            suggestions.append(RepairSuggestion(
                fix="// Check header file includes",
                confidence=0.5,
                reason="Cannot determine required header",
            ))
        
        return suggestions
    
    def _suggest_linker_fix(self, diag: Diagnostic) -> list[RepairSuggestion]:
        """Suggest linker fixes."""
        suggestions = []
        
        msg = diag.message
        
        # Extract symbol name
        match = re.search(r"`(.+?)'", msg)
        if match:
            symbol = match.group(1)
            suggestions.append(RepairSuggestion(
                fix=f"// Check if '{symbol}' is defined in source",
                confidence=0.7,
                reason="Symbol not found in linked objects",
            ))
            suggestions.append(RepairSuggestion(
                fix=f"// Add source file to build",
                confidence=0.6,
                reason="Source file may not be compiled",
            ))
        
        return suggestions
    
    def _suggest_type_fix(self, diag: Diagnostic) -> list[RepairSuggestion]:
        """Suggest type fixes."""
        suggestions = []
        
        suggestions.append(RepairSuggestion(
            fix="// Check pointer types match",
            confidence=0.7,
            reason="Incompatible pointer types",
        ))
        suggestions.append(RepairSuggestion(
            fix="// Verify function signature",
            confidence=0.6,
            reason="Type mismatch may be in function call",
        ))
        
        return suggestions
    
    def _suggest_redefinition_fix(self, diag: Diagnostic) -> list[RepairSuggestion]:
        """Suggest redefinition fixes."""
        suggestions = []
        
        suggestions.append(RepairSuggestion(
            fix="// Add include guards or #pragma once",
            confidence=0.9,
            reason="Symbol defined multiple times",
        ))
        suggestions.append(RepairSuggestion(
            fix="// Use 'static' or 'inline' for local symbols",
            confidence=0.7,
            reason="Avoid ODR violations",
        ))
        
        return suggestions
    
    async def try_fix(
        self,
        file_path: str,
        fix: str,
    ) -> bool:
        """Try applying a fix (placeholder for future implementation)."""
        # In full implementation, this would:
        # 1. Read file
        # 2. Apply fix
        # 3. Verify with build
        # 4. Revert if build fails
        logger.info("repair_attempt: file=%s fix=%s", file_path, fix)
        return False


# =============================================================================
# GLOBAL EXECUTOR
# =============================================================================


_executor: ToolExecutor | None = None
_repair_engine: AutonomousRepairEngine | None = None


def get_tool_executor() -> ToolExecutor:
    """Get global tool executor."""
    global _executor
    if _executor is None:
        _executor = ToolExecutor()
    return _executor


def get_repair_engine() -> AutonomousRepairEngine:
    """Get global repair engine."""
    global _repair_engine
    if _repair_engine is None:
        _repair_engine = AutonomousRepairEngine(get_tool_executor())
    return _repair_engine

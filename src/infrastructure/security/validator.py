"""
Security Validation Module

Pre-patch security scanning for firmware generation:
- Vulnerability detection (buffer overflow, format string, etc.)
- Dangerous action detection (memory write, flash erase, etc.)
- Permission model for AI actions

Usage:
    from src.infrastructure.security.validator import SecurityValidator
    
    validator = SecurityValidator()
    result = validator.validate_firmware_patch(code_snippet)
    if not result["allowed"]:
        print(f"Security blocked: {result['reason']}")
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional, Set


class SecurityLevel(Enum):
    SAFE = "safe"
    CAUTION = "caution"
    DANGEROUS = "dangerous"
    BLOCKED = "blocked"


class ActionCategory(Enum):
    MEMORY_WRITE = "memory_write"
    FLASH_MODIFY = "flash_modify"
    REGISTER_WRITE = "register_write"
    INTERRUPT_CHANGE = "interrupt_change"
    CLOCK_CHANGE = "clock_change"
    PERIPHERAL_ENABLE = "peripheral_enable"
    DMA_CONFIG = "dma_config"
    EXTERNAL_INTERFACE = "external_interface"


@dataclass
class SecurityFinding:
    """A security finding from analysis."""
    severity: str  # "error", "warning", "info"
    category: str
    rule_id: str
    message: str
    location: Optional[str] = None
    cwe_id: Optional[str] = None
    remediation: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "category": self.category,
            "rule_id": self.rule_id,
            "message": self.message,
            "location": self.location,
            "cwe_id": self.cwe_id,
            "remediation": self.remediation,
        }


@dataclass
class SecurityValidationResult:
    """Result of security validation."""
    allowed: bool
    level: SecurityLevel
    findings: List[SecurityFinding] = field(default_factory=list)
    reason: Optional[str] = None

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warning")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "level": self.level.value,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "reason": self.reason,
            "findings": [f.to_dict() for f in self.findings],
        }


# Dangerous patterns that require review
DANGEROUS_PATTERNS = {
    # Memory safety
    "buffer_overflow": {
        "patterns": [
            r"\bstrcpy\s*\(",
            r"\bstrcat\s*\(",
            r"\bsprintf\s*\([^,]*%s",
            r"\bgets\s*\(",
            r"\bmemcpy\s*\([^,]*,\s*[^,]*\s*\)",  # memcpy without size check
        ],
        "cwe": "CWE-120",
        "severity": "error",
        "message": "Potential buffer overflow - use bounded string functions",
        "remediation": "Use strncpy, strncat, snprintf with explicit size limits",
    },
    "format_string": {
        "patterns": [
            r'\bprintf\s*\(\s*[a-zA-Z_]\w*\s*\)',  # printf(variable) without format
            r'\bfprintf\s*\(\s*[a-zA-Z_]\w*\s*,\s*[a-zA-Z_]\w*\s*\)',  # fprintf(file, var)
        ],
        "cwe": "CWE-134",
        "severity": "error",
        "message": "Potential format string vulnerability",
        "remediation": "Use printf(\"%s\", variable) instead of printf(variable)",
    },
    "integer_overflow": {
        "patterns": [
            r"\bmalloc\s*\([^)]*\+[^)]*\)",
            r"\bcalloc\s*\([^)]*\+[^)]*\)",
            r"\[\s*[a-zA-Z_]\w*\s*\+\s*[a-zA-Z_]\w*\s*\]",  # array[index + offset]
        ],
        "cwe": "CWE-190",
        "severity": "warning",
        "message": "Potential integer overflow in size calculation",
        "remediation": "Validate size calculations before allocation or array access",
    },
    "use_after_free": {
        "patterns": [
            r"\bvPortFree\s*\([^)]*\)\s*;[^}]*[^=]\s*[a-zA-Z_]\w*\s*;",  # free then use
            r"\bfree\s*\([^)]*\)\s*;[^}]*[^=]\s*[a-zA-Z_]\w*\s*;",
        ],
        "cwe": "CWE-416",
        "severity": "error",
        "message": "Potential use-after-free vulnerability",
        "remediation": "Null pointer assignment after free, or use smart pointer pattern",
    },
    "null_deref": {
        "patterns": [
            r"if\s*\(\s*![a-zA-Z_]\w*\s*\)\s*\{[^}]*->[a-zA-Z_]\w*",
            r"if\s*\(\s*[a-zA-Z_]\w*\s*==\s*NULL\s*\)\s*\{[^}]*->[a-zA-Z_]\w*",
        ],
        "cwe": "CWE-476",
        "severity": "warning",
        "message": "Potential null pointer dereference",
        "remediation": "Add null check before pointer access",
    },
}

# Dangerous actions that require permission
DANGEROUS_ACTIONS = {
    "flash_erase": {
        "patterns": [
            r"\bFLASH_\w*ERASE",
            r"\bHAL_FLASH_\w*ERASE",
            r"\bFLASH_Erase",
            r"\bErase_Flash",
        ],
        "category": ActionCategory.FLASH_MODIFY,
        "severity": "error",
        "requires_confirmation": True,
        "message": "Flash erase operation detected - destructive action",
    },
    "flash_write": {
        "patterns": [
            r"\bHAL_FLASH_\w*Program",
            r"\bFLASH_Program",
            r"\bProgram_Flash",
        ],
        "category": ActionCategory.FLASH_MODIFY,
        "severity": "error",
        "requires_confirmation": True,
        "message": "Flash write operation detected - verify address range",
    },
    "memory_write": {
        "patterns": [
            r"\*\s*[a-zA-Z_]\w*\s*=\s*[^;]+",  # Direct memory write: *ptr = value
            r"\bvolatile\s+uint32_t\s*\*\s*[a-zA-Z_]\w*\s*=\s*[^;]+",
        ],
        "category": ActionCategory.MEMORY_WRITE,
        "severity": "warning",
        "requires_confirmation": False,
        "message": "Direct memory write - ensure address is valid",
    },
    "register_write": {
        "patterns": [
            r"->\s*(CR|CSR|SR|DR|REG)\s*=",  # Common register names
            r"\*\s*\(\s*uint32_t\s*\)\s*[A-Z_]+\s*\)",  # *(uint32_t *)REGISTER
            r"\b([A-Z]{2,}_REG)\s*\|=",  # |= with register (set bits)
            r"\b([A-Z]{2,}_REG)\s*&=",  # &= with register (clear bits)
        ],
        "category": ActionCategory.REGISTER_WRITE,
        "severity": "warning",
        "requires_confirmation": False,
        "message": "Hardware register write - verify register semantics",
    },
    "interrupt_disable": {
        "patterns": [
            r"\b__disable_irq\s*\(",
            r"\b__asm__\s*\(\s*\"cpsid",
            r"\bNVIC_\w*DISABLE",
        ],
        "category": ActionCategory.INTERRUPT_CHANGE,
        "severity": "warning",
        "requires_confirmation": False,
        "message": "Interrupt disable - ensure re-enable and minimal duration",
    },
    "clock_change": {
        "patterns": [
            r"\bRCC_\w*PLL",
            r"\bHAL_RCC_OscConfig",
            r"\bHAL_RCC_ClockConfig",
            r"\bSystemClock_Config",
        ],
        "category": ActionCategory.CLOCK_CHANGE,
        "severity": "warning",
        "requires_confirmation": False,
        "message": "Clock configuration change - verify PLL and timing constraints",
    },
    "dma_config": {
        "patterns": [
            r"\bDMA_\w*Init",
            r"\bHAL_DMA_\w*Init",
            r"\bDMA_Start",
        ],
        "category": ActionCategory.DMA_CONFIG,
        "severity": "warning",
        "requires_confirmation": False,
        "message": "DMA configuration - verify stream/channel and transfer size",
    },
}


class SecurityValidator:
    """
    Security validation for firmware generation.
    
    Features:
    - Pre-patch vulnerability scanning
    - Dangerous action detection
    - Permission model for AI operations
    
    Usage:
        validator = SecurityValidator()
        
        # Scan code before execution
        result = validator.validate_firmware_patch(code_snippet)
        if not result.allowed:
            print(f"Blocked: {result.reason}")
    """

    def __init__(self):
        self.findings_history: List[SecurityFinding] = []
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Pre-compile regex patterns for performance."""
        for pattern_group in [DANGEROUS_PATTERNS, DANGEROUS_ACTIONS]:
            for pattern_data in pattern_group.values():
                if isinstance(pattern_data, dict) and "patterns" in pattern_data:
                    pattern_data["_compiled"] = [
                        re.compile(p, re.MULTILINE) for p in pattern_data["patterns"]
                    ]

    def validate_firmware_patch(
        self,
        code: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> SecurityValidationResult:
        """
        Validate a firmware code patch before execution.
        
        Args:
            code: The firmware code to validate
            context: Optional context (file path, function name, etc.)
        
        Returns:
            SecurityValidationResult with findings and allowed status
        """
        findings: List[SecurityFinding] = []

        # Check for vulnerability patterns
        findings.extend(self._scan_vulnerabilities(code, context))

        # Check for dangerous actions
        findings.extend(self._scan_dangerous_actions(code, context))

        # Determine overall result
        errors = sum(1 for f in findings if f.severity == "error")
        warnings = sum(1 for f in findings if f.severity == "warning")

        if errors > 0:
            level = SecurityLevel.BLOCKED if errors >= 3 else SecurityLevel.DANGEROUS
            reason = f"Found {errors} critical security issue(s)"
        elif warnings >= 5:
            level = SecurityLevel.CAUTION
            reason = f"Found {warnings} warning(s) - review recommended"
        else:
            level = SecurityLevel.SAFE
            reason = None

        # Block if too many critical errors
        allowed = level != SecurityLevel.BLOCKED

        result = SecurityValidationResult(
            allowed=allowed,
            level=level,
            findings=findings,
            reason=reason,
        )

        # Store in history
        self.findings_history.extend(findings)

        return result

    def _scan_vulnerabilities(
        self, code: str, context: Optional[Dict[str, Any]]
    ) -> List[SecurityFinding]:
        """Scan for vulnerability patterns."""
        findings: List[SecurityFinding] = []

        for rule_id, pattern_data in DANGEROUS_PATTERNS.items():
            compiled = pattern_data.get("_compiled", [])
            for pattern in compiled:
                matches = pattern.finditer(code)
                for match in matches:
                    findings.append(SecurityFinding(
                        severity=pattern_data["severity"],
                        category="vulnerability",
                        rule_id=rule_id,
                        message=pattern_data["message"],
                        cwe_id=pattern_data.get("cwe"),
                        remediation=pattern_data.get("remediation"),
                        location=self._extract_location(code, match.start()),
                    ))

        return findings

    def _scan_dangerous_actions(
        self, code: str, context: Optional[Dict[str, Any]]
    ) -> List[SecurityFinding]:
        """Scan for dangerous action patterns."""
        findings: List[SecurityFinding] = []

        for action_id, action_data in DANGEROUS_ACTIONS.items():
            compiled = action_data.get("_compiled", [])
            for pattern in compiled:
                matches = pattern.finditer(code)
                for match in matches:
                    findings.append(SecurityFinding(
                        severity=action_data["severity"],
                        category=action_data["category"].value,
                        rule_id=action_id,
                        message=action_data["message"],
                        location=self._extract_location(code, match.start()),
                    ))

        return findings

    def _extract_location(self, code: str, position: int) -> Optional[str]:
        """Extract line number from position."""
        lines = code[:position].split("\n")
        if lines:
            return f"line {len(lines)}"
        return None

    def check_permission(
        self,
        action: ActionCategory,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Check if an action is permitted.
        
        Args:
            action: The action category to check
            context: Optional context for permission decision
        
        Returns:
            True if action is permitted, False otherwise
        """
        # High-risk actions always require confirmation
        high_risk = {
            ActionCategory.FLASH_MODIFY,
            ActionCategory.MEMORY_WRITE,
        }

        if action in high_risk:
            # Check if confirmation was provided
            if context and context.get("confirmed"):
                return True
            return False

        # Medium-risk actions require caution level
        medium_risk = {
            ActionCategory.REGISTER_WRITE,
            ActionCategory.CLOCK_CHANGE,
        }

        if action in medium_risk:
            if context and context.get("verified"):
                return True
            return True  # Allow but warn

        # Low-risk actions are allowed
        return True

    def get_security_summary(self) -> Dict[str, Any]:
        """Get summary of all security findings."""
        if not self.findings_history:
            return {
                "total_findings": 0,
                "by_severity": {},
                "by_category": {},
                "recommendation": "No security issues detected",
            }

        by_severity: Dict[str, int] = {}
        by_category: Dict[str, int] = {}

        for finding in self.findings_history:
            by_severity[finding.severity] = by_severity.get(finding.severity, 0) + 1
            by_category[finding.category] = by_category.get(finding.category, 0) + 1

        errors = by_severity.get("error", 0)
        if errors >= 5:
            recommendation = "CRITICAL: Multiple security issues found - review required"
        elif errors >= 1:
            recommendation = "WARNING: Security issues detected - review before deployment"
        else:
            recommendation = "OK: Minor warnings only - proceed with caution"

        return {
            "total_findings": len(self.findings_history),
            "by_severity": by_severity,
            "by_category": by_category,
            "recommendation": recommendation,
        }


def validate_before_execution(code: str) -> SecurityValidationResult:
    """
    Convenience function for quick validation.
    
    Usage:
        result = validate_before_execution(code_snippet)
        if not result.allowed:
            raise SecurityError(result.reason)
    """
    validator = SecurityValidator()
    return validator.validate_firmware_patch(code)

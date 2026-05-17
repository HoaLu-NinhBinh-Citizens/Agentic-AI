"""Poison tool defense - Phase 5B v10.

Implements tool output sanitization and trust scoring:
- ToolOutputSanitizer: Sanitizes tool outputs
- TrustScoreManager: Tracks tool trust scores
- PoisonToolDefense: Full poison defense system
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Callable


class SanitizationAction(Enum):
    """Action to take on sanitization."""
    ALLOW = "allow"
    QUARANTINE = "quarantine"
    REJECT = "reject"


@dataclass
class SanitizationResult:
    """Result of sanitization."""
    action: SanitizationAction
    sanitized_output: Any
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class TrustScore:
    """Trust score for a tool."""
    tool_name: str
    score: float = 0.8
    success_count: int = 0
    failure_count: int = 0
    quarantine_until: Optional[int] = None
    last_success: Optional[int] = None
    last_failure: Optional[int] = None


class ToolOutputSanitizer:
    """Sanitizes tool outputs for safety.
    
    Checks:
    - Schema compliance
    - Size limits
    - Dangerous content patterns
    - Output type safety
    """
    
    def __init__(
        self,
        max_output_size: int = 1024 * 1024,  # 1MB
        dangerous_patterns: Optional[list[str]] = None,
    ):
        self._max_size = max_output_size
        self._patterns = dangerous_patterns or self._default_patterns()
    
    def _default_patterns(self) -> list[str]:
        """Default dangerous content patterns."""
        return [
            r"<script.*?>.*?</script>",
            r"javascript:",
            r"on\w+\s*=",
            r"eval\s*\(",
            r"__import__",
            r"subprocess",
            r"os\.system",
            r"exec\s*\(",
        ]
    
    def sanitize(
        self,
        output: Any,
        schema: Optional[dict] = None,
        tool_name: str = "unknown",
    ) -> SanitizationResult:
        """Sanitize tool output.
        
        Args:
            output: Tool output
            schema: Optional schema to validate against
            tool_name: Name of the tool
            
        Returns:
            Sanitization result
        """
        issues = []
        warnings = []
        action = SanitizationAction.ALLOW
        
        if output is None:
            return SanitizationResult(
                action=SanitizationAction.ALLOW,
                sanitized_output=None,
            )
        
        if isinstance(output, str):
            size_issues, output = self._check_size(output)
            issues.extend(size_issues)
            
            pattern_issues = self._check_patterns(output)
            issues.extend(pattern_issues)
        
        if isinstance(output, dict) and schema:
            schema_issues = self._check_schema(output, schema)
            issues.extend(schema_issues)
        
        if issues:
            action = SanitizationAction.QUARANTINE
        
        return SanitizationResult(
            action=action,
            sanitized_output=output,
            issues=issues,
            warnings=warnings,
        )
    
    def _check_size(self, output: str) -> tuple[list[str], str]:
        """Check output size."""
        issues = []
        
        size = len(output.encode('utf-8'))
        if size > self._max_size:
            issues.append(f"Output size {size} exceeds limit {self._max_size}")
            output = output[:self._max_size]
        
        return issues, output
    
    def _check_patterns(self, output: str) -> list[str]:
        """Check for dangerous patterns."""
        issues = []
        
        output_lower = output.lower()
        for pattern in self._patterns:
            if re.search(pattern, output_lower, re.IGNORECASE):
                issues.append(f"Dangerous pattern detected: {pattern}")
        
        return issues
    
    def _check_schema(self, output: dict, schema: dict) -> list[str]:
        """Check output against schema."""
        issues = []
        
        required = schema.get("required", [])
        for field_name in required:
            if field_name not in output:
                issues.append(f"Missing required field: {field_name}")
        
        return issues


class TrustScoreManager:
    """Manages trust scores for tools.
    
    Tracks success/failure history and calculates
    trust scores for poison detection.
    """
    
    def __init__(
        self,
        initial_score: float = 0.8,
        quarantine_threshold: float = 0.3,
        reject_threshold: float = 0.1,
        decay_rate: float = 0.01,
    ):
        self._scores: dict[str, TrustScore] = {}
        self._quarantine_threshold = quarantine_threshold
        self._reject_threshold = reject_threshold
        self._decay_rate = decay_rate
    
    def get_score(self, tool_name: str) -> TrustScore:
        """Get trust score for a tool."""
        if tool_name not in self._scores:
            self._scores[tool_name] = TrustScore(tool_name=tool_name)
        return self._scores[tool_name]
    
    def record_success(self, tool_name: str) -> None:
        """Record a successful execution."""
        score = self.get_score(tool_name)
        score.success_count += 1
        score.last_success = int(time.time())
        self._recalculate_score(score)
    
    def record_failure(self, tool_name: str, severity: str = "normal") -> None:
        """Record a failed execution.
        
        Args:
            tool_name: Tool name
            severity: Failure severity (normal, severe, critical)
        """
        score = self.get_score(tool_name)
        score.failure_count += 1
        score.last_failure = int(time.time())
        
        if severity == "critical":
            score.score = 0.0
        elif severity == "severe":
            score.score = max(0, score.score - 0.3)
        else:
            self._recalculate_score(score)
    
    def _recalculate_score(self, score: TrustScore) -> None:
        """Recalculate trust score from history."""
        total = score.success_count + score.failure_count
        
        if total == 0:
            return
        
        success_rate = score.success_count / total
        
        recency_factor = 1.0
        if score.last_failure:
            age = time.time() - score.last_failure
            recency_factor = max(0.5, 1.0 - (age / 86400) * self._decay_rate)
        
        score.score = success_rate * recency_factor
    
    def is_quarantined(self, tool_name: str) -> bool:
        """Check if a tool is quarantined."""
        score = self.get_score(tool_name)
        
        if score.quarantine_until:
            if time.time() < score.quarantine_until:
                return True
            score.quarantine_until = None
        
        return score.score < self._quarantine_threshold
    
    def is_rejected(self, tool_name: str) -> bool:
        """Check if a tool should be rejected."""
        score = self.get_score(tool_name)
        
        if score.score < self._reject_threshold:
            return True
        
        return False
    
    def quarantine(self, tool_name: str, duration_seconds: int = 300) -> None:
        """Quarantine a tool.
        
        Args:
            tool_name: Tool name
            duration_seconds: Duration of quarantine
        """
        score = self.get_score(tool_name)
        score.quarantine_until = int(time.time()) + duration_seconds
    
    def remove_quarantine(self, tool_name: str) -> None:
        """Remove quarantine from a tool."""
        score = self.get_score(tool_name)
        score.quarantine_until = None
    
    def reset_score(self, tool_name: str) -> None:
        """Reset trust score for a tool."""
        self._scores[tool_name] = TrustScore(tool_name=tool_name)


class PoisonToolDefense:
    """Full poison tool defense system.
    
    Combines sanitization and trust scoring to detect
    and handle poisoned tool outputs.
    """
    
    def __init__(
        self,
        sanitizer: Optional[ToolOutputSanitizer] = None,
        trust_manager: Optional[TrustScoreManager] = None,
    ):
        self._sanitizer = sanitizer or ToolOutputSanitizer()
        self._trust_manager = trust_manager or TrustScoreManager()
    
    async def process_output(
        self,
        tool_name: str,
        output: Any,
        schema: Optional[dict] = None,
    ) -> tuple[bool, Any, list[str]]:
        """Process tool output through defense system.
        
        Args:
            tool_name: Name of the tool
            output: Tool output
            schema: Optional schema to validate
            
        Returns:
            Tuple of (allowed, sanitized_output, issues)
        """
        if self._trust_manager.is_rejected(tool_name):
            self._trust_manager.record_failure(tool_name, "critical")
            return False, None, [f"Tool {tool_name} is rejected due to low trust score"]
        
        if self._trust_manager.is_quarantined(tool_name):
            return False, None, [f"Tool {tool_name} is currently quarantined"]
        
        sanitized = self._sanitizer.sanitize(output, schema, tool_name)
        
        if sanitized.action == SanitizationAction.REJECT:
            self._trust_manager.record_failure(tool_name, "severe")
            return False, None, sanitized.issues
        
        if sanitized.action == SanitizationAction.QUARANTINE:
            self._trust_manager.record_failure(tool_name, "normal")
            self._trust_manager.quarantine(tool_name, 300)
            return False, sanitized.sanitized_output, sanitized.issues
        
        self._trust_manager.record_success(tool_name)
        
        return True, sanitized.sanitized_output, sanitized.warnings
    
    def get_trust_score(self, tool_name: str) -> float:
        """Get trust score for a tool."""
        return self._trust_manager.get_score(tool_name).score
    
    def is_allowed(self, tool_name: str) -> bool:
        """Check if a tool is allowed."""
        if self._trust_manager.is_rejected(tool_name):
            return False
        if self._trust_manager.is_quarantined(tool_name):
            return False
        return True

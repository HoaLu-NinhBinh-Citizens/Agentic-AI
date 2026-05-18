"""
Safe Prompt Injection Explainer with Redacted Reasoning.

Features:
- Safe explanation abstraction (no pattern leakage)
- Redacted reasoning (hides detector logic)
- Multi-level explanation severity
- Audit-safe detection feedback
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ExplanationLevel(str, Enum):
    """Levels of explanation detail."""
    NONE = "none"           # Just detected/not detected
    SAFE = "safe"          # Generic reason, no patterns
    AUDIT = "audit"        # Detailed for compliance, internal only
    DEBUG = "debug"        # Full details, never expose to user


@dataclass
class SafeExplanation:
    """Safe explanation that doesn't leak detector logic."""
    detected: bool
    level: ExplanationLevel
    risk_score: float  # 0-1, redacted score
    reason_code: str  # Abstracted reason code
    action_taken: str  # What was done
    audit_id: str  # For internal reference
    
    # Safe message for user (never exposes patterns)
    user_message: str
    
    # Internal details (only for audit)
    internal_details: Optional[Dict[str, Any]] = None


class SafeInjectionExplainer:
    """
    Prompt injection detection with safe explanation.
    
    Key principle: NEVER expose matched patterns to users.
    This prevents attackers from reverse-engineering the detector.
    
    Explanation levels:
    - NONE: Just pass/fail
    - SAFE: Generic reason, no patterns
    - AUDIT: Detailed for compliance, internal only
    - DEBUG: Full details, never expose to users
    """
    
    # Internal pattern categories (for audit only)
    _PATTERN_CATEGORIES = {
        "instruction_override": [
            r"ignore\s+(previous|all|prior)",
            r"(disregard|dismiss|forget)\s+",
        ],
        "role_manipulation": [
            r"(system|admin|developer)\s*:",
            r"developer\s+mode",
        ],
        "prompt_extraction": [
            r"(reveal|show)\s+.*prompt",
            r"(what|show).*instructions",
        ],
        "encoding_tricks": [
            r"(base64|utf-?8)\s*:",
            r"\\u[0-9a-f]{4}",
        ],
        "delimiter_abuse": [
            r"\[INST\]",
            r"{{",
            r"<\|",
        ],
    }
    
    # Abstracted reason codes (safe to expose)
    REASON_CODES = {
        "CONTENT_SUSPICIOUS": "Content appears unusual",
        "PATTERN_MATCHED": "Unusual patterns detected",
        "STRUCTURE_SUSPICIOUS": "Unusual structure detected",
        "ENCODING_DETECTED": "Encoded content detected",
        "MANIPULATION_ATTEMPT": "Possible manipulation pattern",
    }
    
    # Safe user messages
    USER_MESSAGES = {
        "blocked": "This request has been flagged for safety review.",
        "warning": "This request has unusual characteristics.",
        "allowed": "Request processed normally.",
    }
    
    def __init__(
        self,
        default_level: ExplanationLevel = ExplanationLevel.SAFE,
        enable_audit: bool = True,
    ):
        self.default_level = default_level
        self.enable_audit = enable_audit
        
        # Detection counters
        self._detection_counts: Dict[str, int] = {}
        
        # Audit log
        self._audit_log: List[Dict[str, Any]] = []
    
    async def detect_with_safe_explanation(
        self,
        prompt: str,
        level: ExplanationLevel = None,
        user_id: Optional[str] = None,
    ) -> SafeExplanation:
        """
        Detect injection with safe explanation.
        
        Never exposes matched patterns to users.
        """
        level = level or self.default_level
        
        # Run detection
        detection_result = await self._detect(prompt)
        
        # Generate safe explanation
        explanation = self._generate_safe_explanation(
            detection_result,
            level,
            prompt,
        )
        
        # Log for audit (internal only)
        if self.enable_audit:
            await self._log_detection(explanation, prompt, user_id)
        
        return explanation
    
    async def _detect(self, prompt: str) -> Dict[str, Any]:
        """Run detection algorithms."""
        results = {
            "score": 0.0,
            "categories": [],
            "matched_rules": [],
        }
        
        prompt_lower = prompt.lower()
        
        # Check each category
        for category, patterns in self._PATTERN_CATEGORIES.items():
            for pattern in patterns:
                if re.search(pattern, prompt, re.IGNORECASE):
                    results["categories"].append(category)
                    results["matched_rules"].append(f"{category}_rule")
                    results["score"] += 0.2
        
        # Normalize score
        results["score"] = min(1.0, results["score"])
        
        return results
    
    def _generate_safe_explanation(
        self,
        detection_result: Dict[str, Any],
        level: ExplanationLevel,
        prompt: str,
    ) -> SafeExplanation:
        """Generate safe explanation based on level."""
        detected = detection_result["score"] >= 0.5
        score = detection_result["score"]
        categories = detection_result["categories"]
        
        # Generate reason code
        reason_code = self._get_reason_code(categories, score)
        
        # Generate user message
        if detected:
            if score >= 0.8:
                user_message = self.USER_MESSAGES["blocked"]
                action = "blocked"
            elif score >= 0.5:
                user_message = self.USER_MESSAGES["warning"]
                action = "warning"
            else:
                user_message = self.USER_MESSAGES["allowed"]
                action = "allowed"
        else:
            user_message = self.USER_MESSAGES["allowed"]
            action = "allowed"
        
        # Generate audit ID
        import uuid
        audit_id = str(uuid.uuid4())[:8]
        
        # Internal details (only for AUDIT/DEBUG)
        internal_details = None
        if level in [ExplanationLevel.AUDIT, ExplanationLevel.DEBUG]:
            internal_details = {
                "raw_score": score,
                "categories_detected": categories,
                "match_count": len(categories),
                "prompt_length": len(prompt),
            }
        
        # Redact score for user exposure
        redacted_score = self._redact_score(score)
        
        return SafeExplanation(
            detected=detected,
            level=level,
            risk_score=redacted_score,
            reason_code=reason_code,
            action_taken=action,
            audit_id=audit_id,
            user_message=user_message,
            internal_details=internal_details,
        )
    
    def _get_reason_code(
        self,
        categories: List[str],
        score: float,
    ) -> str:
        """Get abstracted reason code."""
        if not categories:
            return "CONTENT_SUSPICIOUS"
        
        # Map categories to reason codes
        category_map = {
            "instruction_override": "PATTERN_MATCHED",
            "role_manipulation": "MANIPULATION_ATTEMPT",
            "prompt_extraction": "PATTERN_MATCHED",
            "encoding_tricks": "ENCODING_DETECTED",
            "delimiter_abuse": "STRUCTURE_SUSPICIOUS",
        }
        
        # Return most severe reason
        for category in categories:
            if category in category_map:
                return category_map[category]
        
        return "CONTENT_SUSPICIOUS"
    
    def _redact_score(self, score: float) -> float:
        """Redact score to prevent pattern inference."""
        # Round to nearest 0.1
        return round(score * 10) / 10
    
    async def _log_detection(
        self,
        explanation: SafeExplanation,
        prompt: str,
        user_id: Optional[str],
    ) -> None:
        """Log detection for audit (internal only)."""
        import hashlib
        
        entry = {
            "audit_id": explanation.audit_id,
            "timestamp": asyncio.get_event_loop().time(),
            "detected": explanation.detected,
            "risk_score": explanation.risk_score,
            "reason_code": explanation.reason_code,
            "action_taken": explanation.action_taken,
            "user_id": user_id,
            "level": explanation.level.value,
            # Hash of prompt (don't store actual prompt)
            "prompt_hash": hashlib.sha256(prompt.encode()).hexdigest()[:16],
        }
        
        self._audit_log.append(entry)
        
        # Update counters
        reason_code = explanation.reason_code
        self._detection_counts[reason_code] = self._detection_counts.get(reason_code, 0) + 1
    
    async def get_audit_log(
        self,
        limit: int = 100,
        reason_code: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get audit log (internal use only)."""
        entries = self._audit_log[-limit:]
        
        if reason_code:
            entries = [e for e in entries if e["reason_code"] == reason_code]
        
        return entries
    
    async def get_detection_stats(self) -> Dict[str, Any]:
        """Get detection statistics."""
        total = len(self._audit_log)
        detected = sum(1 for e in self._audit_log if e["detected"])
        
        return {
            "total_checked": total,
            "total_detected": detected,
            "detection_rate": detected / total if total > 0 else 0.0,
            "by_reason_code": self._detection_counts.copy(),
        }
    
    async def check_for_audit(
        self,
        audit_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Get details for audit ID (compliance use)."""
        for entry in self._audit_log:
            if entry["audit_id"] == audit_id:
                return entry
        return None


class AuditOnlyExplainer:
    """
    Audit-only explainer for compliance scenarios.
    
    Always returns minimal info, stores details internally.
    """
    
    def __init__(self):
        self._internal_detector = SafeInjectionExplainer(
            default_level=ExplanationLevel.NONE,
            enable_audit=True,
        )
    
    async def detect(
        self,
        prompt: str,
        user_id: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Detect without explanation (audit only)."""
        result = await self._internal_detector.detect_with_safe_explanation(
            prompt,
            level=ExplanationLevel.NONE,
            user_id=user_id,
        )
        
        return result.detected, result.audit_id
    
    async def get_audit_details(
        self,
        audit_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Get full audit details by ID."""
        return await self._internal_detector.check_for_audit(audit_id)

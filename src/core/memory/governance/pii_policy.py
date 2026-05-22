"""PII detection and redaction for memory governance.

Prevents PII (Personally Identifiable Information) from being stored
in long-term memory by detecting and redacting before storage.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class PIIType(str, Enum):
    """Types of PII that can be detected."""

    EMAIL = "email"
    PHONE = "phone"
    SSN = "ssn"
    CREDIT_CARD = "credit_card"
    IP_ADDRESS = "ip_address"
    NAME = "name"
    ADDRESS = "address"
    DATE_OF_BIRTH = "dob"
    PASSWORD = "password"
    API_KEY = "api_key"
    CUSTOM = "custom"


@dataclass
class PIIMatch:
    """Represents a detected PII match."""

    pii_type: PIIType
    start: int
    end: int
    value: str
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "pii_type": self.pii_type.value,
            "start": self.start,
            "end": self.end,
            "value": self.value,
            "confidence": self.confidence,
        }


@dataclass
class PIIPolicy:
    """Policy configuration for PII handling."""

    enabled: bool = True
    redact_before_storage: bool = True
    redact_before_retrieval: bool = False
    allowed_pii_types: list[PIIType] = field(
        default_factory=lambda: [
            PIIType.EMAIL,
            PIIType.PHONE,
            PIIType.SSN,
            PIIType.CREDIT_CARD,
            PIIType.IP_ADDRESS,
            PIIType.PASSWORD,
            PIIType.API_KEY,
        ]
    )
    custom_patterns: dict[str, str] = field(default_factory=dict)
    replacement: str = "[REDACTED]"

    def should_redact(self, pii_type: PIIType) -> bool:
        """Check if PII type should be redacted."""
        return pii_type in self.allowed_pii_types


class PIIDetector:
    """Detects PII in text using regex patterns."""

    PATTERNS: dict[PIIType, str] = {
        PIIType.EMAIL: r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        PIIType.PHONE: r"\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b",
        PIIType.SSN: r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b",
        PIIType.CREDIT_CARD: r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
        PIIType.IP_ADDRESS: r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        PIIType.PASSWORD: r"(?:password|pwd|passwd)[=:\s]+\S+",
        PIIType.API_KEY: r"(?:api[_-]?key|apikey|secret)[=:\s]+['\"]?[A-Za-z0-9_-]{16,}['\"]?",
    }

    def __init__(self, policy: PIIPolicy | None = None) -> None:
        """Initialize the PII detector.

        Args:
            policy: PII policy configuration.
        """
        self._policy = policy or PIIPolicy()
        self._compiled_patterns: dict[PIIType, re.Pattern] = {}

        for pii_type, pattern in self.PATTERNS.items():
            self._compiled_patterns[pii_type] = re.compile(pattern, re.IGNORECASE)

        for name, pattern in self._policy.custom_patterns.items():
            self._compiled_patterns[PIIType.CUSTOM] = re.compile(pattern)

    def detect(self, text: str) -> list[PIIMatch]:
        """Detect PII in text.

        Args:
            text: Text to scan for PII.

        Returns:
            List of detected PII matches.
        """
        if not self._policy.enabled:
            return []

        matches: list[PIIMatch] = []

        for pii_type, pattern in self._compiled_patterns.items():
            if pii_type == PIIType.CUSTOM:
                continue

            if not self._policy.should_redact(pii_type):
                continue

            for match in pattern.finditer(text):
                matches.append(
                    PIIMatch(
                        pii_type=pii_type,
                        start=match.start(),
                        end=match.end(),
                        value=match.group(),
                        confidence=1.0,
                    )
                )

        for name, pattern in self._policy.custom_patterns.items():
            pii_type = PIIType.CUSTOM
            if not self._policy.should_redact(pii_type):
                continue

            for match in pattern.finditer(text):
                matches.append(
                    PIIMatch(
                        pii_type=pii_type,
                        start=match.start(),
                        end=match.end(),
                        value=match.group(),
                        confidence=1.0,
                    )
                )

        matches.sort(key=lambda m: m.start)
        return matches

    def has_pii(self, text: str) -> bool:
        """Check if text contains PII.

        Args:
            text: Text to check.

        Returns:
            True if PII detected.
        """
        return len(self.detect(text)) > 0

    def get_pii_types(self, text: str) -> list[PIIType]:
        """Get types of PII in text.

        Args:
            text: Text to analyze.

        Returns:
            List of PII types found.
        """
        matches = self.detect(text)
        return list(set(m.pi_type for m in matches))


class PIIRedactor:
    """Redacts PII from text."""

    def __init__(self, policy: PIIPolicy | None = None) -> None:
        """Initialize the PII redactor.

        Args:
            policy: PII policy configuration.
        """
        self._policy = policy or PIIPolicy()
        self._detector = PIIDetector(self._policy)

    def redact(self, text: str) -> tuple[str, list[PIIMatch]]:
        """Redact PII from text.

        Args:
            text: Text to redact.

        Returns:
            Tuple of (redacted_text, list_of_detected_matches).
        """
        matches = self._detector.detect(text)

        if not matches:
            return text, []

        result = text
        offset = 0

        for match in matches:
            if not self._policy.should_redact(match.pii_type):
                continue

            start = match.start + offset
            end = match.end + offset

            result = result[:start] + self._policy.replacement + result[end:]
            offset += len(self._policy.replacement) - (match.end - match.start)

        return result, matches

    def get_stats(self) -> dict[str, Any]:
        """Get redaction statistics.

        Returns:
            Statistics dictionary.
        """
        return {
            "enabled": self._policy.enabled,
            "redact_before_storage": self._policy.redact_before_storage,
            "allowed_pii_types": [p.value for p in self._policy.allowed_pii_types],
            "replacement": self._policy.replacement,
        }

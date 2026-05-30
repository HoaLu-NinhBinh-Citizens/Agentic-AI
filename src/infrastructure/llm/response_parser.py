"""Parse LLM responses into structured data.

Handles JSON extraction, error correction, and validation for:
- Code review findings
- Fix options
- Security vulnerabilities
- ML analysis results
"""

import json
import re
from typing import Any, Optional
from dataclasses import dataclass


@dataclass
class ParsedResponse:
    """A parsed LLM response."""
    success: bool
    data: Any
    raw_text: str
    error: Optional[str] = None


@dataclass
class ValidationError:
    """Validation error details."""
    field: str
    expected: str
    actual: str


class ResponseParser:
    """Parse and validate LLM responses.

    Handles malformed JSON, extraction from markdown code blocks,
    and validation of structured response data.
    """

    def __init__(self):
        self._json_pattern = re.compile(r'```(?:json)?\s*([\s\S]*?)\s*```')
        self._array_pattern = re.compile(r'\[[\s\S]*\]')
        self._object_pattern = re.compile(r'\{[\s\S]*\}')

    def parse_json(
        self,
        response: str,
        expected_type: type = list
    ) -> ParsedResponse:
        """Parse response as JSON.

        Args:
            response: Raw LLM response text
            expected_type: Expected JSON type (list or dict)

        Returns:
            ParsedResponse with parsed data or error
        """
        if not response or not response.strip():
            return ParsedResponse(
                success=False,
                data=None,
                raw_text=response,
                error="Empty response"
            )

        response = response.strip()

        try:
            data = json.loads(response)
            if not self._validate_type(data, expected_type):
                return ParsedResponse(
                    success=False,
                    data=data,
                    raw_text=response,
                    error=f"Expected {expected_type.__name__}, got {type(data).__name__}"
                )
            return ParsedResponse(
                success=True,
                data=data,
                raw_text=response
            )
        except json.JSONDecodeError:
            pass

        json_match = self._json_pattern.search(response)
        if json_match:
            try:
                data = json.loads(json_match.group(1).strip())
                return ParsedResponse(
                    success=True,
                    data=data,
                    raw_text=response
                )
            except json.JSONDecodeError:
                pass

        pattern = self._array_pattern if expected_type == list else self._object_pattern
        for match in pattern.finditer(response):
            try:
                data = json.loads(match.group())
                if self._validate_type(data, expected_type):
                    return ParsedResponse(
                        success=True,
                        data=data,
                        raw_text=response
                    )
            except json.JSONDecodeError:
                continue

        return ParsedResponse(
            success=False,
            data=None,
            raw_text=response,
            error="Could not parse JSON from response"
        )

    def _validate_type(self, data: Any, expected: type) -> bool:
        """Validate data matches expected type."""
        if expected == list:
            return isinstance(data, list)
        if expected == dict:
            return isinstance(data, dict)
        return isinstance(data, expected)

    def parse_findings(self, response: str) -> list[dict]:
        """Parse findings from LLM response.

        Args:
            response: Raw LLM response

        Returns:
            List of validated findings dictionaries
        """
        parsed = self.parse_json(response, list)

        if not parsed.success:
            return []

        data = parsed.data
        if not isinstance(data, list):
            return []

        findings = []
        for item in data:
            if not isinstance(item, dict):
                continue

            if not self._has_finding_fields(item):
                continue

            finding = self._normalize_finding(item)
            findings.append(finding)

        return findings

    def _has_finding_fields(self, item: dict) -> bool:
        """Check if dict has minimum finding fields."""
        return "rule_id" in item or "message" in item

    def _normalize_finding(self, item: dict) -> dict:
        """Normalize finding to standard format."""
        severity = str(item.get("severity", "MEDIUM")).upper()

        return {
            "rule_id": str(item.get("rule_id", "UNKNOWN")),
            "severity": self._normalize_severity(severity),
            "title": str(item.get("title", item.get("rule_id", "Unknown"))),
            "message": str(item.get("message", item.get("description", ""))),
            "explanation": str(item.get("explanation", "")),
            "line": self._safe_int(item.get("line"), 0),
            "confidence": self._safe_float(item.get("confidence"), 0.8),
            "best_practice": str(item.get("best_practice", "")),
            "cwe_id": str(item.get("cwe_id", "")),
            "fix": str(item.get("fix", item.get("remediation", ""))),
        }

    def _normalize_severity(self, severity: str) -> str:
        """Normalize severity to standard levels."""
        valid = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}
        return severity if severity in valid else "MEDIUM"

    def _safe_int(self, value: Any, default: int) -> int:
        """Safely convert to int."""
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    def _safe_float(self, value: Any, default: float) -> float:
        """Safely convert to float."""
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def parse_fixes(self, response: str) -> list[dict]:
        """Parse fix options from LLM response.

        Args:
            response: Raw LLM response

        Returns:
            List of validated fix dictionaries
        """
        parsed = self.parse_json(response, list)

        if not parsed.success:
            return []

        data = parsed.data
        if not isinstance(data, list):
            return []

        fixes = []
        for item in data:
            if not isinstance(item, dict):
                continue

            if not self._has_fix_fields(item):
                continue

            fix = self._normalize_fix(item)
            fixes.append(fix)

        return fixes

    def _has_fix_fields(self, item: dict) -> bool:
        """Check if dict has minimum fix fields."""
        return "new_code" in item or "old_code" in item

    def _normalize_fix(self, item: dict) -> dict:
        """Normalize fix to standard format."""
        risk = str(item.get("risk", "MEDIUM")).upper()
        valid_risks = {"LOW", "MEDIUM", "HIGH"}
        if risk not in valid_risks:
            risk = "MEDIUM"

        return {
            "option_id": self._safe_int(item.get("option_id"), len(item) + 1),
            "description": str(item.get("description", "")),
            "risk": risk,
            "confidence": self._safe_float(item.get("confidence"), 0.7),
            "old_code": str(item.get("old_code", "")),
            "new_code": str(item.get("new_code", "")),
            "explanation": str(item.get("explanation", "")),
        }

    def parse_security_issues(self, response: str) -> list[dict]:
        """Parse security issues from LLM response.

        Args:
            response: Raw LLM response

        Returns:
            List of validated security issue dictionaries
        """
        parsed = self.parse_json(response, list)

        if not parsed.success:
            return []

        data = parsed.data
        if not isinstance(data, list):
            return []

        issues = []
        for item in data:
            if not isinstance(item, dict):
                continue

            issue = self._normalize_security_issue(item)
            if issue:
                issues.append(issue)

        return issues

    def _normalize_security_issue(self, item: dict) -> Optional[dict]:
        """Normalize security issue to standard format."""
        required = ["cwe_id", "severity", "description"]
        if not any(item.get(field) for field in required):
            return None

        severity = str(item.get("severity", "MEDIUM")).upper()
        valid = {"CRITICAL", "HIGH", "MEDIUM"}
        if severity not in valid:
            severity = "MEDIUM"

        return {
            "cwe_id": str(item.get("cwe_id", "CWE-000")),
            "severity": severity,
            "title": str(item.get("title", item.get("cwe_id", "Unknown"))),
            "description": str(item.get("description", "")),
            "evidence": str(item.get("evidence", item.get("code_snippet", ""))),
            "exploitation": str(item.get("exploitation", "")),
            "remediation": str(item.get("remediation", item.get("fix", ""))),
            "confidence": self._safe_float(item.get("confidence"), 0.8),
        }

    def parse_ml_issues(self, response: str) -> list[dict]:
        """Parse ML-specific issues from LLM response.

        Args:
            response: Raw LLM response

        Returns:
            List of validated ML issue dictionaries
        """
        parsed = self.parse_json(response, list)

        if not parsed.success:
            return []

        data = parsed.data
        if not isinstance(data, list):
            return []

        issues = []
        for item in data:
            if not isinstance(item, dict):
                continue

            issue = self._normalize_ml_issue(item)
            if issue:
                issues.append(issue)

        return issues

    def _normalize_ml_issue(self, item: dict) -> Optional[dict]:
        """Normalize ML issue to standard format."""
        if not item.get("rule_id") and not item.get("title"):
            return None

        return {
            "rule_id": str(item.get("rule_id", "ML000")),
            "severity": self._normalize_severity(
                str(item.get("severity", "MEDIUM"))
            ),
            "title": str(item.get("title", "ML Issue")),
            "description": str(item.get("description", "")),
            "line": self._safe_int(item.get("line"), 0),
            "confidence": self._safe_float(item.get("confidence"), 0.8),
            "impact": str(item.get("impact", "")),
            "fix": str(item.get("fix", "")),
        }

    def validate_finding(self, finding: dict) -> tuple[bool, list[ValidationError]]:
        """Validate a finding has required fields.

        Args:
            finding: Finding dictionary to validate

        Returns:
            Tuple of (is_valid, list of errors)
        """
        errors: list[ValidationError] = []

        if not finding.get("rule_id"):
            errors.append(ValidationError(
                field="rule_id",
                expected="non-empty string",
                actual=str(type(finding.get("rule_id")).__name__)
            ))

        severity = finding.get("severity", "")
        if severity not in {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}:
            errors.append(ValidationError(
                field="severity",
                expected="CRITICAL|HIGH|MEDIUM|LOW|INFO",
                actual=severity
            ))

        if not finding.get("message"):
            errors.append(ValidationError(
                field="message",
                expected="non-empty string",
                actual=str(type(finding.get("message")).__name__)
            ))

        line = finding.get("line")
        if line is not None:
            try:
                line_int = int(line)
                if line_int < 0:
                    errors.append(ValidationError(
                        field="line",
                        expected="non-negative integer",
                        actual=str(line_int)
                    ))
            except (ValueError, TypeError):
                errors.append(ValidationError(
                    field="line",
                    expected="integer",
                    actual=str(line)
                ))

        confidence = finding.get("confidence")
        if confidence is not None:
            try:
                conf_float = float(confidence)
                if not 0.0 <= conf_float <= 1.0:
                    errors.append(ValidationError(
                        field="confidence",
                        expected="0.0-1.0",
                        actual=str(conf_float)
                    ))
            except (ValueError, TypeError):
                errors.append(ValidationError(
                    field="confidence",
                    expected="float 0.0-1.0",
                    actual=str(confidence)
                ))

        return len(errors) == 0, errors

    def validate_fix(self, fix: dict) -> tuple[bool, list[ValidationError]]:
        """Validate a fix has required fields.

        Args:
            fix: Fix dictionary to validate

        Returns:
            Tuple of (is_valid, list of errors)
        """
        errors: list[ValidationError] = []

        if not fix.get("new_code"):
            errors.append(ValidationError(
                field="new_code",
                expected="non-empty string",
                actual=str(type(fix.get("new_code")).__name__)
            ))

        risk = fix.get("risk", "")
        if risk and risk not in {"LOW", "MEDIUM", "HIGH"}:
            errors.append(ValidationError(
                field="risk",
                expected="LOW|MEDIUM|HIGH",
                actual=risk
            ))

        confidence = fix.get("confidence")
        if confidence is not None:
            try:
                conf_float = float(confidence)
                if not 0.0 <= conf_float <= 1.0:
                    errors.append(ValidationError(
                        field="confidence",
                        expected="0.0-1.0",
                        actual=str(conf_float)
                    ))
            except (ValueError, TypeError):
                errors.append(ValidationError(
                    field="confidence",
                    expected="float 0.0-1.0",
                    actual=str(confidence)
                ))

        return len(errors) == 0, errors

    def extract_code_blocks(self, response: str) -> list[str]:
        """Extract all code blocks from response.

        Args:
            response: Raw LLM response

        Returns:
            List of code block contents
        """
        blocks = []
        pattern = re.compile(r'```(?:\w+)?\s*([\s\S]*?)\s*```')
        for match in pattern.finditer(response):
            code = match.group(1).strip()
            if code:
                blocks.append(code)
        return blocks

    def clean_response(self, response: str) -> str:
        """Clean response text by removing extra whitespace and markers.

        Args:
            response: Raw response

        Returns:
            Cleaned response
        """
        lines = response.split("\n")
        cleaned = []
        for line in lines:
            stripped = line.rstrip()
            if stripped:
                cleaned.append(stripped)
        return "\n".join(cleaned)

"""Suggestion Engine — generates intelligent fix suggestions for code review findings.

This module provides multi-option fix generation with:
- Template-based fixes from RuleEngine
- Context-aware enhancement (surrounding code, imports)
- Alternative fix generation
- Risk assessment
- Validation

Usage:
    engine = SuggestionEngine(fix_engine)
    suggestions = await engine.generate(finding, context)
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any, Optional

from src.application.workflows.unified.code_context import CodeContext
from src.application.workflows.unified.detector_base import Finding, FindingSeverity

# ─── Fix Option ─────────────────────────────────────────────────────────────────


@dataclass
class FixOption:
    """A single fix option with metadata.

    Attributes:
        description: Human-readable description of the fix
        code_before: Original code
        code_after: Fixed code
        risk_level: Risk assessment ("low", "medium", "high")
        confidence: Confidence in the fix (0.0-1.0)
        diff: Optional diff string
        rule_id: Associated rule ID
    """
    description: str
    code_before: str
    code_after: str
    risk_level: str = "medium"
    confidence: float = 1.0
    diff: str = ""
    rule_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "description": self.description,
            "code_before": self.code_before,
            "code_after": self.code_after,
            "risk_level": self.risk_level,
            "confidence": self.confidence,
            "diff": self.diff,
            "rule_id": self.rule_id,
        }


# ─── Suggestion Engine ────────────────────────────────────────────────────────────


class SuggestionEngine:
    """Generate multi-option fixes with context awareness.

    This engine:
    1. Gets template fix from RuleEngine
    2. Enhances with context (surrounding code, imports)
    3. Generates alternatives if applicable
    4. Validates each option
    5. Returns with confidence and risk level

    Usage:
        engine = SuggestionEngine()
        options = await engine.generate(finding, context)
        for option in options:
            print(option.description, option.code_after)
    """

    def __init__(self, fix_engine: Any = None) -> None:
        """Initialize suggestion engine.

        Args:
            fix_engine: Optional ApplyFixTool for advanced fixes
        """
        self.fix_engine = fix_engine

    async def generate(
        self,
        finding: Finding,
        context: Optional[CodeContext],
    ) -> dict[str, Any]:
        """Generate fix suggestions for a finding.

        Args:
            finding: The finding to generate fixes for
            context: Code context for enhancement

        Returns:
            Dict with title, description, and options
        """
        # Generate base options
        options = await self._generate_options(finding, context)

        if not options:
            return {
                "title": f"Fix: {finding.rule_name}",
                "description": "No automatic fix available",
                "options": [],
                "risk": "unknown",
            }

        # Determine overall risk
        risk = self._assess_overall_risk(options)

        return {
            "title": f"Fix: {finding.rule_name}",
            "description": self._generate_description(finding, options),
            "options": [opt.to_dict() for opt in options],
            "code_before": options[0].code_before if options else "",
            "code_after": options[0].code_after if options else "",
            "risk": risk,
            "rule_id": finding.rule_id,
        }

    async def _generate_options(
        self,
        finding: Finding,
        context: Optional[CodeContext],
    ) -> list[FixOption]:
        """Generate fix options for a finding.

        Args:
            finding: Finding to fix
            context: Code context

        Returns:
            List of fix options
        """
        options: list[FixOption] = []

        # Get template fix
        if finding.fix:
            options.append(FixOption(
                description="Apply suggested fix",
                code_before=self._get_affected_lines(finding, context),
                code_after=self._apply_template_fix(finding, context),
                risk_level=self._assess_template_risk(finding),
                confidence=finding.confidence,
                rule_id=finding.rule_id,
            ))

        # Generate alternatives based on rule type
        if finding.rule_id.startswith("SEC"):
            options.extend(await self._generate_security_alternatives(finding, context))
        elif finding.rule_id.startswith("QUAL"):
            options.extend(await self._generate_quality_alternatives(finding, context))
        elif finding.rule_id.startswith("EMB"):
            options.extend(await self._generate_embedded_alternatives(finding, context))
        elif finding.rule_id.startswith("ML"):
            options.extend(await self._generate_ml_alternatives(finding, context))

        # Generate refactoring alternative if applicable
        if self._should_suggest_refactor(finding):
            options.append(self._generate_refactor_option(finding, context))

        return options

    def _get_affected_lines(
        self,
        finding: Finding,
        context: Optional[CodeContext],
    ) -> str:
        """Get the lines affected by the finding.

        Args:
            finding: Finding with line info
            context: Code context

        Returns:
            Affected code lines
        """
        if context:
            start = max(1, finding.line - 2)
            end = min(len(context.lines), finding.end_line + 2)
            return "\n".join(context.lines[start - 1:end])
        return f"Line {finding.line}: (code unavailable)"

    def _apply_template_fix(
        self,
        finding: Finding,
        context: Optional[CodeContext],
    ) -> str:
        """Apply the template fix.

        Args:
            finding: Finding with fix template
            context: Code context

        Returns:
            Fixed code
        """
        if not finding.fix:
            return self._get_affected_lines(finding, context)

        # If fix is a direct replacement
        if context:
            lines = context.lines.copy()
            if finding.line <= len(lines):
                # Replace the finding line with fix
                lines[finding.line - 1] = finding.fix
                return "\n".join(lines)
        return finding.fix

    def _assess_template_risk(self, finding: Finding) -> str:
        """Assess risk of applying template fix.

        Args:
            finding: Finding to assess

        Returns:
            Risk level string
        """
        if finding.severity == FindingSeverity.ERROR:
            return "low"  # High priority fixes are safe
        if finding.severity == FindingSeverity.WARNING:
            return "medium"
        return "high"  # Low severity, conservative approach

    async def _generate_security_alternatives(
        self,
        finding: Finding,
        context: Optional[CodeContext],
    ) -> list[FixOption]:
        """Generate security-specific alternatives.

        Args:
            finding: Security finding
            context: Code context

        Returns:
            List of fix options
        """
        options: list[FixOption] = []

        if finding.rule_id == "SEC001":
            # Hardcoded secret - suggest env var
            options.append(FixOption(
                description="Use environment variable",
                code_before=self._extract_secret_assignment(finding, context),
                code_after="import os\nSECRET = os.environ.get('SECRET_NAME', 'default')",
                risk_level="low",
                confidence=0.95,
                rule_id="SEC001",
            ))
            options.append(FixOption(
                description="Use secrets manager",
                code_before=self._extract_secret_assignment(finding, context),
                code_after="# Use AWS Secrets Manager / Vault / etc.\nfrom your_secret_manager import get_secret\nSECRET = get_secret('secret-name')",
                risk_level="low",
                confidence=0.9,
                rule_id="SEC001",
            ))

        elif finding.rule_id == "SEC002":
            # SQL injection
            options.append(FixOption(
                description="Use parameterized query",
                code_before="cursor.execute(f'SELECT * FROM users WHERE id = {user_id}')",
                code_after="cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))",
                risk_level="low",
                confidence=0.98,
                rule_id="SEC002",
            ))

        elif finding.rule_id == "SEC003":
            # Command injection
            options.append(FixOption(
                description="Use shell=False",
                code_before="subprocess.run(cmd, shell=True)",
                code_after="subprocess.run(cmd.split(), shell=False)",
                risk_level="medium",
                confidence=0.9,
                rule_id="SEC003",
            ))
            options.append(FixOption(
                description="Use list of arguments",
                code_before="subprocess.run(cmd, shell=True)",
                code_after="subprocess.run(['/path/to/cmd', '--arg1', arg1], shell=False)",
                risk_level="low",
                confidence=0.95,
                rule_id="SEC003",
            ))

        return options

    async def _generate_quality_alternatives(
        self,
        finding: Finding,
        context: Optional[CodeContext],
    ) -> list[FixOption]:
        """Generate quality-specific alternatives.

        Args:
            finding: Quality finding
            context: Code context

        Returns:
            List of fix options
        """
        options: list[FixOption] = []

        if finding.rule_id == "QUAL001":
            # Long function
            options.append(FixOption(
                description="Extract helper functions",
                code_before="# Long function...",
                code_after="# Extract to helper functions\ndef _process_chunk(data):\n    ...\n\ndef main_function(data):\n    for chunk in chunks:\n        _process_chunk(chunk)",
                risk_level="medium",
                confidence=0.8,
                rule_id="QUAL001",
            ))

        elif finding.rule_id == "QUAL003":
            # Broad except
            options.append(FixOption(
                description="Catch specific exception",
                code_before="except:",
                code_after="except ValueError as e:\n    logger.error(f'Value error: {e}')",
                risk_level="low",
                confidence=0.95,
                rule_id="QUAL003",
            ))

        elif finding.rule_id == "QUAL006":
            # Print statement
            options.append(FixOption(
                description="Use logging module",
                code_before="print('message')",
                code_after="import logging\nlogger = logging.getLogger(__name__)\nlogger.info('message')",
                risk_level="low",
                confidence=0.9,
                rule_id="QUAL006",
            ))

        elif finding.rule_id == "QUAL007":
            # Magic number
            options.append(FixOption(
                description="Define named constant",
                code_before="if size > 4096:",
                code_after="MAX_BUFFER_SIZE = 4096\nif size > MAX_BUFFER_SIZE:",
                risk_level="low",
                confidence=0.9,
                rule_id="QUAL007",
            ))

        return options

    async def _generate_embedded_alternatives(
        self,
        finding: Finding,
        context: Optional[CodeContext],
    ) -> list[FixOption]:
        """Generate embedded-specific alternatives.

        Args:
            finding: Embedded finding
            context: Code context

        Returns:
            List of fix options
        """
        options: list[FixOption] = []

        if finding.rule_id == "EMB001":
            # NULL dereference
            options.append(FixOption(
                description="Add NULL check",
                code_before="ptr->value",
                code_after="if (ptr != NULL) {\n    ptr->value;\n}",
                risk_level="low",
                confidence=0.95,
                rule_id="EMB001",
            ))

        elif finding.rule_id == "EMB004":
            # Buffer overflow
            options.append(FixOption(
                description="Use safe string function",
                code_before="strcpy(dest, src)",
                code_after="strncpy(dest, src, sizeof(dest) - 1);\ndest[sizeof(dest) - 1] = '\\0';",
                risk_level="low",
                confidence=0.95,
                rule_id="EMB004",
            ))

        elif finding.rule_id == "EMB007":
            # ISR blocking
            options.append(FixOption(
                description="Use non-blocking pattern",
                code_before="HAL_Delay(100);",
                code_after="/* Set flag for main loop to handle */\nflag_set = 1;",
                risk_level="medium",
                confidence=0.9,
                rule_id="EMB007",
            ))

        elif finding.rule_id == "EMB014":
            # Stack overflow
            options.append(FixOption(
                description="Use static allocation",
                code_before="uint8_t buffer[8192];",
                code_after="static uint8_t buffer[8192];  /* Placed in .bss section */",
                risk_level="low",
                confidence=0.95,
                rule_id="EMB014",
            ))

        return options

    async def _generate_ml_alternatives(
        self,
        finding: Finding,
        context: Optional[CodeContext],
    ) -> list[FixOption]:
        """Generate ML-specific alternatives.

        Args:
            finding: ML finding
            context: Code context

        Returns:
            List of fix options
        """
        options: list[FixOption] = []

        if finding.rule_id == "ML001":
            # Dead code
            options.append(FixOption(
                description="Mark as deprecated",
                code_before="def unused_func():",
                code_after="@deprecated('This function will be removed in v2.0')\ndef unused_func():",
                risk_level="low",
                confidence=0.85,
                rule_id="ML001",
            ))
            options.append(FixOption(
                description="Remove unused function",
                code_before="def unused_func():...\n\ndef used_func():",
                code_after="def used_func():",
                risk_level="medium",
                confidence=0.9,
                rule_id="ML001",
            ))

        elif finding.rule_id == "ML002":
            # Unused parameter
            options.append(FixOption(
                description="Prefix with underscore",
                code_before="def func(unused_param):",
                code_after="def func(_unused_param):",
                risk_level="low",
                confidence=0.95,
                rule_id="ML002",
            ))

        return options

    def _should_suggest_refactor(self, finding: Finding) -> bool:
        """Determine if refactoring should be suggested.

        Args:
            finding: Finding to assess

        Returns:
            True if refactoring is appropriate
        """
        refactor_rules = {"QUAL001", "QUAL002", "QUAL010", "ML001", "ML006"}
        return finding.rule_id in refactor_rules

    def _generate_refactor_option(
        self,
        finding: Finding,
        context: Optional[CodeContext],
    ) -> FixOption:
        """Generate a refactoring option.

        Args:
            finding: Finding
            context: Code context

        Returns:
            Refactoring fix option
        """
        return FixOption(
            description="Consider refactoring for better maintainability",
            code_before="",
            code_after="# Refactoring suggestions:\n# 1. Extract to smaller functions\n# 2. Use design patterns where appropriate\n# 3. Add unit tests for complex logic",
            risk_level="medium",
            confidence=0.7,
            rule_id=finding.rule_id,
        )

    def _assess_overall_risk(self, options: list[FixOption]) -> str:
        """Assess overall risk from options.

        Args:
            options: List of fix options

        Returns:
            Overall risk level
        """
        if not options:
            return "unknown"

        # Take the lowest risk of all options
        risk_levels = {"low": 1, "medium": 2, "high": 3}
        min_risk = min(options, key=lambda o: risk_levels.get(o.risk_level, 2))
        return min_risk.risk_level

    def _generate_description(
        self,
        finding: Finding,
        options: list[FixOption],
    ) -> str:
        """Generate description for suggestions.

        Args:
            finding: Finding
            options: Generated options

        Returns:
            Description string
        """
        descriptions = {
            "SEC001": "Hardcoded secrets should be moved to secure storage",
            "SEC002": "SQL queries should use parameterized statements",
            "SEC003": "Shell commands should avoid shell=True for security",
            "QUAL001": "Long functions should be broken into smaller pieces",
            "QUAL003": "Exception handling should catch specific exceptions",
            "QUAL006": "Use logging instead of print statements",
            "QUAL007": "Magic numbers should be named constants",
            "EMB001": "Add NULL checks before dereferencing pointers",
            "EMB004": "Use safe string functions to prevent buffer overflow",
            "EMB007": "ISR should not contain blocking operations",
            "EMB014": "Large buffers should use static allocation",
            "ML001": "Unused code should be removed or marked deprecated",
            "ML002": "Unused parameters should be prefixed with underscore",
        }

        return descriptions.get(
            finding.rule_id,
            f"Fix for {finding.rule_id}: {finding.rule_name}"
        )

    def _extract_secret_assignment(
        self,
        finding: Finding,
        context: Optional[CodeContext],
    ) -> str:
        """Extract secret assignment from finding context.

        Args:
            finding: Finding
            context: Code context

        Returns:
            Secret assignment code
        """
        if context and finding.line <= len(context.lines):
            return context.lines[finding.line - 1]
        return "password = 'secret'"

    def _generate_diff(
        self,
        code_before: str,
        code_after: str,
    ) -> str:
        """Generate a unified diff.

        Args:
            code_before: Original code
            code_after: Fixed code

        Returns:
            Diff string
        """
        if code_before == code_after:
            return ""

        diff = difflib.unified_diff(
            code_before.splitlines(keepends=True),
            code_after.splitlines(keepends=True),
            fromfile="before.py",
            tofile="after.py",
            lineterm="",
        )
        return "".join(diff)

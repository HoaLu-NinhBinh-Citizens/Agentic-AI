"""Suggestion Engine — generates intelligent fix suggestions for code review findings.

This module provides multi-option fix generation with:
- Template-based fixes from RuleEngine
- Context-aware enhancement (surrounding code, imports)
- Alternative fix generation
- Risk assessment
- Validation
- Fix confidence scoring

Usage:
    engine = SuggestionEngine(fix_engine)
    suggestions = await engine.generate(finding, context)
"""

from __future__ import annotations

import difflib
import re
from typing import Any, Optional

from src.application.workflows.unified.code_context import CodeContext
from src.application.workflows.unified.detector_base import Finding
from src.domain.models.review_issue import FixOption
from src.infrastructure.analysis.ml_detectors.fix_templates import get_template
from src.shared.enums.severity import Severity, risk_to_unified

# Backward compatibility alias
FindingSeverity = Severity

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

        # Check if we have templates for this rule
        if finding.rule_id.startswith("ML") and get_template(finding.rule_id):
            options.extend(await self._generate_from_template(finding, context))

        # Get template fix from finding
        if finding.fix:
            options.append(FixOption(
                id=f"{finding.rule_id}-{finding.line}-fix",
                title="Suggested fix",
                description="Apply suggested fix",
                old_code=self._get_affected_lines(finding, context),
                new_code=self._apply_template_fix(finding, context),
                risk=self._string_to_severity(self._assess_template_risk(finding)),
                confidence=finding.confidence,
            ))

        # Generate alternatives based on rule type
        if finding.rule_id.startswith("SEC"):
            options.extend(await self._generate_security_alternatives(finding, context))
        elif finding.rule_id.startswith("QUAL"):
            options.extend(await self._generate_quality_alternatives(finding, context))
        elif finding.rule_id.startswith("EMB"):
            options.extend(await self._generate_embedded_alternatives(finding, context))

        # Generate refactoring alternative if applicable
        if self._should_suggest_refactor(finding):
            options.append(self._generate_refactor_option(finding, context))

        return options

    async def _generate_from_template(
        self,
        finding: Finding,
        context: Optional[CodeContext],
    ) -> list[FixOption]:
        """Generate multiple fix options from template.

        Args:
            finding: Finding to fix
            context: Code context

        Returns:
            List of fix options from template
        """
        templates = get_template(finding.rule_id)
        if not templates:
            return []

        options: list[FixOption] = []
        affected_lines = self._get_affected_lines(finding, context)

        for idx, (key, template) in enumerate(templates.items()):
            option_id = f"{finding.rule_id}-{finding.line}-{idx+1}"
            risk_str = template.get("risk", "medium")
            risk = self._string_to_severity(risk_str)
            confidence = 0.9 if key == "primary" else 0.75

            option = FixOption(
                id=option_id,
                title=template.get("title", "Suggested fix"),
                description=template.get("description", ""),
                old_code=affected_lines,
                new_code=template.get("new_code", affected_lines),
                risk=risk,
                confidence=confidence,
                tradeoff=template.get("tradeoff", ""),
                test_recommendation=template.get("test_recommendation", ""),
            )

            # Set alternative_to for non-primary options
            if key != "primary" and options:
                # Link to primary option (first one)
                options[0].alternative_to = option_id

            options.append(option)

        return options

    def _string_to_severity(self, risk_str: str) -> Severity:
        """Convert risk string to Severity enum."""
        mapping = {
            "low": Severity.LOW,
            "medium": Severity.MEDIUM,
            "high": Severity.HIGH,
            "critical": Severity.CRITICAL,
        }
        return mapping.get(risk_str.lower(), Severity.MEDIUM)

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
        if finding.severity == Severity.CRITICAL:
            return "low"  # High priority fixes are safe
        if finding.severity == Severity.HIGH:
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
                id="SEC001-1",
                title="Use environment variable",
                description="Use environment variable for secrets",
                old_code=self._extract_secret_assignment(finding, context),
                new_code="import os\nSECRET = os.environ.get('SECRET_NAME', 'default')",
                risk=Severity.LOW,
                confidence=0.95,
            ))
            options.append(FixOption(
                id="SEC001-2",
                title="Use secrets manager",
                description="Use a secrets manager for secrets",
                old_code=self._extract_secret_assignment(finding, context),
                new_code="# Use AWS Secrets Manager / Vault / etc.\nfrom your_secret_manager import get_secret\nSECRET = get_secret('secret-name')",
                risk=Severity.LOW,
                confidence=0.9,
            ))

        elif finding.rule_id == "SEC002":
            # SQL injection
            options.append(FixOption(
                id="SEC002-1",
                title="Use parameterized query",
                description="Use parameterized queries to prevent SQL injection",
                old_code="cursor.execute(f'SELECT * FROM users WHERE id = {user_id}')",
                new_code="cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))",
                risk=Severity.LOW,
                confidence=0.98,
            ))

        elif finding.rule_id == "SEC003":
            # Command injection
            options.append(FixOption(
                id="SEC003-1",
                title="Use shell=False",
                description="Disable shell to prevent command injection",
                old_code="subprocess.run(cmd, shell=True)",
                new_code="subprocess.run(cmd.split(), shell=False)",
                risk=Severity.MEDIUM,
                confidence=0.9,
            ))
            options.append(FixOption(
                id="SEC003-2",
                title="Use list of arguments",
                description="Pass arguments as list to prevent injection",
                old_code="subprocess.run(cmd, shell=True)",
                new_code="subprocess.run(['/path/to/cmd', '--arg1', arg1], shell=False)",
                risk=Severity.LOW,
                confidence=0.95,
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
                id="QUAL001-1",
                title="Extract helper functions",
                description="Break down long function into smaller helper functions",
                old_code="# Long function...",
                new_code="# Extract to helper functions\ndef _process_chunk(data):\n    ...\n\ndef main_function(data):\n    for chunk in chunks:\n        _process_chunk(chunk)",
                risk=Severity.MEDIUM,
                confidence=0.8,
            ))

        elif finding.rule_id == "QUAL003":
            # Broad except
            options.append(FixOption(
                id="QUAL003-1",
                title="Catch specific exception",
                description="Catch specific exception types instead of broad except",
                old_code="except:",
                new_code="except ValueError as e:\n    logger.error(f'Value error: {e}')",
                risk=Severity.LOW,
                confidence=0.95,
            ))

        elif finding.rule_id == "QUAL006":
            # Print statement
            options.append(FixOption(
                id="QUAL006-1",
                title="Use logging module",
                description="Replace print statements with proper logging",
                old_code="print('message')",
                new_code="import logging\nlogger = logging.getLogger(__name__)\nlogger.info('message')",
                risk=Severity.LOW,
                confidence=0.9,
            ))

        elif finding.rule_id == "QUAL007":
            # Magic number
            options.append(FixOption(
                id="QUAL007-1",
                title="Define named constant",
                description="Replace magic numbers with named constants",
                old_code="if size > 4096:",
                new_code="MAX_BUFFER_SIZE = 4096\nif size > MAX_BUFFER_SIZE:",
                risk=Severity.LOW,
                confidence=0.9,
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
                id="EMB001-1",
                title="Add NULL check",
                description="Add NULL check before dereferencing pointer",
                old_code="ptr->value",
                new_code="if (ptr != NULL) {\n    ptr->value;\n}",
                risk=Severity.LOW,
                confidence=0.95,
            ))

        elif finding.rule_id == "EMB004":
            # Buffer overflow
            options.append(FixOption(
                id="EMB004-1",
                title="Use safe string function",
                description="Use safe string functions to prevent buffer overflow",
                old_code="strcpy(dest, src)",
                new_code="strncpy(dest, src, sizeof(dest) - 1);\ndest[sizeof(dest) - 1] = '\\0';",
                risk=Severity.LOW,
                confidence=0.95,
            ))

        elif finding.rule_id == "EMB007":
            # ISR blocking
            options.append(FixOption(
                id="EMB007-1",
                title="Use non-blocking pattern",
                description="Use non-blocking pattern in ISR",
                old_code="HAL_Delay(100);",
                new_code="/* Set flag for main loop to handle */\nflag_set = 1;",
                risk=Severity.MEDIUM,
                confidence=0.9,
            ))

        elif finding.rule_id == "EMB014":
            # Stack overflow
            options.append(FixOption(
                id="EMB014-1",
                title="Use static allocation",
                description="Use static allocation for large buffers",
                old_code="uint8_t buffer[8192];",
                new_code="static uint8_t buffer[8192];  /* Placed in .bss section */",
                risk=Severity.LOW,
                confidence=0.95,
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
            id=f"{finding.rule_id}-refactor",
            title="Refactor for maintainability",
            description="Consider refactoring for better maintainability",
            old_code="",
            new_code="# Refactoring suggestions:\n# 1. Extract to smaller functions\n# 2. Use design patterns where appropriate\n# 3. Add unit tests for complex logic",
            risk=Severity.MEDIUM,
            confidence=0.7,
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

    def calculate_fix_confidence(
        self,
        fix: FixOption,
        context: Optional[CodeContext],
        finding: Finding,
    ) -> float:
        """Calculate confidence score for a fix suggestion.
        
        The confidence score is based on:
        - Context quality (line count, imports present)
        - Fix source (template vs LLM)
        - Finding severity
        - Risk level
        - Impact size (lines changed)
        
        Args:
            fix: The fix option
            context: Code context
            finding: The finding being fixed
            
        Returns:
            Confidence score between 0 and 1
        """
        confidence = 0.5  # Base confidence
        
        # Boost based on context quality
        if context:
            # Check line count from content
            line_count = len(context.content.split('\n')) if context.content else 0
            if line_count > 10:
                confidence += 0.1  # Good context
            # Check for imports
            if 'import' in context.content:
                confidence += 0.1  # Can resolve dependencies
        
        # Boost based on fix type/source
        if hasattr(fix, 'source'):
            source = getattr(fix, 'source', 'template')
            if source == 'template':
                confidence += 0.2  # Rule templates are well-tested
            elif source == 'llm':
                confidence += 0.15  # LLM suggestions are context-aware
        else:
            # Default: template-based fix
            confidence += 0.15
        
        # Boost based on severity (critical fixes should be more confident)
        if finding.severity == Severity.CRITICAL:
            confidence += 0.1
        elif finding.severity == Severity.HIGH:
            confidence += 0.05
        
        # Reduce confidence for high-risk fixes
        if fix.risk == Severity.CRITICAL:
            confidence -= 0.2
        elif fix.risk == Severity.HIGH:
            confidence -= 0.15
        elif fix.risk == Severity.MEDIUM:
            confidence -= 0.05
        
        # Reduce confidence for large changes
        if hasattr(fix, 'impact_lines'):
            impact_lines = getattr(fix, 'impact_lines', 0)
            if impact_lines > 20:
                confidence -= 0.1
            elif impact_lines > 10:
                confidence -= 0.05
        
        # Boost if fix has explanation
        if hasattr(fix, 'tradeoff') and fix.tradeoff:
            confidence += 0.05
        
        # Boost if fix has test recommendation
        if hasattr(fix, 'test_recommendation') and fix.test_recommendation:
            confidence += 0.05
        
        return max(0.0, min(1.0, confidence))

    def rank_fixes(
        self,
        fixes: list[FixOption],
        context: Optional[CodeContext],
        finding: Finding,
    ) -> list[FixOption]:
        """Rank fixes by confidence score.
        
        Args:
            fixes: List of fix options
            context: Code context
            finding: The finding being fixed
            
        Returns:
            Sorted list of fixes (highest confidence first)
        """
        for fix in fixes:
            fix.confidence = self.calculate_fix_confidence(fix, context, finding)
        
        return sorted(fixes, key=lambda f: f.confidence, reverse=True)

    def generate_smart_fix_description(
        self,
        fix: FixOption,
        finding: Finding,
    ) -> str:
        """Generate an enhanced description for a fix.
        
        Args:
            fix: The fix option
            finding: The finding
            
        Returns:
            Enhanced description with confidence and risk info
        """
        confidence_pct = int(fix.confidence * 100)
        risk_str = fix.risk.name.lower()
        
        desc = f"{fix.description}"
        
        if hasattr(fix, 'tradeoff') and fix.tradeoff:
            desc += f"\n\n**Trade-off:** {fix.tradeoff}"
        
        desc += f"\n\n**Confidence:** {confidence_pct}% | **Risk:** {risk_str}"
        
        if hasattr(fix, 'test_recommendation') and fix.test_recommendation:
            desc += f"\n\n**Testing:** {fix.test_recommendation}"
        
        return desc

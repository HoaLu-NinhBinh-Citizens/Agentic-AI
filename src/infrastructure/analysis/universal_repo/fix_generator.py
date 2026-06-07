"""Fix generator with template-first, LLM-fallback strategy.

Produces FixPatch suggestions from CompilerErrors using deterministic
template matching for common patterns, falling back to LLM inference
when no template applies.

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from .models import (
    CompilerError,
    FixPatch,
    MIN_CONFIDENCE,
    MAX_CONFIDENCE,
    NO_CONFIDENT_FIX_THRESHOLD,
)

logger = logging.getLogger(__name__)


# ─── Supporting Dataclass ────────────────────────────────────────────────────


@dataclass
class FileContext:
    """Context around an error location for fix generation.

    Provides the file content and surrounding lines so fix generators
    can understand the code around the error.
    """

    file_path: str
    content: str
    surrounding_lines: list[str] = field(default_factory=list)


# ─── Template Constants ──────────────────────────────────────────────────────

# Confidence scores for template vs LLM fixes
TEMPLATE_CONFIDENCE_HIGH = 0.9
TEMPLATE_CONFIDENCE_MEDIUM = 0.8
LLM_DEFAULT_TEMPERATURE = 0.3
LLM_MAX_TOKENS = 1024

# Ranking limits
MAX_RANKED_FIXES = 3

# LLM prompt system instruction
LLM_SYSTEM_PROMPT = (
    "You are a compiler error fix assistant. Given a compiler error and "
    "surrounding code context, suggest a minimal code fix. Respond in this "
    "exact format:\n"
    "CONFIDENCE: <0.0-1.0>\n"
    "EXPLANATION: <one line explanation>\n"
    "OLD_CODE: <original code line(s)>\n"
    "NEW_CODE: <fixed code line(s)>\n"
    "Only suggest fixes you are confident about."
)


# ─── Fix Generator ───────────────────────────────────────────────────────────


class FixGenerator:
    """Generates FixPatch suggestions from compiler errors.

    Uses a template-first strategy: common error patterns are matched
    against deterministic fix templates for fast, reliable patches.
    When no template applies, falls back to LLM-based generation with
    confidence scoring.

    Requirements:
        6.1 — Produce FixPatch with suggested code correction.
        6.2 — Use templates before LLM fallback.
        6.3 — Include confidence score and explanation for LLM fixes.
    """

    def __init__(self, llm_provider=None) -> None:
        """Initialize FixGenerator.

        Args:
            llm_provider: Optional LLMProvider instance (from
                infrastructure.llm.adapters). If None, LLM fallback
                is disabled and only template fixes are returned.
        """
        self._llm_provider = llm_provider
        self._templates = _build_template_registry()

    @property
    def llm_provider(self):
        """Return the configured LLM provider (or None)."""
        return self._llm_provider

    async def generate_fix(
        self, error: CompilerError, context: FileContext
    ) -> list[FixPatch]:
        """Generate fix suggestions for a compiler error.

        Strategy:
        1. Try template fix first (fast, deterministic).
        2. If no template matches, fall back to LLM fix.
        3. Return list of FixPatch (may be empty).

        Args:
            error: Structured compiler error to fix.
            context: File context around the error location.

        Returns:
            List of FixPatch suggestions, possibly empty.
        """
        # Try template fix first
        template_fix = self.get_template_fix(error)
        if template_fix is not None:
            logger.debug(
                "Template fix found for %s:%d [%s]",
                error.file_path,
                error.line,
                error.error_code,
            )
            return [template_fix]

        # Fall back to LLM
        llm_fix = await self.get_llm_fix(error, context)
        if llm_fix is not None:
            logger.debug(
                "LLM fix generated for %s:%d [%s] confidence=%.2f",
                error.file_path,
                error.line,
                error.error_code,
                llm_fix.confidence,
            )
            return [llm_fix]

        logger.debug(
            "No fix available for %s:%d [%s]",
            error.file_path,
            error.line,
            error.error_code,
        )
        return []

    async def generate_fixes_ranked(
        self, error: CompilerError, context: FileContext
    ) -> list[FixPatch]:
        """Generate and rank fix suggestions by confidence.

        Collects fixes from both template matching and LLM generation,
        sorts by confidence descending, and returns the top 3.

        If no fix exceeds NO_CONFIDENT_FIX_THRESHOLD (0.3), returns a
        single FixPatch with source="no_confident_fix" and confidence=0.0
        containing the error context for manual resolution.

        Args:
            error: Structured compiler error to fix.
            context: File context around the error location.

        Returns:
            List of up to 3 FixPatch suggestions ranked by confidence,
            or a single no_confident_fix sentinel.

        Requirements: 6.4, 6.5, 6.6
        """
        candidates: list[FixPatch] = []

        # Collect template fix
        template_fix = self.get_template_fix(error)
        if template_fix is not None:
            candidates.append(template_fix)

        # Also try LLM to get multiple options
        llm_fix = await self.get_llm_fix(error, context)
        if llm_fix is not None:
            candidates.append(llm_fix)

        # Filter out duplicates (same source, same new_code)
        seen: set[tuple[str, str]] = set()
        unique: list[FixPatch] = []
        for fix in candidates:
            key = (fix.source, fix.new_code)
            if key not in seen:
                seen.add(key)
                unique.append(fix)
        candidates = unique

        # Sort by confidence descending
        candidates.sort(key=lambda f: f.confidence, reverse=True)

        # Check if any fix exceeds threshold
        if not candidates or candidates[0].confidence <= NO_CONFIDENT_FIX_THRESHOLD:
            logger.debug(
                "No confident fix for %s:%d [%s] — max confidence=%.2f",
                error.file_path,
                error.line,
                error.error_code,
                candidates[0].confidence if candidates else 0.0,
            )
            return [
                FixPatch(
                    file_path=error.file_path,
                    line_start=error.line,
                    line_end=error.line,
                    old_code="",
                    new_code="",
                    explanation=(
                        f"No confident fix available for {error.compiler} "
                        f"error [{error.error_code}]: {error.message} "
                        f"at {error.file_path}:{error.line}:{error.column}"
                    ),
                    confidence=0.0,
                    source="no_confident_fix",
                    error_ref=error,
                )
            ]

        # Return top 3
        return candidates[:MAX_RANKED_FIXES]

    async def generate_fix_from_finding(
        self, finding, context: FileContext
    ) -> list[FixPatch]:
        """Generate fix suggestions from a Rule_Engine Finding.

        Converts the Finding into a CompilerError-compatible representation
        and delegates to generate_fix() for the actual fix generation.

        Args:
            finding: A Finding object from the Rule_Engine with attributes:
                rule_id, rule_name, severity, file, line, end_line,
                column, message.
            context: File context around the finding location.

        Returns:
            List of FixPatch suggestions, possibly empty.

        Requirements: 6.1
        """
        # Map Finding severity to string (handles both Enum and str)
        severity_str = (
            finding.severity.value
            if hasattr(finding.severity, "value")
            else str(finding.severity)
        )

        # Convert Finding to CompilerError representation
        adapted_error = CompilerError(
            file_path=finding.file,
            line=finding.line,
            column=finding.column,
            severity=severity_str,
            error_code=finding.rule_id,
            message=finding.message or finding.rule_name,
            compiler="static_analysis",
        )

        return await self.generate_fix(adapted_error, context)

    def get_template_fix(self, error: CompilerError) -> Optional[FixPatch]:
        """Attempt template-based fix for common error patterns.

        Matches the error code and message against a registry of known
        fix templates per compiler/language. Returns a FixPatch with
        source='template' and high confidence (0.8-0.9).

        Args:
            error: Structured compiler error.

        Returns:
            FixPatch with source="template" or None if no template matches.
        """
        for template in self._templates:
            fix = template.try_match(error)
            if fix is not None:
                return fix
        return None

    async def get_llm_fix(
        self, error: CompilerError, context: FileContext
    ) -> Optional[FixPatch]:
        """Generate fix using LLM with confidence scoring.

        Constructs a prompt with error details and file context, calls
        the LLM provider, and parses the response into a FixPatch.

        Args:
            error: Structured compiler error.
            context: File context around the error location.

        Returns:
            FixPatch with source="llm" or None if LLM is unavailable
            or response is unparseable.
        """
        if self._llm_provider is None:
            return None

        if not self._llm_provider.is_available():
            logger.debug("LLM provider not available, skipping LLM fix")
            return None

        prompt = self._build_llm_prompt(error, context)

        try:
            response = await self._llm_provider.generate(
                prompt=prompt,
                system_prompt=LLM_SYSTEM_PROMPT,
                temperature=LLM_DEFAULT_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
            )
            return self._parse_llm_response(response.content, error)
        except Exception as exc:
            logger.warning("LLM fix generation failed: %s", exc)
            return None

    # ─── Private Helpers ─────────────────────────────────────────────────

    def _build_llm_prompt(
        self, error: CompilerError, context: FileContext
    ) -> str:
        """Build the prompt sent to the LLM for fix generation."""
        surrounding = "\n".join(context.surrounding_lines) if context.surrounding_lines else ""
        return (
            f"Compiler: {error.compiler}\n"
            f"Error code: {error.error_code}\n"
            f"Severity: {error.severity}\n"
            f"File: {error.file_path}\n"
            f"Line: {error.line}, Column: {error.column}\n"
            f"Message: {error.message}\n"
            f"\nSurrounding code:\n```\n{surrounding}\n```\n"
            f"\nSuggest a minimal fix."
        )

    def _parse_llm_response(
        self, content: str, error: CompilerError
    ) -> Optional[FixPatch]:
        """Parse structured LLM response into a FixPatch."""
        confidence = self._extract_field(content, "CONFIDENCE")
        explanation = self._extract_field(content, "EXPLANATION")
        old_code = self._extract_field(content, "OLD_CODE")
        new_code = self._extract_field(content, "NEW_CODE")

        if not all([confidence, explanation, old_code, new_code]):
            logger.debug("LLM response missing required fields")
            return None

        try:
            confidence_score = float(confidence)
        except (ValueError, TypeError):
            logger.debug("LLM response has invalid confidence: %s", confidence)
            return None

        confidence_score = max(MIN_CONFIDENCE, min(MAX_CONFIDENCE, confidence_score))

        return FixPatch(
            file_path=error.file_path,
            line_start=error.line,
            line_end=error.line,
            old_code=old_code,
            new_code=new_code,
            explanation=explanation,
            confidence=confidence_score,
            source="llm",
            error_ref=error,
        )

    @staticmethod
    def _extract_field(content: str, field_name: str) -> Optional[str]:
        """Extract a field value from structured LLM output."""
        pattern = rf"^{re.escape(field_name)}:\s*(.+)$"
        match = re.search(pattern, content, re.MULTILINE)
        if match:
            return match.group(1).strip()
        return None


# ─── Template Infrastructure ─────────────────────────────────────────────────


class _FixTemplate:
    """A single fix template matching an error pattern."""

    def __init__(
        self,
        compiler: str,
        error_code_pattern: str,
        message_pattern: str,
        fix_fn,
        confidence: float,
        explanation: str,
    ) -> None:
        self.compiler = compiler
        self._code_re = re.compile(error_code_pattern) if error_code_pattern else None
        self._msg_re = re.compile(message_pattern, re.IGNORECASE) if message_pattern else None
        self._fix_fn = fix_fn
        self.confidence = confidence
        self.explanation = explanation

    def try_match(self, error: CompilerError) -> Optional[FixPatch]:
        """Try to match this template against the error."""
        # Compiler must match
        if self.compiler != "*" and error.compiler != self.compiler:
            return None

        # Error code pattern (if specified)
        if self._code_re and not self._code_re.search(error.error_code):
            return None

        # Message pattern (if specified)
        if self._msg_re and not self._msg_re.search(error.message):
            return None

        # Generate fix
        fix_result = self._fix_fn(error)
        if fix_result is None:
            return None

        old_code, new_code = fix_result
        return FixPatch(
            file_path=error.file_path,
            line_start=error.line,
            line_end=error.line,
            old_code=old_code,
            new_code=new_code,
            explanation=self.explanation,
            confidence=self.confidence,
            source="template",
            error_ref=error,
        )


# ─── Template Fix Functions ──────────────────────────────────────────────────


def _fix_missing_semicolon(error: CompilerError) -> Optional[tuple[str, str]]:
    """Fix missing semicolon for TypeScript/JavaScript."""
    # Use the raw message to infer the missing token
    return ("", ";")


def _fix_undeclared_identifier_include(error: CompilerError) -> Optional[tuple[str, str]]:
    """Suggest #include for undeclared identifier in C/C++."""
    # Extract identifier from message like: use of undeclared identifier 'printf'
    match = re.search(r"'(\w+)'", error.message)
    if not match:
        return None
    identifier = match.group(1)

    # Common standard library mappings
    include_map = {
        "printf": "<stdio.h>",
        "fprintf": "<stdio.h>",
        "sprintf": "<stdio.h>",
        "scanf": "<stdio.h>",
        "malloc": "<stdlib.h>",
        "free": "<stdlib.h>",
        "calloc": "<stdlib.h>",
        "realloc": "<stdlib.h>",
        "strlen": "<string.h>",
        "strcpy": "<string.h>",
        "strcat": "<string.h>",
        "strcmp": "<string.h>",
        "memcpy": "<string.h>",
        "memset": "<string.h>",
        "sqrt": "<math.h>",
        "pow": "<math.h>",
        "abs": "<stdlib.h>",
        "exit": "<stdlib.h>",
        "NULL": "<stddef.h>",
        "size_t": "<stddef.h>",
        "uint8_t": "<stdint.h>",
        "uint16_t": "<stdint.h>",
        "uint32_t": "<stdint.h>",
        "int8_t": "<stdint.h>",
        "int16_t": "<stdint.h>",
        "int32_t": "<stdint.h>",
    }

    header = include_map.get(identifier)
    if header is None:
        return None

    return ("", f"#include {header}")


def _fix_missing_import_ts(error: CompilerError) -> Optional[tuple[str, str]]:
    """Suggest import for 'Cannot find name' in TypeScript."""
    match = re.search(r"Cannot find name '(\w+)'", error.message)
    if not match:
        return None
    name = match.group(1)
    return ("", f"import {{ {name} }} from './{name}';")


def _fix_unused_variable_gcc(error: CompilerError) -> Optional[tuple[str, str]]:
    """Fix unused variable warning in C/C++ with (void) cast."""
    match = re.search(r"'(\w+)'", error.message)
    if not match:
        return None
    var_name = match.group(1)
    return ("", f"(void){var_name};")


def _fix_type_mismatch_simple(error: CompilerError) -> Optional[tuple[str, str]]:
    """Handle simple type mismatch by suggesting a cast (TSC)."""
    # For TS2322: Type 'X' is not assignable to type 'Y'
    match = re.search(
        r"Type '(\w+)' is not assignable to type '(\w+)'", error.message
    )
    if not match:
        return None
    source_type = match.group(1)
    target_type = match.group(2)

    # Only handle simple primitive conversions
    simple_casts = {
        ("number", "string"): "String(value)",
        ("string", "number"): "Number(value)",
        ("number", "boolean"): "Boolean(value)",
        ("string", "boolean"): "Boolean(value)",
    }
    cast = simple_casts.get((source_type, target_type))
    if cast is None:
        return None

    return (f"/* type: {source_type} */", f"/* cast to {target_type}: {cast} */")


# ─── Template Registry ───────────────────────────────────────────────────────


def _build_template_registry() -> list[_FixTemplate]:
    """Build the registry of all fix templates.

    Returns:
        List of _FixTemplate instances covering common error patterns.
    """
    return [
        # TSC: Missing semicolon (TS1005)
        _FixTemplate(
            compiler="tsc",
            error_code_pattern=r"^TS1005$",
            message_pattern=r"';' expected",
            fix_fn=_fix_missing_semicolon,
            confidence=TEMPLATE_CONFIDENCE_HIGH,
            explanation="Add missing semicolon.",
        ),
        # GCC/Clang: Undeclared identifier → suggest #include
        _FixTemplate(
            compiler="gcc",
            error_code_pattern=r"^(C2065|E0020)?$",
            message_pattern=r"(undeclared identifier|implicitly declaring library function|implicit declaration of function)",
            fix_fn=_fix_undeclared_identifier_include,
            confidence=TEMPLATE_CONFIDENCE_MEDIUM,
            explanation="Add missing #include for standard library function.",
        ),
        # TSC: Cannot find name → suggest import (TS2304)
        _FixTemplate(
            compiler="tsc",
            error_code_pattern=r"^TS2304$",
            message_pattern=r"Cannot find name",
            fix_fn=_fix_missing_import_ts,
            confidence=TEMPLATE_CONFIDENCE_MEDIUM,
            explanation="Add missing import statement.",
        ),
        # GCC: Unused variable warning
        _FixTemplate(
            compiler="gcc",
            error_code_pattern=r"",
            message_pattern=r"unused variable",
            fix_fn=_fix_unused_variable_gcc,
            confidence=TEMPLATE_CONFIDENCE_HIGH,
            explanation="Suppress unused variable warning with (void) cast.",
        ),
        # TSC: Type mismatch (TS2322)
        _FixTemplate(
            compiler="tsc",
            error_code_pattern=r"^TS2322$",
            message_pattern=r"Type '\\w+' is not assignable to type '\\w+'",
            fix_fn=_fix_type_mismatch_simple,
            confidence=TEMPLATE_CONFIDENCE_MEDIUM,
            explanation="Add type cast for simple type mismatch.",
        ),
    ]

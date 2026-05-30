"""Unified Suggestion Engine - Generates intelligent, multi-option fixes.

Features:
- Context-aware fix generation
- Multiple fix options per finding
- Risk level assessment
- Confidence scoring
- Before/after patch generation
- LLM integration for complex fixes
- Template-based fallback

Usage:
    engine = UnifiedSuggestionEngine(config)
    result = await engine.generate(finding, context)
    for option in result.options:
        print(option.description, option.risk, option.confidence)
"""

from __future__ import annotations

import asyncio
import difflib
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from src.application.workflows.unified.code_context import CodeContext
from src.application.workflows.unified.detector_base import Finding, FindingSeverity

logger = logging.getLogger(__name__)


# ─── Enums ─────────────────────────────────────────────────────────────────────


class RiskLevel(Enum):
    """Risk level for fix options."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @classmethod
    def from_severity(cls, severity: FindingSeverity) -> RiskLevel:
        """Convert finding severity to risk level."""
        mapping = {
            FindingSeverity.ERROR: cls.LOW,
            FindingSeverity.WARNING: cls.MEDIUM,
            FindingSeverity.INFO: cls.MEDIUM,
            FindingSeverity.HINT: cls.HIGH,
        }
        return mapping.get(severity, cls.MEDIUM)

    def to_numeric(self) -> int:
        """Convert to numeric score for ranking."""
        mapping = {
            RiskLevel.LOW: 0,
            RiskLevel.MEDIUM: 1,
            RiskLevel.HIGH: 2,
            RiskLevel.CRITICAL: 3,
        }
        return mapping.get(self, 1)


# ─── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class FixOption:
    """A single fix option for a finding."""
    id: str
    description: str
    old_code: str
    new_code: str
    risk: RiskLevel
    confidence: float = 1.0
    explanation: str = ""
    automated: bool = False
    requires_review: bool = True
    dependencies: list[str] = field(default_factory=list)
    diff: str = ""
    line_hint: tuple[int, int] = (0, 0)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "description": self.description,
            "old_code": self.old_code,
            "new_code": self.new_code,
            "risk": self.risk.value,
            "confidence": self.confidence,
            "explanation": self.explanation,
            "automated": self.automated,
            "requires_review": self.requires_review,
            "dependencies": self.dependencies,
            "diff": self.diff,
            "line_hint": list(self.line_hint),
        }

    def generate_diff(self, file_path: str = "file.py") -> str:
        """Generate unified diff for this option."""
        if not self.diff and self.old_code != self.new_code:
            self.diff = _generate_unified_diff(
                self.old_code,
                self.new_code,
                file_path,
            )
        return self.diff


@dataclass
class SuggestionResult:
    """Complete suggestion for a finding."""
    finding_id: str
    file_path: str
    line: int
    rule_id: str
    options: list[FixOption]
    best_option: Optional[FixOption] = None
    context_snippet: str = ""
    all_options_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "finding_id": self.finding_id,
            "file_path": self.file_path,
            "line": self.line,
            "rule_id": self.rule_id,
            "options": [opt.to_dict() for opt in self.options],
            "best_option": self.best_option.to_dict() if self.best_option else None,
            "context_snippet": self.context_snippet,
            "all_options_count": self.all_options_count,
            "metadata": self.metadata,
        }


@dataclass
class SuggestionConfig:
    """Configuration for the suggestion engine."""
    max_options_per_finding: int = 3
    include_llm_fixes: bool = True
    llm_model: str = "llama3"
    confidence_threshold: float = 0.5
    prefer_automated: bool = True
    context_radius: int = 5
    enable_batch_processing: bool = True


@dataclass
class FixTemplate:
    """A template for a fix option."""
    rule_id: str
    description: str
    replacement: str
    risk: str
    automated: bool = True
    requires_review: bool = False
    explanation: str = ""
    dependencies: list[str] = field(default_factory=list)


# ─── LLM Provider Interface ───────────────────────────────────────────────────


class LLMProviderInterface:
    """Interface for LLM providers used by the suggestion engine."""

    async def generate(self, prompt: str, system: Optional[str] = None) -> str:
        """Generate text from prompt."""
        raise NotImplementedError

    async def is_available(self) -> bool:
        """Check if LLM is available."""
        raise NotImplementedError


# ─── Unified Suggestion Engine ─────────────────────────────────────────────────


class UnifiedSuggestionEngine:
    """Unified engine for generating fix suggestions.

    Combines multiple fix generation strategies:
    1. Template-based: Pre-defined fixes for known patterns
    2. Rule-based: Pattern matching and replacement
    3. LLM-based: AI-generated fixes for complex cases
    4. Common patterns: Known solutions from codebase patterns
    """

    def __init__(
        self,
        config: Optional[SuggestionConfig] = None,
        llm_provider: Optional[LLMProviderInterface] = None,
    ) -> None:
        """Initialize the suggestion engine."""
        self.config = config or SuggestionConfig()
        self._llm_provider = llm_provider
        self._templates = self._load_templates()
        self._rule_patterns = self._load_rule_patterns()
        self._common_patterns = self._load_common_patterns()

    async def generate(
        self,
        finding: Finding,
        context: Optional[CodeContext],
        max_options: Optional[int] = None,
    ) -> SuggestionResult:
        """Generate fix suggestions for a finding."""
        max_opts = max_options or self.config.max_options_per_finding
        options: list[FixOption] = []

        # 1. Template-based fix
        template_opts = await self._generate_template_fix(finding, context)
        options.extend(template_opts)

        # 2. Rule-based alternative
        rule_opts = await self._generate_rule_fix(finding, context)
        options.extend(rule_opts)

        # 3. LLM-generated fixes
        if self.config.include_llm_fixes and self._llm_provider:
            llm_opts = await self._generate_llm_fixes(
                finding, context, max_opts - len(options)
            )
            options.extend(llm_opts)

        # 4. Common patterns
        common_opts = await self._find_common_patterns(
            finding, context, max_opts - len(options)
        )
        options.extend(common_opts)

        # Filter by confidence threshold
        options = [opt for opt in options if opt.confidence >= self.config.confidence_threshold]

        # Rank options by confidence and risk
        options = self._rank_options(options)

        # Pick best option
        best = options[0] if options else None

        # Generate diffs for all options
        for opt in options:
            opt.generate_diff(finding.file)

        return SuggestionResult(
            finding_id=finding.rule_id,
            file_path=finding.file,
            line=finding.line,
            rule_id=finding.rule_id,
            options=options[:max_opts],
            best_option=best,
            context_snippet=self._get_context_snippet(finding, context),
            all_options_count=len(options),
            metadata={
                "severity": finding.severity.value,
                "confidence": finding.confidence,
                "detector": finding.detector,
            },
        )

    async def generate_batch(
        self,
        findings: list[Finding],
        contexts: dict[str, CodeContext],
    ) -> list[SuggestionResult]:
        """Generate suggestions for multiple findings in parallel."""
        if self.config.enable_batch_processing:
            tasks = [
                self.generate(f, contexts.get(f.file))
                for f in findings
            ]
            return await asyncio.gather(*tasks)
        else:
            return [await self.generate(f, contexts.get(f.file)) for f in findings]

    async def _generate_template_fix(
        self,
        finding: Finding,
        context: Optional[CodeContext],
    ) -> list[FixOption]:
        """Generate fix from pre-defined templates."""
        options: list[FixOption] = []
        rule_id = finding.rule_id

        if rule_id not in self._templates:
            return options

        template = self._templates[rule_id]
        old_code = self._get_affected_code(finding, context)

        options.append(FixOption(
            id=f"{rule_id}-template-auto",
            description=f"{template.description} (Automated)",
            old_code=old_code,
            new_code=self._apply_template(finding, template, context),
            risk=RiskLevel(template.risk),
            confidence=0.85,
            explanation=template.explanation,
            automated=template.automated,
            requires_review=template.requires_review,
            dependencies=template.dependencies,
            line_hint=(finding.line, finding.end_line),
        ))

        if template.requires_review:
            options.append(FixOption(
                id=f"{rule_id}-template-review",
                description=f"{template.description} (Review Required)",
                old_code=old_code,
                new_code=self._apply_template(finding, template, context),
                risk=RiskLevel(template.risk),
                confidence=0.90,
                explanation=f"{template.explanation} (Manual verification recommended)",
                automated=False,
                requires_review=True,
                dependencies=template.dependencies,
                line_hint=(finding.line, finding.end_line),
            ))

        return options

    def _apply_template(
        self,
        finding: Finding,
        template: FixTemplate,
        context: Optional[CodeContext],
    ) -> str:
        """Apply template replacement to finding code."""
        if template.replacement:
            return template.replacement

        old_code = self._get_affected_code(finding, context)
        return self._apply_pattern_replacement(old_code, finding.rule_id)

    def _apply_pattern_replacement(self, old_code: str, rule_id: str) -> str:
        """Apply pattern-based replacement based on rule ID."""
        replacements = {
            "QUAL001": self._fix_long_function(old_code),
            "QUAL003": self._fix_broad_except(old_code),
            "QUAL006": self._fix_print_statement(old_code),
            "QUAL007": self._fix_magic_number(old_code),
            "SEC001": self._fix_hardcoded_secret(old_code),
            "SEC002": self._fix_sql_injection(old_code),
            "SEC003": self._fix_command_injection(old_code),
            "EMB001": self._fix_null_dereference(old_code),
            "EMB004": self._fix_buffer_overflow(old_code),
            "EMB007": self._fix_isr_blocking(old_code),
            "EMB014": self._fix_stack_overflow(old_code),
            "ML001": self._fix_dead_code(old_code),
            "ML002": self._fix_unused_parameter(old_code),
        }

        fix_func = replacements.get(rule_id)
        if fix_func:
            return fix_func(old_code)
        return old_code

    async def _generate_rule_fix(
        self,
        finding: Finding,
        context: Optional[CodeContext],
    ) -> list[FixOption]:
        """Generate fixes using rule engine patterns."""
        options: list[FixOption] = []
        old_code = self._get_affected_code(finding, context)

        if finding.rule_id in self._rule_patterns:
            pattern = self._rule_patterns[finding.rule_id]
            for alt in pattern.get("alternatives", []):
                options.append(FixOption(
                    id=f"{finding.rule_id}-rule-{alt['id']}",
                    description=alt["description"],
                    old_code=old_code,
                    new_code=alt["replacement"],
                    risk=RiskLevel(alt.get("risk", "medium")),
                    confidence=float(alt.get("confidence", 0.75)),
                    explanation=alt.get("explanation", ""),
                    automated=alt.get("automated", False),
                    requires_review=alt.get("requires_review", True),
                    dependencies=alt.get("dependencies", []),
                    line_hint=(finding.line, finding.end_line),
                ))

        return options

    async def _generate_llm_fixes(
        self,
        finding: Finding,
        context: Optional[CodeContext],
        count: int,
    ) -> list[FixOption]:
        """Generate fixes using LLM."""
        if not self._llm_provider:
            return []

        if not await self._llm_provider.is_available():
            logger.debug("LLM provider not available, skipping LLM fixes")
            return []

        prompt = self._build_llm_prompt(finding, context, count)
        system_prompt = """You are a code fix assistant. Generate fix options for code issues.
Respond ONLY with valid JSON array of fix options. Each option must have:
- id: unique identifier
- description: what the fix does
- old_code: problematic code
- new_code: fixed code
- risk: LOW/MEDIUM/HIGH
- confidence: 0.0-1.0
- explanation: why this fix works
- automated: true/false
- requires_review: true/false"""

        try:
            response = await self._llm_provider.generate(prompt, system_prompt)
            return self._parse_llm_response(response, count, finding.rule_id)
        except Exception as e:
            logger.warning("LLM fix generation failed: %s", e)
            return []

    def _build_llm_prompt(
        self,
        finding: Finding,
        context: Optional[CodeContext],
        count: int,
    ) -> str:
        """Build prompt for LLM fix generation."""
        context_snippet = self._get_context_snippet(finding, context)

        return f"""Generate {count} fix options for this code issue:

File: {finding.file}
Line: {finding.line}
Rule: {finding.rule_id}
Severity: {finding.severity.value.upper()}
Confidence: {finding.confidence:.2f}

Issue: {finding.message}

Problematic Code:
```
{finding.context or 'Code not available'}
```

Surrounding Context:
```
{context_snippet}
```

Generate {count} distinct fix options, each with different approach.
Respond with JSON array."""

    def _parse_llm_response(
        self,
        response: str,
        count: int,
        rule_id: str,
    ) -> list[FixOption]:
        """Parse LLM JSON response into FixOption objects."""
        options: list[FixOption] = []

        try:
            data = None

            # Find JSON array first
            array_start = response.find("[")
            if array_start >= 0:
                for i in range(array_start + 1, len(response)):
                    if response[i] == "]":
                        try:
                            data = json.loads(response[array_start:i + 1])
                            break
                        except json.JSONDecodeError:
                            pass

            # Try JSON object if no array found
            if data is None:
                obj_start = response.find("{")
                if obj_start >= 0:
                    for i in range(obj_start + 1, len(response)):
                        if response[i] == "}":
                            try:
                                data = json.loads(response[obj_start:i + 1])
                                break
                            except json.JSONDecodeError:
                                pass

            if data is None:
                return []

            items = data if isinstance(data, list) else [data]

            for item in items[:count]:
                if not isinstance(item, dict):
                    continue

                risk_str = item.get("risk", "medium").lower()
                try:
                    risk = RiskLevel(risk_str)
                except ValueError:
                    risk = RiskLevel.MEDIUM

                options.append(FixOption(
                    id=f"{rule_id}-llm-{item.get('id', len(options))}",
                    description=item.get("description", "LLM-generated fix"),
                    old_code=item.get("old_code", ""),
                    new_code=item.get("new_code", ""),
                    risk=risk,
                    confidence=float(item.get("confidence", 0.7)),
                    explanation=item.get("explanation", ""),
                    automated=bool(item.get("automated", False)),
                    requires_review=bool(item.get("requires_review", True)),
                    dependencies=item.get("dependencies", []),
                ))

        except Exception as e:
            logger.warning("Failed to parse LLM response: %s", e)

        return options

    async def _find_common_patterns(
        self,
        finding: Finding,
        context: Optional[CodeContext],
        count: int,
    ) -> list[FixOption]:
        """Find common fix patterns from codebase patterns."""
        options: list[FixOption] = []
        old_code = self._get_affected_code(finding, context)

        if count <= 0:
            return options

        if finding.rule_id in self._common_patterns:
            patterns = self._common_patterns[finding.rule_id]
            for i, pattern in enumerate(patterns[:count]):
                options.append(FixOption(
                    id=f"{finding.rule_id}-common-{i}",
                    description=pattern["description"],
                    old_code=old_code,
                    new_code=pattern["replacement"],
                    risk=RiskLevel(pattern.get("risk", "medium")),
                    confidence=float(pattern.get("confidence", 0.7)),
                    explanation=pattern.get("explanation", ""),
                    automated=pattern.get("automated", False),
                    requires_review=pattern.get("requires_review", True),
                    dependencies=pattern.get("dependencies", []),
                    line_hint=(finding.line, finding.end_line),
                ))

        return options

    def _rank_options(self, options: list[FixOption]) -> list[FixOption]:
        """Rank options by confidence and risk."""
        def sort_key(opt: FixOption) -> tuple:
            risk_score = opt.risk.to_numeric()
            confidence_score = -opt.confidence

            if self.config.prefer_automated:
                automated_bonus = 0 if opt.automated else 1
            else:
                automated_bonus = 0

            return (confidence_score, risk_score, automated_bonus, opt.id)

        return sorted(options, key=sort_key)

    def _get_context_snippet(
        self,
        finding: Finding,
        context: Optional[CodeContext],
    ) -> str:
        """Get surrounding code context."""
        if context:
            radius = self.config.context_radius
            lines = context.lines
            start = max(0, finding.line - radius - 1)
            end = min(len(lines), finding.line + radius)

            snippet_lines = []
            for i in range(start, end):
                prefix = ">>>" if i == finding.line - 1 else "   "
                snippet_lines.append(f"{prefix} {i + 1:4d} | {lines[i]}")

            return "\n".join(snippet_lines)

        return f"Line {finding.line}: {finding.context}"

    def _get_affected_code(
        self,
        finding: Finding,
        context: Optional[CodeContext],
    ) -> str:
        """Get the code lines affected by the finding."""
        if context:
            lines = context.lines
            start = max(0, finding.line - 1)
            end = min(len(lines), finding.end_line)
            return "\n".join(lines[start:end])

        return finding.context or f"Line {finding.line}"

    # ─── Pattern-specific fix methods ───────────────────────────────────────────

    def _fix_long_function(self, old_code: str) -> str:
        """Extract helper functions from long function."""
        return "# Extract to smaller helper functions\n# Consider using the 'extract method' refactoring"

    def _fix_broad_except(self, old_code: str) -> str:
        """Catch specific exception instead of bare except."""
        return "except SpecificException as e:\n    logger.error(f'Error: {e}')"

    def _fix_print_statement(self, old_code: str) -> str:
        """Replace print with logging."""
        return "logger.info('message')  # Use logger instead of print"

    def _fix_magic_number(self, old_code: str) -> str:
        """Replace magic number with named constant."""
        return "MAX_BUFFER_SIZE = 4096\n# Use constant instead of magic number"

    def _fix_hardcoded_secret(self, old_code: str) -> str:
        """Use environment variable for secret."""
        return "import os\nSECRET = os.environ.get('SECRET_NAME', 'default')"

    def _fix_sql_injection(self, old_code: str) -> str:
        """Use parameterized query."""
        return "cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))"

    def _fix_command_injection(self, old_code: str) -> str:
        """Use shell=False or list of arguments."""
        return "subprocess.run(cmd.split(), shell=False)"

    def _fix_null_dereference(self, old_code: str) -> str:
        """Add NULL check before dereference."""
        return "if ptr is not None:\n    ptr.value"

    def _fix_buffer_overflow(self, old_code: str) -> str:
        """Use safe string function."""
        return "strncpy(dest, src, sizeof(dest) - 1)\ndest[sizeof(dest) - 1] = '\\0'"

    def _fix_isr_blocking(self, old_code: str) -> str:
        """Remove blocking operation from ISR."""
        return "/* Set flag for main loop to handle */\nflag_set = 1"

    def _fix_stack_overflow(self, old_code: str) -> str:
        """Use static allocation for large buffers."""
        return "static uint8_t buffer[8192]  /* Placed in .bss section */"

    def _fix_dead_code(self, old_code: str) -> str:
        """Remove or deprecate unused code."""
        return "@deprecated('This will be removed in v2.0')\ndef unused_func():"

    def _fix_unused_parameter(self, old_code: str) -> str:
        """Prefix unused parameter with underscore."""
        return "def func(_unused_param):"

    # ─── Template and pattern loading ───────────────────────────────────────────

    def _load_templates(self) -> dict[str, FixTemplate]:
        """Load fix templates for known rules."""
        return {
            "ML001": FixTemplate(
                rule_id="ML001",
                description="Use fit_transform() instead of fit()",
                replacement="X_train_scaled = scaler.fit_transform(X_train)\nX_test_scaled = scaler.transform(X_test)",
                risk="low",
                automated=True,
                explanation="fit_transform() combines fit and transform, preventing data leakage",
            ),
            "SEC001": FixTemplate(
                rule_id="SEC001",
                description="Remove hardcoded secret, use environment variable",
                replacement="api_key = os.environ.get('API_KEY')",
                risk="medium",
                automated=False,
                requires_review=True,
                explanation="Secrets should never be hardcoded in source code",
            ),
            "QUAL003": FixTemplate(
                rule_id="QUAL003",
                description="Catch specific exception instead of bare except",
                replacement="except ValueError as e:\n    logger.error(f'Value error: {e}')",
                risk="low",
                automated=True,
                explanation="Specific exception handling prevents masking unexpected errors",
            ),
            "QUAL006": FixTemplate(
                rule_id="QUAL006",
                description="Replace print with logging",
                replacement="import logging\nlogger = logging.getLogger(__name__)\nlogger.info('message')",
                risk="low",
                automated=True,
                explanation="Logging provides better control over output in production",
            ),
            "QUAL007": FixTemplate(
                rule_id="QUAL007",
                description="Define named constant for magic number",
                replacement="MAX_BUFFER_SIZE = 4096\nif size > MAX_BUFFER_SIZE:",
                risk="low",
                automated=True,
                explanation="Named constants improve code readability and maintainability",
            ),
            "SEC002": FixTemplate(
                rule_id="SEC002",
                description="Use parameterized query to prevent SQL injection",
                replacement="cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))",
                risk="low",
                automated=True,
                explanation="Parameterized queries prevent SQL injection attacks",
            ),
            "SEC003": FixTemplate(
                rule_id="SEC003",
                description="Use shell=False or list arguments",
                replacement="subprocess.run(cmd.split(), shell=False)",
                risk="medium",
                automated=False,
                requires_review=True,
                explanation="Avoiding shell=True prevents command injection vulnerabilities",
            ),
            "EMB001": FixTemplate(
                rule_id="EMB001",
                description="Add NULL check before dereferencing pointer",
                replacement="if (ptr != NULL) {\n    ptr->value;\n}",
                risk="low",
                automated=True,
                explanation="NULL checks prevent dereference crashes",
            ),
            "EMB004": FixTemplate(
                rule_id="EMB004",
                description="Use safe string function to prevent buffer overflow",
                replacement="strncpy(dest, src, sizeof(dest) - 1);\ndest[sizeof(dest) - 1] = '\\0';",
                risk="low",
                automated=True,
                explanation="Safe string functions prevent buffer overflow vulnerabilities",
            ),
            "EMB007": FixTemplate(
                rule_id="EMB007",
                description="Remove blocking operation from ISR",
                replacement="/* Set flag for main loop to handle */\nflag_set = 1;",
                risk="medium",
                automated=False,
                requires_review=True,
                explanation="ISRs should not block; use flags for main loop processing",
            ),
            "EMB014": FixTemplate(
                rule_id="EMB014",
                description="Use static allocation for large buffers",
                replacement="static uint8_t buffer[8192];  /* Placed in .bss section */",
                risk="low",
                automated=True,
                explanation="Static allocation prevents stack overflow in embedded systems",
            ),
        }

    def _load_rule_patterns(self) -> dict[str, dict]:
        """Load rule-based pattern alternatives."""
        return {
            "SEC001": {
                "alternatives": [
                    {
                        "id": "env",
                        "description": "Use environment variable",
                        "replacement": "import os\nSECRET = os.environ.get('SECRET_NAME', 'default')",
                        "risk": "medium",
                        "confidence": 0.9,
                        "explanation": "Environment variables are the simplest secure approach",
                        "automated": False,
                        "requires_review": True,
                    },
                    {
                        "id": "vault",
                        "description": "Use secrets manager (Vault/AWS)",
                        "replacement": "from your_secret_manager import get_secret\nSECRET = get_secret('secret-name')",
                        "risk": "low",
                        "confidence": 0.85,
                        "explanation": "Centralized secrets management with rotation support",
                        "automated": False,
                        "requires_review": True,
                    },
                ]
            },
            "QUAL003": {
                "alternatives": [
                    {
                        "id": "specific",
                        "description": "Catch specific exception type",
                        "replacement": "except ValueError as e:\n    logger.error(f'Value error: {e}')",
                        "risk": "low",
                        "confidence": 0.95,
                        "explanation": "Specific exceptions are easier to debug and handle",
                        "automated": True,
                        "requires_review": False,
                    },
                    {
                        "id": "reraise",
                        "description": "Catch, log, and re-raise",
                        "replacement": "except Exception as e:\n    logger.error(f'Unexpected error: {e}')\n    raise",
                        "risk": "low",
                        "confidence": 0.9,
                        "explanation": "Logging before re-raising preserves error context",
                        "automated": True,
                        "requires_review": False,
                    },
                ]
            },
        }

    def _load_common_patterns(self) -> dict[str, list[dict]]:
        """Load common fix patterns for various rule IDs."""
        return {
            "QUAL006": [
                {
                    "description": "Use Python logging module",
                    "replacement": "import logging\nlogger = logging.getLogger(__name__)\nlogger.info('message')",
                    "risk": "low",
                    "confidence": 0.9,
                    "explanation": "Logging provides configurable output levels",
                    "automated": True,
                },
                {
                    "description": "Use structlog for structured logging",
                    "replacement": "import structlog\nlog = structlog.get_logger()\nlog.info('message', key=value)",
                    "risk": "low",
                    "confidence": 0.8,
                    "explanation": "Structured logging is easier to parse and analyze",
                    "automated": False,
                    "requires_review": True,
                },
            ],
            "EMB001": [
                {
                    "description": "Add explicit NULL check",
                    "replacement": "if (ptr != NULL) {\n    /* Safe to dereference */\n}",
                    "risk": "low",
                    "confidence": 0.95,
                    "explanation": "Explicit NULL checks are defensive programming",
                    "automated": True,
                },
                {
                    "description": "Use assert for debugging",
                    "replacement": "assert(ptr != NULL, 'Pointer must not be NULL')",
                    "risk": "low",
                    "confidence": 0.85,
                    "explanation": "Asserts help catch bugs during development",
                    "automated": True,
                },
            ],
        }


# ─── Helper Functions ──────────────────────────────────────────────────────────


def _generate_unified_diff(
    old_code: str,
    new_code: str,
    file_path: str = "file.py",
) -> str:
    """Generate a unified diff string."""
    old_lines = old_code.splitlines(keepends=True)
    new_lines = new_code.splitlines(keepends=True)

    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        lineterm="\n",
    )

    return "".join(diff)


def create_engine(
    config: Optional[SuggestionConfig] = None,
    llm_provider: Optional[LLMProviderInterface] = None,
) -> UnifiedSuggestionEngine:
    """Factory function to create a suggestion engine."""
    return UnifiedSuggestionEngine(config=config, llm_provider=llm_provider)

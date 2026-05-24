"""Root Cause Analyzer - Distinguishes symptom fix from root cause fix.

PROBLEM:
AI fix bug nhưng chỉ fix symptom:
- "Buffer overflow" → tăng buffer size (symptom relief, không fix root cause)
- "Timeout" → thêm retry (mask symptom, không fix hang)
- "Null pointer" → thêm null check (handle symptom, không fix initialization)

SOLUTION:
┌─────────────────────────────────────────────────────────────────┐
│                     RootCauseAnalyzer                                │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Symptom Collector                                          │  │
│  │  - Error messages                                         │  │
│  │  - Crash reports                                          │  │
│  │  - Test failures                                          │  │
│  │  - Performance degradation                                │  │
│  └───────────────────────────────────────────────────────────┘  │
│                           ↓                                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Question Generator                                        │  │
│  │  - WHY questions (5 whys pattern)                        │  │
│  │  - Dependency questions                                   │  │
│  │  - Sequence questions                                     │  │
│  └───────────────────────────────────────────────────────────┘  │
│                           ↓                                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Root Cause Hypothesis Generator                          │  │
│  │  - Generate candidate root causes                         │  │
│  │  - Score by evidence strength                             │  │
│  │  - Validate against codebase                              │  │
│  └───────────────────────────────────────────────────────────┘  │
│                           ↓                                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Fix Validator                                            │  │
│  │  - Does fix address root cause?                          │  │
│  │  - Does fix prevent recurrence?                          │  │
│  │  - Does fix break anything else?                         │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘

KEY FEATURES:
1. 5 Whys analysis - drill down to root cause
2. Dependency tracing - understand causal chains
3. Fix validation - verify fix addresses root cause
4. Impact analysis - understand what fix affects
5. Prevention check - will fix prevent recurrence?
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class RootCauseType(Enum):
    """Types of root causes."""
    INITIALIZATION = "initialization"
    TIMING = "timing"
    MEMORY = "memory"
    CONCURRENCY = "concurrency"
    CONFIGURATION = "configuration"
    INTERFACE = "interface"
    LOGIC = "logic"
    RESOURCE = "resource"
    DATA = "data"
    UNKNOWN = "unknown"


@dataclass
class Symptom:
    """Observed symptom."""
    symptom_id: str
    description: str
    severity: str
    occurrence_count: int = 1
    first_observed: Optional[float] = None
    last_observed: Optional[float] = None


@dataclass
class Question:
    """Analysis question."""
    question: str
    category: str  # "why", "what", "when", "where"
    depth: int  # How many whys deep


@dataclass
class RootCauseHypothesis:
    """Hypothesis for root cause."""
    hypothesis_id: str
    description: str
    cause_type: RootCauseType
    confidence: float  # 0-1
    evidence: list[str] = field(default_factory=list)
    questions_answered: list[str] = field(default_factory=list)
    code_evidence: list[str] = field(default_factory=list)


@dataclass
class FixValidation:
    """Validation of proposed fix."""
    fix_description: str
    addresses_root_cause: bool
    prevents_recurrence: bool
    is_symptom_relief: bool
    regression_risk: str  # "low", "medium", "high"
    additional_changes_needed: list[str] = field(default_factory=list)
    validation_notes: list[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    """Result of root cause analysis."""
    symptoms: list[Symptom]
    root_cause: Optional[RootCauseHypothesis]
    hypotheses: list[RootCauseHypothesis]
    questions: list[Question]
    fix_validation: Optional[FixValidation]
    summary: str


class FiveWhysAnalyzer:
    """
    Implements 5 Whys analysis for root cause determination.
    """

    @staticmethod
    def generate_questions(symptom: Symptom, depth: int = 0) -> list[Question]:
        """Generate WHY questions to drill down."""
        if depth >= 5:
            return []

        questions = []

        # Pattern-based question generation
        symptom_lower = symptom.description.lower()

        if "overflow" in symptom_lower:
            questions.append(Question(
                question="WHY did the buffer overflow?",
                category="why",
                depth=depth,
            ))
            if depth < 4:
                questions.append(Question(
                    question="WHY did the data exceed buffer capacity?",
                    category="why",
                    depth=depth + 1,
                ))

        if "timeout" in symptom_lower:
            questions.append(Question(
                question="WHY did the operation timeout?",
                category="why",
                depth=depth,
            ))

        if "null" in symptom_lower or "None" in symptom_lower:
            questions.append(Question(
                question="WHY is the pointer null?",
                category="why",
                depth=depth,
            ))

        if "hang" in symptom_lower or "deadlock" in symptom_lower:
            questions.append(Question(
                question="WHY did the system hang?",
                category="why",
                depth=depth,
            ))

        if "error" in symptom_lower:
            questions.append(Question(
                question="WHY did the error occur?",
                category="why",
                depth=depth,
            ))

        # Default questions
        if not questions:
            questions.append(Question(
                question=f"WHY did this happen? ({symptom.description})",
                category="why",
                depth=depth,
            ))

        return questions

    @staticmethod
    def answer_question(question: Question, code_context: str) -> list[str]:
        """Generate possible answers based on code context."""
        answers = []

        question_lower = question.question.lower()

        if "overflow" in question_lower:
            answers.append("Data written without bounds checking")
            answers.append("Buffer size insufficient for worst case")
            answers.append("Index not validated before access")
            if "increment" in code_context.lower() or "++" in code_context:
                answers.append("Index incremented past buffer end")

        if "timeout" in question_lower:
            answers.append("Operation waiting for external resource")
            answers.append("Hardware not responding")
            answers.append("Clock/peripheral not configured")
            answers.append("Interrupt not firing")

        if "null" in question_lower:
            answers.append("Handle never initialized")
            answers.append("Initialization failed silently")
            answers.append("Handle freed prematurely")
            answers.append("Wrong handle passed")

        if "hang" in question_lower or "deadlock" in question_lower:
            answers.append("Circular wait on mutexes")
            answers.append("Task waiting on semaphore held by itself")
            answers.append("ISR blocking on resource")
            answers.append("Priority inversion")

        return answers


class RootCauseAnalyzer:
    """
    Analyzes symptoms to find root causes.

    Uses:
    1. 5 Whys for causal chain
    2. Pattern matching for common root causes
    3. Fix validation to ensure root cause is addressed
    """

    # Common root cause patterns
    ROOT_CAUSE_PATTERNS = {
        "buffer_overflow": {
            "patterns": [r"overflow", r"out.of.bounds", r"buffer.too.small"],
            "causes": [
                "Missing bounds check before write",
                "Buffer size insufficient for data",
                "Index not reset after overflow",
                "Off-by-one in loop condition",
            ],
            "fix_validation": "Does fix add bounds check or increase buffer AND reset index?",
        },
        "timeout": {
            "patterns": [r"timeout", r"timed.out", r"too.slow"],
            "causes": [
                "Clock not enabled",
                "Peripheral not initialized",
                "Interrupt not enabled",
                "Resource deadlock",
                "Infinite loop in critical section",
            ],
            "fix_validation": "Does fix address the actual blocking cause, not just add retry?",
        },
        "null_pointer": {
            "patterns": [r"null", r"None", r"uninitialized"],
            "causes": [
                "Handle never initialized",
                "Init function not called",
                "Init failed but not checked",
                "Handle freed but still used",
            ],
            "fix_validation": "Does fix ensure init is called and checked?",
        },
        "deadlock": {
            "patterns": [r"deadlock", r"hang", r"blocked.forever"],
            "causes": [
                "Mutex acquired in wrong order",
                "ISR trying to acquire mutex",
                "Priority inversion",
                "Missing timeout on lock",
            ],
            "fix_validation": "Does fix prevent circular wait or add timeout?",
        },
        "race_condition": {
            "patterns": [r"race", r"concurrent", r"thread.safe"],
            "causes": [
                "Shared resource not protected",
                "Non-atomic read-modify-write",
                "Check-then-act not atomic",
                "Memory visibility issue",
            ],
            "fix_validation": "Does fix add proper synchronization?",
        },
        "memory_leak": {
            "patterns": [r"leak", r"out.of.memory", r"malloc.failed"],
            "causes": [
                "Memory allocated but never freed",
                "Pointer to heap memory lost",
                "Allocation in loop without free",
                "ISR allocating memory",
            ],
            "fix_validation": "Does fix ensure every alloc has matching free?",
        },
    }

    # Mapping from pattern keys to RootCauseType
    CAUSE_TYPE_MAP = {
        "buffer_overflow": RootCauseType.MEMORY,
        "timeout": RootCauseType.TIMING,
        "null_pointer": RootCauseType.INITIALIZATION,
        "deadlock": RootCauseType.CONCURRENCY,
        "race_condition": RootCauseType.CONCURRENCY,
        "memory_leak": RootCauseType.MEMORY,
    }

    def __init__(self) -> None:
        self._symptoms: list[Symptom] = []
        self._analysis_result: Optional[AnalysisResult] = None

    def add_symptom(self, symptom: Symptom) -> None:
        """Add observed symptom."""
        self._symptoms.append(symptom)

    def analyze(
        self,
        symptom: Symptom,
        code_context: Optional[str] = None,
    ) -> AnalysisResult:
        """
        Analyze symptom to find root cause.

        Returns:
            AnalysisResult with hypotheses and root cause
        """
        self._symptoms.append(symptom)

        hypotheses: list[RootCauseHypothesis] = []
        questions: list[Question] = []

        # Generate 5 Whys questions
        why_questions = FiveWhysAnalyzer.generate_questions(symptom)
        questions.extend(why_questions)

        # Match symptom patterns
        symptom_lower = symptom.description.lower()

        for cause_type, info in self.ROOT_CAUSE_PATTERNS.items():
            for pattern in info["patterns"]:
                if re.search(pattern, symptom_lower, re.IGNORECASE):
                    # Found matching pattern
                    for cause in info["causes"]:
                        mapped_type = self.CAUSE_TYPE_MAP.get(cause_type, RootCauseType.UNKNOWN)
                        hypothesis = RootCauseHypothesis(
                            hypothesis_id=f"{cause_type}_{len(hypotheses)}",
                            description=cause,
                            cause_type=mapped_type,
                            confidence=0.5,  # Initial confidence
                            evidence=[f"Matches pattern: {pattern}"],
                        )

                        # Score based on code context
                        if code_context:
                            if cause.lower() in code_context.lower():
                                hypothesis.confidence += 0.3
                                hypothesis.code_evidence.append(f"Found '{cause}' in code")

                            # Check for fixes
                            if "bounds" in cause and "check" in code_context.lower():
                                hypothesis.confidence += 0.2
                                hypothesis.evidence.append("Bounds check found")

                        hypotheses.append(hypothesis)

        # Sort by confidence
        hypotheses.sort(key=lambda h: -h.confidence)

        # Generate additional questions based on top hypothesis
        if hypotheses:
            top = hypotheses[0]
            additional_qs = self._generate_followup_questions(top, code_context or "")
            questions.extend(additional_qs)

        # Determine root cause (highest confidence)
        root_cause = hypotheses[0] if hypotheses else None

        self._analysis_result = AnalysisResult(
            symptoms=self._symptoms,
            root_cause=root_cause,
            hypotheses=hypotheses,
            questions=questions,
            fix_validation=None,
            summary=self._generate_summary(root_cause, hypotheses),
        )

        return self._analysis_result

    def _generate_followup_questions(
        self,
        hypothesis: RootCauseHypothesis,
        code_context: str,
    ) -> list[Question]:
        """Generate follow-up questions based on hypothesis."""
        questions = []

        cause_lower = hypothesis.description.lower()

        if "not initialized" in cause_lower or "init" in cause_lower:
            questions.append(Question(
                question="Is initialization called before use?",
                category="where",
                depth=1,
            ))
            questions.append(Question(
                question="Is initialization return value checked?",
                category="what",
                depth=1,
            ))

        if "not enabled" in cause_lower or "clock" in cause_lower:
            questions.append(Question(
                question="Is RCC peripheral clock enabled?",
                category="what",
                depth=1,
            ))

        if "bounds" in cause_lower or "check" in cause_lower:
            questions.append(Question(
                question="Is there a bounds check before the access?",
                category="where",
                depth=1,
            ))
            questions.append(Question(
                question="Is the index reset after processing?",
                category="what",
                depth=1,
            ))

        return questions

    def _generate_summary(
        self,
        root_cause: Optional[RootCauseHypothesis],
        hypotheses: list[RootCauseHypothesis],
    ) -> str:
        """Generate analysis summary."""
        if not root_cause:
            return "Unable to determine root cause. More information needed."

        summary = f"Most likely root cause ({root_cause.confidence:.0%} confidence):\n"
        summary += f"  {root_cause.description}\n\n"

        summary += "Evidence:\n"
        for evidence in root_cause.evidence[:3]:
            summary += f"  - {evidence}\n"

        if len(hypotheses) > 1:
            summary += f"\nAlternative hypotheses:\n"
            for h in hypotheses[1:4]:
                summary += f"  - {h.description} ({h.confidence:.0%})\n"

        return summary

    def validate_fix(
        self,
        fix_description: str,
        root_cause: Optional[RootCauseHypothesis],
    ) -> FixValidation:
        """
        Validate if fix addresses root cause.

        Returns:
            FixValidation with analysis
        """
        if not root_cause:
            return FixValidation(
                fix_description=fix_description,
                addresses_root_cause=False,
                prevents_recurrence=False,
                is_symptom_relief=True,
                regression_risk="unknown",
                validation_notes=["Cannot validate - root cause unknown"],
            )

        fix_lower = fix_description.lower()
        cause_lower = root_cause.description.lower()

        validation = FixValidation(
            fix_description=fix_description,
            addresses_root_cause=False,
            prevents_recurrence=False,
            is_symptom_relief=False,
            regression_risk="low",
        )

        # Check for symptom relief patterns
        symptom_relief_patterns = [
            "increase size", "increase buffer", "larger buffer",
            "add timeout", "add retry", "ignore error",
            "catch exception", "suppress warning",
        ]

        for pattern in symptom_relief_patterns:
            if pattern in fix_lower:
                validation.is_symptom_relief = True
                validation.validation_notes.append(
                    f"Fix appears to treat symptom ({pattern})"
                )

        # Check if fix addresses root cause
        root_cause_keywords = cause_lower.split()
        fix_addresses = sum(1 for kw in root_cause_keywords if kw in fix_lower)

        if fix_addresses >= 2:
            validation.addresses_root_cause = True
            validation.validation_notes.append("Fix matches root cause keywords")

        # Check for regression risk
        risky_patterns = ["global", "shared", "static", "interrupt"]
        for pattern in risky_patterns:
            if pattern in fix_lower:
                validation.regression_risk = "medium"
                validation.validation_notes.append(
                    f"Fix modifies {pattern} - check for regressions"
                )

        return validation

    def generate_fix_guidance(self, root_cause: RootCauseHypothesis) -> str:
        """Generate guidance for fixing the root cause."""
        cause_lower = root_cause.description.lower()
        cause_type = root_cause.cause_type.value

        guidance = f"Root Cause: {root_cause.description}\n"
        guidance += f"Type: {cause_type}\n\n"

        # Type-specific guidance
        type_guidance = {
            "initialization": [
                "1. Verify init function is called",
                "2. Check init return value",
                "3. Ensure correct init sequence",
                "4. Add init status check in constructor",
            ],
            "memory": [
                "1. Add bounds check before write",
                "2. Validate index before access",
                "3. Reset index after buffer flush",
                "4. Consider circular buffer",
            ],
            "timing": [
                "1. Verify clock configuration",
                "2. Check peripheral enable flags",
                "3. Ensure interrupt NVIC enabled",
                "4. Add timeout with proper handling",
            ],
            "concurrency": [
                "1. Review mutex acquisition order",
                "2. Add timeout to locks",
                "3. Check for ISR lock usage",
                "4. Verify task priorities",
            ],
            "configuration": [
                "1. Verify clock tree setup",
                "2. Check peripheral config",
                "3. Validate pin multiplexing",
                "4. Review power settings",
            ],
        }

        if cause_type in type_guidance:
            guidance += "Fix Steps:\n"
            for step in type_guidance[cause_type]:
                guidance += f"  {step}\n"

        guidance += "\nPrevention:\n"
        guidance += "  - Add assertions for invariants\n"
        guidance += "  - Write unit tests for edge cases\n"
        guidance += "  - Add static analysis checks\n"

        return guidance


def quick_analyze(symptom: str, code_context: Optional[str] = None) -> str:
    """
    Quick root cause analysis helper.

    Usage:
        result = quick_analyze("Buffer overflow in UART ISR", code)
    """
    analyzer = RootCauseAnalyzer()

    symptom_obj = Symptom(
        symptom_id="quick_1",
        description=symptom,
        severity="high",
    )

    result = analyzer.analyze(symptom_obj, code_context)

    output = f"Analysis: {result.summary}\n\n"

    if result.root_cause:
        output += analyzer.generate_fix_guidance(result.root_cause)

    return output

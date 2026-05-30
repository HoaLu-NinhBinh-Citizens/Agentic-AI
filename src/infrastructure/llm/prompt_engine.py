"""Advanced prompt engineering for LLM-powered code analysis.

Generates context-aware, high-quality prompts with domain-specific
templates for ML, security, embedded systems, and general code review.
"""

from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class PromptContext:
    """Context for prompt generation."""
    file_path: Optional[Path] = None
    file_content: str = ""
    language: str = "python"
    surrounding_code: str = ""
    findings: list[dict] = field(default_factory=list)
    project_type: str = "general"
    framework: str = ""
    imports: list[str] = field(default_factory=list)


@dataclass
class PromptTemplate:
    """A prompt template with variables."""
    system: str
    user: str
    examples: list[tuple[str, str]] = field(default_factory=list)

    def format(self, **kwargs) -> tuple[str, str]:
        """Format template with provided variables."""
        system = self.system.format(**kwargs)
        user = self.user.format(**kwargs)
        return system, user


class PromptEngine:
    """Advanced prompt engineering engine.

    Generates context-aware prompts for code analysis with support for:
    - Code review (general, ML-specific, embedded-specific)
    - Fix generation
    - Security scanning
    - Refactoring suggestions
    - Code explanation
    """

    def __init__(self):
        self._templates = self._build_templates()

    def _build_templates(self) -> dict[str, PromptTemplate]:
        """Build all prompt templates."""
        return {
            "code_review": self._build_code_review_template(),
            "fix_generation": self._build_fix_template(),
            "explanation": self._build_explanation_template(),
            "security_scan": self._build_security_template(),
            "ml_analysis": self._build_ml_template(),
            "embedded_analysis": self._build_embedded_template(),
            "refactoring": self._build_refactor_template(),
        }

    def _build_code_review_template(self) -> PromptTemplate:
        return PromptTemplate(
            system="""You are an expert code reviewer with deep knowledge of:
- Software engineering best practices
- Design patterns and SOLID principles
- Security vulnerabilities and secure coding
- Performance optimization
- Code maintainability and readability

Analyze the provided code and identify issues ranging from:
- Critical bugs that could cause crashes or data loss
- Security vulnerabilities (injection, XSS, SQL injection, etc.)
- Performance anti-patterns (N+1 queries, memory leaks, etc.)
- Code smells and maintainability issues
- Best practice violations

Respond ONLY with valid JSON array of findings.""",
            user="""Review this {language} code:

```{language}
{code}
```

Context:
- File: {file_path}
- Project type: {project_type}
- Framework: {framework}
- Imports: {imports}

Surrounding code (for context):
```{language}
{surrounding}
```

Find all issues and respond with JSON array:
```json
[
  {{
    "rule_id": "UNIQUE_ID",
    "severity": "CRITICAL|HIGH|MEDIUM|LOW|INFO",
    "title": "Brief title",
    "message": "What the issue is",
    "explanation": "Why this is a problem",
    "line": {line_number},
    "confidence": 0.0-1.0,
    "best_practice": "What should be done instead"
  }}
]
```"""
        )

    def _build_fix_template(self) -> PromptTemplate:
        return PromptTemplate(
            system="""You are an expert programmer specializing in generating precise, safe code fixes.

For each issue:
1. Generate the minimal fix that addresses the problem
2. Ensure the fix doesn't introduce new issues
3. Consider edge cases and error handling
4. Follow language idioms and best practices

Respond ONLY with valid JSON.""",
            user="""Generate a fix for this issue in {file_path}:

Issue: {issue_title}
Severity: {severity}
Line: {line_number}

Current code:
```{language}
{old_code}
```

Context around the issue:
```{language}
{surrounding}
```

Generate fix with multiple options:
```json
[
  {{
    "option_id": 1,
    "description": "Brief description",
    "risk": "LOW|MEDIUM|HIGH",
    "confidence": 0.0-1.0,
    "old_code": "problematic code",
    "new_code": "fixed code",
    "explanation": "Why this fix works"
  }}
]
```"""
        )

    def _build_explanation_template(self) -> PromptTemplate:
        return PromptTemplate(
            system="""You are a patient teacher who explains code issues clearly.

For each explanation:
1. Start with the core concept
2. Use simple language
3. Provide a concrete example
4. Give actionable advice

Keep explanations concise but complete.""",
            user="""Explain this code issue:

**Rule:** {rule_id}
**Severity:** {severity}
**File:** {file_path}:{line_number}

**Issue:** {issue_message}

**Problematic Code:**
```{language}
{old_code}
```

Provide a clear explanation that:
1. Explains what the issue is
2. Why it matters
3. How to fix it
4. Best practices to avoid it"""
        )

    def _build_security_template(self) -> PromptTemplate:
        return PromptTemplate(
            system="""You are a security expert specializing in application security.

Focus on:
- Injection attacks (SQL, XSS, Command, LDAP, etc.)
- Authentication and authorization flaws
- Sensitive data exposure
- Cryptographic weaknesses
- Common OWASP Top 10 vulnerabilities
- Supply chain security

Be thorough and think like an attacker.""",
            user="""Perform security analysis on this code:

```{language}
{code}
```

Context:
- File: {file_path}
- Project type: {project_type}
- Imports: {imports}

Security issues to look for:
1. Hardcoded secrets (passwords, API keys, tokens)
2. SQL/Command injection vulnerabilities
3. XSS and input validation issues
4. Authentication/authorization problems
5. Insecure cryptographic usage
6. Path traversal vulnerabilities
7. Deserialization issues

Report as JSON:
```json
[
  {{
    "cwe_id": "CWE-XX",
    "severity": "CRITICAL|HIGH|MEDIUM",
    "title": "CWE title",
    "description": "Detailed description",
    "evidence": "Where it occurs in code",
    "exploitation": "How an attacker could exploit",
    "remediation": "How to fix"
  }}
]
```"""
        )

    def _build_ml_template(self) -> PromptTemplate:
        return PromptTemplate(
            system="""You are an ML engineer with expertise in:
- Data preprocessing and feature engineering
- Model training and evaluation
- ML frameworks (PyTorch, TensorFlow, scikit-learn)
- MLOps best practices
- Common ML pitfalls (data leakage, overfitting, etc.)

Focus on:
- Data leakage detection
- Proper train/test splits
- Model evaluation metrics
- Hyperparameter tuning
- GPU/memory efficiency
- Reproducibility""",
            user="""Analyze this ML code for issues:

```{python}
{code}
```

Context:
- Project type: {project_type}
- Framework: {framework}

Check for:
1. **Data Leakage**: Scaler.fit() before split, target leakage, etc.
2. **Device Mismatch**: Model on GPU, data on CPU
3. **Missing no_grad**: In inference or evaluation
4. **Wrong Loss Function**: CrossEntropy vs BCELoss for task type
5. **Missing Seeds**: Non-reproducible training
6. **Evaluation Issues**: Wrong metrics, data leakage in CV

Report as JSON:
```json
[
  {{
    "rule_id": "ML001-007",
    "severity": "CRITICAL|HIGH|MEDIUM",
    "title": "Issue title",
    "description": "Detailed description",
    "line": {line},
    "confidence": 0.0-1.0,
    "impact": "Why this matters for model performance",
    "fix": "How to fix"
  }}
]
```"""
        )

    def _build_embedded_template(self) -> PromptTemplate:
        return PromptTemplate(
            system="""You are an embedded systems engineer with expertise in:
- MCU programming (ARM Cortex-M, AVR, etc.)
- Real-time operating systems (FreeRTOS, Zephyr)
- Interrupt handling and ISR design
- Memory management (stack, heap, DMA)
- Peripheral configuration (GPIO, UART, SPI, I2C, ADC)
- Automotive protocols (CAN, LIN, UDS)
- Safety-critical coding (MISRA, AUTOSAR)

Focus on:
- ISR safety and efficiency
- Memory management issues
- Timing constraints
- Peripheral initialization
- Hardware abstraction layers""",
            user="""Analyze this embedded C/C++ code:

```{c}
{code}
```

Context:
- File: {file_path}
- MCU: {mcu_type}
- RTOS: {rtos}

Check for:
1. **Infinite loops** without exit conditions
2. **Blocking in ISR** (HAL_Delay, printf, mutex)
3. **Stack overflow** in recursive functions
4. **Race conditions** with shared resources
5. **Missing volatile** for hardware registers
6. **DMA configuration** issues
7. **Interrupt priority** problems

Report as JSON:
```json
[
  {{
    "rule_id": "EMB001-015",
    "severity": "CRITICAL|HIGH|MEDIUM",
    "title": "Issue title",
    "description": "What the problem is",
    "line": {line},
    "why_matters": "Impact on embedded system",
    "suggestion": "How to fix"
  }}
]
```"""
        )

    def _build_refactor_template(self) -> PromptTemplate:
        return PromptTemplate(
            system="""You are a software architect specializing in code refactoring.

Focus on:
- Improving code structure without changing behavior
- Applying SOLID principles
- Extracting reusable components
- Simplifying complex logic
- Improving testability
- Reducing technical debt

Preserve original behavior while improving design.""",
            user="""Suggest refactoring for this code:

```{language}
{code}
```

Goals:
1. Improve readability
2. Reduce complexity
3. Increase maintainability
4. Enhance testability

Suggest specific refactorings:
```json
[
  {{
    "type": "extract_method|rename|split_class|etc",
    "title": "Refactoring suggestion",
    "before": "current code",
    "after": "refactored code",
    "benefits": ["benefit1", "benefit2"],
    "risks": ["risk1"] or []
  }}
]
```"""
        )

    def generate_prompt(
        self,
        template_name: str,
        context: PromptContext,
        **kwargs
    ) -> tuple[str, str]:
        """Generate a formatted prompt from template and context.

        Args:
            template_name: Name of the template to use
            context: Prompt context with code and metadata
            **kwargs: Additional template variables

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        template = self._templates.get(template_name)
        if not template:
            available = list(self._templates.keys())
            raise ValueError(
                f"Unknown template: {template_name}. Available: {available}"
            )

        variables = self._build_variables(context, **kwargs)
        return template.format(**variables)

    def _build_variables(
        self,
        context: PromptContext,
        **kwargs
    ) -> dict[str, str]:
        """Build template variables from context."""
        return {
            "language": context.language,
            "file_path": str(context.file_path or "unknown"),
            "code": context.file_content,
            "surrounding": context.surrounding_code,
            "project_type": context.project_type,
            "framework": context.framework,
            "imports": ", ".join(context.imports[:20]),
            **kwargs
        }

    def generate_code_review(
        self,
        context: PromptContext,
        line_number: int
    ) -> tuple[str, str]:
        """Generate code review prompt for a specific line.

        Args:
            context: Prompt context
            line_number: Line number to focus on

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        lines = context.file_content.split("\n")
        old_code = ""
        if 0 <= line_number - 1 < len(lines):
            old_code = lines[line_number - 1]

        return self.generate_prompt(
            "code_review",
            context,
            line_number=line_number,
            old_code=old_code
        )

    def generate_fix(
        self,
        context: PromptContext,
        issue: dict
    ) -> tuple[str, str]:
        """Generate fix prompt for an issue.

        Args:
            context: Prompt context
            issue: Issue dictionary with title, severity, line, old_code

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        line = issue.get("line", 1)
        surrounding = self._get_surrounding(context.file_content, line)

        return self.generate_prompt(
            "fix_generation",
            context,
            issue_title=issue.get("title", ""),
            severity=issue.get("severity", "MEDIUM"),
            line_number=issue.get("line", 0),
            old_code=issue.get("old_code", ""),
            surrounding=surrounding
        )

    def generate_security_scan(
        self,
        context: PromptContext
    ) -> tuple[str, str]:
        """Generate security scan prompt.

        Args:
            context: Prompt context

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        return self.generate_prompt("security_scan", context)

    def generate_ml_analysis(
        self,
        context: PromptContext
    ) -> tuple[str, str]:
        """Generate ML-specific analysis prompt.

        Args:
            context: Prompt context

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        return self.generate_prompt("ml_analysis", context)

    def generate_explanation(
        self,
        context: PromptContext,
        finding: dict
    ) -> tuple[str, str]:
        """Generate explanation prompt for a finding.

        Args:
            context: Prompt context
            finding: Finding dictionary

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        return self.generate_prompt(
            "explanation",
            context,
            rule_id=finding.get("rule_id", "UNKNOWN"),
            severity=finding.get("severity", "MEDIUM"),
            line_number=finding.get("line", 0),
            issue_message=finding.get("message", ""),
            old_code=finding.get("old_code", "")
        )

    def _get_surrounding(
        self,
        content: str,
        line: int,
        radius: int = 5
    ) -> str:
        """Get surrounding code context.

        Args:
            content: Full file content
            line: Line number to center on (1-indexed)
            radius: Number of lines before/after to include

        Returns:
            Surrounding code snippet
        """
        lines = content.split("\n")
        start = max(0, line - radius - 1)
        end = min(len(lines), line + radius)
        return "\n".join(lines[start:end])

    def list_templates(self) -> list[str]:
        """List available template names."""
        return list(self._templates.keys())

    def get_template(self, name: str) -> PromptTemplate | None:
        """Get a template by name."""
        return self._templates.get(name)

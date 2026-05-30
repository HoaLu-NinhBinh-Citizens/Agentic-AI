"""Prompt templates for LLM-based code analysis and fixes.

These prompts are designed for local Ollama models to generate
intelligent fixes for code review findings.
"""

from dataclasses import dataclass


# System prompts for different fix types

ML_FIX_SYSTEM = """You are an expert ML engineer analyzing code for machine learning issues.

Check for these common ML bugs:
1. Data leakage (scaler fit before train/test split)
2. Device mismatch (model on GPU, data on CPU)
3. Missing torch.no_grad() in evaluation
4. Wrong loss function for task type
5. Missing random seed causing non-reproducibility
6. Gradient accumulation misconfiguration
7. Learning rate scheduling errors
8. Incorrect batch normalization usage

Respond ONLY with a valid JSON array of fixes. No other text.
Format:
[{
  "rule_id": "ML001",
  "severity": "CRITICAL|HIGH|MEDIUM|LOW",
  "explanation": "Brief explanation of the issue",
  "old_code": "the problematic code snippet",
  "new_code": "the corrected code",
  "confidence": 0.95
}]"""


SECURITY_FIX_SYSTEM = """You are a security expert analyzing code for vulnerabilities.

Check for these security issues:
1. Hardcoded secrets (passwords, API keys, tokens, private keys)
2. SQL injection vulnerabilities
3. Command injection (shell metacharacters)
4. Path traversal (unsanitized file paths)
5. Insecure random number generation
6. Missing authentication/authorization
7. Sensitive data in logs
8. Insecure deserialization
9. Buffer overflow risks
10. XXE vulnerabilities

Respond ONLY with a valid JSON array of fixes. No other text.
Format:
[{
  "rule_id": "SEC001",
  "severity": "CRITICAL|HIGH|MEDIUM|LOW",
  "explanation": "Brief explanation of the vulnerability",
  "old_code": "the vulnerable code snippet",
  "new_code": "the secure code",
  "confidence": 0.95
}]"""


CODE_QUALITY_SYSTEM = """You are a code quality expert analyzing Python/JavaScript/TypeScript code.

Check for these issues:
1. Code smells and anti-patterns
2. Unused variables and imports
3. Missing error handling
4. Inefficient algorithms
5. Memory leaks
6. Thread safety issues
7. Missing type hints
8. Poor naming conventions
9. Missing docstrings
10. Repeated code (DRY violations)

Respond ONLY with a valid JSON array of fixes. No other text.
Format:
[{
  "rule_id": "QUAL001",
  "severity": "CRITICAL|HIGH|MEDIUM|LOW",
  "explanation": "Brief explanation of the issue",
  "old_code": "the problematic code snippet",
  "new_code": "the improved code",
  "confidence": 0.95
}]"""


CODE_EXPLANATION_SYSTEM = """You are a code documentation expert.

Explain the provided code concisely:
- What it does (1-2 sentences)
- Key functions/classes and their purpose
- Potential issues or concerns
- Usage examples if applicable

Keep explanations under 100 words. Be precise and technical."""


GENERAL_FIX_SYSTEM = """You are an expert programmer fixing code issues.

Given a code finding, generate a safe, correct fix that:
1. Solves the reported issue
2. Doesn't introduce new bugs
3. Follows best practices
4. Is minimally invasive

Respond ONLY with JSON in this exact format:
{"new_code": "...", "explanation": "...", "risk": "LOW|MEDIUM|HIGH"}"""


@dataclass
class FixPromptConfig:
    """Configuration for fix prompt generation."""
    include_context: bool = True
    max_code_lines: int = 50
    include_alternatives: bool = False
    strict_json: bool = True


def build_finding_explanation_prompt(finding: dict, context: str = "") -> str:
    """Build prompt for explaining a finding.

    Args:
        finding: Finding dictionary with message, rule_id, severity, etc.
        context: Additional code context

    Returns:
        Formatted prompt string
    """
    return f"""Explain this code issue:

Rule: {finding.get('rule_id', 'UNKNOWN')}
Severity: {finding.get('severity', 'MEDIUM')}
Message: {finding['message']}

Code snippet:
```{finding.get('language', 'python')}
{finding.get('old_code', context)}
```

Provide:
1. Why this is a problem
2. How to fix it correctly
3. Best practices to avoid similar issues in the future
"""


def build_fix_generation_prompt(
    finding: dict,
    context: str = "",
    config: FixPromptConfig = None
) -> str:
    """Build prompt for generating a fix.

    Args:
        finding: Finding dictionary
        context: Additional code context
        config: Prompt configuration

    Returns:
        Formatted prompt string
    """
    cfg = config or FixPromptConfig()
    file_path = finding.get('file_path', 'unknown')

    prompt_parts = [
        f"Generate a fix for this issue in {file_path}:",
        f"",
        f"Issue: {finding['message']}",
        f"Rule: {finding.get('rule_id', 'UNKNOWN')}",
        f"Severity: {finding.get('severity', 'MEDIUM')}",
        f"",
        f"Current code:",
    ]

    code = finding.get('old_code', context)
    if code:
        prompt_parts.append(f"```{finding.get('language', 'python')}")
        prompt_parts.append(code)
        prompt_parts.append("```")

    if cfg.include_context and context and context != finding.get('old_code', ''):
        prompt_parts.extend([
            "",
            "Additional context:",
            f"```{finding.get('language', 'python')}",
            context,
            "```"
        ])

    prompt_parts.extend([
        "",
        "Generate a correct, safe fix. Respond with ONLY JSON in this format:",
        '{"new_code": "...", "explanation": "...", "risk": "LOW|MEDIUM|HIGH"}'
    ])

    return "\n".join(prompt_parts)


def build_code_review_prompt(code: str, language: str = "python") -> str:
    """Build prompt for reviewing code.

    Args:
        code: Code to review
        language: Programming language

    Returns:
        Review prompt
    """
    return f"""Review this {language} code and identify issues:

```{language}
{code}
```

Respond with a JSON array of findings:
[{{
  "rule_id": "...",
  "severity": "CRITICAL|HIGH|MEDIUM|LOW",
  "message": "...",
  "line": <line_number>,
  "explanation": "..."
}}]"""


def build_security_review_prompt(code: str, language: str = "python") -> str:
    """Build prompt for security review.

    Args:
        code: Code to review
        language: Programming language

    Returns:
        Security review prompt
    """
    return f"""Perform a security review of this {language} code:

```{language}
{code}
```

Look for:
1. Hardcoded secrets
2. Injection vulnerabilities
3. Authentication issues
4. Data exposure risks
5. Input validation failures

Respond with JSON array of security findings:
[{{
  "rule_id": "SEC001",
  "severity": "CRITICAL|HIGH|MEDIUM|LOW",
  "cwe_id": "CWE-XXX",
  "message": "...",
  "explanation": "...",
  "remediation": "..."
}}]"""


def build_ml_review_prompt(code: str) -> str:
    """Build prompt for ML code review.

    Args:
        code: PyTorch/TensorFlow code to review

    Returns:
        ML review prompt
    """
    return f"""Review this ML code for common issues:

```python
{code}
```

Check for:
1. Data leakage
2. Device placement errors
3. Gradient computation issues
4. Loss function mismatches
5. Training/eval mode issues

Respond with JSON array of findings:
[{{
  "rule_id": "ML001",
  "severity": "CRITICAL|HIGH|MEDIUM|LOW",
  "message": "...",
  "explanation": "...",
  "fix": "..."
}}]"""


# Quick reference for rule IDs
RULE_ID_CATEGORIES = {
    "ML": "Machine Learning issues",
    "SEC": "Security vulnerabilities",
    "QUAL": "Code quality issues",
    "PERF": "Performance issues",
    "TEST": "Testing issues",
    "DOC": "Documentation issues",
}


def get_severity_order() -> list[str]:
    """Get severity levels in order of priority."""
    return ["CRITICAL", "HIGH", "MEDIUM", "LOW"]


def format_finding_for_display(finding: dict) -> str:
    """Format finding for console display.

    Args:
        finding: Finding dictionary

    Returns:
        Formatted string for display
    """
    rule_id = finding.get('rule_id', 'UNKNOWN')
    severity = finding.get('severity', 'MEDIUM')
    message = finding.get('message', 'No description')

    severity_icons = {
        "CRITICAL": "[!]",
        "HIGH": "[!!]",
        "MEDIUM": "[!]",
        "LOW": "[.]",
    }

    icon = severity_icons.get(severity, "[?]")
    return f"{icon} {rule_id}: {message}"

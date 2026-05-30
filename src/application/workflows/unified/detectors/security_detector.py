"""Security Detector — security vulnerability detection rules.

Integrates with RuleEngine to provide security-focused detection:
- SEC001: Hardcoded secrets (API keys, passwords, tokens)
- SEC002: SQL injection vulnerabilities
- SEC003: Command injection risks
- SEC004: Path traversal vulnerabilities
- SEC005: Dangerous eval/exec usage
- SEC006: Insecure random number generation

Each rule is CWE-mapped for compliance reporting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.application.workflows.unified.code_context import CodeContext
from src.application.workflows.unified.detector_base import (
    Detector,
    DetectorConfig,
    Finding,
    FindingSeverity,
)

if TYPE_CHECKING:
    from src.infrastructure.analysis.rule_engine import Rule, RuleEngine

# ─── CWE Mapping ────────────────────────────────────────────────────────────────


CWE_MAPPING = {
    "SEC001": "CWE-798",  # Use of Hard-coded Credentials
    "SEC002": "CWE-89",   # SQL Injection
    "SEC003": "CWE-78",   # OS Command Injection
    "SEC004": "CWE-22",   # Path Traversal
    "SEC005": "CWE-95",   # Code Injection
    "SEC006": "CWE-338",  # Use of Cryptographically Weak PRNG
}

# ─── Security Rule Definitions ─────────────────────────────────────────────────


@dataclass
class SecurityRule:
    """Definition of a security detection rule."""
    id: str
    name: str
    description: str
    severity: FindingSeverity
    patterns: list[str]
    fix_template: str
    cwe_id: str = ""
    languages: list[str] = None

    def __post_init__(self) -> None:
        if self.languages is None:
            self.languages = ["python", "javascript", "typescript", "java", "go"]


# ─── Security Detector ──────────────────────────────────────────────────────────


class SecurityDetector(Detector):
    """Security vulnerability detector.

    Detects common security issues:
    - Hardcoded secrets
    - SQL injection
    - Command injection
    - Path traversal
    - Dangerous functions
    - Insecure cryptography

    Supported languages: python, javascript, typescript, java, go, c, cpp

    Usage:
        config = DetectorConfig(focus_areas=["security"])
        detector = SecurityDetector(config)
        findings = detector.detect(context)
    """

    # Security rules
    RULES: list[SecurityRule] = []

    def __init__(self, config: DetectorConfig | None = None) -> None:
        super().__init__(config)
        self._name = "security"
        self._init_rules()

    def _init_rules(self) -> None:
        """Initialize security rules."""
        self.RULES = [
            # SEC001: Hardcoded secrets
            SecurityRule(
                id="SEC001",
                name="hardcoded-secret",
                description="Hardcoded API key, token, password, or secret detected",
                severity=FindingSeverity.ERROR,
                patterns=[
                    r'["\']api[_-]?key["\']\s*[:=]\s*["\'][a-zA-Z0-9_\-]{16,}["\']',
                    r'["\']secret["\']\s*[:=]\s*["\'][a-zA-Z0-9_\-]{8,}["\']',
                    r'["\']password["\']\s*[:=]\s*["\'][^"\']{4,}["\']',
                    r'["\']token["\']\s*[:=]\s*["\'][a-zA-Z0-9_\-\.]{16,}["\']',
                    r'Bearer\s+[a-zA-Z0-9_\-\.]+',
                    r'ghp_[a-zA-Z0-9]{36}',
                    r'AKIA[0-9A-Z]{16}',
                    r'sk-[a-zA-Z0-9]{32,}',
                    r'xox[baprs]-[a-zA-Z0-9]{10,}',
                ],
                fix_template="Use environment variable: os.getenv('SECRET_NAME')",
                cwe_id="CWE-798",
            ),

            # SEC002: SQL injection
            SecurityRule(
                id="SEC002",
                name="sql-injection",
                description="Potential SQL injection via string concatenation",
                severity=FindingSeverity.ERROR,
                patterns=[
                    r'execute\s*\(\s*["\'].*\%s.*["\'].*%',
                    r'execute\s*\(\s*f["\']',
                    r'execute\s*\(\s*["\'].*\+',
                    r'cursor\.execute\s*\([^)]*\+[^)]*\)',
                    r'pool\.execute\s*\([^)]*\+[^)]*\)',
                    r'query\s*\(\s*["\'].*\+',
                    r'\$\{.*\}.*from|insert|update|delete|select',
                    r'\.format\s*\([^)]*SELECT|INSERT|UPDATE|DELETE',
                ],
                fix_template="Use parameterized queries: cursor.execute('SELECT * FROM users WHERE id = %s', (id,))",
                cwe_id="CWE-89",
            ),

            # SEC003: Command injection
            SecurityRule(
                id="SEC003",
                name="command-injection",
                description="Shell command injection risk via subprocess with shell=True",
                severity=FindingSeverity.ERROR,
                patterns=[
                    r'subprocess\.(run|call|popen|Popen|run_shell)\s*\([^)]*shell\s*=\s*True',
                    r'exec\s*\(',
                    r'eval\s*\(',
                    r'child_process\.exec\s*\(',
                    r'Runtime\.getRuntime\(\)\.exec\s*\(',
                    r'shell_exec\s*\(',
                    r'system\s*\([^)]*\$',
                ],
                fix_template="Use subprocess.run with shell=False and list of arguments",
                cwe_id="CWE-78",
            ),

            # SEC004: Path traversal
            SecurityRule(
                id="SEC004",
                name="path-traversal",
                description="Potential path traversal vulnerability",
                severity=FindingSeverity.ERROR,
                patterns=[
                    r'open\s*\([^)]*\+\s*path',
                    r'open\s*\([^)]*\%s[^)]*%',
                    r'os\.path\.join\s*\([^)]*\+',
                    r'readFile\s*\([^)]*\+',
                    r'readFile\s*\([^)]*\$',
                    r'FileInputStream\s*\([^)]*\+',
                    r'ioutil\.ReadFile\s*\([^)]*\.',
                    r'\.join\(.*request\.',
                    r'\.format\(.*path|file|dir',
                ],
                fix_template="Validate and sanitize path input, use os.path.realpath()",
                cwe_id="CWE-22",
            ),

            # SEC005: Dangerous eval/exec
            SecurityRule(
                id="SEC005",
                name="eval-usage",
                description="Use of eval() or exec() is a security risk",
                severity=FindingSeverity.WARNING,
                patterns=[
                    r'\beval\s*\(',
                    r'\bexec\s*\(',
                    r'new\s+Function\s*\(',
                    r'vm\.runIn',
                    r'\bruby\s*\(',
                    r'\bperl\s*\(',
                ],
                fix_template="Avoid eval/exec; use safer alternatives like ast.literal_eval",
                cwe_id="CWE-95",
            ),

            # SEC006: Insecure random
            SecurityRule(
                id="SEC006",
                name="insecure-random",
                description="Using random.random() or Math.random() for security purposes",
                severity=FindingSeverity.WARNING,
                patterns=[
                    r'random\.random\s*\(\s*\)',
                    r'Math\.random\s*\(\s*\)',
                    r'random\.choice\s*\(\s*\)',
                    r'java\.util\.Random\s*\(',
                    r'new\s+Random\s*\(',
                ],
                fix_template="Use secrets module: secrets.randbelow() or crypto.randomBytes()",
                cwe_id="CWE-338",
            ),

            # SEC007: Weak cryptography
            SecurityRule(
                id="SEC007",
                name="weak-crypto",
                description="Weak cryptographic algorithm or usage",
                severity=FindingSeverity.WARNING,
                patterns=[
                    r'MD5\s*\(',
                    r'SHA1\s*\(',
                    r'DES\s*\(',
                    r'RC4\s*\(',
                    r'crypto\.createCipher\s*\(',
                    r'hashlib\.md5\s*\(',
                    r'hashlib\.sha1\s*\(',
                    r'insecure\s*\(',
                    r'md5_hash\s*\(',
                ],
                fix_template="Use SHA-256 or stronger: hashlib.sha256()",
                cwe_id="CWE-327",
            ),

            # SEC008: Hardcoded IP
            SecurityRule(
                id="SEC008",
                name="hardcoded-ip",
                description="Hardcoded IP address reduces flexibility",
                severity=FindingSeverity.INFO,
                patterns=[
                    r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}'
                    r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b',
                    r'https?://(?:127\.0\.0\.1|localhost)',
                ],
                fix_template="Use configuration for IP addresses",
                cwe_id="",
            ),

            # SEC009: XXE vulnerability
            SecurityRule(
                id="SEC009",
                name="xxe-vulnerability",
                description="XML external entity (XXE) vulnerability",
                severity=FindingSeverity.ERROR,
                patterns=[
                    r'etree\.parse\s*\([^)]*\)(?!.*no_ents',
                    r'XMLParser\s*\([^)]*\)(?!.*DTDLoad',
                    r'SAXBuilder\s*\([^)]*\)(?!.*Disable',
                    r'documentBuilder\.parse\s*\([^)]*\)',
                ],
                fix_template="Disable XXE: xmlParser.setFeature(XMLConstants.ACCESS_EXTERNAL_DTD, \"\")",
                cwe_id="CWE-611",
            ),

            # SEC010: Insecure cookie
            SecurityRule(
                id="SEC010",
                name="insecure-cookie",
                description="Cookie set without security flags",
                severity=FindingSeverity.WARNING,
                patterns=[
                    r'cookie\s*\([^)]*secure\s*=\s*False',
                    r'setcookie\s*\([^)]*(?!.*secure)',
                    r'response\.set_cookie\s*\([^)]*(?!.*secure)',
                    r'\.cookie\(.*httponly\s*=\s*False',
                ],
                fix_template="Set secure=True, httponly=True for sensitive cookies",
                cwe_id="CWE-614",
            ),
        ]

    def detect(self, context: CodeContext) -> list[Finding]:
        """Detect security vulnerabilities.

        Args:
            context: Unified code context

        Returns:
            List of security findings
        """
        findings: list[Finding] = []

        # Check language support
        for rule in self.RULES:
            if context.language not in rule.languages:
                continue

            rule_findings = self._run_rule(rule, context)
            findings.extend(rule_findings)

        return findings

    def _run_rule(self, rule: SecurityRule, context: CodeContext) -> list[Finding]:
        """Run a single security rule.

        Args:
            rule: Security rule to run
            context: Code context

        Returns:
            Findings from this rule
        """
        findings: list[Finding] = []

        for i, line in enumerate(context.lines, 1):
            for pattern in rule.patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    # Check for false positives by looking at context
                    if self._is_false_positive(rule.id, line, match.group()):
                        continue

                    # Get column position
                    col = match.start()

                    # Get surrounding context
                    context_lines = context.get_surrounding_code(i)

                    findings.append(Finding(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        severity=rule.severity,
                        file=str(context.file_path),
                        line=i,
                        end_line=i,
                        column=col,
                        message=self._format_message(rule, match.group()),
                        fix=rule.fix_template,
                        confidence=self._calculate_confidence(rule.id, line, match.group()),
                        context=context_lines,
                        detector=self._name,
                        metadata={
                            "tags": ["security", rule.id],
                            "cwe": rule.cwe_id or CWE_MAPPING.get(rule.id, ""),
                            "matched_text": match.group()[:50],
                        },
                    ))

        return findings

    def _is_false_positive(self, rule_id: str, line: str, matched: str) -> bool:
        """Check if a match is a false positive.

        Args:
            rule_id: Rule that matched
            line: Full line containing match
            matched: Matched text

        Returns:
            True if false positive
        """
        # SEC001: Skip if it's a placeholder/example
        if rule_id == "SEC001":
            if any(placeholder in line.lower() for placeholder in [
                "your_", "example", "test", "dummy", "fake", "xxx"
            ]):
                return True

        # SEC002: Skip if in comments
        if "#" in line.split(matched)[0]:
            return True

        # SEC003: Skip subprocess with shell=False
        if rule_id == "SEC003" and "shell=False" in line:
            return True

        # SEC005: Skip if in tests
        if rule_id == "SEC005" and "test" in line.lower():
            return True

        return False

    def _calculate_confidence(self, rule_id: str, line: str, matched: str) -> float:
        """Calculate confidence score for a match.

        Args:
            rule_id: Rule that matched
            line: Full line
            matched: Matched text

        Returns:
            Confidence score (0.0-1.0)
        """
        base_confidence = 0.9

        # Reduce confidence for comments
        if "#" in line.split(matched)[0] if matched in line else False:
            return 0.5

        # Reduce confidence for test files
        if "test" in line.lower():
            return 0.6

        # Increase confidence for obvious patterns
        if matched.startswith("ghp_") or matched.startswith("sk-"):
            return 1.0

        if matched.startswith("password") or matched.startswith("api_key"):
            return 1.0

        return base_confidence

    def _format_message(self, rule: SecurityRule, matched: str) -> str:
        """Format finding message.

        Args:
            rule: Security rule
            matched: Matched text

        Returns:
            Formatted message
        """
        if len(matched) > 40:
            matched = matched[:37] + "..."

        cwe = f" ({rule.cwe_id})" if rule.cwe_id else ""
        return f"[{rule.id}] {rule.name}: {rule.description}{cwe}\nMatched: {matched}"

    def integrate_with_rule_engine(
        self,
        rule_engine: "RuleEngine",
    ) -> None:
        """Integrate with RuleEngine to share findings.

        Args:
            rule_engine: Existing RuleEngine instance
        """
        # Register security rules in rule engine
        from src.infrastructure.analysis.rule_engine import Rule, RuleSeverity

        for security_rule in self.RULES:
            rule = Rule(
                id=security_rule.id,
                name=security_rule.name,
                description=security_rule.description,
                severity=RuleSeverity[security_rule.severity.name.upper()],
                languages=security_rule.languages,
                patterns=security_rule.patterns,
                fix_template=security_rule.fix_template,
                cwe_id=security_rule.cwe_id,
                tags=["security"],
            )
            try:
                rule_engine.register(rule)
            except ValueError:
                pass  # Rule already registered

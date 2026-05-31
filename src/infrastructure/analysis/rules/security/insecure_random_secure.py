"""Insecure random number generation detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class InsecureRandomRule2:
    """Detect insecure random number generation.

    Using random module for security-sensitive operations
    can be predictable.
    """

    rule_id: str = "SEC040"
    severity: Severity = Severity.MEDIUM

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        insecure_patterns = [
            (r'random\.random\s*\(\)', "random.random() is not secure"),
            (r'random\.randint\s*\(\)', "random.randint() is not secure"),
            (r'random\.choice\s*\(\s*\w+\s*\)', "random.choice() is not secure"),
            (r'random\.shuffle\s*\(\s*\w+\s*\)', "random.shuffle() is not secure"),
            (r'random\.sample\s*\(\s*\w+', "random.sample() is not secure"),
            (r'random\.gauss\s*\(', "random.gauss() is not secure"),
            (r'Math\.random\s*\(\)', "JavaScript Math.random() is not secure"),
        ]

        secure_patterns = [
            (r'secrets\.', "secrets module (cryptographically secure)"),
            (r'secrets\.randbelow', "secrets.randbelow()"),
            (r'secrets\.choice', "secrets.choice()"),
            (r'secrets\.token', "secrets.token generation"),
            (r'os\.urandom', "os.urandom() is secure"),
        ]

        lines = content.split('\n')
        has_secure = any(re.search(p, content) for p in secure_patterns)

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in insecure_patterns:
                if re.search(pattern, line):
                    if not has_secure:
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": i,
                            "message": f"Insecure random: {desc}",
                            "explanation": "random module is not cryptographically secure. "
                                           "Predictable values can compromise security.",
                            "fix": "Use secrets module instead: secrets.choice(), secrets.randbelow()",
                        })
                    break

        return findings

"""Django hardcoded SECRET_KEY detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class SecretKeyRule:
    """Detect hardcoded SECRET_KEY in Django settings.

    SECRET_KEY should never be committed to version control.
    It enables session hijacking and other security issues.
    """

    rule_id: str = "DJANGO005"
    severity: Severity = Severity.CRITICAL

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        secret_key_patterns = [
            (r'SECRET_KEY\s*=\s*["\'][^"\']{20,}["\']', "Hardcoded SECRET_KEY"),
            (r'SECRET_KEY\s*=\s*["\'][\w\-!@#$%^&*()+=]{20,}["\']', "SECRET_KEY with special chars"),
        ]

        development_patterns = [
            (r'django\.conf\.global_settings', "Using global settings"),
            (r'DEBUG\s*=\s*True', "DEBUG mode"),
            (r'if\s+not\s+DEBUG', "Conditional debug check"),
        ]

        is_settings = any(p in file_path.lower() for p in ['settings', 'config'])
        has_django = 'django' in content.lower()

        if not (is_settings or has_django):
            return findings

        lines = content.split('\n')

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//', '#')):
                continue

            for pattern, desc in secret_key_patterns:
                match = re.search(pattern, line)
                if match:
                    secret_value = match.group(0).split('=')[1].strip().strip('"\'')
                    is_short = len(secret_value) < 50

                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": "Hardcoded SECRET_KEY detected",
                        "explanation": f"SECRET_KEY should be loaded from environment variables, "
                                       "not hardcoded. Current value is {len(secret_value)} chars.",
                        "fix": "Use: SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY') or "
                               "django-environ: env('DJANGO_SECRET_KEY')",
                    })

        if not findings and is_settings and has_django:
            if not re.search(r'os\.environ|getenv|env\(', content):
                if re.search(r'SECRET_KEY', content):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": 1,
                        "message": "SECRET_KEY may not be loaded from environment",
                        "explanation": "SECRET_KEY should be loaded from environment variables for security.",
                        "fix": "Use: SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')",
                    })

        return findings

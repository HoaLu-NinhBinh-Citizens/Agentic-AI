"""Django debug mode in production detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class DjangoDebugModeRule:
    """Detect DEBUG=True in Django production settings.

    DEBUG=True exposes sensitive information including source code,
    stack traces, and environment variables.
    """

    rule_id: str = "DJANGO004"
    severity: Severity = Severity.CRITICAL

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        debug_patterns = [
            (r'DEBUG\s*=\s*True', "DEBUG=True in settings"),
            (r'DEBUG\s*=\s*1', "DEBUG=1 in settings"),
            (r'"DEBUG"\s*:\s*["\']?true', "DEBUG: true in JSON config"),
        ]

        production_patterns = [
            (r'ENV\s*=', "Environment variable check"),
            (r'ENVIRONMENT', "Environment check"),
            (r'production|prod', "Production context"),
            (r'settings\.py', "Settings file"),
            (r'settings/', "Settings directory"),
            (r'config/', "Config directory"),
        ]

        lines = content.split('\n')

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//', '#')):
                continue

            for pattern, desc in debug_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    is_settings = any(p in file_path.lower() for p in ['settings', 'config'])
                    is_in_if = 'if' in line or 'when' in line.lower()

                    severity = Severity.CRITICAL
                    message = f"DEBUG enabled: {desc}"

                    if is_in_if:
                        severity = Severity.HIGH
                        message = f"Conditional DEBUG found: {desc}"

                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": severity.value,
                        "file": file_path,
                        "line": i,
                        "message": message,
                        "explanation": "DEBUG=True exposes sensitive information in error pages "
                                       "including source code, environment variables, and database queries.",
                        "fix": "Set DEBUG=False in production. Use environment variables: "
                               "DEBUG=os.environ.get('DEBUG', 'False') == 'True'",
                    })

        if not findings:
            is_settings = any(p in file_path.lower() for p in ['settings.py', '/settings/'])
            has_django = 'django' in content.lower()

            if is_settings and has_django:
                if not re.search(r'DEBUG\s*=\s*False', content):
                    if re.search(r'ALLOWED_HOSTS\s*=', content):
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": 1,
                            "message": "Settings file should explicitly set DEBUG=False",
                            "explanation": "Production settings should explicitly disable DEBUG mode.",
                            "fix": "Add DEBUG = False at the top of settings.py",
                        })

        return findings

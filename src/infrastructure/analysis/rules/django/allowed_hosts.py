"""Django ALLOWED_HOSTS security rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class AllowedHostsRule:
    """Detect insecure ALLOWED_HOSTS configuration in Django.

    ALLOWED_HOSTS=['*'] allows any host, enabling host header injection attacks.
    """

    rule_id: str = "DJANGO006"
    severity: Severity = Severity.HIGH

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        allowed_hosts_patterns = [
            (r'ALLOWED_HOSTS\s*=\s*\[\s*["\']\*["\']\s*\]', "ALLOWED_HOSTS with wildcard"),
            (r'ALLOWED_HOSTS\s*=\s*\[\s*["\'](?!www\.|[\w\-]+\.)', "ALLOWED_HOSTS may include wildcard"),
        ]

        is_settings = any(p in file_path.lower() for p in ['settings', 'config'])
        has_django = 'django' in content.lower()

        if not (is_settings or has_django):
            return findings

        lines = content.split('\n')

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//', '#')):
                continue

            for pattern, desc in allowed_hosts_patterns:
                if re.search(pattern, line):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": "Insecure ALLOWED_HOSTS configuration",
                        "explanation": "ALLOWED_HOSTS=['*'] allows any HTTP Host header, "
                                       "enabling cache poisoning and XSS attacks.",
                        "fix": "Specify exact domains: ALLOWED_HOSTS=['example.com', 'www.example.com']",
                    })

        if not findings and is_settings:
            if re.search(r'ALLOWED_HOSTS', content):
                if not re.search(r'ALLOWED_HOSTS\s*=\s*\[', content):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": 1,
                        "message": "ALLOWED_HOSTS may not be properly configured",
                        "explanation": "ALLOWED_HOSTS should be a list of allowed domains.",
                        "fix": "Set: ALLOWED_HOSTS = ['example.com'] or load from environment",
                    })

        return findings

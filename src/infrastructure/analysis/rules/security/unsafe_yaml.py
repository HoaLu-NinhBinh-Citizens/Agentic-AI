"""YAML unsafe loading detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class UnsafeYAMLRule:
    """Detect unsafe yaml.load() usage.

    yaml.load() without a safe Loader can execute arbitrary Python code.
    Always use yaml.safe_load() or yaml.load(Loader=yaml.SafeLoader).
    """

    rule_id: str = "SEC010"
    severity: Severity = Severity.HIGH

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        unsafe_yaml_pattern = r'yaml\.load\s*\(([^)]+)(?<!Loader=yaml\.SafeLoader)(?<!Loader=yaml\.SafeLoader\))'

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            if re.search(r'yaml\.load\s*\(', line):
                if not re.search(r'Loader=yaml\.SafeLoader', line):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": "Unsafe YAML loading detected",
                        "explanation": "yaml.load() without SafeLoader can execute arbitrary code. "
                                       "This is a security risk.",
                        "fix": "Use yaml.safe_load() or yaml.load(Loader=yaml.SafeLoader)",
                    })

        return findings

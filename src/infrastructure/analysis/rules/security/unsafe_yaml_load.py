"""YAML unsafe load detection rule (alternative name)."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class UnsafeYAMLLoadRule:
    """Detect unsafe yaml.load() without safe Loader.

    yaml.load() can execute arbitrary Python code through
    special YAML tags. Always use yaml.safe_load() or
    specify a SafeLoader.
    """

    rule_id: str = "SEC025"
    severity: Severity = Severity.HIGH

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        lines = content.split('\n')

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            if 'yaml.load' in line and 'yaml.safe_load' not in line:
                if 'Loader=' not in line or 'SafeLoader' not in line:
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": "YAML unsafe load without SafeLoader",
                        "explanation": "yaml.load() without SafeLoader can execute arbitrary "
                                       "Python code from the YAML input.",
                        "fix": "Replace with yaml.safe_load() or add Loader=yaml.SafeLoader",
                    })

            if 'yaml.unsafe_load' in line:
                findings.append({
                    "rule_id": self.rule_id,
                    "severity": self.severity.value,
                    "file": file_path,
                    "line": i,
                    "message": "YAML unsafe_load() detected",
                    "explanation": "yaml.unsafe_load() allows arbitrary Python object "
                                   "construction and is a security risk.",
                    "fix": "Use yaml.safe_load() instead",
                })

        return findings

"""Unsafe deserialization detection rule."""

from dataclasses import dataclass
import re
import ast

from src.shared.enums.severity import Severity


@dataclass
class UnsafeDeserializationRule:
    """Detect unsafe deserialization patterns.

    Unsafe deserialization can lead to remote code execution attacks.
    Always validate and sanitize data before deserializing.
    """

    rule_id: str = "SEC008"
    severity: Severity = Severity.CRITICAL

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        dangerous_patterns = [
            (r'pickle\.loads?', "pickle.loads() is unsafe"),
            (r'yaml\.load\s*\([^)]*(?<!Loader=)', "yaml.load() without Loader is unsafe"),
            (r'marshal\.load', "marshal.load() is unsafe"),
            (r'shelve\.open', "shelve uses pickle internally"),
            (r'eval\s*\(', "eval() can execute arbitrary code"),
            (r'exec\s*\(', "exec() can execute arbitrary code"),
        ]

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in dangerous_patterns:
                if re.search(pattern, line):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"Unsafe deserialization: {desc}",
                        "explanation": f"Using {desc} can allow remote code execution. "
                                       "Use json.loads() or yaml.safe_load() instead.",
                        "fix": "Use json.loads() for JSON or yaml.safe_load(Loader=yaml.SafeLoader)",
                    })
                    break

        return findings

"""Unsafe pickle usage detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class UnsafePickleRule:
    """Detect unsafe pickle operations.

    pickle.loads() can execute arbitrary code from untrusted sources.
    Never unpickle data from untrusted input.
    """

    rule_id: str = "SEC022"
    severity: Severity = Severity.CRITICAL

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        pickle_patterns = [
            (r'pickle\.loads\s*\(', "pickle.loads() is unsafe"),
            (r'pickle\.load\s*\(', "pickle.load() is unsafe"),
            (r'pickle\.Unpickler', "Custom unpickler detected"),
            (r'cpickle\.loads', "cPickle loads is unsafe"),
        ]

        safe_patterns = [
            (r'secure_load', "PyYAML secure loader"),
            (r'msgpack\.unpackb', "msgpack is safe for untrusted data"),
            (r'marshal\.loads', "marshal has security limitations"),
            (r'json\.loads', "JSON is inherently safe"),
        ]

        lines = content.split('\n')
        has_safe_loader = False

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, _ in safe_patterns:
                if re.search(pattern, line):
                    has_safe_loader = True
                    break

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in pickle_patterns:
                if re.search(pattern, line):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"Unsafe pickle: {desc}",
                        "explanation": "pickle can execute arbitrary code. "
                                       "Only unpickle trusted, validated data.",
                        "fix": "Use json.loads() or msgpack.unpackb() instead",
                    })
                    break

        return findings

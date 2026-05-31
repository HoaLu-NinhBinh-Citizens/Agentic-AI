"""Insecure temporary file detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class InsecureTempFileRule:
    """Detect insecure temporary file usage.

    Insecure temp file patterns can lead to symlink attacks,
    information disclosure, or race conditions.
    """

    rule_id: str = "SEC024"
    severity: Severity = Severity.MEDIUM

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        insecure_patterns = [
            (r'TemporaryFile\s*\(', "TemporaryFile usage (review mode)"),
            (r'NamedTemporaryFile\s*\(', "NamedTemporaryFile may leave traces"),
            (r'mktemp\s*\(', "mktemp() is insecure due to race condition"),
            (r'TempPath\s*\(', "Temp directory creation"),
            (r'tempfile\.gettempdir\s*\(\)', "Using system temp directory"),
            (r'os\.tempnam\s*\(', "os.tempnam() is insecure"),
            (r'os\.tmpnam\s*\(', "os.tmpnam() is insecure"),
        ]

        safe_patterns = [
            (r'TemporaryDirectory\s*\(', "TemporaryDirectory auto-cleans"),
            (r'SpooledTemporaryFile', "SpooledTemporaryFile in memory first"),
            (r'mkstemp\s*\(', "mkstemp() creates files securely"),
            (r'mkdtemp\s*\(', "mkdtemp() creates dirs securely"),
            (r'mode="w"\s*,\s*prefix=', "NamedTemporaryFile with secure settings"),
        ]

        lines = content.split('\n')
        has_safe_pattern = False

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, _ in safe_patterns:
                if re.search(pattern, line):
                    has_safe_pattern = True
                    break

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in insecure_patterns:
                if re.search(pattern, line):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"Insecure temp file: {desc}",
                        "explanation": "This pattern can be vulnerable to symlink attacks "
                                       "or race conditions.",
                        "fix": "Use tempfile.mkstemp() or TemporaryDirectory()",
                    })
                    break

        return findings

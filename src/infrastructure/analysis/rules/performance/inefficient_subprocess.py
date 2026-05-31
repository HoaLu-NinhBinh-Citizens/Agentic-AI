"""Inefficient subprocess usage detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class InefficientSubprocessRule:
    """Detect inefficient subprocess patterns.

    Some subprocess patterns can be optimized for better
    performance and security.
    """

    rule_id: str = "PERF025"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        inefficient_patterns = [
            (r'subprocess\.call\s*\([^)]*\)', "subprocess.call (use run instead)"),
            (r'subprocess\.Popen.*\.communicate\(\)', "Popen.communicate without input"),
            (r'subprocess\.check_output\s*\([^)]*shell\s*=\s*True', "shell=True in check_output"),
            (r'os\.system\s*\(', "os.system() (insecure and inefficient)"),
            (r'os\.popen\s*\(', "os.popen() (deprecated)"),
        ]

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in inefficient_patterns:
                if re.search(pattern, line):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"Inefficient subprocess: {desc}",
                        "explanation": "This subprocess pattern is inefficient or insecure.",
                        "fix": "Use subprocess.run() with proper arguments",
                    })
                    break

        return findings

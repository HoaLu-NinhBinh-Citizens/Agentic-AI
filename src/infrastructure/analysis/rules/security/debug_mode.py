"""Debug mode enabled in production detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class DebugModeRule:
    """Detect debug mode enabled in code.

    Debug mode should never be enabled in production as it
    can expose sensitive information.
    """

    rule_id: str = "SEC034"
    severity: Severity = Severity.HIGH

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        debug_patterns = [
            (r'debug\s*=\s*True', "Debug mode enabled"),
            (r'DEBUG\s*=\s*True', "DEBUG constant set to True"),
            (r'app\.run\s*\([^)]*debug\s*=\s*True', "Flask debug enabled"),
            (r'django\.conf\.settings\s*DEBUG\s*=\s*True', "Django DEBUG set"),
            (r'logger\.level\s*=\s*logging\.DEBUG', "Logger set to DEBUG level"),
            (r'TEMPLATE_DEBUG\s*=\s*True', "Template debug enabled"),
            (r'PDBC_DEBUG\s*=', "PDB debugger in code"),
        ]

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            if self._is_production_context(line):
                for pattern, desc in debug_patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": i,
                            "message": f"Debug mode enabled: {desc}",
                            "explanation": "Debug mode can expose sensitive information and "
                                           "should never be enabled in production.",
                            "fix": "Set debug=False or use environment variables for debug setting",
                        })
                        break

        return findings

    def _is_production_context(self, line: str) -> bool:
        if 'DEBUG' in line and 'False' in line:
            return False
        return True

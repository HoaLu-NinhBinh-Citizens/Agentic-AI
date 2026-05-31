"""Mass assignment detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class MassAssignmentRule:
    """Detect potential mass assignment vulnerabilities.

    Mass assignment allows attackers to set arbitrary attributes
    by passing them in request data.
    """

    rule_id: str = "SEC032"
    severity: Severity = Severity.MEDIUM

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        mass_assign_patterns = [
            (r'\.update\s*\([^)]*request', "Updating from request data"),
            (r'\.create\s*\([^)]*request', "Creating from request data"),
            (r'\.save\s*\([^)]*request', "Saving from request data"),
            (r'\*\*request', "Unpacking request data"),
            (r'\*\*kwargs', "Unpacking kwargs"),
            (r'Model\(.*\*\*', "Model with unpacked data"),
        ]

        safe_patterns = [
            (r'\.fields\s*=', "Whitelisting allowed fields"),
            (r'only\s*\(', "Selecting specific fields"),
            (r'depends\s*=', "Dependency injection for fields"),
            (r'@fillable', "Fillable decorator"),
            (r'@guarded', "Guarded decorator"),
        ]

        lines = content.split('\n')
        has_protection = any(re.search(p, content) for p in safe_patterns)

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in mass_assign_patterns:
                if re.search(pattern, line):
                    if not has_protection:
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": i,
                            "message": f"Mass assignment risk: {desc}",
                            "explanation": "Model updated directly from request data without field protection.",
                            "fix": "Whitelist allowed fields or use explicit attribute assignment",
                        })
                    break

        return findings

"""XML injection detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class XMLInjectionRule:
    """Detect potential XML injection vulnerabilities.

    XML injection can allow attackers to manipulate XML documents
    or extract sensitive data.
    """

    rule_id: str = "SEC028"
    severity: Severity = Severity.MEDIUM

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        injection_patterns = [
            (r'ET\.fromstring\s*\(', "Parsing XML from string"),
            (r'ElementTree\.XML\s*\(', "XML parsing detected"),
            (r'minidom\.parseString\s*\(', "DOM XML parsing"),
            (r'dom\.parseString\s*\(', "DOM XML parsing"),
            (r'xml\.etree\.ElementTree', "ElementTree XML parsing"),
        ]

        safe_patterns = [
            (r'defusedxml', "Using defusedxml for safe parsing"),
            (r'lxml\.etree', "lxml with default safe parsing"),
        ]

        lines = content.split('\n')
        has_safe_parser = any(re.search(p, content) for p in safe_patterns)

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in injection_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    if not has_safe_parser:
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": i,
                            "message": f"XML injection risk: {desc}",
                            "explanation": "XML parsing without safe defaults can be vulnerable to injection.",
                            "fix": "Use defusedxml or validate/sanitize XML input",
                        })
                    break

        return findings

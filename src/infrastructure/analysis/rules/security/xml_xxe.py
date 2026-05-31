"""XML External Entity (XXE) injection detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class XXERule:
    """Detect XML External Entity (XXE) vulnerabilities.

    XXE allows attackers to read internal files, perform SSRF attacks,
    or cause denial of service.
    """

    rule_id: str = "SEC011"
    severity: Severity = Severity.CRITICAL

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        dangerous_patterns = [
            (r'lxml\.etree\.XML\s*\(', "lxml.etree.XML can be vulnerable to XXE"),
            (r'etree\.XML\s*\(', "XML parsing without XXE protection"),
            (r'defusedxml', "defusedxml provides safe XML parsing"),
            (r'xmlrpc\.client\.ServerProxy', "XML-RPC can be vulnerable to XXE"),
            (r'<![CDATA\[', "CDATA sections may indicate XXE risk"),
            (r'SYSTEM\s+"file:', "External entity reference detected"),
            (r'ENTITY\s+\w+\s+SYSTEM', "External entity definition detected"),
        ]

        lines = content.split('\n')
        has_defusedxml = 'defusedxml' in content

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            if has_defusedxml:
                continue

            for pattern, desc in dangerous_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"XXE vulnerability: {desc}",
                        "explanation": "XXE attacks can read sensitive files, perform SSRF, "
                                       "or cause DoS. Use defusedxml for safe parsing.",
                        "fix": "Use defusedxml.cElementTree instead of xml.etree or lxml",
                    })
                    break

        return findings

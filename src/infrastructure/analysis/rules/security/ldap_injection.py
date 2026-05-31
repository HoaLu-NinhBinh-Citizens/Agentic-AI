"""LDAP injection detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class LDAPInjectionRule:
    """Detect LDAP injection vulnerabilities.

    LDAP injection can allow attackers to bypass authentication,
    access unauthorized data, or modify LDAP directory.
    """

    rule_id: str = "SEC012"
    severity: Severity = Severity.HIGH

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        ldap_patterns = [
            (r'ldap\.initialize', "LDAP connection established"),
            (r'ldap3\.Connection', "ldap3 connection used"),
            (r'\.search\s*\(', "LDAP search operation"),
            (r'ldap\.search_s', "LDAP search operation"),
        ]

        injection_patterns = [
            (r'%\s*\)', "String formatting in LDAP query"),
            (r'"\s*\+\s*\w+\s*\+', "String concatenation in query"),
            (r'f"', "f-string in LDAP query"),
            (r'\.format\s*\(', ".format() in LDAP query"),
        ]

        has_ldap = False
        lines = content.split('\n')

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, _ in ldap_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    has_ldap = True
                    break

            if has_ldap:
                for pattern, desc in injection_patterns:
                    if re.search(pattern, line):
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": i,
                            "message": f"LDAP injection risk: {desc}",
                            "explanation": "Dynamic string construction in LDAP queries "
                                           "can allow injection attacks.",
                            "fix": "Use parameterized queries or escape special characters",
                        })
                        break

        return findings

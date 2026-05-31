"""Outdated docstring detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class OutdatedDocstringRule:
    """Detect potentially outdated docstrings.

    Docstrings with TODO markers or mismatched parameter names
    may be outdated.
    """

    rule_id: str = "DOC002"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        outdated_patterns = [
            (r'TODO.*docstring', "TODO in docstring (may be outdated)"),
            (r'FIXME.*docstring', "FIXME in docstring (may be outdated)"),
            (r'XXX.*docstring', "XXX in docstring (may be outdated)"),
            (r'@param.*\n\s*:return:', "Multi-line docstring without type hints"),
            (r'Args:\s*\n\s*-.*:.*deprecated', "Deprecated parameter in docstring"),
            (r'.. deprecated::', "Deprecated element marker"),
            (r'@deprecated', "Deprecated marker"),
        ]

        lines = content.split('\n')
        in_docstring = False
        docstring_start = 0
        docstring_lines = []

        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            if stripped.startswith('"""') or stripped.startswith("'''"):
                if not in_docstring:
                    in_docstring = True
                    docstring_start = i
                    docstring_lines = [stripped]
                else:
                    for j, pattern in enumerate(outdated_patterns):
                        if any(p in ' '.join(docstring_lines) for p in [pattern[0]]):
                            findings.append({
                                "rule_id": self.rule_id,
                                "severity": self.severity.value,
                                "file": file_path,
                                "line": docstring_start,
                                "message": f"Potentially outdated docstring: {outdated_patterns[j][1]}",
                                "explanation": "This docstring may be outdated or incomplete.",
                                "fix": "Update the docstring to reflect current implementation",
                            })
                    in_docstring = False
                    docstring_lines = []
            elif in_docstring:
                docstring_lines.append(stripped)

        return findings

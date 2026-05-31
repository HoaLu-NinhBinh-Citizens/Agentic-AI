"""Broken link detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class BrokenLinkRule:
    """Detect potentially broken links in documentation.

    Links to files, URLs, or sections that may not exist
    can lead to poor documentation experience.
    """

    rule_id: str = "DOC004"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        link_patterns = [
            (r'\[.*\]\(.*\.md#[^\)]+\)', "Internal markdown link"),
            (r'\[.*\]\(https?://[^\)]+\)', "External URL link"),
            (r':doc:`[^`]+`', "Sphinx doc reference"),
            (r':ref:`[^`]+`', "Sphinx cross-reference"),
        ]

        broken_patterns = [
            (r'\[.*\]\(#.*\)', "Internal anchor link"),
            (r'\.\./\.\./\.\./', "Deep relative path (may be fragile)"),
            (r'\.html#', "HTML anchor link"),
        ]

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in broken_patterns:
                if re.search(pattern, line):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"Potentially broken link: {desc}",
                        "explanation": "This link pattern may lead to broken references.",
                        "fix": "Verify the link target exists and is correct",
                    })
                    break

        return findings

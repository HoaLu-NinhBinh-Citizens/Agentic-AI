"""glob vs listdir detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class GlobVsListdirRule:
    """Detect unnecessary glob usage when listdir would suffice.

    glob.glob() is slower than os.listdir() for simple directory
    listing without pattern matching.
    """

    rule_id: str = "PERF013"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        glob_patterns = [
            (r'glob\.glob\s*\(\s*os\.path\.join\s*\(\s*\w+\s*,\s*["\']\*["\']\s*\)', 
             "glob.glob with only * pattern"),
            (r'glob\.glob\s*\(\s*os\.path\.join\s*\(\s*\w+\s*,\s*["\']*.*["\']\s*\)', 
             "glob.glob with pattern"),
        ]

        listdir_patterns = [
            (r'os\.listdir\s*\(', "Using os.listdir()"),
            (r'Path\(\)\.iterdir\s*\(', "Using Path.iterdir()"),
            (r'os\.scandir\s*\(', "Using os.scandir() (efficient)"),
        ]

        lines = content.split('\n')
        has_listdir = any(re.search(p, content) for p in listdir_patterns)

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in glob_patterns:
                if re.search(pattern, line):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"glob vs listdir: {desc}",
                        "explanation": "glob.glob() is slower than os.listdir() for simple "
                                       "directory listings without pattern matching.",
                        "fix": "Use os.listdir() or Path.iterdir() instead",
                    })
                    break

        return findings

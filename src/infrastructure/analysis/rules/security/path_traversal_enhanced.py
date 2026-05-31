"""Path traversal detection rule (enhanced)."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class EnhancedPathTraversalRule:
    """Detect path traversal vulnerabilities.

    Path traversal allows attackers to access files outside
    the intended directory.
    """

    rule_id: str = "SEC038"
    severity: Severity = Severity.HIGH

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        traversal_patterns = [
            (r'\.\./', "Directory traversal pattern ../"),
            (r'\.\.\\\\', "Directory traversal pattern ..\\"),
            (r'%2e%2e/', "URL encoded traversal"),
            (r'%2e%2e\\\\', "URL encoded traversal"),
            (r'os\.path\.join\s*\([^)]*\.\.[^)]*\)', "os.path.join with .."),
            (r'open\s*\([^)]*\+[^)]*\.\.[^)]*\)', "open() with traversal in path"),
            (r'read\s*\([^)]*\.\.[^)]*\)', "read() with traversal"),
        ]

        safe_patterns = [
            (r'os\.path\.abspath', "Absolute path conversion"),
            (r'os\.path\.realpath', "Real path resolution"),
            (r'Path\.resolve\s*\(', "Path resolution"),
            (r'os\.path\.normpath', "Path normalization"),
            (r'safe_join', "Safe join function"),
            (r'send_from_directory', "Safe file serving"),
        ]

        lines = content.split('\n')
        has_safe = any(re.search(p, content) for p in safe_patterns)

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in traversal_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    if not has_safe:
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": i,
                            "message": f"Path traversal: {desc}",
                            "explanation": "Path traversal patterns detected. Use secure path handling.",
                            "fix": "Use os.path.realpath() and validate paths are within allowed directory",
                        })
                    break

        return findings

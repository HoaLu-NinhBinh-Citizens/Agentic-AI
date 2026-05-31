"""Insecure file upload detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class InsecureFileUploadRule:
    """Detect insecure file upload handling.

    File uploads without proper validation can lead to
    remote code execution or file overwrite attacks.
    """

    rule_id: str = "SEC035"
    severity: Severity = Severity.HIGH

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        upload_patterns = [
            (r'request\.files', "File upload handling"),
            (r'upload', "File upload functionality"),
            (r'save\s*\([^)]*filename', "Saving uploaded file"),
            (r'file\.save\s*\(', "Saving uploaded file"),
            (r'upload_to\s*=', "Django file upload path"),
        ]

        validation_patterns = [
            (r'secure_filename', "Secure filename generation"),
            (r'allowed_extensions', "Extension allowlist"),
            (r'mimetype\s*in\s*\[', "MIME type validation"),
            (r'Content-Type\s*in\s*\[', "Content-Type validation"),
            (r'\\.content_length', "File size check"),
            (r'\\.content_type', "Content type validation"),
        ]

        safe_patterns = [
            (r'\\.filename\s*=\s*secure_filename', "Using secure_filename"),
            (r'allowed=\[', "Allowed extensions list"),
            (r're\.match.*\\.filename', "Filename validation regex"),
        ]

        lines = content.split('\n')
        has_upload = any(re.search(p, content, re.IGNORECASE) for p in upload_patterns)
        has_validation = any(re.search(p, content) for p in validation_patterns)
        has_safe = any(re.search(p, content) for p in safe_patterns)

        if has_upload:
            if not has_validation and not has_safe:
                findings.append({
                    "rule_id": self.rule_id,
                    "severity": self.severity.value,
                    "file": file_path,
                    "line": 1,
                    "message": "Insecure file upload: no validation detected",
                    "explanation": "File uploads without validation can allow malicious file execution.",
                    "fix": "Validate filename, extension, MIME type, and file size",
                })

        return findings

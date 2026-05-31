"""FastAPI unsafe file upload rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class UnsafeFileUploadRule:
    """Detect insecure file upload handling in FastAPI.

    File uploads without proper validation can lead to remote code
    execution, file overwrite attacks, or storage exhaustion.
    """

    rule_id: str = "FASTAPI010"
    severity: Severity = Severity.HIGH

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        upload_patterns = [
            (r'UploadFile', "FastAPI UploadFile usage"),
            (r'request\.files', "Starlette file upload"),
            (r'upload', "File upload functionality"),
            (r'file\.save\s*\(', "Saving uploaded file directly"),
            (r'\.filename\s*=', "Using upload filename"),
        ]

        validation_patterns = [
            (r'secure_filename', "secure_filename from werkzeug"),
            (r'allowed_extensions', "Extension allowlist defined"),
            (r'mimetype\s*in\s*\[', "MIME type validation"),
            (r'ContentType\s+in\s*\[', "Content-Type validation"),
            (r'content_length', "File size check"),
            (r'max_size', "Maximum size check"),
            (r'file\.content_type', "Content type check"),
            (r'\.file\.seek\s*\(', "File seek for size check"),
            (r'PIL|Image\.open', "Image validation with PIL"),
            (r'python_magic', "File type validation with magic"),
        ]

        has_upload = any(re.search(p, content, re.IGNORECASE) for p, _ in upload_patterns)
        has_validation = any(re.search(p, content) for p, _ in validation_patterns)
        has_fastapi = 'fastapi' in content.lower() or 'FastAPI' in content

        if not has_upload or not has_fastapi:
            return findings

        lines = content.split('\n')
        
        if has_upload and not has_validation:
            for i, line in enumerate(lines, 1):
                if re.search(r'(UploadFile|request\.files|file\.save)', line):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": "Insecure file upload: no validation detected",
                        "explanation": "File uploads without validation can allow malicious file execution, "
                                       "path traversal attacks, or storage exhaustion.",
                        "fix": "Validate: (1) file extension whitelist, (2) MIME type, (3) file size, "
                               "(4) content verification, (5) use secure_filename()",
                    })
                    break
        else:
            for i, line in enumerate(lines, 1):
                if line.strip().startswith(('#', '//')):
                    continue
                    
                if re.search(r'file\.save\s*\(', line):
                    next_lines = '\n'.join(lines[i:min(i+10, len(lines))])
                    
                    if 'secure_filename' not in next_lines and '.filename' in next_lines:
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": i,
                            "message": "File saved without secure_filename",
                            "explanation": "Using the original filename directly can allow path traversal attacks.",
                            "fix": "Use: secure_filename(file.filename) before saving",
                        })

        return findings

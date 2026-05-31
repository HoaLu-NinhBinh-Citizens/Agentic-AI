"""FastAPI insecure CORS configuration rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class InsecureCORSRule:
    """Detect insecure CORS configurations in FastAPI.

    CORS allowing all origins (*) exposes the API to cross-site attacks.
    """

    rule_id: str = "FASTAPI002"
    severity: Severity = Severity.HIGH

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        cors_patterns = [
            (r'CORSMiddleware', "CORS middleware usage"),
            (r'allow_origins\s*=\s*\[\s*["\']\*["\']\s*\]', "CORS allow all origins (explicit)"),
            (r'allow_origins\s*=\s*\*', "CORS allow all origins (wildcard)"),
            (r'add_cors_headers', "Manual CORS headers"),
            (r'Access-Control-Allow-Origin', "Manual CORS header setting"),
        ]

        for i, line in enumerate(content.split('\n'), 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in cors_patterns:
                if re.search(pattern, line):
                    if 'allow_origins' in pattern and '*' in line:
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": i,
                            "message": "Insecure CORS: allowing all origins",
                            "explanation": "Setting allow_origins=['*'] allows any website to make "
                                           "requests to your API, enabling cross-site attacks.",
                            "fix": "Specify exact allowed origins: allow_origins=['https://yourdomain.com']",
                        })
                    elif 'CORSMiddleware' in line:
                        context_lines = content.split('\n')
                        context = '\n'.join(context_lines[max(0, i-1):min(len(context_lines), i+20)])
                        
                        if 'allow_origins' not in context or '*' in context:
                            if re.search(r'allow_origins\s*=\s*\*', context):
                                continue
                            findings.append({
                                "rule_id": self.rule_id,
                                "severity": self.severity.value,
                                "file": file_path,
                                "line": i,
                                "message": "CORS middleware may allow all origins",
                                "explanation": "Verify CORS configuration does not allow all origins in production.",
                                "fix": "Use specific origins: allow_origins=['https://example.com']",
                            })

        return findings

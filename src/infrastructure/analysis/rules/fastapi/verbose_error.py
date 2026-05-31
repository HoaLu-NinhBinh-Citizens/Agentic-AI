"""FastAPI verbose error handling rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class VerboseErrorRule:
    """Detect verbose error messages that may leak sensitive information.

    Detailed error messages in production can expose internal implementation
    details, stack traces, and database information to attackers.
    """

    rule_id: str = "FASTAPI007"
    severity: Severity = Severity.MEDIUM

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        verbose_error_patterns = [
            (r'except\s*\([^)]*\)\s*:\s*[^#\n]*\s*traceback\.print_exc', "Printing traceback to stdout"),
            (r'except\s*\([^)]*\)\s*:\s*[^#\n]*raise\s+\w+Exception\s*\(\s*f["\']', "Raising detailed exceptions"),
            (r'logger\.exception\s*\(', "Logging exception details"),
            (r'return\s+\{[^}]*["\']error["\'][^}]*traceback', "Returning error with traceback"),
            (r'return\s+\{[^}]*["\']detail["\'][^}]*traceback', "Returning detail with traceback"),
            (r'except.*:\s*.*str\s*\(\s*e\s*\)', "Converting exception to string in response"),
            (r'HTTPException.*detail\s*=\s*str\s*\(\s*\w+\s*\)', "Exception detail from exception object"),
        ]

        production_patterns = [
            (r'uvicorn\.run.*debug\s*=\s*False', "Production mode explicitly set"),
            (r'environment.*production', "Production environment check"),
        ]

        is_production = any(
            re.search(p, content, re.IGNORECASE) 
            for p, _ in production_patterns
        )

        lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in verbose_error_patterns:
                if re.search(pattern, line, re.DOTALL):
                    if 'debug' not in line.lower() and 'test' not in line.lower():
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": i,
                            "message": f"Verbose error handling: {desc}",
                            "explanation": "Detailed error messages can leak sensitive information about "
                                           "your system's internal structure.",
                            "fix": "Use generic error messages in production. Log details server-side only.",
                        })

        exception_handlers = re.findall(r'@app\.exception_handler|@router\.exception_handler', content)
        if not exception_handlers and is_production:
            findings.append({
                "rule_id": self.rule_id,
                "severity": self.severity.value,
                "file": file_path,
                "line": 1,
                "message": "No custom exception handlers defined",
                "explanation": "Custom exception handlers can ensure consistent, safe error responses.",
                "fix": "Add @app.exception_handler(HTTPException) to return safe error messages",
            })

        return findings

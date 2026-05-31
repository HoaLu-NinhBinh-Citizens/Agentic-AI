"""FastAPI debug mode in production detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class FastAPIDebugModeRule:
    """Detect debug mode enabled in FastAPI applications.

    Debug mode should never be enabled in production as it exposes
    sensitive information including stack traces and environment variables.
    """

    rule_id: str = "FASTAPI009"
    severity: Severity = Severity.CRITICAL

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        debug_patterns = [
            (r'uvicorn\.run\s*\([^)]*debug\s*=\s*True', "uvicorn debug=True"),
            (r'uvicorn\.run\s*\([^)]*reload\s*=\s*True', "uvicorn reload=True (dev mode)"),
            (r'FastAPI\s*\([^)]*debug\s*=\s*True', "FastAPI debug=True"),
            (r'app\s*=\s*FastAPI\s*\([^)]*debug\s*=\s*True', "FastAPI app with debug=True"),
            (r'if\s+__name__\s*==\s*["\']__main__["\'][\s\n]+.*debug\s*=\s*True', "Debug in main block"),
            (r'logging\.basicConfig\s*\([^)]*level\s*=\s*logging\.DEBUG', "Logging set to DEBUG level"),
            (r'logger\.setLevel\s*\(\s*logging\.DEBUG\s*\)', "Logger level set to DEBUG"),
        ]

        production_patterns = [
            (r'environment\s*==\s*["\']production["\']', "Production environment check"),
            (r'ENV\s*==\s*["\']production["\']', "ENV=production check"),
            (r'os\.getenv\s*\([^)]*["\']production["\']', "Production env var check"),
            (r'deploy|prod', "Production deployment context"),
        ]

        is_production = any(
            re.search(pattern, content, re.IGNORECASE) 
            for pattern, _ in production_patterns
        )

        lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in debug_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    severity = Severity.CRITICAL if 'debug=True' in line else Severity.HIGH
                    
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"Debug mode enabled: {desc}",
                        "explanation": "Debug mode exposes sensitive information including stack traces, "
                                       "internal variables, and environment configuration.",
                        "fix": "Set debug=False, reload=False in production. Use environment variables: "
                               "debug=os.getenv('DEBUG', 'False').lower() == 'true'",
                    })

        if is_production and not findings:
            if re.search(r'debug\s*=\s*(?!False)', content):
                findings.append({
                    "rule_id": self.rule_id,
                    "severity": self.severity.value,
                    "file": file_path,
                    "line": 1,
                    "message": "Production code may have debug enabled",
                    "explanation": "Debug mode should be explicitly disabled in production environments.",
                    "fix": "Ensure debug=False or use: debug=os.getenv('DEBUG', 'False').lower() == 'true'",
                })

        return findings

"""Input validation missing detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class MissingInputValidationRule:
    """Detect missing input validation.

    User input should always be validated before use.
    """

    rule_id: str = "SEC030"
    severity: Severity = Severity.MEDIUM

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        input_patterns = [
            (r'request\.args\.get', "URL query parameter"),
            (r'request\.form\.get', "Form data"),
            (r'request\.json', "JSON body"),
            (r'request\.data', "Raw request data"),
            (r'request\.files', "Uploaded files"),
            (r'input\s*\(', "User input() call"),
            (r'sys\.argv', "Command line arguments"),
            (r'os\.environ\.get', "Environment variables"),
        ]

        validation_patterns = [
            (r'validate', "Validation function"),
            (r'schema\.validate', "Schema validation"),
            (r'pydantic', "Pydantic validation"),
            (r'validator', "Custom validator"),
            (r'type\s*=\s*str,\s*regex', "Type/regex validation"),
            (r'@field_validator', "Pydantic field validator"),
            (r're\.match\s*\(', "Regex validation"),
            (r'in\s+\[', "Allowlist check"),
        ]

        lines = content.split('\n')
        has_validation = any(re.search(p, content, re.IGNORECASE) for p in validation_patterns)

        input_count = 0
        for pattern, desc in input_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                input_count += 1

        if input_count > 0 and not has_validation:
            findings.append({
                "rule_id": self.rule_id,
                "severity": self.severity.value,
                "file": file_path,
                "line": 1,
                "message": f"Missing input validation ({input_count} inputs)",
                "explanation": "User input detected but no validation patterns found. "
                               "All input should be validated before use.",
                "fix": "Add input validation using schemas, type hints, or allowlists",
            })

        return findings

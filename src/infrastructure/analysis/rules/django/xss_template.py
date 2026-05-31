"""Django XSS via template variables rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class XSSTemplateRule:
    """Detect unsafe template variables that may allow XSS attacks.

    Django auto-escapes HTML, but using |safe or autoescape off
    can introduce XSS vulnerabilities.
    """

    rule_id: str = "DJANGO002"
    severity: Severity = Severity.HIGH

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        unsafe_template_patterns = [
            (r'\{\{\s*\w+\s*\|\s*safe\s*\}\}', "Template variable with |safe filter"),
            (r'\{\%\s*autoescape\s+off\s*\%\}', "autoescape turned off"),
            (r'\{\%\s*autoescape\s+False\s*\%\}', "autoescape set to False"),
            (r'\{\{\s*\w+\.\w+\s*\|\s*safe\s*\}\}', "Nested variable with |safe"),
            (r'\{\{\s*.*\|linebreaks\|safe', "linebreaks with |safe"),
            (r'\{\{\s*.*\|safe\|safe', "Double |safe filter"),
        ]

        user_input_patterns = [
            (r'request\.GET', "User input from GET params"),
            (r'request\.POST', "User input from POST data"),
            (r'request\.COOKIES', "User input from cookies"),
            (r'request\.data', "User input from request data"),
        ]

        is_template = '.html' in file_path or '.htm' in file_path
        has_django = 'django' in content.lower() or 'jinja' in content.lower()

        if not (is_template or has_django):
            return findings

        lines = content.split('\n')

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('{', '#', '<!--')):
                if '<!--' in line:
                    continue

            for pattern, desc in unsafe_template_patterns:
                if re.search(pattern, line):
                    has_user_input = any(re.search(p, content) for p in user_input_patterns)

                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"Potential XSS: {desc}",
                        "explanation": "|safe disables HTML escaping, allowing potential XSS if the "
                                       "content contains user input.",
                        "fix": "Avoid |safe with user-generated content. If needed, explicitly sanitize "
                               "with mark_safe() after validation in the view.",
                    })

        if has_django:
            safe_with_user_input = re.search(
                r'(request\.(GET|POST|COOKIES|data)|user\.)[^}]*\|\s*safe',
                content
            )
            if safe_with_user_input:
                findings.append({
                    "rule_id": self.rule_id,
                    "severity": self.severity.value,
                    "file": file_path,
                    "line": 1,
                    "message": "User input marked as safe without sanitization",
                    "explanation": "Marking user input as safe without proper sanitization can lead to XSS.",
                    "fix": "Sanitize user input before marking safe, or use a whitelist approach.",
                })

        return findings

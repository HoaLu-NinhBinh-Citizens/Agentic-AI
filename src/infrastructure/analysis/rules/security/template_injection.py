"""Template injection detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class TemplateInjectionRule:
    """Detect potential template injection vulnerabilities.

    Template injection can allow attackers to execute
    arbitrary code through template engines.
    """

    rule_id: str = "SEC029"
    severity: Severity = Severity.CRITICAL

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        template_patterns = [
            (r'jinja2| Jinja2|jinja', "Jinja2 template engine"),
            (r'Template\s*\(', "Flask/other template"),
            (r'render_template_string', "Flask template rendering"),
            (r'{{.*}}', "Template syntax in code"),
            (r'{%.*%}', "Template control syntax"),
            (r'genshi', "Genshi template engine"),
            (r'Mako', "Mako template engine"),
            (r'Template.render', "Template rendering"),
        ]

        injection_risk = [
            (r'render_template_string\s*\([^)]*\+', "Template from concatenation"),
            (r'Template\s*\([^)]*\+', "Template from user input"),
            (r'{{.*request\.|render_template_string.*request', "User input in template"),
        ]

        safe_patterns = [
            (r'AutoEscape', "Autoescaping enabled"),
            (r'select_autoescape', "Autoescape configured"),
            (r'{%\s+autoescape', "Autoescape block"),
            (r'from_string', "Using from_string safely"),
        ]

        lines = content.split('\n')
        has_safe = any(re.search(p, content) for p in safe_patterns)

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in injection_risk:
                if re.search(pattern, line):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"Template injection: {desc}",
                        "explanation": "Template rendering with user input can lead to code execution.",
                        "fix": "Never render user input as template; use autoescape and input validation",
                    })
                    break

        for pattern, desc in template_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                if not has_safe:
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": Severity.MEDIUM.value,
                        "file": file_path,
                        "line": 1,
                        "message": f"Template engine usage: {desc}",
                        "explanation": "Ensure templates properly escape user input.",
                        "fix": "Enable autoescape and validate all template inputs",
                    })
                break

        return findings

"""Django missing CSRF protection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class CSRFMissingRule:
    """Detect missing CSRF protection on Django forms and views.

    CSRF tokens prevent cross-site request forgery attacks on state-changing operations.
    """

    rule_id: str = "DJANGO003"
    severity: Severity = Severity.HIGH

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        csrf_token_patterns = [
            (r'\{\%\s*csrf_token\s*\%\}', "CSRF token in template"),
            (r'@csrf_protect', "csrf_protect decorator"),
            (r'@ensure_csrf_cookie', "ensure_csrf_cookie decorator"),
            (r'csrf_exempt', "csrf_exempt decorator (should be rare)"),
        ]

        mutation_patterns = [
            (r'@require_http_methods\s*\(\s*\[["\']POST["\']', "POST-only view"),
            (r'@require_POST', "require_POST decorator"),
            (r'@login_required', "login_required decorator (implies state change)"),
            (r'def\s+\w+\s*\(.*request\)\s*:[\s\n]+.*request\.method\s*==\s*["\']POST["\']',
             "View handling POST"),
        ]

        has_django = 'django' in content.lower() or 'from django' in content

        if not has_django:
            return findings

        has_csrf = any(re.search(p, content, re.IGNORECASE) for p in csrf_token_patterns)
        has_mutation = any(re.search(p, content, re.DOTALL) for p in mutation_patterns)

        is_view_file = 'view' in file_path.lower() or 'form' in file_path.lower()
        is_template = '.html' in file_path or '.htm' in file_path

        if is_template and has_mutation and not has_csrf:
            forms = re.findall(r'<form[^>]*>', content, re.IGNORECASE)
            for i, line in enumerate(content.split('\n'), 1):
                form_match = re.search(r'<form[^>]*>', line, re.IGNORECASE)
                if form_match:
                    form_tag = form_match.group(0)
                    if 'method=' in form_tag.lower() and 'post' in form_tag.lower():
                        if 'csrf' not in line.lower():
                            findings.append({
                                "rule_id": self.rule_id,
                                "severity": self.severity.value,
                                "file": file_path,
                                "line": i,
                                "message": "POST form without CSRF token",
                                "explanation": "Forms that submit data should include {% csrf_token %} "
                                               "to prevent CSRF attacks.",
                                "fix": "Add {% csrf_token %} inside the <form> tag",
                            })

        if is_view_file and has_mutation:
            if not has_csrf:
                function_names = re.findall(r'def\s+(\w+)\s*\(', content)
                for func_name in function_names:
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": 1,
                        "message": f"View {func_name}() may lack CSRF protection",
                        "explanation": "State-changing views should use CSRF protection.",
                        "fix": "Ensure CSRF middleware is enabled in settings.py or use @csrf_protect",
                    })
                    break

        return findings

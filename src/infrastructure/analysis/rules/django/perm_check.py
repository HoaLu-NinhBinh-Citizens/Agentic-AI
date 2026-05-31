"""Django missing permission check rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class PermissionCheckRule:
    """Detect views without proper permission checks in Django.

    Views should verify user permissions before allowing access to sensitive data or actions.
    """

    rule_id: str = "DJANGO007"
    severity: Severity = Severity.MEDIUM

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        permission_patterns = [
            (r'@permission_required', "permission_required decorator"),
            (r'@user_passes_test', "user_passes_test decorator"),
            (r'@login_required', "login_required decorator"),
            (r'\.has_perm\s*\(', "has_perm permission check"),
            (r'\.has_perms\s*\(', "has_perms permission check"),
            (r'request\.user\.is_authenticated', "Authenticated user check"),
            (r'PermissionRequiredMixin', "PermissionRequiredMixin class"),
            (r'UserPassesTestMixin', "UserPassesTestMixin class"),
        ]

        sensitive_keywords = [
            'admin', 'dashboard', 'user', 'account', 'profile',
            'settings', 'config', 'manage', 'delete', 'create',
            'update', 'edit', 'password', 'payment', 'billing',
        ]

        mutation_keywords = [
            'post', 'put', 'patch', 'delete', 'create', 'update',
            'delete', 'remove', 'disable', 'enable', 'activate',
        ]

        is_view = any(p in file_path.lower() for p in ['view', 'views', 'api'])
        has_django = 'django' in content.lower()

        if not (is_view or has_django):
            return findings

        lines = content.split('\n')

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//', '#')):
                continue

            if re.search(r'def\s+\w+\s*\(.*request', line):
                func_name_match = re.search(r'def\s+(\w+)\s*\(', line)
                if not func_name_match:
                    continue

                func_name = func_name_match.group(1)
                next_lines = '\n'.join(lines[i:min(i+30, len(lines))])

                has_permission = any(re.search(p, next_lines) for p in permission_patterns)
                is_sensitive = any(kw in func_name.lower() for kw in sensitive_keywords)
                is_mutation = any(kw in func_name.lower() for kw in mutation_keywords)

                if (is_sensitive or is_mutation) and not has_permission:
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"View {func_name}() may lack permission checks",
                        "explanation": "Sensitive views should verify user permissions before granting access.",
                        "fix": "Add @permission_required('app.view_model') or @login_required decorator",
                    })

        return findings

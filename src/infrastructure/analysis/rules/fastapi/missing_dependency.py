"""FastAPI missing dependency injection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class MissingDependencyRule:
    """Detect FastAPI endpoints without proper dependency injection.

    Using dependency injection ensures proper separation of concerns,
    easier testing, and cleaner request handling.
    """

    rule_id: str = "FASTAPI001"
    severity: Severity = Severity.MEDIUM

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        endpoint_pattern = r'@(?:app|router)\.(get|post|put|delete|patch|options|head)\(["\']([^"\']+)["\']'
        auth_keywords = ['token', 'auth', 'user', 'session', 'jwt', 'bearer', 'api_key', 'apikey']
        db_keywords = ['db', 'database', 'session', 'cursor']
        
        has_endpoint = re.search(endpoint_pattern, content)
        has_fastapi = 'fastapi' in content.lower() or 'uvicorn' in content.lower()
        
        if not has_endpoint or not has_fastapi:
            return findings

        lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            endpoint_match = re.search(endpoint_pattern, line)
            if endpoint_match:
                method, path = endpoint_match.groups()
                next_lines = '\n'.join(lines[i:min(i+10, len(lines))])
                
                has_auth_dep = any(kw in next_lines.lower() for kw in auth_keywords)
                has_db_dep = any(kw in next_lines.lower() for kw in db_keywords)
                has_dep_depends = 'Depends' in next_lines
                has_security = 'Security' in next_lines or 'OAuth2' in next_lines
                
                is_protected_path = not any(p in path.lower() for p in ['/health', '/docs', '/openapi', '/redoc', '/login', '/auth'])
                
                if is_protected_path and not has_dep_depends and not has_security:
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"Endpoint {method.upper()} {path} may lack dependency injection",
                        "explanation": "Endpoints should use FastAPI's Depends() for authentication, "
                                       "database sessions, and other shared dependencies.",
                        "fix": f"Add dependency injection: async def endpoint(Depends(get_current_user))",
                    })

        return findings

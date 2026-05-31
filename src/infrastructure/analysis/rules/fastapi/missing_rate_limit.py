"""FastAPI missing rate limiting rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class MissingRateLimitRule:
    """Detect FastAPI endpoints without rate limiting.

    Without rate limiting, APIs are vulnerable to abuse, DoS attacks,
    and resource exhaustion.
    """

    rule_id: str = "FASTAPI006"
    severity: Severity = Severity.MEDIUM

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        rate_limit_patterns = [
            (r'RateLimiter', "RateLimiter usage"),
            (r'slowapi', "SlowAPI rate limiting"),
            (r'rate_limit', "Rate limit decorator"),
            (r'max_requests', "Max requests configuration"),
            (r'throttle', "Throttle decorator"),
            (r'@limiter\.limit', "Limiter decorator"),
        ]

        has_rate_limit = any(
            re.search(p, content, re.IGNORECASE) 
            for p, _ in rate_limit_patterns
        )
        has_fastapi = 'fastapi' in content.lower() or 'FastAPI' in content
        has_endpoint = re.search(r'@(?:app|router)\.(get|post|put|delete|patch)', content)
        
        if not has_fastapi or not has_endpoint:
            return findings

        if not has_rate_limit:
            auth_endpoints = []
            mutation_endpoints = []
            
            lines = content.split('\n')
            for i, line in enumerate(lines, 1):
                endpoint_match = re.search(r'@(?:app|router)\.(get|post|put|delete|patch)\(["\']([^"\']+)["\']', line)
                if endpoint_match:
                    method, path = endpoint_match.groups()
                    is_auth = any(k in path.lower() for k in ['login', 'auth', 'token', 'signup', 'register'])
                    is_mutation = method in ['post', 'put', 'delete', 'patch']
                    
                    if is_auth:
                        auth_endpoints.append((i, method.upper(), path))
                    elif is_mutation:
                        mutation_endpoints.append((i, method.upper(), path))
            
            for line_num, method, path in auth_endpoints:
                findings.append({
                    "rule_id": self.rule_id,
                    "severity": self.severity.value,
                    "file": file_path,
                    "line": line_num,
                    "message": f"Authentication endpoint {method} {path} lacks rate limiting",
                    "explanation": "Authentication endpoints are prime targets for brute force attacks. "
                                   "Rate limiting is essential for security.",
                    "fix": "Add rate limiting: @limiter.limit('5/minute') or use slowapi",
                })

        return findings

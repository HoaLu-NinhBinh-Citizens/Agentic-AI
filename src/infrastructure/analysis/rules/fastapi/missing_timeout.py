"""FastAPI missing timeout configuration rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class MissingTimeoutRule:
    """Detect missing timeout configurations in FastAPI requests.

    Without timeouts, requests can hang indefinitely, leading to
    resource exhaustion and DoS vulnerabilities.
    """

    rule_id: str = "FASTAPI008"
    severity: Severity = Severity.MEDIUM

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        timeout_patterns = [
            (r'timeout\s*=', "Timeout parameter usage"),
            (r'httpx\.Timeout', "httpx Timeout configuration"),
            (r'aiohttp\.ClientSession.*timeout', "aiohttp timeout"),
            (r'asyncio\.wait_for', "asyncio.wait_for with timeout"),
            (r'@after_request.*timeout', "After-request timeout header"),
        ]

        has_timeout = any(
            re.search(pattern, content, re.IGNORECASE) 
            for pattern, _ in timeout_patterns
        )
        has_external_calls = any(re.search(p, content) for p in [
            r'requests\.(get|post|put|delete)',
            r'httpx\.(get|post|put|delete|client)',
            r'aiohttp\.',
            r'urllib3\.',
            r'http\.client\.',
        ])

        if has_external_calls and not has_timeout:
            lines = content.split('\n')
            for i, line in enumerate(lines, 1):
                if line.strip().startswith(('#', '//')):
                    continue

                if re.search(r'(requests\.(get|post|put|delete)|httpx\.(get|post|put|delete|Client))', line):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": "HTTP request without timeout configuration",
                        "explanation": "HTTP requests without timeouts can hang indefinitely, "
                                       "blocking the event loop and exhausting resources.",
                        "fix": "Add timeout: requests.get(url, timeout=30) or httpx.AsyncClient(timeout=10.0)",
                    })

        http_client_patterns = [
            (r'httpx\.AsyncClient\s*\([^)]*\)(?!\s*,\s*timeout)', "AsyncClient without timeout"),
            (r'httpx\.Client\s*\([^)]*\)(?!\s*,\s*timeout)', "Client without timeout"),
            (r'aiohttp\.ClientSession\s*\([^)]*\)(?!\s*,\s*timeout)', "ClientSession without timeout"),
        ]

        for pattern, desc in http_client_patterns:
            if re.search(pattern, line) if 'line' in locals() else False:
                continue
            for i, line in enumerate(content.split('\n'), 1):
                if re.search(pattern, line):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"{desc}",
                        "explanation": "HTTP clients should have explicit timeout configurations.",
                        "fix": "Add timeout parameter: httpx.AsyncClient(timeout=30.0)",
                    })
                    break

        return findings

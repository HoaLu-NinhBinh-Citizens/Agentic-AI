"""FastAPI synchronous code in async endpoint rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class FastAPISyncInAsyncRule:
    """Detect synchronous blocking calls in FastAPI async endpoints.

    Using blocking I/O in async functions blocks the entire event loop,
    degrading performance for all concurrent requests.
    """

    rule_id: str = "FASTAPI005"
    severity: Severity = Severity.HIGH

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        blocking_patterns = [
            (r'\btime\.sleep\s*\(', "Blocking time.sleep() in async endpoint"),
            (r'\brequests\.(get|post|put|delete|patch)\s*\(', "Blocking requests library in async"),
            (r'\bhttpx\.Client\s*\(', "Synchronous httpx.Client in async endpoint"),
            (r'\bsubprocess\.(run|Popen)\s*\(', "Blocking subprocess in async"),
            (r'\bopen\s*\([^)]*["\']r["\']', "Synchronous file read in async"),
            (r'\.read\s*\(\s*\)', "Synchronous read in async"),
            (r'\.write\s*\(\s*\)', "Synchronous write in async"),
            (r'\bcursor\.execute\s*\(', "Blocking database execute in async"),
            (r'\bdb\.execute\s*\(', "Blocking db.execute in async"),
            (r'\bsync_session\.', "Synchronous SQLAlchemy session in async"),
        ]

        async_patterns = [
            (r'async\s+def\s+', "Async function definition"),
            (r'aiohttp', "Async HTTP library (aiohttp)"),
            (r'asyncio\.', "Asyncio module"),
            (r'httpx\.AsyncClient', "Async HTTPX client"),
            (r'asyncpg', "Async PostgreSQL library"),
            (r'aiomysql', "Async MySQL library"),
            (r'SQLModel\.select', "Async SQLModel"),
            (r'\bawait\s+', "Await keyword"),
        ]

        if not any(re.search(p, content) for p, _ in async_patterns):
            return findings

        lines = content.split('\n')
        in_async_func = False
        async_depth = 0
        func_indent = 0

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            if re.search(r'async\s+def\s+', line):
                in_async_func = True
                async_depth = len(line) - len(line.lstrip())

            if in_async_func:
                if line.strip() and not line.strip().startswith('#'):
                    current_depth = len(line) - len(line.lstrip())
                    if current_depth <= async_depth and 'async def' not in line:
                        in_async_func = False

                for pattern, desc in blocking_patterns:
                    if re.search(pattern, line):
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": i,
                            "message": f"Blocking call in async: {desc}",
                            "explanation": "Synchronous blocking calls in async functions prevent other "
                                           "coroutines from running, blocking the entire event loop.",
                            "fix": "Use async alternatives: asyncio.sleep, httpx.AsyncClient, aiohttp, "
                                   "or run blocking code in executor: await loop.run_in_executor()",
                        })

        return findings

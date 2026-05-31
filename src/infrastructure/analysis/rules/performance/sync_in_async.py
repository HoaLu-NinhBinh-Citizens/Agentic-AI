"""Synchronous code in async function detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class SyncInAsyncRule:
    """Detect synchronous blocking calls in async functions.

    Using blocking I/O in async functions blocks the entire event loop.
    Use async equivalents or run in thread pool.
    """

    rule_id: str = "PERF008"
    severity: Severity = Severity.HIGH

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        blocking_patterns = [
            (r'time\.sleep\s*\(', "Blocking time.sleep() in async function"),
            (r'requests\.get\s*\(', "Blocking requests.get() in async"),
            (r'requests\.post\s*\(', "Blocking requests.post() in async"),
            (r'httpx\.sync', "Blocking HTTPX sync call"),
            (r'subprocess\.run\s*\(', "Blocking subprocess.run() in async"),
            (r'subprocess\.Popen\s*\(', "Blocking subprocess.Popen() in async"),
            (r'open\s*\(', "Blocking file open() in async"),
            (r'\.read\s*\(', "Blocking file read() in async"),
            (r'\.write\s*\(', "Blocking file write() in async"),
            (r'database\.execute\s*\(', "Blocking DB execute in async"),
            (r'cursor\.execute\s*\(', "Blocking cursor.execute() in async"),
        ]

        async_patterns = [
            (r'async\s+def\s+', "Async function definition"),
            (r'await\s+', "Await keyword used"),
            (r'aiohttp', "Async HTTP library"),
            (r'asyncio\.', "Asyncio module usage"),
            (r'httpx\.AsyncClient', "Async HTTPX client"),
            (r'asyncpg', "Async PostgreSQL library"),
            (r'aiomysql', "Async MySQL library"),
            (r'aioredis', "Async Redis library"),
        ]

        lines = content.split('\n')
        in_async_func = False
        async_depth = 0

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            if 'async def' in line:
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
                        "explanation": "Blocking calls in async functions prevent other "
                                       "coroutines from running.",
                        "fix": "Use async equivalent (e.g., asyncio.sleep, aiohttp) or "
                               "run in executor with loop.run_in_executor()",
                    })

        return findings

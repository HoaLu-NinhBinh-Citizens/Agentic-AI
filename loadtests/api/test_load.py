"""Load test for API server."""

import asyncio
import aiohttp
import time


async def test_concurrent_requests():
    async with aiohttp.ClientSession() as session:
        tasks = []
        for _ in range(100):
            task = session.get('http://localhost:8766/health')
            tasks.append(task)
        
        start = time.perf_counter()
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.perf_counter() - start
        
        print(f"Completed 100 requests in {elapsed:.2f}s")
        assert elapsed < 10.0

"""Quick load test for probe operations.

Run: python tests/integration/test_probe_load.py
"""

from __future__ import annotations

import asyncio
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


async def benchmark_memory_read(adapter, iterations: int = 100):
    """Benchmark memory read operations."""
    print(f"\n--- Memory Read Benchmark ({iterations} iterations) ---")
    
    times = []
    for i in range(iterations):
        start = time.perf_counter()
        result = await adapter.read_memory(0x20000000, 32)
        elapsed = (time.perf_counter() - start) * 1000  # ms
        times.append(elapsed)
    
    avg = sum(times) / len(times)
    min_t = min(times)
    max_t = max(times)
    
    print(f"  Avg: {avg:.2f} ms")
    print(f"  Min: {min_t:.2f} ms")
    print(f"  Max: {max_t:.2f} ms")
    
    return avg


async def benchmark_register_read(adapter, iterations: int = 100):
    """Benchmark register read operations."""
    print(f"\n--- Register Read Benchmark ({iterations} iterations) ---")
    
    times = []
    for i in range(iterations):
        start = time.perf_counter()
        await adapter.read_register("pc")
        elapsed = (time.perf_counter() - start) * 1000  # ms
        times.append(elapsed)
    
    avg = sum(times) / len(times)
    min_t = min(times)
    max_t = max(times)
    
    print(f"  Avg: {avg:.2f} ms")
    print(f"  Min: {min_t:.2f} ms")
    print(f"  Max: {max_t:.2f} ms")
    
    return avg


async def benchmark_concurrent_reads(adapter, concurrency: int = 10, iterations: int = 100):
    """Benchmark concurrent read operations."""
    print(f"\n--- Concurrent Reads Benchmark ({concurrency} concurrent, {iterations} total) ---")
    
    async def read_batch(n: int):
        times = []
        for _ in range(n):
            start = time.perf_counter()
            await adapter.read_memory(0x20000000, 32)
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)
        return times
    
    batch_size = iterations // concurrency
    start = time.perf_counter()
    
    tasks = [read_batch(batch_size) for _ in range(concurrency)]
    results = await asyncio.gather(*tasks)
    
    total_time = time.perf_counter() - start
    all_times = [t for batch in results for t in batch]
    
    avg = sum(all_times) / len(all_times)
    throughput = iterations / total_time
    
    print(f"  Total time: {total_time*1000:.2f} ms")
    print(f"  Avg per op: {avg:.2f} ms")
    print(f"  Throughput: {throughput:.1f} ops/sec")
    
    return throughput


async def run_load_test():
    """Run load tests on mock probe."""
    print("=" * 60)
    print("PROBE LOAD TEST")
    print("=" * 60)
    
    from src.infrastructure.hardware.jlink.probe import JLinkProbeAdapter
    
    # Create adapter with mock backend
    adapter = JLinkProbeAdapter(
        serial="LOAD_TEST",
        interface=1,
        speed_khz=4000,
        use_mock=True,
    )
    
    await adapter.connect()
    print("\nConnected to mock probe")
    
    # Benchmark tests
    await benchmark_memory_read(adapter, 100)
    await benchmark_register_read(adapter, 100)
    await benchmark_concurrent_reads(adapter, concurrency=10, iterations=100)
    
    await adapter.disconnect()
    
    print("\n" + "=" * 60)
    print("LOAD TEST COMPLETE")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    asyncio.run(run_load_test())

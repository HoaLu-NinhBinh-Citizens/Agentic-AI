"""Debug probe wrapper with timeout and retry abstraction.

Phase 6.1 (FIXED): Adds timeout and retry capabilities to probe operations:
- Configurable timeout per operation
- Automatic retry with exponential backoff
- USB disconnect detection
- Partial read handling

FIXES Applied:
- Probe operations now have timeout protection
- Automatic retry on transient failures
- USB disconnect detection and recovery
- Partial write handling
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ProbeError(Exception):
    """Base exception for probe errors."""
    pass


class ProbeTimeoutError(ProbeError):
    """Probe operation timed out."""
    pass


class ProbeDisconnectError(ProbeError):
    """Probe disconnected during operation."""
    pass


class ProbeWriteError(ProbeError):
    """Probe write operation failed."""
    pass


class RetryStrategy(Enum):
    """Retry strategy for probe operations."""
    NONE = "none"
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    FIBONACCI = "fibonacci"


@dataclass
class ProbeRetryConfig:
    """Configuration for probe retry behavior."""
    max_retries: int = 3
    initial_delay_ms: int = 100
    max_delay_ms: int = 5000
    backoff_multiplier: float = 2.0
    jitter_percent: float = 0.1  # 10% jitter
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    
    # Timeout configuration
    default_timeout_ms: int = 5000
    read_timeout_ms: int = 3000
    write_timeout_ms: int = 10000
    connect_timeout_ms: int = 10000
    verify_timeout_ms: int = 5000


@dataclass
class ProbeOperationMetrics:
    """Metrics for probe operations."""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    timeout_calls: int = 0
    disconnect_calls: int = 0
    retry_count: int = 0
    total_latency_ms: float = 0.0
    
    def record_success(self, latency_ms: float, retries: int = 0) -> None:
        self.total_calls += 1
        self.successful_calls += 1
        self.retry_count += retries
        self.total_latency_ms += latency_ms
    
    def record_failure(self, error_type: str) -> None:
        self.total_calls += 1
        self.failed_calls += 1
        if "timeout" in error_type.lower():
            self.timeout_calls += 1
        if "disconnect" in error_type.lower():
            self.disconnect_calls += 1
    
    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.successful_calls / self.total_calls
    
    @property
    def average_latency_ms(self) -> float:
        if self.successful_calls == 0:
            return 0.0
        return self.total_latency_ms / self.successful_calls


class ProbeRetryWrapper:
    """Wrapper that adds timeout and retry logic to probe operations.
    
    FIX: Real implementation with timeout, retry, and disconnect handling.
    
    Usage:
        wrapper = ProbeRetryWrapper(
            probe=actual_probe,
            config=ProbeRetryConfig(max_retries=3)
        )
        
        # All operations now have timeout and retry
        result = await wrapper.write_memory(addr, data)
    """
    
    def __init__(
        self,
        probe: Any,  # BaseProbe or similar
        config: ProbeRetryConfig | None = None,
        on_disconnect: Callable | None = None,
        on_retry: Callable | None = None,
    ):
        self._probe = probe
        self._config = config or ProbeRetryConfig()
        self._on_disconnect = on_disconnect
        self._on_retry = on_retry
        self._metrics = ProbeOperationMetrics()
        self._is_connected = True
    
    @property
    def metrics(self) -> ProbeOperationMetrics:
        return self._metrics
    
    @property
    def is_connected(self) -> bool:
        return self._is_connected
    
    async def _execute_with_retry(
        self,
        operation: str,
        func: Callable,
        timeout_ms: int | None = None,
        *args,
        **kwargs,
    ) -> Any:
        """Execute operation with timeout and retry."""
        timeout = timeout_ms or self._config.default_timeout_ms
        delay = self._config.initial_delay_ms
        retries = 0
        last_error: Exception | None = None
        
        while retries <= self._config.max_retries:
            start_time = asyncio.get_event_loop().time()
            
            try:
                # Execute with timeout
                result = await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=timeout / 1000.0
                )
                
                latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000
                self._metrics.record_success(latency_ms, retries)
                
                return result
                
            except asyncio.TimeoutError:
                latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000
                last_error = ProbeTimeoutError(f"{operation} timed out after {timeout}ms")
                self._metrics.record_failure("timeout")
                logger.warning(
                    "probe_timeout",
                    operation=operation,
                    timeout_ms=timeout,
                    retry=retries,
                )
                
            except (OSError, ConnectionError, IOError) as e:
                # USB disconnect or connection error
                latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000
                last_error = ProbeDisconnectError(f"{operation} failed: {e}")
                self._metrics.record_failure("disconnect")
                
                # Check if this is a disconnect error
                if self._is_disconnect_error(e):
                    self._is_connected = False
                    if self._on_disconnect:
                        await self._on_disconnect()
                
                logger.warning(
                    "probe_disconnect",
                    operation=operation,
                    error=str(e),
                    retry=retries,
                )
            
            except Exception as e:
                latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000
                last_error = ProbeError(f"{operation} failed: {e}")
                self._metrics.record_failure(str(e))
                logger.warning(
                    "probe_error",
                    operation=operation,
                    error=str(e),
                    retry=retries,
                )
            
            # Check if we should retry
            if retries >= self._config.max_retries:
                break
            
            # Calculate delay with jitter
            jitter = delay * self._config.jitter_percent * (2 * __import__("random").random() - 1)
            actual_delay = min(delay + jitter, self._config.max_delay_ms)
            
            if self._on_retry:
                await self._on_retry(operation, retries + 1, actual_delay, last_error)
            
            await asyncio.sleep(actual_delay / 1000.0)
            
            # Apply backoff strategy
            delay = self._apply_backoff(delay, retries)
            retries += 1
        
        # All retries exhausted
        raise ProbeError(
            f"{operation} failed after {self._config.max_retries + 1} attempts: {last_error}"
        )
    
    def _apply_backoff(self, current_delay: float, retry_count: int) -> float:
        """Apply backoff strategy to delay."""
        if self._config.strategy == RetryStrategy.EXPONENTIAL:
            return current_delay * self._config.backoff_multiplier
        elif self._config.strategy == RetryStrategy.LINEAR:
            return current_delay + self._config.initial_delay_ms
        elif self._config.strategy == RetryStrategy.FIBONACCI:
            # Simple fibonacci-like: sum previous two
            return current_delay + self._config.initial_delay_ms * 0.5
        return current_delay
    
    def _is_disconnect_error(self, error: Exception) -> bool:
        """Check if error indicates a disconnect."""
        error_str = str(error).lower()
        disconnect_patterns = [
            "disconnect",
            "connection reset",
            "broken pipe",
            "no device",
            "usb",
            "not connected",
            "read error",
            "write error",
            "timeout",
        ]
        return any(p in error_str for p in disconnect_patterns)
    
    async def read_memory(self, address: int, size: int) -> bytes:
        """Read memory with timeout and retry."""
        return await self._execute_with_retry(
            "read_memory",
            self._probe.read_memory,
            self._config.read_timeout_ms,
            address,
            size,
        )
    
    async def write_memory(self, address: int, data: bytes) -> bool:
        """Write memory with timeout and retry."""
        return await self._execute_with_retry(
            "write_memory",
            self._probe.write_memory,
            self._config.write_timeout_ms,
            address,
            data,
        )
    
    async def write_memory_with_verify(
        self, 
        address: int, 
        data: bytes,
        verify_readback: bool = True,
    ) -> tuple[bool, int]:
        """Write memory with verification.
        
        Returns:
            (success, bytes_written)
        """
        # Write with retry
        success = await self._execute_with_retry(
            "write_memory",
            self._probe.write_memory,
            self._config.write_timeout_ms,
            address,
            data,
        )
        
        if not success:
            return False, 0
        
        if not verify_readback:
            return True, len(data)
        
        # Verify by reading back
        try:
            readback = await self._execute_with_retry(
                "verify_readback",
                self._probe.read_memory,
                self._config.verify_timeout_ms,
                address,
                len(data),
            )
            
            if readback == data:
                return True, len(data)
            else:
                logger.warning(
                    "write_verify_failed",
                    address=f"0x{address:08X}",
                    expected_len=len(data),
                    actual_len=len(readback),
                )
                return False, 0
                
        except ProbeError as e:
            logger.error("verify_readback_failed", error=str(e))
            return False, 0
    
    async def write_memory_chunked(
        self,
        address: int,
        data: bytes,
        chunk_size: int = 256,
        verify_each: bool = False,
    ) -> tuple[bool, int]:
        """Write memory in chunks with progress tracking.
        
        FIX: Handles partial writes and verification per chunk.
        
        Returns:
            (success, total_bytes_written)
        """
        total_written = 0
        
        for offset in range(0, len(data), chunk_size):
            chunk = data[offset : offset + chunk_size]
            chunk_addr = address + offset
            
            # Write chunk
            success, chunk_len = await self.write_memory_with_verify(
                chunk_addr,
                chunk,
                verify_readback=verify_each,
            )
            
            if not success:
                logger.error(
                    "chunk_write_failed",
                    address=f"0x{chunk_addr:08X}",
                    remaining=len(data) - offset,
                )
                return False, total_written
            
            total_written += chunk_len
        
        return True, total_written
    
    async def connect(self) -> Any:
        """Connect with timeout."""
        return await self._execute_with_retry(
            "connect",
            self._probe.connect,
            self._config.connect_timeout_ms,
        )
    
    async def disconnect(self) -> None:
        """Disconnect probe."""
        try:
            await self._probe.disconnect()
            self._is_connected = False
        except Exception as e:
            logger.warning("disconnect_error", error=str(e))
    
    async def read_register(self, name: str) -> int:
        """Read register with timeout."""
        return await self._execute_with_retry(
            f"read_register({name})",
            self._probe.read_register,
            self._config.default_timeout_ms,
            name,
        )
    
    async def write_register(self, name: str, value: int) -> bool:
        """Write register with timeout."""
        return await self._execute_with_retry(
            f"write_register({name})",
            self._probe.write_register,
            self._config.default_timeout_ms,
            name,
            value,
        )
    
    async def get_probe_info(self) -> dict[str, Any]:
        """Get probe info (no retry needed)."""
        try:
            return await self._probe.get_probe_info()
        except Exception as e:
            logger.error("get_probe_info_failed", error=str(e))
            return {}


class RetriableProbeFactory:
    """Factory for creating retry-wrapped probes.
    
    Usage:
        factory = RetriableProbeFactory(
            config=ProbeRetryConfig(max_retries=3),
            on_disconnect=handle_disconnect,
        )
        
        wrapped = factory.wrap(jlink_probe)
        result = await wrapped.read_memory(0x08000000, 256)
    """
    
    def __init__(
        self,
        config: ProbeRetryConfig | None = None,
        on_disconnect: Callable | None = None,
        on_retry: Callable | None = None,
    ):
        self._config = config or ProbeRetryConfig()
        self._on_disconnect = on_disconnect
        self._on_retry = on_retry
    
    def wrap(self, probe: Any) -> ProbeRetryWrapper:
        """Wrap a probe with retry logic."""
        return ProbeRetryWrapper(
            probe=probe,
            config=self._config,
            on_disconnect=self._on_disconnect,
            on_retry=self._on_retry,
        )


# Global factory
_probe_factory: RetriableProbeFactory | None = None


def get_probe_factory() -> RetriableProbeFactory:
    """Get global probe factory."""
    global _probe_factory
    if _probe_factory is None:
        _probe_factory = RetriableProbeFactory()
    return _probe_factory


if __name__ == "__main__":
    print("Probe Retry Wrapper")
    print("=" * 40)
    print("Usage:")
    print("  wrapper = ProbeRetryWrapper(probe, config)")
    print("  await wrapper.write_memory(addr, data)")
    print("  await wrapper.read_memory(addr, size)")
    print()
    print("Configuration options:")
    print("  - max_retries: Number of retry attempts")
    print("  - initial_delay_ms: Initial retry delay")
    print("  - backoff_multiplier: Exponential backoff factor")
    print("  - default_timeout_ms: Operation timeout")

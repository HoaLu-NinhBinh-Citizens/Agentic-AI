"""Testing Doubles for Phase 6.2 Flash Infrastructure.

This module provides mock implementations for testing flash operations
without actual hardware. These mocks simulate:

- MockProbe: Memory read/write, flash operations
- MockFlashDriver: Erase, write, verify with configurable failure modes
- MockRemoteStorage: S3, HTTP stream simulation
- MockSnapshotter: Capture/restore snapshots
- MockLockManager: Distributed lock simulation

Usage:
    from tests.fixtures.mock_hardware import MockProbe, MockFlashDriver
    
    probe = MockProbe(memory_size=1024*1024)
    await probe.write_memory(0x08000000, firmware_data)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import struct
import time
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock


# =============================================================================
# MockProbe - Simulates JTAG/SWD probe for memory operations
# =============================================================================

@dataclass
class MockProbe:
    """Mock JTAG/SWD probe for testing.
    
    Simulates:
    - Memory read/write
    - Flash operations
    - Reset/halt control
    - Breakpoint management
    
    Features:
    - Configurable memory size
    - Injectable errors
    - Disconnect simulation
    - Timing simulation
    """
    
    memory_size: int = 1024 * 1024  # 1MB default
    base_address: int = 0x08000000  # STM32 flash base
    
    _memory: bytearray = field(default_factory=lambda: bytearray(1024 * 1024))
    _halted: bool = False
    _reset_pending: bool = False
    
    # Error injection
    _inject_read_error: bool = False
    _inject_write_error: bool = False
    _inject_erase_error: bool = False
    _error_count: int = 0
    _disconnected: bool = False
    
    # Timing simulation
    _read_latency_ms: float = 0.1
    _write_latency_ms: float = 0.5
    _erase_latency_ms: float = 10.0
    
    async def read_memory(self, address: int, size: int) -> bytes:
        """Read memory from target."""
        if self._disconnected:
            raise ConnectionError("Probe disconnected")
        
        if self._inject_read_error:
            self._error_count += 1
            raise IOError(f"Read error at {hex(address)}")
        
        # Simulate latency
        await asyncio.sleep(self._read_latency_ms / 1000)
        
        # Bounds check
        offset = address - self.base_address
        if offset < 0 or offset + size > self.memory_size:
            raise ValueError(f"Read out of bounds: {hex(address)}")
        
        return bytes(self._memory[offset : offset + size])
    
    async def write_memory(self, address: int, data: bytes) -> None:
        """Write memory to target."""
        if self._disconnected:
            raise ConnectionError("Probe disconnected")
        
        if self._inject_write_error:
            self._error_count += 1
            raise IOError(f"Write error at {hex(address)}")
        
        # Simulate latency
        await asyncio.sleep(self._write_latency_ms / 1000)
        
        # Bounds check
        offset = address - self.base_address
        if offset < 0 or offset + len(data) > self.memory_size:
            raise ValueError(f"Write out of bounds: {hex(address)}")
        
        self._memory[offset : offset + len(data)] = data
    
    async def erase_sector(self, address: int) -> None:
        """Erase a flash sector."""
        if self._disconnected:
            raise ConnectionError("Probe disconnected")
        
        if self._inject_erase_error:
            self._error_count += 1
            raise IOError(f"Erase error at {hex(address)}")
        
        # Simulate erase latency
        await asyncio.sleep(self._erase_latency_ms / 1000)
        
        # Erase: set to 0xFF
        sector_size = 2048  # Default STM32 sector size
        offset = address - self.base_address
        if offset >= 0 and offset + sector_size <= self.memory_size:
            for i in range(sector_size):
                self._memory[offset + i] = 0xFF
    
    async def erase_full(self, address: int, size: int) -> None:
        """Erase entire flash region."""
        if self._disconnected:
            raise ConnectionError("Probe disconnected")
        
        await asyncio.sleep(self._erase_latency_ms * (size / 2048) / 1000)
        
        offset = address - self.base_address
        if offset >= 0 and offset + size <= self.memory_size:
            for i in range(size):
                self._memory[offset + i] = 0xFF
    
    async def reset(self) -> None:
        """Reset target."""
        if self._disconnected:
            raise ConnectionError("Probe disconnected")
        
        self._reset_pending = True
        await asyncio.sleep(0.1)
        self._reset_pending = False
        self._halted = False
    
    async def halt(self) -> None:
        """Halt target."""
        self._halted = True
    
    async def resume(self) -> None:
        """Resume target execution."""
        self._halted = False
    
    def is_halted(self) -> bool:
        """Check if target is halted."""
        return self._halted
    
    def disconnect(self) -> None:
        """Simulate probe disconnect."""
        self._disconnected = True
    
    def reconnect(self) -> None:
        """Simulate probe reconnect."""
        self._disconnected = False
    
    # Error injection controls
    def inject_read_error(self) -> None:
        """Inject read errors on next read."""
        self._inject_read_error = True
    
    def inject_write_error(self) -> None:
        """Inject write errors on next write."""
        self._inject_write_error = True
    
    def inject_erase_error(self) -> None:
        """Inject erase errors on next erase."""
        self._inject_erase_error = True
    
    def clear_errors(self) -> None:
        """Clear all injected errors."""
        self._inject_read_error = False
        self._inject_write_error = False
        self._inject_erase_error = False
    
    def get_memory_hash(self, address: int, size: int) -> str:
        """Get hash of memory region."""
        offset = address - self.base_address
        return hashlib.sha256(self._memory[offset : offset + size]).hexdigest()


# =============================================================================
# MockFlashDriver - Simulates flash controller with failure modes
# =============================================================================

@dataclass
class MockFlashDriver:
    """Mock flash controller driver.
    
    Simulates:
    - Sector erase
    - Page write
    - Verify
    - Configurable failure modes
    """
    
    sector_size: int = 2048
    page_size: int = 2048
    flash_base: int = 0x08000000
    
    _probe: MockProbe | None = None
    _operation_count: int = 0
    _fail_after_operations: int = 0  # 0 = disabled
    _failure_mode: str = ""  # "write", "verify", "erase"
    
    def __post_init__(self) -> None:
        """Initialize with default probe."""
        if self._probe is None:
            self._probe = MockProbe()
    
    async def write_page(self, address: int, data: bytes) -> bool:
        """Write a page to flash."""
        self._operation_count += 1
        
        if self._fail_after_operations > 0:
            if self._operation_count >= self._fail_after_operations:
                if self._failure_mode in ("write", "all"):
                    raise IOError("Simulated write failure")
        
        await self._probe.write_memory(address, data)
        return True
    
    async def erase_sector(self, address: int) -> bool:
        """Erase a sector."""
        self._operation_count += 1
        
        if self._fail_after_operations > 0:
            if self._operation_count >= self._fail_after_operations:
                if self._failure_mode in ("erase", "all"):
                    raise IOError("Simulated erase failure")
        
        await self._probe.erase_sector(address)
        return True
    
    async def verify(self, address: int, data: bytes) -> bool:
        """Verify written data."""
        self._operation_count += 1
        
        if self._fail_after_operations > 0:
            if self._operation_count >= self._fail_after_operations:
                if self._failure_mode in ("verify", "all"):
                    return False
        
        read_data = await self._probe.read_memory(address, len(data))
        return read_data == data
    
    async def write_with_verify(self, address: int, data: bytes) -> bool:
        """Write data and verify."""
        await self.write_page(address, data)
        return await self.verify(address, data)
    
    def set_failure_mode(self, mode: str, after_operations: int = 1) -> None:
        """Set failure mode for testing.
        
        Args:
            mode: "write", "verify", "erase", or "all"
            after_operations: Number of operations before failure
        """
        self._failure_mode = mode
        self._fail_after_operations = after_operations
    
    def reset_failure_mode(self) -> None:
        """Reset failure mode."""
        self._failure_mode = ""
        self._fail_after_operations = 0
        self._operation_count = 0
    
    def get_operation_count(self) -> int:
        """Get number of operations performed."""
        return self._operation_count


# =============================================================================
# MockRemoteStorage - Simulates S3/HTTP storage
# =============================================================================

@dataclass
class MockRemoteStorage:
    """Mock remote storage for streaming tests.
    
    Simulates:
    - S3-compatible storage
    - HTTP/HTTPS streaming
    - Chunked transfer
    - Connection failures
    """
    
    _data: dict[str, bytes] = field(default_factory=dict)
    _url_responses: dict[str, tuple[bytes, int]] = field(default_factory=dict)  # url -> (data, status)
    
    _chunk_size: int = 4096
    _delay_ms: int = 10
    _inject_error: bool = False
    _error_message: str = "Simulated network error"
    
    async def put_object(self, key: str, data: bytes) -> None:
        """Store object."""
        self._data[key] = data
    
    async def get_object(self, key: str) -> bytes | None:
        """Retrieve object."""
        if self._inject_error:
            raise ConnectionError(self._error_message)
        return self._data.get(key)
    
    async def stream_object(
        self,
        key: str,
        start: int = 0,
        chunk_callback: Any = None,
    ) -> AsyncIterator[bytes]:
        """Stream object in chunks."""
        if self._inject_error:
            raise ConnectionError(self._error_message)
        
        data = self._data.get(key)
        if data is None:
            return
        
        for i in range(start, len(data), self._chunk_size):
            chunk = data[i : i + self._chunk_size]
            await asyncio.sleep(self._delay_ms / 1000)
            yield chunk
    
    def register_url(self, url: str, data: bytes, status: int = 200) -> None:
        """Register URL for HTTP mock."""
        self._url_responses[url] = (data, status)
    
    async def fetch_url(self, url: str) -> tuple[bytes, int]:
        """Fetch URL (mock implementation)."""
        if self._inject_error:
            raise ConnectionError(self._error_message)
        
        if url in self._url_responses:
            return self._url_responses[url]
        
        raise ValueError(f"URL not registered: {url}")
    
    def inject_error(self, message: str = "Simulated error") -> None:
        """Inject error on next operation."""
        self._inject_error = True
        self._error_message = message
    
    def clear_error(self) -> None:
        """Clear injected error."""
        self._inject_error = False


# =============================================================================
# MockSnapshotter - Simulates Phase 6.1 snapshot system
# =============================================================================

@dataclass
class MockSnapshotter:
    """Mock snapshot manager for recovery testing.
    
    Simulates:
    - Register capture
    - Memory capture
    - State restoration
    - Snapshot storage
    """
    
    _snapshots: dict[str, dict[str, Any]] = field(default_factory=dict)
    _capture_delay_ms: int = 50
    _restore_delay_ms: int = 50
    
    _inject_capture_error: bool = False
    _inject_restore_error: bool = False
    
    async def capture(
        self,
        target_name: str,
        name: str,
        registers: dict[str, int] | None = None,
        memory_regions: list[tuple[int, int]] | None = None,
    ) -> str:
        """Capture snapshot."""
        if self._inject_capture_error:
            raise IOError("Simulated capture error")
        
        await asyncio.sleep(self._capture_delay_ms / 1000)
        
        snapshot_id = f"snap_{name}_{int(time.time() * 1000)}"
        
        self._snapshots[snapshot_id] = {
            "target_name": target_name,
            "name": name,
            "registers": registers or {},
            "memory_regions": memory_regions or [],
            "captured_at": time.time(),
        }
        
        return snapshot_id
    
    async def restore(
        self,
        snapshot_id: str,
        target_name: str | None = None,
    ) -> bool:
        """Restore from snapshot."""
        if self._inject_restore_error:
            raise IOError("Simulated restore error")
        
        if snapshot_id not in self._snapshots:
            raise ValueError(f"Snapshot not found: {snapshot_id}")
        
        await asyncio.sleep(self._restore_delay_ms / 1000)
        return True
    
    def get_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        """Get snapshot data."""
        return self._snapshots.get(snapshot_id)
    
    def list_snapshots(self, target_name: str | None = None) -> list[str]:
        """List snapshot IDs."""
        if target_name:
            return [
                sid for sid, snap in self._snapshots.items()
                if snap["target_name"] == target_name
            ]
        return list(self._snapshots.keys())
    
    def inject_capture_error(self) -> None:
        """Inject capture error."""
        self._inject_capture_error = True
    
    def inject_restore_error(self) -> None:
        """Inject restore error."""
        self._inject_restore_error = True
    
    def clear_errors(self) -> None:
        """Clear injected errors."""
        self._inject_capture_error = False
        self._inject_restore_error = False


# =============================================================================
# MockLockManager - Simulates distributed locking
# =============================================================================

@dataclass
class MockLockManager:
    """Mock distributed lock manager.
    
    Simulates:
    - Lock acquisition
    - Lease expiration
    - Concurrent access
    - Lock release
    """
    
    _locks: dict[str, dict[str, Any]] = field(default_factory=dict)
    _lock_timeout_seconds: float = 60.0
    _acquire_delay_ms: int = 10
    
    _inject_timeout: bool = False
    _inject_acquire_error: bool = False
    
    async def acquire(
        self,
        target_name: str,
        owner_id: str,
        timeout_seconds: float = 30.0,
    ) -> dict[str, Any] | None:
        """Acquire lock."""
        if self._inject_acquire_error:
            raise ConnectionError("Simulated acquire error")
        
        await asyncio.sleep(self._acquire_delay_ms / 1000)
        
        # Check existing lock
        if target_name in self._locks:
            lock = self._locks[target_name]
            
            # Check if expired
            if time.time() > lock["expires_at"]:
                # Expired, can acquire
                pass
            elif lock["owner_id"] == owner_id:
                # Same owner, renew
                lock["expires_at"] = time.time() + self._lock_timeout_seconds
                lock["version"] += 1
                return lock
            else:
                # Different owner, wait
                if timeout_seconds <= 0:
                    return None
                
                # Simulate wait
                await asyncio.sleep(0.1)
                return None
        
        # Create new lock
        lock = {
            "target_name": target_name,
            "owner_id": owner_id,
            "acquired_at": time.time(),
            "expires_at": time.time() + self._lock_timeout_seconds,
            "version": 1,
        }
        self._locks[target_name] = lock
        return lock
    
    async def release(
        self,
        target_name: str,
        owner_id: str,
    ) -> bool:
        """Release lock."""
        if target_name not in self._locks:
            return True
        
        lock = self._locks[target_name]
        if lock["owner_id"] != owner_id:
            return False
        
        del self._locks[target_name]
        return True
    
    async def extend(
        self,
        target_name: str,
        owner_id: str,
        additional_seconds: float = 60.0,
    ) -> bool:
        """Extend lock lease."""
        if target_name not in self._locks:
            return False
        
        lock = self._locks[target_name]
        if lock["owner_id"] != owner_id:
            return False
        
        lock["expires_at"] = time.time() + additional_seconds
        return True
    
    def is_locked(self, target_name: str) -> bool:
        """Check if target is locked."""
        if target_name not in self._locks:
            return False
        
        lock = self._locks[target_name]
        return time.time() <= lock["expires_at"]
    
    def get_lock_owner(self, target_name: str) -> str | None:
        """Get lock owner."""
        if target_name not in self._locks:
            return None
        return self._locks[target_name]["owner_id"]
    
    def inject_acquire_error(self) -> None:
        """Inject acquire error."""
        self._inject_acquire_error = True
    
    def clear_errors(self) -> None:
        """Clear injected errors."""
        self._inject_acquire_error = False


# =============================================================================
# Helper: Async iterator for streaming
# =============================================================================

class AsyncIterator:
    """Helper class to create async iterators."""
    
    def __init__(self, data: bytes, chunk_size: int = 4096, delay_ms: int = 10) -> None:
        self.data = data
        self.chunk_size = chunk_size
        self.delay_ms = delay_ms
        self.offset = 0
    
    def __aiter__(self):
        return self
    
    async def __anext__(self):
        if self.offset >= len(self.data):
            raise StopAsyncIteration
        
        chunk = self.data[self.offset : self.offset + self.chunk_size]
        self.offset += len(chunk)
        
        if self.delay_ms > 0:
            await asyncio.sleep(self.delay_ms / 1000)
        
        return chunk


# Export all mocks
__all__ = [
    "MockProbe",
    "MockFlashDriver",
    "MockRemoteStorage",
    "MockSnapshotter",
    "MockLockManager",
    "AsyncIterator",
]

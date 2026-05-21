"""Pytest fixtures for chaos tests.

Provides mock hardware fixtures and shared utilities for testing.
"""

from __future__ import annotations

import pytest
import asyncio
import time
import hashlib


# =============================================================================
# Mock Hardware Fixtures
# =============================================================================

@pytest.fixture
def mock_probe():
    """Create a mock probe for testing."""
    class MockProbe:
        def __init__(self, memory_size=1024*1024, base_address=0x08000000):
            self.memory_size = memory_size
            self.base_address = base_address
            self._memory = bytearray(memory_size)
            self._halted = False
            self._disconnected = False
        
        async def read_memory(self, address, size):
            if self._disconnected:
                raise ConnectionError("Probe disconnected")
            offset = address - self.base_address
            if offset < 0 or offset + size > self.memory_size:
                raise ValueError(f"Read out of bounds: {hex(address)}")
            return bytes(self._memory[offset : offset + size])
        
        async def write_memory(self, address, data):
            if self._disconnected:
                raise ConnectionError("Probe disconnected")
            offset = address - self.base_address
            if offset < 0 or offset + len(data) > self.memory_size:
                raise ValueError(f"Write out of bounds: {hex(address)}")
            self._memory[offset : offset + len(data)] = data
        
        async def erase_sector(self, address):
            if self._disconnected:
                raise ConnectionError("Probe disconnected")
            sector_size = 2048
            offset = address - self.base_address
            if offset >= 0 and offset + sector_size <= self.memory_size:
                for i in range(sector_size):
                    self._memory[offset + i] = 0xFF
        
        async def reset(self):
            if self._disconnected:
                raise ConnectionError("Probe disconnected")
            self._halted = False
        
        async def halt(self):
            self._halted = True
        
        async def resume(self):
            self._halted = False
        
        def is_halted(self):
            return self._halted
        
        def disconnect(self):
            self._disconnected = True
        
        def reconnect(self):
            self._disconnected = False
        
        def get_memory_hash(self, address, size):
            offset = address - self.base_address
            return hashlib.sha256(self._memory[offset : offset + size]).hexdigest()
    
    return MockProbe()


@pytest.fixture
def mock_flash_driver(mock_probe):
    """Create a mock flash driver for testing."""
    class MockFlashDriver:
        def __init__(self, probe):
            self.probe = probe
            self.sector_size = 2048
            self._operation_count = 0
            self._fail_after = 0
            self._failure_mode = None
        
        async def write_page(self, address, data):
            self._operation_count += 1
            if self._fail_after > 0 and self._operation_count >= self._fail_after:
                if self._failure_mode in ("write", "all", None):
                    raise IOError("Simulated write failure")
            await self.probe.write_memory(address, data)
            return True
        
        async def erase_sector(self, address):
            self._operation_count += 1
            if self._fail_after > 0 and self._operation_count >= self._fail_after:
                if self._failure_mode in ("erase", "all", None):
                    raise IOError("Simulated erase failure")
            await self.probe.erase_sector(address)
            return True
        
        async def verify(self, address, data):
            self._operation_count += 1
            if self._fail_after > 0 and self._operation_count >= self._fail_after:
                if self._failure_mode in ("verify", "all", None):
                    return False
            read_data = await self.probe.read_memory(address, len(data))
            return read_data == data
        
        async def write_with_verify(self, address, data):
            await self.write_page(address, data)
            return await self.verify(address, data)
        
        def set_failure_mode(self, mode="write", after_operations=1):
            self._failure_mode = mode
            self._fail_after = after_operations
        
        def reset_failure_mode(self):
            self._failure_mode = None
            self._fail_after = 0
            self._operation_count = 0
        
        def get_operation_count(self):
            return self._operation_count
    
    return MockFlashDriver(mock_probe)


@pytest.fixture
def mock_lock_manager():
    """Create a mock lock manager for testing."""
    class MockLockManager:
        def __init__(self):
            self._locks = {}
            self._lock_timeout = 60.0
        
        async def acquire(self, target_name, owner_id, timeout_seconds=30.0):
            await asyncio.sleep(0.01)
            
            if target_name in self._locks:
                lock = self._locks[target_name]
                if time.time() > lock["expires_at"]:
                    pass
                elif lock["owner_id"] == owner_id:
                    lock["expires_at"] = time.time() + self._lock_timeout
                    lock["version"] += 1
                    return lock
                else:
                    if timeout_seconds <= 0:
                        return None
                    await asyncio.sleep(0.1)
                    return None
            
            lock = {
                "target_name": target_name,
                "owner_id": owner_id,
                "acquired_at": time.time(),
                "expires_at": time.time() + self._lock_timeout,
                "version": 1,
            }
            self._locks[target_name] = lock
            return lock
        
        async def release(self, target_name, owner_id):
            if target_name not in self._locks:
                return True
            lock = self._locks[target_name]
            if lock["owner_id"] != owner_id:
                return False
            del self._locks[target_name]
            return True
        
        async def extend(self, target_name, owner_id, additional_seconds=60.0):
            if target_name not in self._locks:
                return False
            lock = self._locks[target_name]
            if lock["owner_id"] != owner_id:
                return False
            lock["expires_at"] = time.time() + additional_seconds
            return True
        
        def is_locked(self, target_name):
            if target_name not in self._locks:
                return False
            lock = self._locks[target_name]
            return time.time() <= lock["expires_at"]
        
        def get_lock_owner(self, target_name):
            if target_name not in self._locks:
                return None
            return self._locks[target_name]["owner_id"]
    
    return MockLockManager()


@pytest.fixture
def mock_snapshotter():
    """Create a mock snapshot manager for testing."""
    class MockSnapshotter:
        def __init__(self):
            self._snapshots = {}
        
        async def capture(self, target_name, name, registers=None, memory_regions=None):
            await asyncio.sleep(0.05)
            snapshot_id = f"snap_{name}_{int(time.time() * 1000)}"
            self._snapshots[snapshot_id] = {
                "target_name": target_name,
                "name": name,
                "registers": registers or {},
                "memory_regions": memory_regions or [],
                "captured_at": time.time(),
            }
            return snapshot_id
        
        async def restore(self, snapshot_id, target_name=None):
            await asyncio.sleep(0.05)
            if snapshot_id not in self._snapshots:
                raise ValueError(f"Snapshot not found: {snapshot_id}")
            return True
        
        def get_snapshot(self, snapshot_id):
            return self._snapshots.get(snapshot_id)
    
    return MockSnapshotter()


@pytest.fixture
def mock_remote_storage():
    """Create a mock remote storage for testing."""
    class MockRemoteStorage:
        def __init__(self):
            self._data = {}
            self._inject_error = False
        
        async def put_object(self, key, data):
            self._data[key] = data
        
        async def get_object(self, key):
            if self._inject_error:
                raise ConnectionError("Simulated error")
            return self._data.get(key)
        
        def inject_error(self):
            self._inject_error = True
        
        def clear_error(self):
            self._inject_error = False
    
    return MockRemoteStorage()

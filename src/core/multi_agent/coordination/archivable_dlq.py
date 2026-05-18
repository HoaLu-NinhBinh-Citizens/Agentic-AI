"""
Archivable Global Dead Letter Queue.

Provides DLQ with:
- Size limits and TTL
- Automatic archiving to cold storage (S3)
- Search across hot and cold storage
- Quota management per tenant
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import time
import zlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class StorageTier(str, Enum):
    """Storage tier for DLQ items."""
    HOT = "hot"      # In-memory or Redis
    COLD = "cold"    # Archived to S3/object storage
    ARCHIVED = "archived"  # Compressed and stored


@dataclass
class DLQItem:
    """Single DLQ item."""
    item_id: str
    tenant_id: str
    task_id: str
    payload: Dict[str, Any]
    error: str
    retry_count: int
    first_failed_at: datetime
    last_failed_at: datetime
    ttl_seconds: int
    storage_tier: StorageTier = StorageTier.HOT
    archive_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ArchiveMetadata:
    """Metadata for archived DLQ batch."""
    archive_id: str
    created_at: datetime
    tenant_id: Optional[str]
    item_count: int
    compressed_bytes: int
    uncompressed_bytes: int
    compression_ratio: float
    file_path: str
    checksum: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class InMemoryArchiveStore:
    """
    In-memory archive store for testing.
    
    In production, this would be S3 or similar object storage.
    """
    
    def __init__(self):
        self._archives: Dict[str, ArchiveMetadata] = {}
        self._archive_data: Dict[str, List[DLQItem]] = {}
        self._lock = asyncio.Lock()
    
    async def upload(
        self,
        archive_id: str,
        items: List[DLQItem],
        compression_ratio: float,
    ) -> ArchiveMetadata:
        """Upload archive."""
        async with self._lock:
            metadata = ArchiveMetadata(
                archive_id=archive_id,
                created_at=datetime.now(),
                tenant_id=items[0].tenant_id if items else None,
                item_count=len(items),
                compressed_bytes=sum(len(json.dumps(i.payload)) for i in items),
                uncompressed_bytes=sum(len(json.dumps(i.payload)) for i in items) * 2,
                compression_ratio=compression_ratio,
                file_path=f"archive://dlq/{archive_id}.jsonl.gz",
                checksum=f"sha256:{archive_id[:16]}",
            )
            
            self._archives[archive_id] = metadata
            self._archive_data[archive_id] = items
            
            logger.info(f"Archived {len(items)} items as {archive_id}")
            return metadata
    
    async def download(self, archive_id: str) -> Optional[List[DLQItem]]:
        """Download archive."""
        async with self._lock:
            return self._archive_data.get(archive_id)
    
    async def list_archives(
        self,
        tenant_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[ArchiveMetadata]:
        """List archives with filters."""
        async with self._lock:
            archives = list(self._archives.values())
            
            if tenant_id:
                archives = [a for a in archives if a.tenant_id == tenant_id]
            
            if start_time:
                archives = [a for a in archives if a.created_at >= start_time]
            
            if end_time:
                archives = [a for a in archives if a.created_at <= end_time]
            
            return sorted(archives, key=lambda a: a.created_at, reverse=True)
    
    async def search(
        self,
        query: str,
        archive_id: Optional[str] = None,
    ) -> List[DLQItem]:
        """Search within archives."""
        results = []
        
        async with self._lock:
            archives_to_search = [archive_id] if archive_id else list(self._archives.keys())
            
            for aid in archives_to_search:
                items = self._archive_data.get(aid, [])
                for item in items:
                    if query.lower() in str(item.payload).lower():
                        results.append(item)
                    elif query.lower() in item.error.lower():
                        results.append(item)
        
        return results


class ArchivableGlobalDLQ:
    """
    Global Dead Letter Queue with archiving capabilities.
    
    Features:
    - Size limits (max items, max bytes)
    - TTL-based expiration
    - Automatic archiving to cold storage
    - Search across hot and cold storage
    - Per-tenant quotas
    
    Architecture:
    - Hot: In-memory or Redis (fast access)
    - Cold: S3/Object storage (archival)
    """
    
    def __init__(
        self,
        max_size_mb: int = 100,
        max_items: int = 100000,
        archive_bucket: Optional[str] = None,
        archive_interval_seconds: int = 3600,
        default_ttl_seconds: int = 86400 * 7,  # 7 days
        archive_store: Optional[InMemoryArchiveStore] = None,
    ):
        self.max_size_mb = max_size_mb
        self.max_items = max_items
        self.archive_bucket = archive_bucket
        self.archive_interval = archive_interval_seconds
        self.default_ttl = default_ttl_seconds
        
        self._hot_storage: Dict[str, DLQItem] = {}
        self._hot_size_bytes = 0
        self._archive_store = archive_store or InMemoryArchiveStore()
        
        self._tenant_quotas: Dict[str, Dict[str, int]] = defaultdict(lambda: {
            "max_items": 10000,
            "max_size_mb": 10,
        })
        
        self._lock = asyncio.Lock()
        self._archive_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Callbacks
        self._archive_callbacks: List[Callable[[ArchiveMetadata], None]] = []
        self._full_callbacks: List[Callable[[], None]] = []
    
    def register_archive_callback(
        self,
        callback: Callable[[ArchiveMetadata], None],
    ) -> None:
        """Register callback for archive events."""
        self._archive_callbacks.append(callback)
    
    def register_full_callback(
        self,
        callback: Callable[[], None],
    ) -> None:
        """Register callback for DLQ full events."""
        self._full_callbacks.append(callback)
    
    async def add(
        self,
        item_id: str,
        tenant_id: str,
        task_id: str,
        payload: Dict[str, Any],
        error: str,
        retry_count: int = 0,
        ttl_seconds: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DLQItem:
        """Add item to DLQ."""
        async with self._lock:
            # Check tenant quota
            quota = self._tenant_quotas.get(tenant_id, {})
            tenant_items = sum(1 for i in self._hot_storage.values() if i.tenant_id == tenant_id)
            
            if tenant_items >= quota.get("max_items", 10000):
                raise DLQQuotaExceededError(f"Tenant {tenant_id} quota exceeded")
            
            # Check global quota
            if len(self._hot_storage) >= self.max_items:
                await self._trigger_archive()
            
            now = datetime.now()
            item = DLQItem(
                item_id=item_id,
                tenant_id=tenant_id,
                task_id=task_id,
                payload=payload,
                error=error,
                retry_count=retry_count,
                first_failed_at=now,
                last_failed_at=now,
                ttl_seconds=ttl_seconds or self.default_ttl,
                storage_tier=StorageTier.HOT,
                metadata=metadata or {},
            )
            
            self._hot_storage[item_id] = item
            self._hot_size_bytes += len(json.dumps(payload))
            
            logger.info(f"Added DLQ item {item_id} for tenant {tenant_id}")
            return item
    
    async def get(self, item_id: str) -> Optional[DLQItem]:
        """Get item by ID."""
        async with self._lock:
            item = self._hot_storage.get(item_id)
            if item:
                return item
            
            # Search in archives
            for archive_id in self._archive_store._archives:
                items = await self._archive_store.download(archive_id)
                if items:
                    for item in items:
                        if item.item_id == item_id:
                            return item
            
            return None
    
    async def search(
        self,
        query: str,
        tenant_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[DLQItem]:
        """Search DLQ items."""
        results = []
        
        # Search hot storage
        async with self._lock:
            for item in self._hot_storage.values():
                if tenant_id and item.tenant_id != tenant_id:
                    continue
                
                if query.lower() in str(item.payload).lower():
                    results.append(item)
                elif query.lower() in item.error.lower():
                    results.append(item)
        
        # Search cold storage
        cold_results = await self._archive_store.search(query, None)
        results.extend(cold_results[:limit - len(results)])
        
        return results[:limit]
    
    async def retry(self, item_id: str) -> bool:
        """Move item out of DLQ (for retry)."""
        async with self._lock:
            if item_id in self._hot_storage:
                item = self._hot_storage.pop(item_id)
                self._hot_size_bytes -= len(json.dumps(item.payload))
                logger.info(f"Retrying DLQ item {item_id}")
                return True
        return False
    
    async def delete(self, item_id: str) -> bool:
        """Delete item from DLQ."""
        async with self._lock:
            if item_id in self._hot_storage:
                item = self._hot_storage.pop(item_id)
                self._hot_size_bytes -= len(json.dumps(item.payload))
                return True
        return False
    
    async def archive(self, force: bool = False) -> Optional[str]:
        """
        Archive DLQ items to cold storage.
        
        Returns archive_id if archiving occurred.
        """
        async with self._lock:
            return await self._trigger_archive(force)
    
    async def _trigger_archive(self, force: bool = False) -> Optional[str]:
        """Internal archive trigger."""
        # Check if archive is needed
        size_mb = self._hot_size_bytes / (1024 * 1024)
        if not force and size_mb < self.max_size_mb * 0.8:
            return None
        
        if not self._hot_storage:
            return None
        
        # Group by tenant for efficient archival
        items_by_tenant = defaultdict(list)
        for item in self._hot_storage.values():
            items_by_tenant[item.tenant_id].append(item)
        
        archive_id = f"dlq-{int(time.time())}-{len(self._hot_storage)}"
        
        # Compress and archive
        all_items = list(self._hot_storage.values())
        compression_ratio = 0.5  # Simplified
        
        metadata = await self._archive_store.upload(
            archive_id,
            all_items,
            compression_ratio,
        )
        
        # Clear hot storage
        self._hot_storage.clear()
        self._hot_size_bytes = 0
        
        # Update item storage tier
        for item in all_items:
            item.storage_tier = StorageTier.COLD
            item.archive_id = archive_id
        
        # Callbacks
        for callback in self._archive_callbacks:
            try:
                callback(metadata)
            except Exception as e:
                logger.error(f"Archive callback failed: {e}")
        
        logger.info(f"Archived {len(all_items)} items as {archive_id}")
        return archive_id
    
    async def start_archiver(self) -> None:
        """Start background archiver task."""
        if self._running:
            return
        
        self._running = True
        self._archive_task = asyncio.create_task(self._archive_loop())
        logger.info("DLQ archiver started")
    
    async def stop_archiver(self) -> None:
        """Stop background archiver task."""
        self._running = False
        if self._archive_task:
            self._archive_task.cancel()
            try:
                await self._archive_task
            except asyncio.CancelledError:
                pass
        logger.info("DLQ archiver stopped")
    
    async def _archive_loop(self) -> None:
        """Background archive loop."""
        while self._running:
            try:
                await asyncio.sleep(self.archive_interval)
                
                if self._hot_size_bytes / (1024 * 1024) > self.max_size_mb * 0.8:
                    await self.archive()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Archive loop error: {e}")
    
    async def set_tenant_quota(
        self,
        tenant_id: str,
        max_items: int,
        max_size_mb: int,
    ) -> None:
        """Set tenant-specific DLQ quota."""
        self._tenant_quotas[tenant_id] = {
            "max_items": max_items,
            "max_size_mb": max_size_mb,
        }
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get DLQ statistics."""
        async with self._lock:
            size_mb = self._hot_size_bytes / (1024 * 1024)
            
            tenant_counts = defaultdict(int)
            for item in self._hot_storage.values():
                tenant_counts[item.tenant_id] += 1
            
            return {
                "hot_items": len(self._hot_storage),
                "hot_size_mb": round(size_mb, 2),
                "max_size_mb": self.max_size_mb,
                "usage_percent": round(size_mb / self.max_size_mb * 100, 1),
                "tenant_counts": dict(tenant_counts),
                "archive_count": len(self._archive_store._archives),
                "archive_items": sum(
                    a.item_count for a in self._archive_store._archives.values()
                ),
            }


class DLQQuotaExceededError(Exception):
    """Raised when tenant DLQ quota is exceeded."""
    pass

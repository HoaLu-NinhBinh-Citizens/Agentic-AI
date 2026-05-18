"""
Batch Idempotency Store for Multi-Agent Coordination.

Ensures batch operations are idempotent by tracking per-item results.
Each item in a batch has its own idempotency key for safe retries.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional

from src.core.multi_agent.coordination.types import (
    BatchItem,
    BatchResult,
)

logger = logging.getLogger(__name__)


class BatchIdempotencyStore:
    """
    Batch idempotency store for multi-agent coordination.
    
    Ensures batch operations are idempotent by:
    - Generating idempotency keys per item
    - Caching results with TTL
    - Skipping already-processed items
    
    Each item in a batch has its own idempotency key, enabling:
    - Partial batch retries
    - Concurrent processing
    - Safe recovery from failures
    """
    
    def __init__(
        self,
        ttl_seconds: int = 86400,  # 24 hours
        cleanup_interval_seconds: int = 3600,
    ):
        self.ttl_seconds = ttl_seconds
        self.cleanup_interval_seconds = cleanup_interval_seconds
        
        self._store: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self._expiry: Dict[str, datetime] = {}
        self._lock = asyncio.Lock()
        
        self._hit_count = 0
        self._miss_count = 0
        self._total_items = 0
        
        # Start cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start(self) -> None:
        """Start background cleanup task."""
        if self._running:
            return
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("BatchIdempotencyStore started")
    
    async def stop(self) -> None:
        """Stop background cleanup task."""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("BatchIdempotencyStore stopped")
    
    async def _cleanup_loop(self) -> None:
        """Background task to clean up expired entries."""
        while self._running:
            try:
                await asyncio.sleep(self.cleanup_interval_seconds)
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
    
    async def _cleanup_expired(self) -> int:
        """Remove expired entries."""
        async with self._lock:
            now = datetime.now()
            cutoff = now - timedelta(seconds=self.ttl_seconds)
            
            expired_keys = [
                key for key, expiry in self._expiry.items()
                if expiry < cutoff
            ]
            
            for key in expired_keys:
                # Extract batch_id from key (batch_id:item_index)
                batch_id = key.rsplit(":", 1)[0] if ":" in key else key
                item_idx = key.rsplit(":", 1)[1] if ":" in key else "0"
                
                if batch_id in self._store and item_idx in self._store[batch_id]:
                    del self._store[batch_id][item_idx]
                if key in self._expiry:
                    del self._expiry[key]
            
            # Clean up empty batch groups
            empty_batches = [bid for bid, items in self._store.items() if not items]
            for bid in empty_batches:
                del self._store[bid]
            
            if expired_keys:
                logger.info(f"Cleaned up {len(expired_keys)} expired idempotency entries")
            
            return len(expired_keys)
    
    def _make_key(self, batch_id: str, item_index: int) -> str:
        """Create idempotency key for a batch item."""
        return f"{batch_id}:{item_index}"
    
    def _generate_idempotency_key(
        self,
        batch_id: str,
        item_index: int,
        custom_key: Optional[str] = None,
    ) -> str:
        """Generate or use provided idempotency key."""
        if custom_key:
            return custom_key
        return self._make_key(batch_id, item_index)
    
    async def get_result(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        """
        Get cached result for an idempotency key.
        
        Args:
            idempotency_key: Unique key for the item
            
        Returns:
            Cached result if exists and not expired, None otherwise
        """
        async with self._lock:
            # Parse batch_id and item_index
            if ":" in idempotency_key:
                parts = idempotency_key.rsplit(":", 1)
                batch_id, item_idx = parts[0], parts[1]
            else:
                batch_id, item_idx = idempotency_key, "0"
            
            # Check expiry
            if idempotency_key in self._expiry:
                if datetime.now() > self._expiry[idempotency_key]:
                    # Expired, remove
                    if batch_id in self._store and item_idx in self._store[batch_id]:
                        del self._store[batch_id][item_idx]
                    del self._expiry[idempotency_key]
                    return None
            
            # Get result
            result = self._store.get(batch_id, {}).get(item_idx)
            if result:
                self._hit_count += 1
                logger.debug(f"Idempotency hit for key: {idempotency_key}")
                return result
            
            self._miss_count += 1
            return None
    
    async def save_result(
        self,
        idempotency_key: str,
        result: Dict[str, Any],
        batch_id: Optional[str] = None,
    ) -> None:
        """
        Save result for an idempotency key.
        
        Args:
            idempotency_key: Unique key for the item
            result: Result to cache
            batch_id: Optional batch_id if not part of key
        """
        async with self._lock:
            # Parse or extract batch_id
            if ":" in idempotency_key:
                parts = idempotency_key.rsplit(":", 1)
                actual_batch_id, item_idx = parts[0], parts[1]
            else:
                actual_batch_id = batch_id or idempotency_key
                item_idx = "0"
            
            self._store[actual_batch_id][item_idx] = result
            self._expiry[idempotency_key] = datetime.now() + timedelta(seconds=self.ttl_seconds)
            self._total_items += 1
            
            logger.debug(f"Saved result for key: {idempotency_key}")
    
    async def get_or_execute(
        self,
        idempotency_key: str,
        func: Callable[[], Awaitable[Dict[str, Any]]],
        batch_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get cached result or execute function and cache result.
        
        This is the main method for idempotent batch processing.
        
        Args:
            idempotency_key: Unique key for the item
            func: Async function to execute if no cached result
            batch_id: Optional batch_id
            
        Returns:
            Result (cached or newly computed)
        """
        # Check for cached result
        cached = await self.get_result(idempotency_key)
        if cached:
            return cached
        
        # Execute function
        result = await func()
        
        # Save result
        await self.save_result(idempotency_key, result, batch_id)
        
        return result
    
    async def process_batch(
        self,
        batch_id: str,
        items: List[Any],
        processor: Callable[[int, Any], Awaitable[Dict[str, Any]]],
        idempotency_key_func: Optional[Callable[[int, Any], str]] = None,
    ) -> List[BatchResult]:
        """
        Process a batch with idempotency per item.
        
        Args:
            batch_id: Unique batch identifier
            items: List of items to process
            processor: Async function(item_index, item) -> result
            idempotency_key_func: Optional function to generate custom keys
            
        Returns:
            List of BatchResult for each item
        """
        results = []
        
        for i, item in enumerate(items):
            # Generate idempotency key
            if idempotency_key_func:
                key = idempotency_key_func(i, item)
            else:
                key = self._make_key(batch_id, i)
            
            # Try to get cached result
            cached = await self.get_result(key)
            
            if cached:
                results.append(BatchResult(
                    index=i,
                    idempotency_key=key,
                    success=cached.get("success", True),
                    result=cached.get("result"),
                    error=cached.get("error"),
                    skipped=True,
                ))
            else:
                # Process item
                try:
                    result = await processor(i, item)
                    await self.save_result(key, {
                        "success": True,
                        "result": result,
                    }, batch_id)
                    
                    results.append(BatchResult(
                        index=i,
                        idempotency_key=key,
                        success=True,
                        result=result,
                        skipped=False,
                    ))
                except Exception as e:
                    await self.save_result(key, {
                        "success": False,
                        "error": str(e),
                    }, batch_id)
                    
                    results.append(BatchResult(
                        index=i,
                        idempotency_key=key,
                        success=False,
                        error=str(e),
                        skipped=False,
                    ))
        
        return results
    
    async def clear_batch(self, batch_id: str) -> int:
        """
        Clear all entries for a batch.
        
        Args:
            batch_id: Batch identifier
            
        Returns:
            Number of entries cleared
        """
        async with self._lock:
            count = len(self._store.get(batch_id, {}))
            
            # Remove expiry entries
            keys_to_remove = [
                key for key in self._expiry
                if key.startswith(f"{batch_id}:")
            ]
            for key in keys_to_remove:
                del self._expiry[key]
            
            # Remove store entries
            if batch_id in self._store:
                del self._store[batch_id]
            
            logger.info(f"Cleared {count} entries for batch {batch_id}")
            return count
    
    async def clear_expired(self) -> int:
        """Clear all expired entries."""
        return await self._cleanup_expired()
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get store statistics."""
        async with self._lock:
            total_batches = len(self._store)
            total_items = sum(len(items) for items in self._store.values())
            
            return {
                "total_batches": total_batches,
                "total_items": total_items,
                "hit_count": self._hit_count,
                "miss_count": self._miss_count,
                "hit_rate": self._hit_count / max(1, self._hit_count + self._miss_count),
                "total_items_processed": self._total_items,
                "ttl_seconds": self.ttl_seconds,
            }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get metrics snapshot."""
        return {
            "idempotency_hit_total": self._hit_count,
            "idempotency_miss_total": self._miss_count,
            "idempotency_hit_rate": self._hit_count / max(1, self._hit_count + self._miss_count),
        }

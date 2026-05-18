"""
Leader Election for Multi-Agent Coordination.

Provides coordinator leader election using Redis-based distributed locking.
Only the leader processes write operations; followers are read-only.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from src.core.multi_agent.coordination.types import LeaderInfo

logger = logging.getLogger(__name__)


class LeaderElectionError(Exception):
    """Raised for leader election errors."""
    pass


class LeaderNotAvailableError(LeaderElectionError):
    """Raised when no leader is available."""
    pass


class NotLeaderError(LeaderElectionError):
    """Raised when instance is not the leader."""
    pass


class LeaderElector:
    """
    Leader elector for multi-agent coordination.
    
    Uses Redis-based distributed locking for leader election:
    - SETNX with TTL for lock acquisition
    - Heartbeat renewal to maintain leadership
    - Automatic takeover on leader crash
    - Follower promotion on leader failure
    
    Only the leader processes write operations:
    - delegate
    - send_message
    - consensus_propose
    
    Followers serve read-only requests and redirect writes to leader.
    """
    
    def __init__(
        self,
        redis_url: Optional[str] = None,
        lock_key: str = "coordinator:leader",
        heartbeat_interval: float = 10.0,
        lock_ttl: float = 30.0,
        max_retry_attempts: int = 3,
        retry_delay: float = 1.0,
    ):
        self.redis_url = redis_url
        self.lock_key = lock_key
        self.heartbeat_interval = heartbeat_interval
        self.lock_ttl = lock_ttl
        self.max_retry_attempts = max_retry_attempts
        self.retry_delay = retry_delay
        
        self._instance_id: Optional[str] = None
        self._is_leader = False
        self._current_leader: Optional[LeaderInfo] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False
        self._term = 0
        
        # For testing without Redis
        self._in_memory_mode = redis_url is None
        self._in_memory_lock: Optional[str] = None
        self._in_memory_heartbeat: Dict[str, float] = {}
        
        self._lock = asyncio.Lock()
        
        # Metrics
        self._election_count = 0
        self._election_success = 0
        self._heartbeat_count = 0
    
    async def try_become_leader(self, instance_id: str) -> str:
        """
        Attempt to become the leader.
        
        Args:
            instance_id: Unique identifier for this instance
            
        Returns:
            instance_id if this instance became leader, otherwise current leader's ID
            
        Raises:
            LeaderElectionError: If election fails
        """
        self._instance_id = instance_id
        self._election_count += 1
        
        if self._in_memory_mode:
            return await self._try_become_leader_inmemory(instance_id)
        
        return await self._try_become_leader_redis(instance_id)
    
    async def _try_become_leader_inmemory(self, instance_id: str) -> str:
        """In-memory leader election for testing."""
        async with self._lock:
            now = time.monotonic()
            
            # Check current leader
            if self._in_memory_lock:
                last_heartbeat = self._in_memory_heartbeat.get(self._in_memory_lock, 0)
                if now - last_heartbeat < self.lock_ttl:
                    # Current leader still alive
                    if self._in_memory_lock == instance_id:
                        self._is_leader = True
                        self._current_leader = LeaderInfo(
                            leader_id=instance_id,
                            elected_at=datetime.now(),
                            last_heartbeat=datetime.now(),
                            term=self._term,
                        )
                        self._election_success += 1
                        logger.info(f"Instance {instance_id} maintained leadership (term {self._term})")
                    else:
                        self._is_leader = False
                    return self._in_memory_lock
            
            # Acquire lock
            self._in_memory_lock = instance_id
            self._in_memory_heartbeat[instance_id] = now
            self._is_leader = True
            self._term += 1
            self._current_leader = LeaderInfo(
                leader_id=instance_id,
                elected_at=datetime.now(),
                last_heartbeat=datetime.now(),
                term=self._term,
            )
            self._election_success += 1
            
            logger.info(f"Instance {instance_id} became leader (term {self._term})")
            return instance_id
    
    async def _try_become_leader_redis(self, instance_id: str) -> str:
        """Redis-based leader election."""
        try:
            import redis.asyncio as redis
            
            client = redis.from_url(self.redis_url)
            
            # Try to acquire lock with SETNX
            acquired = await client.set(
                self.lock_key,
                f"{instance_id}:{time.time()}",
                nx=True,
                ex=int(self.lock_ttl),
            )
            
            if acquired:
                self._is_leader = True
                self._term += 1
                self._current_leader = LeaderInfo(
                    leader_id=instance_id,
                    elected_at=datetime.now(),
                    last_heartbeat=datetime.now(),
                    term=self._term,
                )
                self._election_success += 1
                logger.info(f"Instance {instance_id} became leader (term {self._term})")
                await client.close()
                return instance_id
            
            # Lock not acquired, get current leader
            leader_data = await client.get(self.lock_key)
            await client.close()
            
            if leader_data:
                current_leader = leader_data.decode().split(":")[0]
                self._is_leader = (current_leader == instance_id)
                
                if not self._is_leader:
                    self._current_leader = LeaderInfo(
                        leader_id=current_leader,
                        elected_at=datetime.now(),
                        last_heartbeat=datetime.now(),
                        term=0,
                    )
                
                return current_leader
            
            # No leader, retry
            raise LeaderNotAvailableError("No leader available")
            
        except Exception as e:
            logger.error(f"Redis leader election failed: {e}")
            # Fallback to in-memory
            return await self._try_become_leader_inmemory(instance_id)
    
    async def heartbeat(self) -> bool:
        """
        Send heartbeat to maintain leadership.
        
        Returns:
            True if still the leader
        """
        if not self._instance_id:
            return False
        
        if self._in_memory_mode:
            return await self._heartbeat_inmemory()
        
        return await self._heartbeat_redis()
    
    async def _heartbeat_inmemory(self) -> bool:
        """In-memory heartbeat."""
        async with self._lock:
            if not self._is_leader:
                return False
            
            now = time.monotonic()
            self._in_memory_heartbeat[self._instance_id] = now
            
            if self._current_leader:
                self._current_leader.last_heartbeat = datetime.now()
            
            self._heartbeat_count += 1
            return True
    
    async def _heartbeat_redis(self) -> bool:
        """Redis heartbeat."""
        if not self._is_leader or not self._instance_id:
            return False
        
        try:
            import redis.asyncio as redis
            
            client = redis.from_url(self.redis_url)
            
            # Extend TTL
            leader_data = await client.get(self.lock_key)
            if not leader_data:
                # Lost leadership
                self._is_leader = False
                await client.close()
                return False
            
            current_leader = leader_data.decode().split(":")[0]
            if current_leader != self._instance_id:
                # Someone else became leader
                self._is_leader = False
                await client.close()
                return False
            
            # Refresh TTL
            await client.expire(self.lock_key, int(self.lock_ttl))
            
            if self._current_leader:
                self._current_leader.last_heartbeat = datetime.now()
            
            self._heartbeat_count += 1
            await client.close()
            return True
            
        except Exception as e:
            logger.error(f"Heartbeat failed: {e}")
            return False
    
    async def start_heartbeat(self) -> None:
        """Start automatic heartbeat task."""
        if self._running:
            return
        
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("Started leader heartbeat task")
    
    async def stop_heartbeat(self) -> None:
        """Stop automatic heartbeat task."""
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped leader heartbeat task")
    
    async def _heartbeat_loop(self) -> None:
        """Background heartbeat loop."""
        while self._running:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                
                if self._is_leader:
                    success = await self.heartbeat()
                    if not success:
                        logger.warning("Lost leadership during heartbeat")
                        self._is_leader = False
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat loop error: {e}")
    
    async def get_leader(self) -> Optional[str]:
        """Get current leader's instance ID."""
        if self._in_memory_mode:
            async with self._lock:
                if self._in_memory_lock:
                    now = time.monotonic()
                    last_heartbeat = self._in_memory_heartbeat.get(self._in_memory_lock, 0)
                    if now - last_heartbeat < self.lock_ttl:
                        return self._in_memory_lock
                    # Leader expired
                    self._in_memory_lock = None
                return None
        
        try:
            import redis.asyncio as redis
            
            client = redis.from_url(self.redis_url)
            leader_data = await client.get(self.lock_key)
            await client.close()
            
            if leader_data:
                return leader_data.decode().split(":")[0]
            return None
            
        except Exception as e:
            logger.error(f"Get leader failed: {e}")
            return None
    
    async def get_leader_info(self) -> Optional[LeaderInfo]:
        """Get detailed leader information."""
        if self._current_leader:
            if not self._current_leader.is_expired(self.lock_ttl):
                return self._current_leader
        
        leader_id = await self.get_leader()
        if leader_id:
            self._current_leader = LeaderInfo(
                leader_id=leader_id,
                elected_at=datetime.now(),
                last_heartbeat=datetime.now(),
            )
            return self._current_leader
        
        return None
    
    async def transfer_leadership(self, new_leader: str) -> None:
        """
        Transfer leadership to another instance.
        
        Args:
            new_leader: Instance ID to transfer leadership to
            
        Raises:
            NotLeaderError: If this instance is not the leader
        """
        if not self._is_leader:
            raise NotLeaderError("This instance is not the leader")
        
        logger.info(f"Transferring leadership from {self._instance_id} to {new_leader}")
        
        # In a real implementation, this would coordinate with the new leader
        # For now, just update state
        async with self._lock:
            self._is_leader = False
            self._current_leader = LeaderInfo(
                leader_id=new_leader,
                elected_at=datetime.now(),
                last_heartbeat=datetime.now(),
                term=self._term,
            )
    
    async def resign_leadership(self) -> None:
        """Resign from leadership."""
        if not self._is_leader:
            return
        
        async with self._lock:
            self._is_leader = False
            self._current_leader = None
            self._in_memory_lock = None
            logger.info(f"Instance {self._instance_id} resigned leadership")
    
    async def is_leader(self) -> bool:
        """Check if this instance is the leader."""
        return self._is_leader
    
    async def assert_leader(self) -> None:
        """
        Assert this instance is the leader.
        
        Raises:
            NotLeaderError: If not the leader
        """
        if not self._is_leader:
            raise NotLeaderError(
                f"Instance {self._instance_id} is not the leader. "
                f"Current leader: {await self.get_leader()}"
            )
    
    async def force_election(self) -> str:
        """
        Force a new election (for recovery scenarios).
        
        Returns:
            New leader's instance ID
        """
        if not self._instance_id:
            raise LeaderElectionError("No instance ID set")
        
        # Resign current leadership
        await self.resign_leadership()
        
        # Try to become leader
        leader = await self.try_become_leader(self._instance_id)
        
        if leader == self._instance_id:
            await self.start_heartbeat()
        
        return leader
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get leader election metrics."""
        return {
            "instance_id": self._instance_id,
            "is_leader": self._is_leader,
            "current_leader": self._current_leader.leader_id if self._current_leader else None,
            "term": self._term,
            "election_count": self._election_count,
            "election_success": self._election_success,
            "heartbeat_count": self._heartbeat_count,
            "heartbeat_interval": self.heartbeat_interval,
            "lock_ttl": self.lock_ttl,
            "in_memory_mode": self._in_memory_mode,
        }

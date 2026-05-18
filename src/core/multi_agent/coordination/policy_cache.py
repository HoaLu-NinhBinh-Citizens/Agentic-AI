"""
Policy Cache Invalidation and Sandbox Egress Policy.

Policy Cache:
- Version-based cache invalidation
- Broadcast events to workers

Sandbox Egress:
- Domain/IP whitelist enforcement
- Only allow connections to allowed domains
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import socket
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class Policy:
    """Cached policy with version."""
    policy_id: str
    version: int
    data: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass
class PolicyCacheEntry:
    """Cache entry with policy."""
    policy_id: str
    version: int
    data: Dict[str, Any]
    cached_at: datetime
    invalidated: bool = False


class PolicyCacheInvalidator:
    """
    Policy cache with version-based invalidation.
    
    Features:
    - Version tracking for each policy
    - Automatic cache invalidation on policy change
    - Broadcast events to workers
    - Atomic version increment
    """
    
    def __init__(
        self,
        cache_ttl_seconds: float = 300.0,
        broadcast_channel: str = "policy_updates",
    ):
        self.cache_ttl = cache_ttl_seconds
        self.broadcast_channel = broadcast_channel
        
        # Policy versions
        self._policy_versions: Dict[str, int] = {}
        
        # Cache storage
        self._cache: Dict[str, PolicyCacheEntry] = {}
        
        # Invalidation subscribers
        self._subscribers: List[Callable] = []
        
        # Pub/sub handlers (would be Redis in production)
        self._pubsub_messages: List[Dict[str, Any]] = []
        
        self._lock = asyncio.Lock()
    
    def register_subscriber(self, callback: Callable) -> None:
        """Register callback for invalidation events."""
        self._subscribers.append(callback)
    
    async def get_policy(self, policy_id: str) -> Optional[Policy]:
        """Get policy from cache or source."""
        # Check if we have the latest version
        cache_key = f"{policy_id}:{self._policy_versions.get(policy_id, 0)}"
        
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if not entry.invalidated:
                return Policy(
                    policy_id=entry.policy_id,
                    version=entry.version,
                    data=entry.data,
                    created_at=entry.cached_at,
                    updated_at=entry.cached_at,
                )
        
        # Cache miss or invalidated - would fetch from source
        # For now, return None
        return None
    
    async def update_policy(
        self,
        policy_id: str,
        data: Dict[str, Any],
    ) -> Policy:
        """Update policy and invalidate cache."""
        async with self._lock:
            # Increment version
            old_version = self._policy_versions.get(policy_id, 0)
            new_version = old_version + 1
            self._policy_versions[policy_id] = new_version
            
            # Mark old cache entries as invalidated
            for key, entry in self._cache.items():
                if entry.policy_id == policy_id:
                    entry.invalidated = True
            
            # Create new policy
            now = datetime.now()
            policy = Policy(
                policy_id=policy_id,
                version=new_version,
                data=data,
                created_at=now,
                updated_at=now,
            )
            
            # Cache new entry
            cache_key = f"{policy_id}:{new_version}"
            self._cache[cache_key] = PolicyCacheEntry(
                policy_id=policy_id,
                version=new_version,
                data=data,
                cached_at=now,
            )
            
            # Broadcast invalidation event
            await self._broadcast_invalidation(policy_id, old_version, new_version)
            
            logger.info(f"Policy {policy_id} updated to version {new_version}")
            return policy
    
    async def invalidate(self, policy_id: str) -> None:
        """Invalidate all cached versions of policy."""
        async with self._lock:
            old_version = self._policy_versions.get(policy_id, 0)
            new_version = old_version + 1
            self._policy_versions[policy_id] = new_version
            
            # Mark all entries as invalidated
            for key, entry in self._cache.items():
                if entry.policy_id == policy_id:
                    entry.invalidated = True
            
            # Broadcast
            await self._broadcast_invalidation(policy_id, old_version, new_version)
    
    async def _broadcast_invalidation(
        self,
        policy_id: str,
        old_version: int,
        new_version: int,
    ) -> None:
        """Broadcast invalidation event to subscribers."""
        message = {
            "type": "policy_invalidated",
            "policy_id": policy_id,
            "old_version": old_version,
            "new_version": new_version,
            "timestamp": datetime.now().isoformat(),
        }
        
        self._pubsub_messages.append(message)
        
        # Notify subscribers
        for callback in self._subscribers:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(message)
                else:
                    callback(message)
            except Exception as e:
                logger.error(f"Invalidation callback failed: {e}")
    
    async def get_version(self, policy_id: str) -> int:
        """Get current version of policy."""
        return self._policy_versions.get(policy_id, 0)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get cache metrics."""
        total_entries = len(self._cache)
        invalidated = sum(1 for e in self._cache.values() if e.invalidated)
        
        return {
            "tracked_policies": len(self._policy_versions),
            "cache_entries": total_entries,
            "invalidated_entries": invalidated,
            "subscribers": len(self._subscribers),
        }


class SandboxEgressPolicy:
    """
    Sandbox egress policy enforcement.
    
    Features:
    - Domain/IP whitelist enforcement
    - DNS resolution caching
    - Background IP updates
    """
    
    def __init__(
        self,
        allowed_domains: Optional[List[str]] = None,
        resolve_interval_seconds: float = 300.0,
    ):
        self.allowed_domains: Set[str] = set(allowed_domains or [])
        self.resolve_interval = resolve_interval_seconds
        
        # Resolved IPs
        self._domain_ips: Dict[str, Set[str]] = {}
        
        # Blocked connections (for metrics)
        self._blocked_connections: List[Dict[str, Any]] = []
        
        self._running = False
        self._resolve_task: Optional[asyncio.Task] = None
        
        self._lock = asyncio.Lock()
    
    async def add_domain(self, domain: str) -> None:
        """Add domain to allowed list."""
        async with self._lock:
            self.allowed_domains.add(domain)
            await self._resolve_domain(domain)
    
    async def remove_domain(self, domain: str) -> None:
        """Remove domain from allowed list."""
        async with self._lock:
            self.allowed_domains.discard(domain)
            self._domain_ips.pop(domain, None)
    
    async def update_allowed_domains(self, domains: List[str]) -> None:
        """Update entire allowed domains list."""
        async with self._lock:
            self.allowed_domains = set(domains)
            for domain in domains:
                await self._resolve_domain(domain)
    
    async def _resolve_domain(self, domain: str) -> None:
        """Resolve domain to IP addresses."""
        try:
            # Could be an IP address already
            if self._is_ip_address(domain):
                self._domain_ips[domain] = {domain}
                return
            
            # Resolve DNS
            addr_info = socket.getaddrinfo(domain, 443)
            ips = set()
            for info in addr_info:
                ips.add(info[4][0])
            
            self._domain_ips[domain] = ips
            logger.debug(f"Resolved {domain} to {ips}")
            
        except Exception as e:
            logger.warning(f"Failed to resolve {domain}: {e}")
            self._domain_ips[domain] = set()
    
    def _is_ip_address(self, address: str) -> bool:
        """Check if string is an IP address."""
        try:
            socket.inet_aton(address)
            return True
        except socket.error:
            return False
    
    async def is_allowed(self, destination: str) -> tuple[bool, str]:
        """
        Check if destination is allowed.
        
        Returns (allowed, reason).
        """
        # Extract host from destination
        host = self._extract_host(destination)
        
        async with self._lock:
            # Check exact match
            if host in self.allowed_domains:
                return True, "domain_whitelisted"
            
            # Check if IP is in resolved IPs
            resolved_ips = set()
            for domain, ips in self._domain_ips.items():
                resolved_ips.update(ips)
            
            if host in resolved_ips:
                return True, "ip_in_resolved_list"
            
            # Check against resolved IPs of allowed domains
            for domain in self.allowed_domains:
                domain_ips = self._domain_ips.get(domain, set())
                if host in domain_ips:
                    return True, "ip_resolved_from_domain"
            
            return False, "not_in_whitelist"
    
    def _extract_host(self, destination: str) -> str:
        """Extract host from destination (url, host:port, or IP)."""
        # Remove protocol
        if "://" in destination:
            destination = destination.split("://")[1]
        
        # Remove port
        if ":" in destination:
            destination = destination.split(":")[0]
        
        # Remove path
        if "/" in destination:
            destination = destination.split("/")[0]
        
        return destination
    
    async def check_connection(
        self,
        source: str,
        destination: str,
    ) -> tuple[bool, str]:
        """Check if connection is allowed."""
        allowed, reason = await self.is_allowed(destination)
        
        if not allowed:
            # Log blocked connection
            async with self._lock:
                self._blocked_connections.append({
                    "source": source,
                    "destination": destination,
                    "timestamp": datetime.now().isoformat(),
                    "reason": reason,
                })
        
        return allowed, reason
    
    async def start_resolver(self) -> None:
        """Start background DNS resolver."""
        if self._running:
            return
        
        self._running = True
        self._resolve_task = asyncio.create_task(self._resolve_loop())
        logger.info("Egress policy DNS resolver started")
    
    async def stop_resolver(self) -> None:
        """Stop background DNS resolver."""
        self._running = False
        if self._resolve_task:
            self._resolve_task.cancel()
            try:
                await self._resolve_task
            except asyncio.CancelledError:
                pass
        logger.info("Egress policy DNS resolver stopped")
    
    async def _resolve_loop(self) -> None:
        """Background DNS resolution loop."""
        while self._running:
            try:
                # Resolve all domains
                async with self._lock:
                    domains = list(self.allowed_domains)
                
                for domain in domains:
                    await self._resolve_domain(domain)
                
                await asyncio.sleep(self.resolve_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Resolve loop error: {e}")
                await asyncio.sleep(60)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get egress policy metrics."""
        return {
            "allowed_domains": len(self.allowed_domains),
            "resolved_domains": len(self._domain_ips),
            "total_resolved_ips": sum(len(ips) for ips in self._domain_ips.values()),
            "blocked_connections": len(self._blocked_connections),
            "recent_blocked": self._blocked_connections[-10:],
        }

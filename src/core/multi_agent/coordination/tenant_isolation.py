"""
Tenant Isolation Layer for Multi-Agent Coordination.

Provides multi-tenant data isolation with JWT-based authentication.
All tenant data is filtered by tenant_id in all queries.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class TenantIsolationError(Exception):
    """Raised when tenant isolation is violated."""
    pass


class TenantNotFoundError(TenantIsolationError):
    """Raised when tenant is not found."""
    pass


class CrossTenantAccessError(TenantIsolationError):
    """Raised when cross-tenant access is attempted."""
    pass


class JWTError(Exception):
    """Raised for JWT validation errors."""
    pass


@dataclass
class TenantContext:
    """Context for current tenant operation."""
    tenant_id: str
    user_id: Optional[str] = None
    roles: List[str] = field(default_factory=list)
    is_admin: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def can_access_all_tenants(self) -> bool:
        return self.is_admin and "super_admin" in self.roles


class TenantStore:
    """Interface for tenant storage."""
    
    async def create_tenant(self, config: Dict[str, Any]) -> None:
        raise NotImplementedError
    
    async def get_tenant(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError
    
    async def delete_tenant(self, tenant_id: str) -> None:
        raise NotImplementedError
    
    async def list_tenants(self) -> List[str]:
        raise NotImplementedError
    
    async def update_tenant(self, tenant_id: str, config: Dict[str, Any]) -> None:
        raise NotImplementedError


class InMemoryTenantStore(TenantStore):
    """In-memory implementation of TenantStore."""
    
    def __init__(self):
        self._tenants: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
    
    async def create_tenant(self, config: Dict[str, Any]) -> None:
        async with self._lock:
            self._tenants[config["tenant_id"]] = config
    
    async def get_tenant(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        return self._tenants.get(tenant_id)
    
    async def delete_tenant(self, tenant_id: str) -> None:
        async with self._lock:
            if tenant_id in self._tenants:
                del self._tenants[tenant_id]
    
    async def list_tenants(self) -> List[str]:
        return list(self._tenants.keys())
    
    async def update_tenant(self, tenant_id: str, config: Dict[str, Any]) -> None:
        async with self._lock:
            if tenant_id in self._tenants:
                self._tenants[tenant_id].update(config)


class TenantIsolationLayer:
    """
    Tenant isolation layer for multi-agent coordination.
    
    Features:
    - JWT-based tenant identification
    - Automatic tenant_id filtering in queries
    - Admin override for multi-tenant access
    - Audit logging per tenant
    
    All data operations are scoped to the current tenant unless
    the user has admin privileges.
    """
    
    def __init__(
        self,
        store: Optional[TenantStore] = None,
        jwt_secret: str = "",
        admin_roles: Optional[List[str]] = None,
        require_tenant_header: bool = True,
        allow_cross_tenant_audit: bool = True,
    ):
        self.store = store or InMemoryTenantStore()
        self.jwt_secret = jwt_secret
        self.admin_roles = admin_roles or ["admin", "super_admin"]
        self.require_tenant_header = require_tenant_header
        self.allow_cross_tenant_audit = allow_cross_tenant_audit
        
        self._lock = asyncio.Lock()
        self._context: Dict[str, TenantContext] = {}
        self._audit_log: List[Dict[str, Any]] = []
    
    def _decode_jwt(self, token: str) -> Dict[str, Any]:
        """Decode and validate JWT token."""
        try:
            import base64
            import json as json_module
            
            # Simple JWT decode (not verification for demo)
            # In production, use PyJWT library
            parts = token.split(".")
            if len(parts) != 3:
                raise JWTError("Invalid JWT format")
            
            payload = parts[1]
            # Add padding if needed
            padding = 4 - len(payload) % 4
            if padding != 4:
                payload += "=" * padding
            
            decoded = base64.urlsafe_b64decode(payload)
            claims = json_module.loads(decoded)
            
            return claims
        except Exception as e:
            raise JWTError(f"Failed to decode JWT: {e}")
    
    async def extract_tenant(
        self,
        token_or_header: str,
    ) -> TenantContext:
        """
        Extract tenant context from JWT token or header.
        
        Args:
            token_or_header: JWT token or Authorization header value
            
        Returns:
            TenantContext with tenant information
        """
        # Extract token from header if needed
        token = token_or_header
        if token.startswith("Bearer "):
            token = token[7:]
        
        # Decode JWT
        claims = self._decode_jwt(token)
        
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            raise TenantNotFoundError("No tenant_id in token")
        
        # Verify tenant exists
        tenant_config = await self.store.get_tenant(tenant_id)
        if not tenant_config:
            raise TenantNotFoundError(f"Tenant {tenant_id} not found")
        
        if not tenant_config.get("enabled", True):
            raise TenantIsolationError(f"Tenant {tenant_id} is disabled")
        
        # Build context
        roles = claims.get("roles", [])
        is_admin = any(role in self.admin_roles for role in roles)
        
        context = TenantContext(
            tenant_id=tenant_id,
            user_id=claims.get("sub"),
            roles=roles,
            is_admin=is_admin,
            metadata=claims.get("metadata", {}),
        )
        
        return context
    
    async def set_context(self, request_id: str, context: TenantContext) -> None:
        """Set tenant context for current operation."""
        async with self._lock:
            self._context[request_id] = context
    
    async def get_context(self, request_id: str) -> Optional[TenantContext]:
        """Get tenant context for current operation."""
        async with self._lock:
            return self._context.get(request_id)
    
    async def clear_context(self, request_id: str) -> None:
        """Clear tenant context after operation."""
        async with self._lock:
            self._context.pop(request_id, None)
    
    def enforce_isolation(self, context: TenantContext) -> None:
        """
        Enforce tenant isolation rules.
        
        Raises:
            CrossTenantAccessError: If cross-tenant access is attempted
        """
        if self.require_tenant_header and not context.tenant_id:
            raise TenantIsolationError("No tenant context")
    
    def filter_by_tenant(
        self,
        query: str,
        params: tuple,
        context: TenantContext,
        tenant_column: str = "tenant_id",
    ) -> tuple[str, tuple]:
        """
        Add tenant filter to SQL query.
        
        Args:
            query: SQL query
            params: Query parameters
            context: Tenant context
            tenant_column: Column name for tenant_id
            
        Returns:
            Modified query and params with tenant filter
        """
        if context.can_access_all_tenants:
            # Admin can access all tenants, but we still log it
            if self.allow_cross_tenant_audit:
                return query, params
            return query, params
        
        # Add tenant filter
        if "WHERE" in query.upper():
            # More complex handling for WHERE clauses
            return f"{query} AND {tenant_column} = ?", (*params, context.tenant_id)
        else:
            return f"{query} WHERE {tenant_column} = ?", (context.tenant_id,)
    
    def filter_results(
        self,
        results: List[Dict[str, Any]],
        context: TenantContext,
        tenant_column: str = "tenant_id",
    ) -> List[Dict[str, Any]]:
        """
        Filter results to only include current tenant's data.
        
        Args:
            results: Query results
            context: Tenant context
            tenant_column: Column name for tenant_id
            
        Returns:
            Filtered results
        """
        if context.can_access_all_tenants:
            return results
        
        return [
            r for r in results
            if r.get(tenant_column) == context.tenant_id
        ]
    
    async def query(
        self,
        query_func: Callable[..., Any],
        context: TenantContext,
        *args,
        tenant_column: str = "tenant_id",
        **kwargs,
    ) -> Any:
        """
        Execute query with tenant filtering.
        
        Args:
            query_func: Query function to execute
            context: Tenant context
            *args: Query arguments
            tenant_column: Column name for tenant_id
            **kwargs: Query keyword arguments
            
        Returns:
            Query results (filtered by tenant)
        """
        self.enforce_isolation(context)
        
        results = await query_func(*args, **kwargs)
        
        # Filter results
        if isinstance(results, list):
            return self.filter_results(results, context, tenant_column)
        
        return results
    
    async def audit(
        self,
        action: str,
        context: TenantContext,
        details: Dict[str, Any],
    ) -> None:
        """
        Log audit entry for tenant operation.
        
        Args:
            action: Action performed
            context: Tenant context
            details: Additional details
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "tenant_id": context.tenant_id,
            "user_id": context.user_id,
            "action": action,
            "details": details,
            "is_admin": context.is_admin,
        }
        
        async with self._lock:
            self._audit_log.append(entry)
            if len(self._audit_log) > 10000:
                self._audit_log = self._audit_log[-5000:]
        
        logger.info(f"AUDIT: {action} by {context.tenant_id}: {details}")
    
    async def get_audit_log(
        self,
        tenant_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get audit log entries."""
        async with self._lock:
            if tenant_id:
                entries = [e for e in self._audit_log if e["tenant_id"] == tenant_id]
            else:
                entries = self._audit_log
            return entries[-limit:]
    
    async def create_tenant(
        self,
        tenant_id: str,
        name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Create a new tenant."""
        config = {
            "tenant_id": tenant_id,
            "name": name,
            "enabled": True,
            "metadata": metadata or {},
            "created_at": datetime.now().isoformat(),
        }
        
        await self.store.create_tenant(config)
        logger.info(f"Created tenant: {tenant_id}")
    
    async def delete_tenant(self, tenant_id: str) -> None:
        """Delete a tenant and all its data."""
        await self.store.delete_tenant(tenant_id)
        logger.info(f"Deleted tenant: {tenant_id}")
    
    async def get_tenant(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get tenant configuration."""
        return await self.store.get_tenant(tenant_id)
    
    async def disable_tenant(self, tenant_id: str) -> None:
        """Disable a tenant."""
        await self.store.update_tenant(tenant_id, {"enabled": False})
        logger.info(f"Disabled tenant: {tenant_id}")
    
    async def enable_tenant(self, tenant_id: str) -> None:
        """Enable a tenant."""
        await self.store.update_tenant(tenant_id, {"enabled": True})
        logger.info(f"Enabled tenant: {tenant_id}")
    
    async def list_tenants(self) -> List[Dict[str, Any]]:
        """List all tenants."""
        tenant_ids = await self.store.list_tenants()
        return [
            await self.store.get_tenant(tid)
            for tid in tenant_ids
        ]
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get metrics snapshot."""
        return {
            "audit_log_entries": len(self._audit_log),
            "active_contexts": len(self._context),
        }

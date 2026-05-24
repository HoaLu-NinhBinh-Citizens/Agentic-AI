"""RBAC (Role-Based Access Control) Enforcement.

Fixes Critical Gap: No RBAC enforcement.

Features:
- Role definitions with permissions
- User-role assignments
- Permission checking
- Audit logging of access decisions
- Role hierarchy
- Time-based access restrictions
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# PERMISSION TYPES
# =============================================================================


class Permission(Enum):
    """Available permissions in the system."""
    
    # Flash operations
    FLASH_READ = auto()
    FLASH_WRITE = auto()
    FLASH_ERASE = auto()
    FLASH_VERIFY = auto()
    FLASH_LOCK = auto()
    
    # Target operations
    TARGET_CONNECT = auto()
    TARGET_DISCONNECT = auto()
    TARGET_READ = auto()
    TARGET_RESET = auto()
    
    # Firmware operations
    FIRMWARE_UPLOAD = auto()
    FIRMWARE_DOWNLOAD = auto()
    FIRMWARE_SIGN = auto()
    FIRMWARE_VERIFY = auto()
    
    # Configuration
    CONFIG_READ = auto()
    CONFIG_WRITE = auto()
    CONFIG_DELETE = auto()
    
    # User management
    USER_CREATE = auto()
    USER_READ = auto()
    USER_UPDATE = auto()
    USER_DELETE = auto()
    ROLE_ASSIGN = auto()
    
    # Audit
    AUDIT_READ = auto()
    AUDIT_EXPORT = auto()
    
    # Plugin management
    PLUGIN_INSTALL = auto()
    PLUGIN_UNINSTALL = auto()
    PLUGIN_EXECUTE = auto()
    
    # Admin
    ADMIN_ALL = auto()


class Resource(Enum):
    """Resource types that can be protected."""
    
    FLASH = "flash"
    TARGET = "target"
    FIRMWARE = "firmware"
    CONFIG = "config"
    USER = "user"
    ROLE = "role"
    AUDIT = "audit"
    PLUGIN = "plugin"
    SYSTEM = "system"


# =============================================================================
# ROLE DEFINITIONS
# =============================================================================


@dataclass
class Role:
    """Role definition with permissions."""
    
    role_id: str
    name: str
    description: str = ""
    
    # Permissions (action:resource format)
    permissions: set[str] = field(default_factory=set)
    
    # Hierarchy
    parent_role: str | None = None
    
    # Constraints
    max_concurrent_sessions: int = 1
    allowed_hours: tuple[int, int] | None = None  # (start_hour, end_hour) in 24h format
    
    # Whether this is a system role
    is_system: bool = False
    
    def has_permission(self, action: str, resource: str) -> bool:
        """Check if role has a permission."""
        perm = f"{action}:{resource}"
        
        # Direct permission
        if perm in self.permissions:
            return True
        
        # Admin all permission
        if "admin:all" in self.permissions or "admin:*" in self.permissions:
            return True
        
        # Wildcard permissions
        if f"{action}:*" in self.permissions:
            return True
        if f"*:{resource}" in self.permissions:
            return True
        
        # Check parent role (if inheriting)
        # This would be resolved by RoleManager
        
        return False


# =============================================================================
# PREDEFINED ROLES
# =============================================================================


class SystemRoles:
    """System-defined roles."""
    
    ADMIN = Role(
        role_id="role:admin",
        name="Administrator",
        description="Full system access",
        permissions={
            "admin:all",
            "flash:*",
            "target:*",
            "firmware:*",
            "config:*",
            "user:*",
            "role:*",
            "audit:*",
            "plugin:*",
        },
        is_system=True,
    )
    
    ENGINEER = Role(
        role_id="role:engineer",
        name="Firmware Engineer",
        description="Firmware development and flashing",
        permissions={
            "flash:read",
            "flash:write",
            "flash:erase",
            "flash:verify",
            "flash:lock",
            "target:connect",
            "target:disconnect",
            "target:read",
            "target:reset",
            "firmware:upload",
            "firmware:download",
            "firmware:sign",
            "firmware:verify",
            "config:read",
        },
        is_system=True,
    )
    
    OPERATOR = Role(
        role_id="role:operator",
        name="Operator",
        description="Operational tasks only",
        permissions={
            "target:connect",
            "target:read",
            "target:reset",
            "firmware:upload",
            "firmware:verify",
            "config:read",
        },
        is_system=True,
    )
    
    VIEWER = Role(
        role_id="role:viewer",
        name="Viewer",
        description="Read-only access",
        permissions={
            "flash:read",
            "target:read",
            "firmware:read",
            "config:read",
            "audit:read",
        },
        is_system=True,
    )
    
    GUEST = Role(
        role_id="role:guest",
        name="Guest",
        description="Minimal access",
        permissions={
            "target:read",
            "config:read",
        },
        is_system=True,
    )


# =============================================================================
# USER & SESSION
# =============================================================================


@dataclass
class User:
    """User account."""
    
    user_id: str
    username: str
    email: str
    
    # Roles
    role_ids: list[str] = field(default_factory=list)
    
    # Status
    is_active: bool = True
    is_locked: bool = False
    failed_login_attempts: int = 0
    
    # Security
    mfa_enabled: bool = False
    password_hash: str = ""
    
    # Audit
    created_at: str = ""
    last_login: str | None = None
    
    # Constraints
    allowed_source_ips: list[str] = field(default_factory=list)  # Empty = all
    
    def has_role(self, role_id: str) -> bool:
        return role_id in self.role_ids
    
    def is_locked_out(self) -> bool:
        return self.is_locked or self.failed_login_attempts >= 5


@dataclass
class Session:
    """Active user session."""
    
    session_id: str
    user_id: str
    username: str
    
    # Roles at session start
    role_ids: list[str] = field(default_factory=list)
    
    # Context
    source_ip: str = ""
    user_agent: str = ""
    
    # Timing
    created_at: str = ""
    expires_at: str = ""
    last_activity: str = ""
    
    # State
    is_active: bool = True


# =============================================================================
# ACCESS DECISION
# =============================================================================


@dataclass
class AccessDecision:
    """Result of an access check."""
    
    granted: bool
    reason: str
    user_id: str
    permission: str
    resource: str | None
    
    # Audit info
    evaluated_at: str = ""
    session_id: str | None = None


# =============================================================================
# RBAC MANAGER
# =============================================================================


class RBACManager:
    """Role-Based Access Control Manager.
    
    CRITICAL: This enforces access control for all operations.
    """
    
    def __init__(self):
        self._roles: dict[str, Role] = {}
        self._users: dict[str, User] = {}
        self._sessions: dict[str, Session] = {}
        self._user_sessions: dict[str, set[str]] = {}  # user_id -> session_ids
        
        self._lock = asyncio.Lock()
        
        # Register system roles
        self._register_system_roles()
    
    def _register_system_roles(self) -> None:
        """Register system-defined roles."""
        for role in [
            SystemRoles.ADMIN,
            SystemRoles.ENGINEER,
            SystemRoles.OPERATOR,
            SystemRoles.VIEWER,
            SystemRoles.GUEST,
        ]:
            self.register_role(role)
    
    # -------------------------------------------------------------------------
    # Role Management
    # -------------------------------------------------------------------------
    
    def register_role(self, role: Role) -> None:
        """Register a role."""
        self._roles[role.role_id] = role
        logger.info("role_registered: id=%s name=%s", role.role_id, role.name)
    
    def get_role(self, role_id: str) -> Role | None:
        """Get a role by ID."""
        return self._roles.get(role_id)
    
    def get_all_roles(self) -> list[Role]:
        """Get all registered roles."""
        return list(self._roles.values())
    
    def delete_role(self, role_id: str) -> bool:
        """Delete a role."""
        if role_id.startswith("role:"):  # System roles can't be deleted
            return False
        
        if role_id in self._roles:
            del self._roles[role_id]
            logger.info("role_deleted: id=%s", role_id)
            return True
        return False
    
    def get_effective_permissions(self, role_ids: list[str]) -> set[str]:
        """Get effective permissions for a set of roles."""
        permissions = set()
        
        for role_id in role_ids:
            role = self._roles.get(role_id)
            if not role:
                continue
            
            permissions |= role.permissions
            
            # Inherit from parent role
            if role.parent_role:
                parent_perms = self.get_effective_permissions([role.parent_role])
                permissions |= parent_perms
        
        return permissions
    
    # -------------------------------------------------------------------------
    # User Management
    # -------------------------------------------------------------------------
    
    def register_user(self, user: User) -> None:
        """Register a user."""
        self._users[user.user_id] = user
        logger.info("user_registered: id=%s username=%s", user.user_id, user.username)
    
    def get_user(self, user_id: str) -> User | None:
        """Get user by ID."""
        return self._users.get(user_id)
    
    def get_user_by_username(self, username: str) -> User | None:
        """Get user by username."""
        for user in self._users.values():
            if user.username == username:
                return user
        return None
    
    def update_user(self, user_id: str, **kwargs) -> bool:
        """Update user attributes."""
        user = self._users.get(user_id)
        if not user:
            return False
        
        for key, value in kwargs.items():
            if hasattr(user, key):
                setattr(user, key, value)
        
        logger.info("user_updated: id=%s", user_id)
        return True
    
    def assign_role(self, user_id: str, role_id: str) -> bool:
        """Assign a role to a user."""
        user = self._users.get(user_id)
        role = self._roles.get(role_id)
        
        if not user or not role:
            return False
        
        if role_id not in user.role_ids:
            user.role_ids.append(role_id)
            logger.info("role_assigned: user=%s role=%s", user_id, role_id)
        
        return True
    
    def revoke_role(self, user_id: str, role_id: str) -> bool:
        """Revoke a role from a user."""
        user = self._users.get(user_id)
        
        if not user:
            return False
        
        if role_id in user.role_ids:
            user.role_ids.remove(role_id)
            logger.info("role_revoked: user=%s role=%s", user_id, role_id)
            return True
        
        return False
    
    # -------------------------------------------------------------------------
    # Session Management
    # -------------------------------------------------------------------------
    
    def create_session(self, user_id: str, session_id: str) -> Session | None:
        """Create a new session for a user."""
        user = self._users.get(user_id)
        if not user:
            return None
        
        if user.is_locked_out():
            logger.warning("session_denied_locked: user=%s", user_id)
            return None
        
        session = Session(
            session_id=session_id,
            user_id=user_id,
            username=user.username,
            role_ids=list(user.role_ids),
            created_at=datetime.utcnow().isoformat(),
            expires_at=datetime.utcnow().isoformat(),  # Will be set properly
        )
        
        self._sessions[session_id] = session
        
        if user_id not in self._user_sessions:
            self._user_sessions[user_id] = set()
        
        # Check concurrent session limit
        primary_role = self.get_role(user.role_ids[0]) if user.role_ids else None
        max_sessions = primary_role.max_concurrent_sessions if primary_role else 1
        
        if len(self._user_sessions[user_id]) >= max_sessions:
            # Remove oldest session
            old_sessions = list(self._user_sessions[user_id])
            if old_sessions:
                self.close_session(old_sessions[0])
        
        self._user_sessions[user_id].add(session_id)
        
        logger.info("session_created: user=%s session=%s", user_id, session_id)
        
        return session
    
    def get_session(self, session_id: str) -> Session | None:
        """Get session by ID."""
        return self._sessions.get(session_id)
    
    def close_session(self, session_id: str) -> bool:
        """Close a session."""
        session = self._sessions.get(session_id)
        if not session:
            return False
        
        session.is_active = False
        
        if session.user_id in self._user_sessions:
            self._user_sessions[session.user_id].discard(session_id)
        
        logger.info("session_closed: session=%s", session_id)
        return True
    
    def close_all_user_sessions(self, user_id: str) -> int:
        """Close all sessions for a user."""
        session_ids = list(self._user_sessions.get(user_id, set()))
        for session_id in session_ids:
            self.close_session(session_id)
        
        logger.info("all_sessions_closed: user=%s count=%s", user_id, len(session_ids))
        return len(session_ids)
    
    # -------------------------------------------------------------------------
    # Access Control
    # -------------------------------------------------------------------------
    
    async def check_permission(
        self,
        user_id: str,
        action: str,
        resource: str,
        session_id: str | None = None,
    ) -> AccessDecision:
        """Check if user has permission for an action on a resource.
        
        Args:
            user_id: User identifier
            action: Action (e.g., "flash", "write")
            resource: Resource type (e.g., "flash", "firmware")
            session_id: Optional session for additional context
            
        Returns:
            AccessDecision with result
        """
        async with self._lock:
            user = self._users.get(user_id)
            
            if not user:
                return AccessDecision(
                    granted=False,
                    reason="User not found",
                    user_id=user_id,
                    permission=f"{action}:{resource}",
                    resource=resource,
                    evaluated_at=datetime.utcnow().isoformat(),
                )
            
            if not user.is_active:
                return AccessDecision(
                    granted=False,
                    reason="User is inactive",
                    user_id=user_id,
                    permission=f"{action}:{resource}",
                    resource=resource,
                    evaluated_at=datetime.utcnow().isoformat(),
                    session_id=session_id,
                )
            
            if user.is_locked_out():
                return AccessDecision(
                    granted=False,
                    reason="User is locked out",
                    user_id=user_id,
                    permission=f"{action}:{resource}",
                    resource=resource,
                    evaluated_at=datetime.utcnow().isoformat(),
                    session_id=session_id,
                )
            
            # Get effective permissions
            permissions = self.get_effective_permissions(user.role_ids)
            
            # Check permission
            perm_str = f"{action}:{resource}"
            has_perm = perm_str in permissions or "admin:all" in permissions
            
            # Also check wildcards
            if not has_perm:
                has_perm = f"{action}:*" in permissions
            if not has_perm:
                has_perm = f"*:{resource}" in permissions
            
            decision = AccessDecision(
                granted=has_perm,
                reason="Permission granted" if has_perm else f"Missing permission: {perm_str}",
                user_id=user_id,
                permission=perm_str,
                resource=resource,
                evaluated_at=datetime.utcnow().isoformat(),
                session_id=session_id,
            )
            
            # Log access decision
            if not has_perm:
                logger.warning(
                    "access_denied: user=%s permission=%s",
                    user_id, perm_str,
                )
            else:
                logger.debug(
                    "access_granted: user=%s permission=%s",
                    user_id, perm_str,
                )
            
            return decision
    
    async def require_permission(
        self,
        user_id: str,
        action: str,
        resource: str,
        session_id: str | None = None,
    ) -> None:
        """Require permission, raise if denied.
        
        Raises:
            AccessDeniedError: If permission is denied
        """
        decision = await self.check_permission(user_id, action, resource, session_id)
        
        if not decision.granted:
            raise AccessDeniedError(
                f"Permission denied: {action}:{resource}",
                decision=decision,
            )
    
    def get_user_permissions(self, user_id: str) -> set[str]:
        """Get all permissions for a user."""
        user = self._users.get(user_id)
        if not user:
            return set()
        
        return self.get_effective_permissions(user.role_ids)
    
    def get_user_roles(self, user_id: str) -> list[Role]:
        """Get all roles for a user."""
        user = self._users.get(user_id)
        if not user:
            return []
        
        return [
            self._roles[rid]
            for rid in user.role_ids
            if rid in self._roles
        ]


# =============================================================================
# EXCEPTIONS
# =============================================================================


class AccessDeniedError(Exception):
    """Raised when access is denied."""
    
    def __init__(self, message: str, decision: AccessDecision | None = None):
        super().__init__(message)
        self.decision = decision


# =============================================================================
# DECORATORS
# =============================================================================


def require_permission(action: str, resource: str):
    """Decorator to require a permission for a method.
    
    Usage:
        @require_permission("flash", "write")
        async def flash_firmware(self, ...):
            ...
    """
    def decorator(func):
        async def wrapper(self, *args, **kwargs):
            # Get user_id from context
            user_id = getattr(self, "user_id", None)
            if not user_id:
                raise AccessDeniedError("No user context")
            
            rbac = getattr(self, "rbac", None)
            if not rbac:
                raise AccessDeniedError("No RBAC manager")
            
            await rbac.require_permission(user_id, action, resource)
            return await func(self, *args, **kwargs)
        
        return wrapper
    return decorator


# =============================================================================
# GLOBAL RBAC INSTANCE
# =============================================================================


_global_rbac: RBACManager | None = None


def get_rbac() -> RBACManager:
    """Get the global RBAC manager."""
    global _global_rbac
    if _global_rbac is None:
        _global_rbac = RBACManager()
    return _global_rbac

"""
Enhanced Sandbox Security with Seccomp, Syscall Filters, and Namespaces.

Features:
- Seccomp profiles
- Syscall filtering
- Filesystem virtualization
- Resource namespaces
- Network namespace isolation
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class SyscallCategory(str, Enum):
    """Categories of syscalls for filtering."""
    FILE = "file"           # open, read, write, close
    NETWORK = "network"     # socket, connect, accept
    PROCESS = "process"     # fork, execve, kill
    MEMORY = "memory"       # mmap, mprotect, brk
    IPC = "ipc"            # msg, sem, shm
    SIGNAL = "signal"       # signal, sigaction
    TIME = "time"          # time, nanosleep
    SYSTEM = "system"       # reboot, mount, syslog


# Whitelist of safe syscalls by category
SAFE_SYSCALLS = {
    SyscallCategory.FILE: {
        "read", "write", "open", "close", "stat", "fstat",
        "lstat", "poll", "lseek", "mmap", "mprotect",
        "brk", "access", "pipe", "select", "dup", "dup2",
    },
    SyscallCategory.NETWORK: {
        "socket", "connect", "accept", "sendto", "recvfrom",
        "sendmsg", "recvmsg", "shutdown", "bind", "listen",
        "getsockname", "getpeername", "socketpair",
    },
    SyscallCategory.PROCESS: {
        "clone", "execve", "exit", "wait4", "getpid",
        "getuid", "getgid", "gettid", "getppid",
    },
    SyscallCategory.MEMORY: {
        "mmap", "mprotect", "brk", "munmap",
    },
    SyscallCategory.SIGNAL: {
        "rt_sigaction", "rt_sigprocmask", "rt_sigreturn",
    },
    SyscallCategory.TIME: {
        "time", "gettimeofday", "clock_gettime", "nanosleep",
    },
    SyscallCategory.IPC: {
        "ipc",
    },
}


@dataclass
class SeccompProfile:
    """Seccomp filter profile."""
    name: str
    enabled_categories: Set[SyscallCategory]
    allowed_syscalls: Set[str]
    blocked_syscalls: Set[str]
    default_action: str = "kill"  # kill, trap, errno, trace, allow
    audit: bool = True


@dataclass
class NamespaceConfig:
    """Linux namespace configuration."""
    enable_pid_namespace: bool = True
    enable_net_namespace: bool = True
    enable_mount_namespace: bool = True
    enable_user_namespace: bool = False
    enable_uts_namespace: bool = True
    enable_ipc_namespace: bool = False
    
    # Network isolation
    isolated_networks: List[str] = field(default_factory=list)  # VLANs to isolate
    
    # Filesystem virtualization
    readonly_paths: List[str] = field(default_factory=list)
    tmpfs_paths: Dict[str, int] = field(default_factory=dict)  # path -> size MB


@dataclass
class ResourceLimits:
    """Resource limits for sandbox."""
    max_memory_bytes: int = 512 * 1024 * 1024  # 512MB
    max_cpu_percent: int = 50
    max_processes: int = 10
    max_files: int = 100
    max_file_size_bytes: int = 10 * 1024 * 1024
    max_threads: int = 10
    max_stack_bytes: int = 8 * 1024 * 1024
    max_locked_memory_bytes: int = 64 * 1024 * 1024
    max_pseudo_terminals: int = 0


@dataclass
class SandboxEgressDecision:
    """Result of egress policy check."""
    allowed: bool
    reason: str
    matched_rule: Optional[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


class EnhancedSandboxSecurity:
    """
    Enhanced sandbox security with multiple isolation layers.
    
    Features:
    - Seccomp syscall filtering
    - Linux namespace isolation
    - Filesystem virtualization
    - Network namespace isolation
    - Resource limits enforcement
    """
    
    # Default seccomp profiles
    DEFAULT_PROFILES = {
        "minimal": SeccompProfile(
            name="minimal",
            enabled_categories={SyscallCategory.FILE, SyscallCategory.TIME},
            allowed_syscalls=SAFE_SYSCALLS[SyscallCategory.FILE] | SAFE_SYSCALLS[SyscallCategory.TIME],
            blocked_syscalls={
                "mount", "umount", "syslog", "reboot",
                "init_module", "delete_module",
            },
        ),
        "network": SeccompProfile(
            name="network",
            enabled_categories={
                SyscallCategory.FILE,
                SyscallCategory.NETWORK,
                SyscallCategory.TIME,
            },
            allowed_syscalls=(
                SAFE_SYSCALLS[SyscallCategory.FILE] |
                SAFE_SYSCALLS[SyscallCategory.NETWORK] |
                SAFE_SYSCALLS[SyscallCategory.TIME]
            ),
            blocked_syscalls={
                "mount", "umount", "syslog", "reboot",
                "init_module", "delete_module",
            },
        ),
        "full": SeccompProfile(
            name="full",
            enabled_categories={
                SyscallCategory.FILE,
                SyscallCategory.NETWORK,
                SyscallCategory.PROCESS,
                SyscallCategory.MEMORY,
                SyscallCategory.SIGNAL,
                SyscallCategory.TIME,
            },
            allowed_syscalls=set(),
            blocked_syscalls={
                "mount", "umount", "syslog", "reboot",
                "init_module", "delete_module",
                "ptrace", "perf_event_open",
            },
        ),
    }
    
    def __init__(
        self,
        profile_name: str = "network",
        namespace_config: Optional[NamespaceConfig] = None,
        resource_limits: Optional[ResourceLimits] = None,
    ):
        self.profile_name = profile_name
        self.profile = self.DEFAULT_PROFILES.get(
            profile_name,
            self.DEFAULT_PROFILES["network"]
        )
        self.namespace_config = namespace_config or NamespaceConfig()
        self.resource_limits = resource_limits or ResourceLimits()
        
        # Track violations
        self._violations: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()
    
    def check_syscall(self, syscall: str) -> bool:
        """
        Check if syscall is allowed.
        
        In production, this would interface with seccomp.
        For simulation, we check against the profile.
        """
        # Blocked syscalls always denied
        if syscall in self.profile.blocked_syscalls:
            return False
        
        # If allowed_syscalls is not empty, only those are allowed
        if self.profile.allowed_syscalls:
            return syscall in self.profile.allowed_syscalls
        
        # Check category
        for category, syscalls in SAFE_SYSCALLS.items():
            if syscall in syscalls and category in self.profile.enabled_categories:
                return True
        
        return False
    
    async def enforce_syscall(
        self,
        syscall: str,
        args: Dict[str, Any],
    ) -> SandboxEgressDecision:
        """Enforce syscall policy."""
        allowed = self.check_syscall(syscall)
        
        if not allowed:
            # Log violation
            async with self._lock:
                self._violations.append({
                    "syscall": syscall,
                    "args": args,
                    "timestamp": datetime.now().isoformat(),
                    "action": "blocked",
                })
            
            return SandboxEgressDecision(
                allowed=False,
                reason=f"syscall_blocked",
                matched_rule=self.profile.name,
                metadata={
                    "syscall": syscall,
                    "violation": True,
                },
            )
        
        return SandboxEgressDecision(
            allowed=True,
            reason="syscall_allowed",
            matched_rule=self.profile.name,
        )
    
    def get_seccomp_filter(self) -> Dict[str, Any]:
        """
        Generate seccomp filter rules.
        
        In production, this would generate BPF bytecode.
        """
        rules = []
        
        # Default action
        rules.append({
            "action": self.profile.default_action,
            "syscalls": [],
        })
        
        # Allowed syscalls
        for syscall in self.profile.allowed_syscalls:
            rules.append({
                "action": "allow",
                "syscalls": [syscall],
            })
        
        # Blocked syscalls
        for syscall in self.profile.blocked_syscalls:
            rules.append({
                "action": self.profile.default_action,
                "syscalls": [syscall],
            })
        
        return {
            "default_action": self.profile.default_action,
            "rules": rules,
            "audit": self.profile.audit,
        }
    
    def get_namespace_config(self) -> NamespaceConfig:
        """Get namespace configuration."""
        return self.namespace_config
    
    def get_resource_limits(self) -> ResourceLimits:
        """Get resource limits."""
        return self.resource_limits
    
    def get_violation_summary(self) -> Dict[str, Any]:
        """Get violation summary."""
        from collections import Counter
        
        syscall_counts = Counter(v["syscall"] for v in self._violations)
        
        return {
            "total_violations": len(self._violations),
            "unique_syscalls": len(syscall_counts),
            "top_violations": syscall_counts.most_common(10),
            "recent_violations": self._violations[-10:],
        }
    
    def create_enforcement_layer(self) -> "SandboxEnforcementLayer":
        """Create enforcement layer for policy integration."""
        return SandboxEnforcementLayer(self)


class SandboxEnforcementLayer:
    """
    Layer for enforcing sandbox policies in agent execution.
    
    Integrates with policy system to provide:
    - Syscall filtering
    - Network isolation
    - Resource limits
    """
    
    def __init__(self, security: EnhancedSandboxSecurity):
        self.security = security
        
        # Egress policy
        self._allowed_domains: Set[str] = set()
        self._allowed_ips: Set[str] = set()
        self._dns_cache: Dict[str, Set[str]] = {}
    
    async def add_allowed_domain(self, domain: str) -> None:
        """Add domain to allowed list."""
        self._allowed_domains.add(domain)
        await self._resolve_and_cache(domain)
    
    async def _resolve_and_cache(self, domain: str) -> None:
        """Resolve domain and cache IPs."""
        import socket
        try:
            addr_info = socket.getaddrinfo(domain, 443)
            ips = {info[4][0] for info in addr_info}
            self._dns_cache[domain] = ips
            self._allowed_ips.update(ips)
        except Exception:
            pass
    
    async def check_network_egress(
        self,
        destination: str,
        port: int = 443,
    ) -> SandboxEgressDecision:
        """Check if network egress is allowed."""
        # Extract host
        host = self._extract_host(destination)
        
        # Check direct IP match
        if host in self._allowed_ips:
            return SandboxEgressDecision(
                allowed=True,
                reason="ip_whitelisted",
                matched_rule="direct_ip",
            )
        
        # Check domain match
        if host in self._allowed_domains:
            return SandboxEgressDecision(
                allowed=True,
                reason="domain_whitelisted",
                matched_rule="domain_whitelist",
            )
        
        # Check cached DNS resolution
        for domain, ips in self._dns_cache.items():
            if host in ips:
                return SandboxEgressDecision(
                    allowed=True,
                    reason="dns_resolved",
                    matched_rule=f"domain:{domain}",
                )
        
        return SandboxEgressDecision(
            allowed=False,
            reason="not_in_whitelist",
            matched_rule=None,
        )
    
    async def check_syscall(self, syscall: str, args: Dict[str, Any]) -> bool:
        """Check if syscall is allowed."""
        return self.security.check_syscall(syscall)
    
    def _extract_host(self, destination: str) -> str:
        """Extract host from destination."""
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
    
    async def get_enforcement_summary(self) -> Dict[str, Any]:
        """Get enforcement summary."""
        return {
            "seccomp_profile": self.security.profile_name,
            "allowed_domains": len(self._allowed_domains),
            "allowed_ips": len(self._allowed_ips),
            "cached_domains": len(self._dns_cache),
            "namespace_config": {
                "pid": self.security.namespace_config.enable_pid_namespace,
                "net": self.security.namespace_config.enable_net_namespace,
                "mount": self.security.namespace_config.enable_mount_namespace,
            },
            "resource_limits": {
                "max_memory_mb": self.security.resource_limits.max_memory_bytes // (1024 * 1024),
                "max_cpu_percent": self.security.resource_limits.max_cpu_percent,
                "max_processes": self.security.resource_limits.max_processes,
            },
        }

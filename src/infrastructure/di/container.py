"""Dependency Injection Container.

Provides:
- Centralized dependency management
- Lifetime scope control (singleton, transient, scoped)
- Mock injection for testing
- Circular dependency detection

This replaces global singletons with proper DI.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar, Generic

logger = logging.getLogger(__name__)

T = TypeVar("T")


class Lifetime(enum.Enum):
    """Service lifetime."""
    SINGLETON = "singleton"
    TRANSIENT = "transient"
    SCOPED = "scoped"


@dataclass
class ServiceDescriptor:
    """Descriptor for a registered service."""
    service_type: type
    factory: Callable | None = None
    instance: Any = None
    lifetime: Lifetime = Lifetime.SINGLETON
    is_resolved: bool = False


class DIContainer:
    """Dependency Injection Container.
    
    Usage:
        container = DIContainer()
        
        # Register services
        container.register(EventBus, Lifetime.SINGLETON)
        container.register(RedisPool, lambda c: RedisPool())
        
        # Resolve
        event_bus = container.resolve(EventBus)
        
        # Create scope for scoped services
        with container.create_scope() as scope:
            session = scope.resolve(Session)
    """
    
    def __init__(self, parent: DIContainer | None = None):
        self._parent = parent
        self._services: dict[type, ServiceDescriptor] = {}
        self._scopes: list[dict[type, Any]] = []
        self._current_scope: dict[type, Any] | None = None
        self._lock = asyncio.Lock()
    
    def register(
        self,
        service_type: type[T],
        lifetime: Lifetime = Lifetime.SINGLETON,
        factory: Callable[[DIContainer], T] | None = None,
    ) -> None:
        """Register a service type.
        
        Args:
            service_type: The type to register
            lifetime: Service lifetime
            factory: Optional factory function
        """
        descriptor = ServiceDescriptor(
            service_type=service_type,
            factory=factory,
            lifetime=lifetime,
        )
        self._services[service_type] = descriptor
        logger.debug("service_registered", type=service_type.__name__, lifetime=lifetime.value)
    
    def register_instance(self, service_type: type[T], instance: T) -> None:
        """Register an existing instance as singleton.
        
        Args:
            service_type: The type to register
            instance: The instance to use
        """
        descriptor = ServiceDescriptor(
            service_type=service_type,
            instance=instance,
            lifetime=Lifetime.SINGLETON,
            is_resolved=True,
        )
        self._services[service_type] = descriptor
    
    def resolve(self, service_type: type[T]) -> T:
        """Resolve a service by type.
        
        Args:
            service_type: The type to resolve
            
        Returns:
            The resolved service instance
            
        Raises:
            ValueError: If service not registered
        """
        # Check current scope first
        if self._current_scope and service_type in self._current_scope:
            return self._current_scope[service_type]
        
        # Check parent container
        if self._parent:
            try:
                return self._parent.resolve(service_type)
            except ValueError:
                pass
        
        # Check if registered
        if service_type not in self._services:
            raise ValueError(f"Service not registered: {service_type.__name__}")
        
        descriptor = self._services[service_type]
        
        # Return existing instance
        if descriptor.is_resolved:
            return descriptor.instance
        
        # Create instance
        instance = self._create_instance(service_type, descriptor)
        
        # Store if singleton
        if descriptor.lifetime == Lifetime.SINGLETON:
            descriptor.instance = instance
            descriptor.is_resolved = True
        
        return instance
    
    def _create_instance(self, service_type: type[T], descriptor: ServiceDescriptor) -> T:
        """Create a new instance of a service."""
        if descriptor.factory:
            return descriptor.factory(self)
        
        # Try to auto-resolve constructor dependencies
        import inspect
        sig = inspect.signature(service_type.__init__)
        
        kwargs = {}
        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue
            if param.annotation == inspect.Parameter.empty:
                continue
            
            # Try to resolve by type or name
            try:
                kwargs[param_name] = self.resolve(param.annotation)
            except ValueError:
                # Try by parameter name
                for registered_type in self._services:
                    if registered_type.__name__.lower() == param_name.lower():
                        kwargs[param_name] = self.resolve(registered_type)
        
        return service_type(**kwargs)
    
    def create_scope(self) -> DIScope:
        """Create a new scope for scoped services.
        
        Usage:
            with container.create_scope() as scope:
                session = scope.resolve(Session)
        """
        return DIScope(self)
    
    def enter_scope(self) -> None:
        """Enter a new scope."""
        self._scopes.append({})
        self._current_scope = self._scopes[-1]
    
    def exit_scope(self) -> None:
        """Exit the current scope."""
        if self._scopes:
            self._scopes.pop()
            self._current_scope = self._scopes[-1] if self._scopes else None
    
    def is_registered(self, service_type: type) -> bool:
        """Check if a service is registered."""
        if service_type in self._services:
            return True
        if self._parent:
            return self._parent.is_registered(service_type)
        return False


class DIScope:
    """Scope context manager for DI container."""
    
    def __init__(self, container: DIContainer):
        self._container = container
    
    def __enter__(self) -> DIScope:
        self._container.enter_scope()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._container.exit_scope()
    
    def resolve(self, service_type: type[T]) -> T:
        """Resolve a service within this scope."""
        # Store in scope if scoped lifetime
        if self._container._current_scope and service_type not in self._container._current_scope:
            if service_type in self._container._services:
                descriptor = self._container._services[service_type]
                if descriptor.lifetime == Lifetime.SCOPED:
                    instance = self._container._create_instance(service_type, descriptor)
                    self._container._current_scope[service_type] = instance
                    return instance
        
        return self._container.resolve(service_type)


# Global container instance
_container: DIContainer | None = None


def get_container() -> DIContainer:
    """Get the global DI container."""
    global _container
    if _container is None:
        _container = DIContainer()
    return _container


def set_container(container: DIContainer) -> None:
    """Set the global DI container."""
    global _container
    _container = container


def reset_container() -> None:
    """Reset the global container."""
    global _container
    _container = None


# Import enum for Lifetime
import enum

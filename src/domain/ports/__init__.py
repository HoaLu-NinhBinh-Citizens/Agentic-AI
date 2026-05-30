"""Domain ports - abstract interfaces for external dependencies.

This package contains abstract interfaces (ports) that define contracts
between the domain layer and infrastructure/implementation details.

The domain layer should only depend on these abstract interfaces, not
on concrete implementations. This follows the Dependency Inversion Principle.

Ports:
    - hardware_security: HSM/crypto operations
"""

from src.domain.ports.hardware_security import HardwareSecurityModule

__all__ = ["HardwareSecurityModule"]

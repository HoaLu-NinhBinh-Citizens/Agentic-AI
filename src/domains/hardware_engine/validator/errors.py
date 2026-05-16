"""Hardware error types."""


class HardwareError(Exception):
    """Base exception for hardware-related errors."""

    def __init__(self, message: str, rule_id: str = "", peripheral: str = ""):
        super().__init__(message)
        self.rule_id = rule_id
        self.peripheral = peripheral


class PinConflictError(HardwareError):
    """Raised when a pin is already reserved."""

    def __init__(self, pin: str, reserved_by: str, requested_by: str = ""):
        msg = f"Pin conflict: {pin} is already reserved by '{reserved_by}'"
        if requested_by:
            msg += f" (requested by {requested_by})"
        super().__init__(msg, rule_id="PIN_CONFLICT", peripheral=requested_by)
        self.pin = pin
        self.reserved_by = reserved_by


class ClockError(HardwareError):
    """Raised for clock configuration errors."""

    def __init__(self, message: str, peripheral: str = "", domain: str = ""):
        super().__init__(message, rule_id="CLOCK_ERROR", peripheral=peripheral)
        self.domain = domain


class InterruptError(HardwareError):
    """Raised for interrupt allocation errors."""

    def __init__(self, message: str, peripheral: str = "", irq_line: int = -1):
        super().__init__(message, rule_id="INTERRUPT_ERROR", peripheral=peripheral)
        self.irq_line = irq_line


class RegisterError(HardwareError):
    """Raised for register access/configuration errors."""

    def __init__(self, message: str, peripheral: str = "", register: str = ""):
        super().__init__(message, rule_id="REGISTER_ERROR", peripheral=peripheral)
        self.register = register


class AllocationError(HardwareError):
    """Raised when hardware resource allocation fails."""

    def __init__(self, message: str, peripheral: str = ""):
        super().__init__(message, rule_id="ALLOCATION_ERROR", peripheral=peripheral)


class ValidationError(HardwareError):
    """Raised when hardware validation fails."""

    def __init__(self, message: str, rule_id: str = ""):
        super().__init__(message, rule_id=rule_id)

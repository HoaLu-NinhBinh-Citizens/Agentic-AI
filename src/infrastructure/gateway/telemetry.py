"""Gateway telemetry module."""

from typing import Any


class TelemetryGateway:
    """Telemetry for gateway operations."""
    
    async def record(self, metric: str, value: Any) -> None:
        """Record telemetry."""
        pass

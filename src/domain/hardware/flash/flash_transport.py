"""Flash Transport - Probe transport capabilities and adaptive strategy.

Phase 6.2: Implements probe transport capabilities for:
- Probe capability detection
- Adaptive flash strategy selection
- Chunk size optimization
- Compression and verification strategies
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ProbeType(Enum):
    """Debug probe types."""
    JLINK = "jlink"
    STLINK = "stlink"
    CMSIS_DAP = "cmsis_dap"
    OPENOCD = "openocd"
    QEMU = "qemu"
    PYOCD = "pyocd"


@dataclass
class FlashTransportCapabilities:
    """Capabilities of debug probe for flash operations.
    
    Determines optimal flash strategy based on probe capabilities.
    """
    
    probe_type: ProbeType
    probe_version: str = ""
    
    # Memory
    max_chunk_size: int = 4096
    min_chunk_size: int = 256
    
    # Speed
    max_write_speed_khz: int = 4000
    max_verify_speed_khz: int = 10000
    
    # Features
    supports_compression: bool = False
    supports_crc_verify: bool = True
    supports_parallel_verify: bool = False
    
    # Protocol
    supports_streaming: bool = False
    supports_resume: bool = True
    
    # Protocol-specific
    protocol_overhead_percent: float = 10.0
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "probe_type": self.probe_type.value,
            "probe_version": self.probe_version,
            "max_chunk_size": self.max_chunk_size,
            "max_write_speed_khz": self.max_write_speed_khz,
            "supports_compression": self.supports_compression,
            "supports_resume": self.supports_resume,
        }
    
    @classmethod
    def from_probe_type(
        cls,
        probe_type: ProbeType,
        probe_info: dict[str, Any] | None = None,
    ) -> FlashTransportCapabilities:
        """Create capabilities from probe type."""
        
        if probe_type == ProbeType.JLINK:
            return cls(
                probe_type=probe_type,
                probe_version=probe_info.get("version", "") if probe_info else "",
                max_chunk_size=16384,
                max_write_speed_khz=10000,
                max_verify_speed_khz=20000,
                supports_compression=True,
                supports_crc_verify=True,
                supports_parallel_verify=True,
                supports_streaming=True,
                supports_resume=True,
                protocol_overhead_percent=5.0,
            )
        
        elif probe_type == ProbeType.STLINK:
            return cls(
                probe_type=probe_type,
                max_chunk_size=6144,
                max_write_speed_khz=4000,
                max_verify_speed_khz=8000,
                supports_compression=False,
                supports_crc_verify=True,
                supports_parallel_verify=False,
                supports_streaming=False,
                supports_resume=True,
                protocol_overhead_percent=10.0,
            )
        
        elif probe_type == ProbeType.CMSIS_DAP:
            return cls(
                probe_type=probe_type,
                max_chunk_size=2048,
                max_write_speed_khz=2000,
                max_verify_speed_khz=4000,
                supports_compression=False,
                supports_crc_verify=True,
                supports_parallel_verify=False,
                supports_streaming=False,
                supports_resume=True,
                protocol_overhead_percent=15.0,
            )
        
        elif probe_type == ProbeType.OPENOCD:
            return cls(
                probe_type=probe_type,
                max_chunk_size=4096,
                max_write_speed_khz=2000,
                max_verify_speed_khz=4000,
                supports_compression=False,
                supports_crc_verify=True,
                supports_parallel_verify=False,
                supports_streaming=False,
                supports_resume=True,
                protocol_overhead_percent=20.0,
            )
        
        elif probe_type == ProbeType.QEMU:
            return cls(
                probe_type=probe_type,
                max_chunk_size=65536,
                max_write_speed_khz=100000,
                max_verify_speed_khz=100000,
                supports_compression=False,
                supports_crc_verify=True,
                supports_parallel_verify=True,
                supports_streaming=True,
                supports_resume=True,
                protocol_overhead_percent=1.0,
            )
        
        elif probe_type == ProbeType.PYOCD:
            return cls(
                probe_type=probe_type,
                max_chunk_size=8192,
                max_write_speed_khz=4000,
                max_verify_speed_khz=8000,
                supports_compression=False,
                supports_crc_verify=True,
                supports_parallel_verify=True,
                supports_streaming=False,
                supports_resume=True,
                protocol_overhead_percent=10.0,
            )
        
        # Default
        return cls(probe_type=probe_type)


@dataclass
class FlashStrategy:
    """Chosen flash strategy based on capabilities and firmware."""
    
    chunk_size: int
    use_compression: bool
    verify_method: str  # "full", "hash", "none"
    parallel_verify: bool
    resume_enabled: bool
    
    # Performance estimates
    estimated_write_time_ms: float = 0
    estimated_verify_time_ms: float = 0
    estimated_total_time_ms: float = 0
    
    # Strategy name
    strategy_name: str = "adaptive"
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "chunk_size": self.chunk_size,
            "use_compression": self.use_compression,
            "verify_method": self.verify_method,
            "parallel_verify": self.parallel_verify,
            "resume_enabled": self.resume_enabled,
            "estimated_write_time_ms": self.estimated_write_time_ms,
            "estimated_verify_time_ms": self.estimated_verify_time_ms,
            "estimated_total_time_ms": self.estimated_total_time_ms,
            "strategy_name": self.strategy_name,
        }


@dataclass
class AdaptiveFlashStrategy:
    """Selects optimal flash strategy based on probe and firmware.
    
    Balances speed, reliability, and resource usage.
    """
    
    capabilities: FlashTransportCapabilities
    
    def select_strategy(
        self,
        firmware_size: int,
        target_partition_size: int,
        session_timeout_seconds: float = 300.0,
    ) -> FlashStrategy:
        """Select optimal flash strategy.
        
        Args:
            firmware_size: Size of firmware in bytes
            target_partition_size: Size of target partition
            session_timeout_seconds: Maximum allowed flash time
        
        Returns:
            FlashStrategy optimized for this scenario
        """
        # Base chunk size - start with probe max, reduce for small files
        chunk_size = self.capabilities.max_chunk_size
        
        if firmware_size < 10000:
            chunk_size = min(chunk_size, 512)
        elif firmware_size < 100000:
            chunk_size = min(chunk_size, 2048)
        
        # Compression decision
        use_compression = (
            self.capabilities.supports_compression
            and firmware_size > 50000  # Only for larger files
        )
        
        # Verify method
        if self.capabilities.supports_crc_verify and firmware_size > 10000:
            verify_method = "hash"
        elif firmware_size > 500000:
            verify_method = "none"
        else:
            verify_method = "full"
        
        # Calculate effective speeds
        effective_write_khz = self.capabilities.max_write_speed_khz * (
            1 - self.capabilities.protocol_overhead_percent / 100
        )
        effective_verify_khz = self.capabilities.max_verify_speed_khz * (
            1 - self.capabilities.protocol_overhead_percent / 100
        )
        
        write_speed_bps = effective_write_khz * 1000 // 8
        verify_speed_bps = effective_verify_khz * 1000 // 8
        
        # Estimate times
        write_time = (firmware_size / write_speed_bps) * 1000
        verify_time = (firmware_size / verify_speed_bps) * 1000 if verify_method != "none" else 0
        
        total_time = write_time + verify_time
        
        # Check if we need resume
        resume_enabled = (
            self.capabilities.supports_resume
            and total_time > (session_timeout_seconds * 1000 * 0.7)
        )
        
        # Adjust for resume
        if resume_enabled:
            chunk_size = min(chunk_size, 2048)
        
        # Strategy naming
        strategy_name = self._get_strategy_name(
            firmware_size, 
            verify_method,
            use_compression,
            resume_enabled,
        )
        
        return FlashStrategy(
            chunk_size=chunk_size,
            use_compression=use_compression,
            verify_method=verify_method,
            parallel_verify=(
                self.capabilities.supports_parallel_verify
                and firmware_size > 100000
            ),
            resume_enabled=resume_enabled,
            estimated_write_time_ms=write_time,
            estimated_verify_time_ms=verify_time,
            estimated_total_time_ms=total_time,
            strategy_name=strategy_name,
        )
    
    def _get_strategy_name(
        self,
        firmware_size: int,
        verify_method: str,
        use_compression: bool,
        resume_enabled: bool,
    ) -> str:
        """Generate descriptive strategy name."""
        parts = []
        
        if firmware_size > 500000:
            parts.append("large")
        elif firmware_size > 100000:
            parts.append("medium")
        else:
            parts.append("small")
        
        parts.append(verify_method)
        
        if use_compression:
            parts.append("compressed")
        
        if resume_enabled:
            parts.append("resumable")
        
        return "_".join(parts)
    
    def estimate_throughput(self, strategy: FlashStrategy) -> dict[str, float]:
        """Estimate throughput for a strategy."""
        if strategy.estimated_total_time_ms > 0:
            firmware_kb = 100  # Normalize to 100KB
            time_s = strategy.estimated_total_time_ms / 1000
            return {
                "kb_per_second": firmware_kb / time_s,
                "bytes_per_ms": 100000 / strategy.estimated_total_time_ms,
            }
        return {"kb_per_second": 0, "bytes_per_ms": 0}


@dataclass
class ProbeCapabilityRegistry:
    """Registry of probe capabilities.
    
    Caches and manages probe capabilities for quick lookup.
    """
    
    _capabilities: dict[str, FlashTransportCapabilities] = field(default_factory=dict)
    
    def register(
        self,
        probe_id: str,
        capabilities: FlashTransportCapabilities,
    ) -> None:
        """Register probe capabilities."""
        self._capabilities[probe_id] = capabilities
    
    def get(self, probe_id: str) -> FlashTransportCapabilities | None:
        """Get capabilities for probe."""
        return self._capabilities.get(probe_id)
    
    def unregister(self, probe_id: str) -> None:
        """Unregister probe."""
        self._capabilities.pop(probe_id, None)
    
    def list_probes(self) -> list[str]:
        """List all registered probes."""
        return list(self._capabilities.keys())

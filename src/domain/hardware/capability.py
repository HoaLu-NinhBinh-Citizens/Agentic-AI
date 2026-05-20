"""Capability model for probe/chip capability negotiation.

Phase 6.1: Defines what a probe or chip can do (SWO, ETM, dual-core, etc.)
and provides negotiation logic to determine the best debug method.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from .provenance import Provenance

if TYPE_CHECKING:
    from .extended_models import ChipDescription


# ============================================================================
# Capability Categories
# ============================================================================


class CapabilityCategory(Enum):
    """Category of capability."""

    DEBUG_INTERFACE = "debug_interface"  # SWD, JTAG, cJTAG
    TRACE = "trace"  # SWO, ETM, HTM
    MEMORY_ACCESS = "memory_access"  # Flash patch, memory map
    SECURITY = "security"  # TrustZone, secure debug
    POWER = "power"  # Power control, voltage sense
    MULTI_CORE = "multi_core"  # Multi-core debugging
    RTOS = "rtos"  # RTOS awareness
    PROGRAMMING = "programming"  # Flash programming
    VENDOR_SPECIFIC = "vendor_specific"  # Vendor-specific features


# ============================================================================
# Specific Capabilities
# ============================================================================


class DebugCapability(Enum):
    """Debug interface capabilities."""

    SWD = "swd"  # Serial Wire Debug
    JTAG = "jtag"  # JTAG interface
    CJTAG = "cjtag"  # Compact JTAG
    DORMANT = "dormant"  # Dormant state support


class TraceCapability(Enum):
    """Trace capabilities."""

    SWO = "swo"  # Serial Wire Output
    SWV = "swv"  # Serial Wire Viewer
    ETM = "etm"  # Embedded Trace Macrocell
    ITM = "itm"  # Instrumentation Trace Macrocell
    HTM = "htm"  # Historical Trace Macrocell
    PTM = "ptm"  # Program Trace Macrocell
    Embedded_Trace_Buffer = "etb"  # Embedded Trace Buffer
    Trace_Port = "trace_port"  # Trace Port Interface Unit


class SecurityCapability(Enum):
    """Security capabilities."""

    ARM_TRUSTZONE = "trustzone"  # ARM TrustZone
    SECURE_DEBUG = "secure_debug"  # Secure debug enable
    DEBUG_AUTHENTICATION = "dbg_auth"  # Debug authentication


class MultiCoreCapability(Enum):
    """Multi-core capabilities."""

    DUAL_CORE = "dual_core"
    TRIPLE_CORE = "triple_core"
    QUAD_CORE = "quad_core"
    SMP = "smp"  # Symmetric Multi-Processing
    AMP = "amp"  # Asymmetric Multi-Processing
    CROSS_TRIGGER = "cross_trigger"  # Cross trigger matrix


class MemoryCapability(Enum):
    """Memory access capabilities."""

    FLASH_PATCH = "flash_patch"
    RAM_PATCH = "ram_patch"
    READ_MODIFY_WRITE = "read_modify_write"
    MEMORY_MAP_VERIFY = "memory_map_verify"
    ECC_CHECK = "ecc_check"


class PowerCapability(Enum):
    """Power control capabilities."""

    VOLTAGE_SENSE = "voltage_sense"
    POWER_CONTROL = "power_control"
    RESET_DETECT = "reset_detect"
    LOW_POWER_DEBUG = "low_power_debug"


class RTOSCapability(Enum):
    """RTOS awareness capabilities."""

    FREE_RTOS = "freertos"
    ZEPHYR = "zephyr"
    THREADX = "threadx"
    MQX = "mqx"
    UCOS = "ucos"
    RTX = "rtx"
    GENERIC_AWARENESS = "generic_rtos"


# ============================================================================
# Capability Model
# ============================================================================


@dataclass
class Capability:
    """A single capability with metadata.

    Represents a discrete capability that can be queried and negotiated.
    """

    # Identification
    name: str
    category: CapabilityCategory
    version: str = "1.0"

    # Status
    supported: bool = True
    enabled: bool = True
    available: bool = True  # Can currently be used

    # Configuration (optional)
    config: dict[str, Any] = field(default_factory=dict)

    # Performance characteristics
    bandwidth_mbps: float = 0.0  # For trace capabilities
    latency_us: float = 0.0  # Typical latency

    # Limitations
    max_frequency_hz: int = 0
    min_frequency_hz: int = 0

    # Dependencies
    requires_capabilities: list[str] = field(default_factory=list)  # Other capability names
    conflicts_with: list[str] = field(default_factory=list)  # Mutually exclusive

    # Implementation
    implementation: str = ""  # e.g., "hardware", "software_emulation"
    vendor_implementation: str = ""  # Vendor-specific detail

    # Provenance
    provenance: Provenance | None = None

    def __post_init__(self) -> None:
        """Validate capability."""
        if not self.name:
            raise ValueError("Capability name is required")
        if self.min_frequency_hz > self.max_frequency_hz:
            raise ValueError("min_frequency_hz cannot exceed max_frequency_hz")

    def is_usable(self) -> bool:
        """Check if capability can be used."""
        return self.supported and self.enabled and self.available

    def meets_requirements(self, **config: Any) -> bool:
        """Check if capability meets requirements.

        Args:
            **config: Required configuration (e.g., frequency_hz=1000000)

        Returns:
            True if all requirements are met
        """
        if "frequency_hz" in config:
            freq = config["frequency_hz"]
            if self.max_frequency_hz > 0 and freq > self.max_frequency_hz:
                return False
            if self.min_frequency_hz > 0 and freq < self.min_frequency_hz:
                return False

        if "bandwidth_mbps" in config:
            if self.bandwidth_mbps > 0 and config["bandwidth_mbps"] > self.bandwidth_mbps:
                return False

        return True

    def conflicts_with_capability(self, other: Capability) -> bool:
        """Check if this capability conflicts with another."""
        return other.name in self.conflicts_with or self.name in other.conflicts_with

    def requires_capability(self, other: Capability) -> bool:
        """Check if this capability requires another."""
        return other.name in self.requires_capabilities

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "category": self.category.value,
            "version": self.version,
            "supported": self.supported,
            "enabled": self.enabled,
            "available": self.available,
            "bandwidth_mbps": self.bandwidth_mbps,
            "max_frequency_hz": self.max_frequency_hz,
            "config": self.config,
        }


@dataclass
class CapabilitySet:
    """A set of capabilities for an entity (probe, chip, board)."""

    entity_id: str  # Probe serial, chip part number, etc.
    entity_type: str  # "probe", "chip", "board"
    capabilities: list[Capability] = field(default_factory=list)

    # Metadata
    discovered_at: datetime = field(default_factory=datetime.now)
    last_verified: datetime | None = None
    version: str = "1.0"

    # Provenance
    provenance: Provenance | None = None

    def add_capability(self, capability: Capability) -> None:
        """Add a capability to the set."""
        # Remove existing capability with same name
        self.capabilities = [c for c in self.capabilities if c.name != capability.name]
        self.capabilities.append(capability)

    def get_capability(self, name: str) -> Capability | None:
        """Get capability by name."""
        for cap in self.capabilities:
            if cap.name == name:
                return cap
        return None

    def has_capability(self, name: str) -> bool:
        """Check if capability exists and is usable."""
        cap = self.get_capability(name)
        return cap is not None and cap.is_usable()

    def get_by_category(self, category: CapabilityCategory) -> list[Capability]:
        """Get all capabilities in a category."""
        return [c for c in self.capabilities if c.category == category]

    def get_usable_capabilities(self) -> list[Capability]:
        """Get all usable capabilities."""
        return [c for c in self.capabilities if c.is_usable()]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "capabilities": [c.to_dict() for c in self.capabilities],
            "capability_count": len(self.capabilities),
            "discovered_at": self.discovered_at.isoformat(),
            "version": self.version,
        }


# ============================================================================
# Capability Registry
# ============================================================================


@dataclass
class CapabilityNegotiationResult:
    """Result of capability negotiation between probe and chip."""

    # The selected debug method
    selected_capability: Capability | None = None
    selected_method: str = ""

    # All usable capabilities
    usable_capabilities: list[Capability] = field(default_factory=list)

    # Warnings and conflicts
    warnings: list[str] = field(default_factory=list)
    conflicts: list[tuple[str, str]] = field(default_factory=list)  # (cap1, cap2)

    # Fallback decisions
    used_fallback: bool = False
    fallback_reason: str = ""

    # Negotiation metadata
    probe_capabilities: CapabilitySet | None = None
    chip_capabilities: CapabilitySet | None = None

    @property
    def success(self) -> bool:
        """Check if negotiation was successful."""
        return self.selected_capability is not None and self.selected_capability.is_usable()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "selected_method": self.selected_method,
            "selected_capability": self.selected_capability.to_dict() if self.selected_capability else None,
            "usable_count": len(self.usable_capabilities),
            "warnings": self.warnings,
            "conflicts": [f"{c[0]} vs {c[1]}" for c in self.conflicts],
            "used_fallback": self.used_fallback,
        }


class CapabilityRegistry:
    """Registry for managing capabilities of all entities.

    Stores capabilities for probes, chips, and boards, and provides
    negotiation logic to determine the best debug method.
    """

    def __init__(self) -> None:
        """Initialize registry."""
        self._probe_capabilities: dict[str, CapabilitySet] = {}
        self._chip_capabilities: dict[str, CapabilitySet] = {}
        self._board_capabilities: dict[str, CapabilitySet] = {}
        self._default_capabilities: dict[str, list[Capability]] = self._get_default_capabilities()

    @staticmethod
    def _get_default_capabilities() -> dict[str, list[Capability]]:
        """Get default capabilities for common entities."""
        return {
            "stlink_v2": [
                Capability(name="swd", category=CapabilityCategory.DEBUG_INTERFACE, supported=True, max_frequency_hz=4_000_000),
                Capability(name="jtag", category=CapabilityCategory.DEBUG_INTERFACE, supported=False),
                Capability(name="swo", category=CapabilityCategory.TRACE, supported=False),
                Capability(name="voltage_sense", category=CapabilityCategory.POWER, supported=True),
                Capability(name="reset_detect", category=CapabilityCategory.POWER, supported=True),
                Capability(name="flash_patch", category=CapabilityCategory.MEMORY_ACCESS, supported=True),
            ],
            "stlink_v3": [
                Capability(name="swd", category=CapabilityCategory.DEBUG_INTERFACE, supported=True, max_frequency_hz=24_000_000),
                Capability(name="jtag", category=CapabilityCategory.DEBUG_INTERFACE, supported=True, max_frequency_hz=24_000_000),
                Capability(name="swo", category=CapabilityCategory.TRACE, supported=True, bandwidth_mbps=10.0),
                Capability(name="trace_port", category=CapabilityCategory.TRACE, supported=True, bandwidth_mbps=80.0),
                Capability(name="voltage_sense", category=CapabilityCategory.POWER, supported=True),
                Capability(name="power_control", category=CapabilityCategory.POWER, supported=True),
                Capability(name="flash_patch", category=CapabilityCategory.MEMORY_ACCESS, supported=True),
                Capability(name="dual_core", category=CapabilityCategory.MULTI_CORE, supported=False),
            ],
            "jlink": [
                Capability(name="swd", category=CapabilityCategory.DEBUG_INTERFACE, supported=True, max_frequency_hz=50_000_000),
                Capability(name="jtag", category=CapabilityCategory.DEBUG_INTERFACE, supported=True, max_frequency_hz=50_000_000),
                Capability(name="cjtag", category=CapabilityCategory.DEBUG_INTERFACE, supported=True),
                Capability(name="swo", category=CapabilityCategory.TRACE, supported=True, bandwidth_mbps=40.0),
                Capability(name="etm", category=CapabilityCategory.TRACE, supported=True),
                Capability(name="itm", category=CapabilityCategory.TRACE, supported=True),
                Capability(name="voltage_sense", category=CapabilityCategory.POWER, supported=True),
                Capability(name="power_control", category=CapabilityCategory.POWER, supported=True),
                Capability(name="flash_patch", category=CapabilityCategory.MEMORY_ACCESS, supported=True),
                Capability(name="secure_debug", category=CapabilityCategory.SECURITY, supported=True),
                Capability(name="dual_core", category=CapabilityCategory.MULTI_CORE, supported=True),
                Capability(name="cross_trigger", category=CapabilityCategory.MULTI_CORE, supported=True),
            ],
            "cmsis_dap": [
                Capability(name="swd", category=CapabilityCategory.DEBUG_INTERFACE, supported=True, max_frequency_hz=10_000_000),
                Capability(name="jtag", category=CapabilityCategory.DEBUG_INTERFACE, supported=True, max_frequency_hz=10_000_000),
                Capability(name="swo", category=CapabilityCategory.TRACE, supported=False),
                Capability(name="voltage_sense", category=CapabilityCategory.POWER, supported=True),
                Capability(name="flash_patch", category=CapabilityCategory.MEMORY_ACCESS, supported=True),
            ],
        }

    # -------------------------------------------------------------------------
    # Registration
    # -------------------------------------------------------------------------

    def register_probe_capabilities(self, probe_serial: str, capabilities: CapabilitySet) -> None:
        """Register capabilities for a probe.

        Args:
            probe_serial: Probe serial number or identifier
            capabilities: Capability set for the probe
        """
        capabilities.entity_id = probe_serial
        capabilities.entity_type = "probe"
        self._probe_capabilities[probe_serial] = capabilities

    def register_chip_capabilities(self, part_number: str, capabilities: CapabilitySet) -> None:
        """Register capabilities for a chip.

        Args:
            part_number: Chip part number
            capabilities: Capability set for the chip
        """
        capabilities.entity_id = part_number
        capabilities.entity_type = "chip"
        self._chip_capabilities[part_number] = capabilities

    def register_board_capabilities(self, board_id: str, capabilities: CapabilitySet) -> None:
        """Register capabilities for a board.

        Args:
            board_id: Board identifier
            capabilities: Capability set for the board
        """
        capabilities.entity_id = board_id
        capabilities.entity_type = "board"
        self._board_capabilities[board_id] = capabilities

    def register_defaults_for_probe_type(self, probe_serial: str, probe_type: str) -> None:
        """Register default capabilities for a probe type.

        Args:
            probe_serial: Probe serial number
            probe_type: Type of probe (e.g., "jlink", "stlink_v3")
        """
        if probe_type not in self._default_capabilities:
            return

        cap_set = CapabilitySet(
            entity_id=probe_serial,
            entity_type="probe",
            capabilities=[cap.copy() for cap in self._default_capabilities[probe_type]],
        )
        self.register_probe_capabilities(probe_serial, cap_set)

    def get_probe_capabilities(self, probe_serial: str) -> CapabilitySet | None:
        """Get capabilities for a probe."""
        return self._probe_capabilities.get(probe_serial)

    def get_chip_capabilities(self, part_number: str) -> CapabilitySet | None:
        """Get capabilities for a chip."""
        return self._chip_capabilities.get(part_number)

    def get_board_capabilities(self, board_id: str) -> CapabilitySet | None:
        """Get capabilities for a board."""
        return self._board_capabilities.get(board_id)

    def clear_probe_capabilities(self, probe_serial: str) -> None:
        """Clear capabilities for a probe."""
        if probe_serial in self._probe_capabilities:
            del self._probe_capabilities[probe_serial]

    # -------------------------------------------------------------------------
    # Capability Negotiation
    # -------------------------------------------------------------------------

    def negotiate(
        self,
        probe_serial: str,
        chip_part_number: str,
        preferred_method: str | None = None,
    ) -> CapabilityNegotiationResult:
        """Negotiate best debug method between probe and chip.

        The negotiation process:
        1. Get capabilities from both probe and chip
        2. Find intersection of usable capabilities
        3. Check for conflicts
        4. Select best method based on priority and preferences
        5. Return result with warnings for any limitations

        Args:
            probe_serial: Probe serial number
            chip_part_number: Chip part number
            preferred_method: Preferred debug method (e.g., "swo", "etm")

        Returns:
            NegotiationResult with selected capability and metadata
        """
        result = CapabilityNegotiationResult()

        probe_caps = self.get_probe_capabilities(probe_serial)
        chip_caps = self.get_chip_capabilities(chip_part_number)

        result.probe_capabilities = probe_caps
        result.chip_capabilities = chip_caps

        if probe_caps is None:
            result.warnings.append(f"Probe {probe_serial} capabilities not registered")
            result.used_fallback = True
            result.fallback_reason = "probe_not_found"
            return result

        if chip_caps is None:
            result.warnings.append(f"Chip {chip_part_number} capabilities not registered")
            result.used_fallback = True
            result.fallback_reason = "chip_not_found"
            return result

        # Find intersection of usable capabilities
        probe_usable = probe_caps.get_usable_capabilities()
        chip_usable = chip_caps.get_usable_capabilities()

        usable_names = {c.name for c in probe_usable} & {c.name for c in chip_usable}
        result.usable_capabilities = [c for c in probe_usable if c.name in usable_names]

        # Check for conflicts
        for cap1 in result.usable_capabilities:
            for cap2 in result.usable_capabilities:
                if cap1.conflicts_with_capability(cap2) and cap1.name != cap2.name:
                    result.conflicts.append((cap1.name, cap2.name))

        if not result.usable_capabilities:
            result.warnings.append("No common capabilities between probe and chip")
            result.used_fallback = True
            result.fallback_reason = "no_common_capabilities"
            return result

        # Select best capability
        if preferred_method:
            # Try to use preferred method first
            preferred = next((c for c in result.usable_capabilities if c.name == preferred_method), None)
            if preferred:
                result.selected_capability = preferred
                result.selected_method = preferred_method
                return result
            else:
                result.warnings.append(f"Preferred method '{preferred_method}' not available")

        # Default priority: SWD > JTAG > SWO > ETM
        priority_order = ["swd", "jtag", "cjtag", "swo", "etm", "itm", "trace_port"]

        for method in priority_order:
            cap = next((c for c in result.usable_capabilities if c.name == method), None)
            if cap:
                result.selected_capability = cap
                result.selected_method = method
                break

        if not result.selected_capability:
            # Just use the first usable capability
            result.selected_capability = result.usable_capabilities[0]
            result.selected_method = result.selected_capability.name

        return result

    def get_debug_methods(self, probe_serial: str) -> list[str]:
        """Get available debug methods for a probe.

        Args:
            probe_serial: Probe serial number

        Returns:
            List of available debug method names
        """
        caps = self.get_probe_capabilities(probe_serial)
        if caps is None:
            return []

        debug_caps = caps.get_by_category(CapabilityCategory.DEBUG_INTERFACE)
        return [c.name for c in debug_caps if c.is_usable()]

    def get_trace_capabilities(self, probe_serial: str) -> list[str]:
        """Get trace capabilities for a probe.

        Args:
            probe_serial: Probe serial number

        Returns:
            List of available trace capability names
        """
        caps = self.get_probe_capabilities(probe_serial)
        if caps is None:
            return []

        trace_caps = caps.get_by_category(CapabilityCategory.TRACE)
        return [c.name for c in trace_caps if c.is_usable()]

    def supports_multi_core(self, probe_serial: str) -> bool:
        """Check if probe supports multi-core debugging.

        Args:
            probe_serial: Probe serial number

        Returns:
            True if probe supports multi-core
        """
        caps = self.get_probe_capabilities(probe_serial)
        if caps is None:
            return False

        multi_core_caps = caps.get_by_category(CapabilityCategory.MULTI_CORE)
        return any(c.is_usable() for c in multi_core_caps)

    def to_dict(self) -> dict[str, Any]:
        """Convert registry to dictionary."""
        return {
            "probe_count": len(self._probe_capabilities),
            "chip_count": len(self._chip_capabilities),
            "board_count": len(self._board_capabilities),
            "default_probe_types": list(self._default_capabilities.keys()),
        }


# ============================================================================
# Standard Capability Builders
# ============================================================================


def create_stm32f4_capabilities(part_number: str = "STM32F407VG") -> CapabilitySet:
    """Create standard capabilities for STM32F4 series."""
    return CapabilitySet(
        entity_id=part_number,
        entity_type="chip",
        capabilities=[
            Capability(name="swd", category=CapabilityCategory.DEBUG_INTERFACE, supported=True, max_frequency_hz=10_000_000),
            Capability(name="jtag", category=CapabilityCategory.DEBUG_INTERFACE, supported=True, max_frequency_hz=10_000_000),
            Capability(name="swo", category=CapabilityCategory.TRACE, supported=True, bandwidth_mbps=10.0, requires_capabilities=["swd"]),
            Capability(name="itm", category=CapabilityCategory.TRACE, supported=True),
            Capability(name="etm", category=CapabilityCategory.TRACE, supported=False),  # Not on F4
            Capability(name="trustzone", category=CapabilityCategory.SECURITY, supported=False),  # M4 has no TZ
            Capability(name="flash_patch", category=CapabilityCategory.MEMORY_ACCESS, supported=True),
            Capability(name="dual_core", category=CapabilityCategory.MULTI_CORE, supported=False),
            Capability(name="freertos", category=CapabilityCategory.RTOS, supported=True),
        ],
    )


def create_stm32h7_capabilities(part_number: str = "STM32H743VI") -> CapabilitySet:
    """Create standard capabilities for STM32H7 series."""
    return CapabilitySet(
        entity_id=part_number,
        entity_type="chip",
        capabilities=[
            Capability(name="swd", category=CapabilityCategory.DEBUG_INTERFACE, supported=True, max_frequency_hz=10_000_000),
            Capability(name="jtag", category=CapabilityCategory.DEBUG_INTERFACE, supported=True, max_frequency_hz=10_000_000),
            Capability(name="swo", category=CapabilityCategory.TRACE, supported=True, bandwidth_mbps=20.0),
            Capability(name="etm", category=CapabilityCategory.TRACE, supported=True),
            Capability(name="itm", category=CapabilityCategory.TRACE, supported=True),
            Capability(name="trace_port", category=CapabilityCategory.TRACE, supported=True, bandwidth_mbps=80.0),
            Capability(name="trustzone", category=CapabilityCategory.SECURITY, supported=True),
            Capability(name="secure_debug", category=CapabilityCategory.SECURITY, supported=True),
            Capability(name="flash_patch", category=CapabilityCategory.MEMORY_ACCESS, supported=True),
            Capability(name="dual_core", category=CapabilityCategory.MULTI_CORE, supported=False),  # Some H7 have dual-core
            Capability(name="cross_trigger", category=CapabilityCategory.MULTI_CORE, supported=True),
            Capability(name="freertos", category=CapabilityCategory.RTOS, supported=True),
        ],
    )


def create_esp32_capabilities(part_number: str = "ESP32") -> CapabilitySet:
    """Create standard capabilities for ESP32 series."""
    return CapabilitySet(
        entity_id=part_number,
        entity_type="chip",
        capabilities=[
            Capability(name="jtag", category=CapabilityCategory.DEBUG_INTERFACE, supported=True, max_frequency_hz=20_000_000),
            Capability(name="dual_core", category=CapabilityCategory.MULTI_CORE, supported=True),
            Capability(name="flash_patch", category=CapabilityCategory.MEMORY_ACCESS, supported=True),
            Capability(name="voltage_sense", category=CapabilityCategory.POWER, supported=True),
            Capability(name="reset_detect", category=CapabilityCategory.POWER, supported=True),
        ],
    )


# Helper method to copy capability
def _copy_capability(cap: Capability) -> Capability:
    """Create a copy of a capability."""
    return Capability(
        name=cap.name,
        category=cap.category,
        version=cap.version,
        supported=cap.supported,
        enabled=cap.enabled,
        available=cap.available,
        config=cap.config.copy(),
        bandwidth_mbps=cap.bandwidth_mbps,
        latency_us=cap.latency_us,
        max_frequency_hz=cap.max_frequency_hz,
        min_frequency_hz=cap.min_frequency_hz,
        requires_capabilities=cap.requires_capabilities.copy(),
        conflicts_with=cap.conflicts_with.copy(),
        implementation=cap.implementation,
        vendor_implementation=cap.vendor_implementation,
        provenance=cap.provenance,
    )

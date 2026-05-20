"""AutoTargetDetector with IDCODE, VID/PID, and fallback detection.

Phase 6.1: Automatic target detection using multiple methods:
1. IDCODE (ARM JTAG/SWD IDCODE register)
2. USB VID/PID (probe identification)
3. Fallback brute-force chip list
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from .capability import CapabilityRegistry
from .chip_plugin import ChipVendorPlugin, PluginLoader
from .event import (
    DomainEvent,
    EventBus,
    TargetDiscoveredEvent,
)
from .exceptions import (
    ProbeNotFoundError,
    TargetNotFoundError,
)
from .extended_models import (
    ChipDescription,
    ChipFamily,
    ChipVendor,
    DebugProbeType,
    IDCODE,
)
from .provenance import (
    Provenance,
    ProvenanceSource,
    auto_detect_provenance,
    cache_provenance,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Detection Methods
# ============================================================================


class DetectionMethod(Enum):
    """Detection method used."""

    IDCODE = "idcode"
    VID_PID = "vid_pid"
    CHIP_ID = "chip_id"
    FALLBACK = "fallback"
    MANUAL = "manual"
    CACHE = "cache"


# ============================================================================
# Detection Result
# ============================================================================


@dataclass
class DetectionResult:
    """Result of target detection.

    Includes the detected chip information and metadata about how
    the detection was performed.
    """

    # Detection outcome
    success: bool = False
    chip_description: ChipDescription | None = None
    plugin: ChipVendorPlugin | None = None

    # Detection method
    method: DetectionMethod = DetectionMethod.MANUAL

    # Probe info
    probe_serial: str | None = None
    probe_type: DebugProbeType | None = None
    idcode: IDCODE | None = None

    # Confidence
    confidence: float = 0.0
    matched_fields: list[str] = field(default_factory=list)

    # Timing
    detection_time_ms: float = 0.0
    attempted_methods: list[DetectionMethod] = field(default_factory=list)

    # Warnings
    warnings: list[str] = field(default_factory=list)

    # Provenance
    provenance: Provenance | None = None

    def __post_init__(self) -> None:
        """Generate provenance if not set."""
        if self.provenance is None and self.success:
            self.provenance = auto_detect_provenance(
                method=self.method.value,
                source_system=self.probe_type.value if self.probe_type else "unknown",
                idcode=hex(self.idcode.full_code) if self.idcode else None,
                probe_serial=self.probe_serial,
                confidence=self.confidence,
            )

    @property
    def detection_id(self) -> str:
        """Generate unique detection ID."""
        content = f"{self.probe_serial}:{self.idcode.full_code if self.idcode else 'unknown'}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


# ============================================================================
# JEP106 Manufacturer Database
# ============================================================================


@dataclass
class JEP106Entry:
    """JEP106 manufacturer entry."""

    manufacturer_id: int
    name: str
    jep106Continuation: int = 0


class JEP106Database:
    """JEP106 JEDEC manufacturer database.

    Maps JEP106 manufacturer IDs to vendor names.
    https://www.jedec.org/standards-documents/industry-jedec-standards-jep-106
    """

    _entries: list[JEP106Entry] = [
        # Common ARM MCU vendors
        JEP106Entry(0x20, "STMicroelectronics", 0),
        JEP106Entry(0x23, "Espressif Systems", 0),
        JEP106Entry(0x28, "NXP Semiconductors", 0),
        JEP106Entry(0x29, "Intel", 0),
        JEP106Entry(0x2B, "Synopsys", 0),
        JEP106Entry(0x31, "Microchip Technology", 0),
        JEP106Entry(0x43, "Renesas Electronics", 0),
        JEP106Entry(0x4B, "Nordic Semiconductor", 0),
        JEP106Entry(0x6B, "GigaDevice", 0),
        JEP106Entry(0x7B, "Chips&Media", 0),
        JEP106Entry(0xA1, "RISC-V Foundation", 0),
    ]

    # IDCODE part number database (manufacturer -> part_id -> chip info)
    _idcode_database: dict[int, dict[int, dict[str, Any]]] = {
        # STMicroelectronics
        0x20: {
            0x0413: {  # STM32F4
                "family": ChipFamily.STM32F4,
                "part_prefix": "STM32F407",
                "core": "Cortex-M4",
            },
            0x0415: {  # STM32F1 high-density
                "family": ChipFamily.STM32F1,
                "part_prefix": "STM32F103",
                "core": "Cortex-M3",
            },
            0x0433: {  # STM32H7
                "family": ChipFamily.STM32H7,
                "part_prefix": "STM32H743",
                "core": "Cortex-M7",
            },
            0x0422: {  # STM32L4
                "family": ChipFamily.STM32L4,
                "part_prefix": "STM32L476",
                "core": "Cortex-M4",
            },
        },
    }

    # USB VID/PID database
    _usb_database: dict[tuple[int, int], dict[str, Any]] = {
        # ST-Link
        (0x0483, 0x3744): {"vendor": "STMicroelectronics", "probe_type": DebugProbeType.STLINK, "name": "ST-Link v2"},
        (0x0483, 0x3745): {"vendor": "STMicroelectronics", "probe_type": DebugProbeType.STLINK, "name": "ST-Link v2-1"},
        (0x0483, 0x3746): {"vendor": "STMicroelectronics", "probe_type": DebugProbeType.STLINK, "name": "ST-Link v3"},
        (0x0483, 0x3747): {"vendor": "STMicroelectronics", "probe_type": DebugProbeType.STLINK, "name": "ST-Link v3 (composite)"},
        (0x0483, 0x3748): {"vendor": "STMicroelectronics", "probe_type": DebugProbeType.STLINK, "name": "ST-Link v3 (isolated)"},
        # J-Link
        (0x1366, 0x0105): {"vendor": "SEGGER", "probe_type": DebugProbeType.JLINK, "name": "J-Link"},
        (0x1366, 0x0201): {"vendor": "SEGGER", "probe_type": DebugProbeType.JLINK, "name": "J-Link Plus"},
        (0x1366, 0x0301): {"vendor": "SEGGER", "probe_type": DebugProbeType.JLINK, "name": "J-Link Pro"},
        # CMSIS-DAP
        (0x0d28, 0x0204): {"vendor": "ARM", "probe_type": DebugProbeType.CMSIS_DAP, "name": "CMSIS-DAP"},
        (0x0d28, 0x0205): {"vendor": "ARM", "probe_type": DebugProbeType.CMSIS_DAP, "name": "CMSIS-DAP v2"},
        # ESP-Prog
        (0x10c4, 0xea60): {"vendor": "Espressif", "probe_type": DebugProbeType.ESP_PROG, "name": "ESP-Prog"},
    }

    @classmethod
    def get_manufacturer(cls, manufacturer_id: int) -> str | None:
        """Get manufacturer name from ID."""
        for entry in cls._entries:
            if entry.manufacturer_id == manufacturer_id:
                return entry.name
        return None

    @classmethod
    def lookup_idcode(cls, idcode: IDCODE) -> dict[str, Any] | None:
        """Lookup chip info from IDCODE.

        Args:
            idcode: IDCODE object

        Returns:
            Chip info dict or None
        """
        # Check manufacturer
        mfg = cls.get_manufacturer(idcode.manufacturer_id)
        if mfg is None:
            return None

        # Look up in manufacturer database
        mfg_db = cls._idcode_database.get(idcode.manufacturer_id, {})
        chip_info = mfg_db.get(idcode.part_id)

        if chip_info:
            chip_info = chip_info.copy()
            chip_info["manufacturer"] = mfg
            chip_info["idcode"] = idcode

        return chip_info

    @classmethod
    def lookup_usb(cls, vid: int, pid: int) -> dict[str, Any] | None:
        """Lookup probe info from USB VID/PID.

        Args:
            vid: USB Vendor ID
            pid: USB Product ID

        Returns:
            Probe info dict or None
        """
        return cls._usb_database.get((vid, pid))


# ============================================================================
# Probe Scanner Interface
# ============================================================================


class ProbeScanner(ABC):
    """Abstract interface for probe scanning."""

    @abstractmethod
    async def scan(self) -> list[dict[str, Any]]:
        """Scan for connected probes.

        Returns:
            List of probe info dicts with keys: serial, type, vid, pid
        """
        ...

    @abstractmethod
    async def read_idcode(self, probe_serial: str) -> IDCODE | None:
        """Read IDCODE from target.

        Args:
            probe_serial: Probe serial number

        Returns:
            IDCODE or None
        """
        ...

    @abstractmethod
    async def connect(self, probe_serial: str) -> bool:
        """Connect to probe.

        Args:
            probe_serial: Probe serial number

        Returns:
            True if connected
        """
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from probe."""
        ...


# ============================================================================
# Auto Target Detector
# ============================================================================


class AutoTargetDetector:
    """Automatic target detector with multiple detection methods.

    Detection methods (in order of priority):
    1. IDCODE - ARM JTAG/SWD IDCODE register
    2. VID/PID - USB Vendor/Product ID
    3. Chip ID - Vendor-specific chip ID registers
    4. Fallback - Brute force chip list

    Features:
    - Result caching (TTL configurable)
    - Multiple probe support
    - Retry with backoff
    - Event publishing on detection
    """

    def __init__(
        self,
        plugin_loader: PluginLoader,
        event_bus: EventBus | None = None,
        cache_ttl_seconds: int = 3600,
        cache: dict[str, DetectionResult] | None = None,
    ) -> None:
        """Initialize detector.

        Args:
            plugin_loader: Plugin loader for chip descriptions
            event_bus: Event bus for publishing events
            cache_ttl_seconds: Cache TTL in seconds
            cache: Optional cache dict (for testing)
        """
        self._plugin_loader = plugin_loader
        self._event_bus = event_bus
        self._cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._cache: dict[str, tuple[DetectionResult, datetime]] = {} if cache is None else {k: (v, datetime.now()) for k, v in (cache or {}).items()}
        self._scanner: ProbeScanner | None = None

    def set_scanner(self, scanner: ProbeScanner) -> None:
        """Set probe scanner.

        Args:
            scanner: Probe scanner implementation
        """
        self._scanner = scanner

    def _get_cache_key(self, probe_serial: str | None, idcode: IDCODE | None) -> str:
        """Generate cache key."""
        content = f"{probe_serial or 'any'}:{idcode.full_code if idcode else 'none'}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _get_cached(self, key: str) -> DetectionResult | None:
        """Get cached result if valid."""
        if key not in self._cache:
            return None

        result, cached_at = self._cache[key]
        if datetime.now() - cached_at > self._cache_ttl:
            del self._cache[key]
            return None

        return result

    def _set_cached(self, key: str, result: DetectionResult) -> None:
        """Cache result."""
        self._cache[key] = (result, datetime.now())

    async def detect(
        self,
        probe_serial: str | None = None,
        fallback_methods: list[DetectionMethod] | None = None,
    ) -> DetectionResult:
        """Detect target automatically.

        Args:
            probe_serial: Optional specific probe serial
            fallback_methods: Methods to try in order (default: all)

        Returns:
            DetectionResult
        """
        start_time = datetime.now()
        fallback_methods = fallback_methods or [
            DetectionMethod.IDCODE,
            DetectionMethod.VID_PID,
            DetectionMethod.CHIP_ID,
            DetectionMethod.FALLBACK,
        ]

        # Check cache first
        cache_key = self._get_cache_key(probe_serial, None)
        cached = self._get_cached(cache_key)
        if cached:
            logger.debug(f"Using cached detection result for {probe_serial}")
            cached.provenance = cache_provenance(
                cache_key=cache_key,
                original_provenance=cached.provenance,
                ttl_seconds=int(self._cache_ttl.total_seconds()),
            )
            return cached

        # Scan for probes
        if self._scanner is None:
            return DetectionResult(
                success=False,
                method=DetectionMethod.MANUAL,
                warnings=["No probe scanner configured"],
            )

        try:
            probes = await self._scanner.scan()
            if not probes:
                return DetectionResult(
                    success=False,
                    method=DetectionMethod.MANUAL,
                    warnings=["No probes found"],
                )
        except Exception as e:
            logger.error(f"Probe scan failed: {e}")
            return DetectionResult(
                success=False,
                method=DetectionMethod.MANUAL,
                warnings=[f"Probe scan error: {e}"],
            )

        # Try each detection method
        for method in fallback_methods:
            result = await self._try_detection(method, probe_serial, probes)

            if result.success:
                # Update timing
                result.detection_time_ms = (datetime.now() - start_time).total_seconds() * 1000
                result.attempted_methods = fallback_methods[:fallback_methods.index(method) + 1]

                # Cache result
                self._set_cached(cache_key, result)

                # Publish event
                await self._publish_detection_event(result)

                return result

        # All methods failed
        return DetectionResult(
            success=False,
            method=DetectionMethod.MANUAL,
            attempted_methods=fallback_methods,
            warnings=["All detection methods failed"],
            detection_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
        )

    async def _try_detection(
        self,
        method: DetectionMethod,
        probe_serial: str | None,
        probes: list[dict[str, Any]],
    ) -> DetectionResult:
        """Try a specific detection method.

        Args:
            method: Detection method
            probe_serial: Target probe serial or None for any
            probes: List of available probes

        Returns:
            DetectionResult
        """
        if method == DetectionMethod.IDCODE:
            return await self._detect_by_idcode(probe_serial, probes)
        elif method == DetectionMethod.VID_PID:
            return await self._detect_by_vid_pid(probe_serial, probes)
        elif method == DetectionMethod.CHIP_ID:
            return await self._detect_by_chip_id(probe_serial, probes)
        elif method == DetectionMethod.FALLBACK:
            return await self._detect_by_fallback(probe_serial, probes)
        else:
            return DetectionResult(success=False)

    async def _detect_by_idcode(
        self,
        probe_serial: str | None,
        probes: list[dict[str, Any]],
    ) -> DetectionResult:
        """Detect using IDCODE register."""
        for probe in probes:
            if probe_serial and probe.get("serial") != probe_serial:
                continue

            try:
                idcode = await self._scanner.read_idcode(probe["serial"])
                if idcode is None:
                    continue

                # Look up in JEP106 database
                chip_info = JEP106Database.lookup_idcode(idcode)
                if chip_info is None:
                    # Unknown manufacturer, still try to match
                    return DetectionResult(
                        success=True,
                        idcode=idcode,
                        method=DetectionMethod.IDCODE,
                        confidence=0.5,
                        probe_serial=probe.get("serial"),
                        probe_type=probe.get("type"),
                        matched_fields=["idcode"],
                        warnings=[f"Unknown manufacturer ID: 0x{idcode.manufacturer_id:03X}"],
                    )

                # Find plugin for chip family
                family = chip_info.get("family")
                plugin = self._plugin_loader.find_plugin_for_chip(family)

                if plugin:
                    try:
                        chip_desc = await plugin.get_chip_description(chip_info.get("part_prefix", "Unknown") + "xx")
                        return DetectionResult(
                            success=True,
                            chip_description=chip_desc,
                            plugin=plugin,
                            idcode=idcode,
                            method=DetectionMethod.IDCODE,
                            confidence=0.95,
                            probe_serial=probe.get("serial"),
                            probe_type=probe.get("type"),
                            matched_fields=["idcode", "family"],
                        )
                    except ValueError:
                        pass

                # Fallback to basic chip description
                chip_desc = ChipDescription(
                    part_number=chip_info.get("part_prefix", "Unknown"),
                    vendor=ChipVendor.ST if "STMicroelectronics" in chip_info.get("manufacturer", "") else ChipVendor.UNKNOWN,
                    family=family or ChipFamily.UNKNOWN,
                )

                return DetectionResult(
                    success=True,
                    chip_description=chip_desc,
                    idcode=idcode,
                    method=DetectionMethod.IDCODE,
                    confidence=0.9,
                    probe_serial=probe.get("serial"),
                    probe_type=probe.get("type"),
                    matched_fields=["idcode"],
                )

            except Exception as e:
                logger.warning(f"IDCODE read failed for {probe.get('serial')}: {e}")

        return DetectionResult(success=False)

    async def _detect_by_vid_pid(
        self,
        probe_serial: str | None,
        probes: list[dict[str, Any]],
    ) -> DetectionResult:
        """Detect using USB VID/PID."""
        for probe in probes:
            vid = probe.get("vid")
            pid = probe.get("pid")
            if vid is None or pid is None:
                continue

            info = JEP106Database.lookup_usb(vid, pid)
            if info is None:
                continue

            probe_type = info.get("probe_type", DebugProbeType.UNKNOWN if hasattr(DebugProbeType, "UNKNOWN") else DebugProbeType.STLINK)

            return DetectionResult(
                success=True,
                method=DetectionMethod.VID_PID,
                confidence=0.7,  # VID/PID is less reliable than IDCODE
                probe_serial=probe.get("serial"),
                probe_type=probe_type,
                matched_fields=["vid", "pid"],
                warnings=["VID/PID detection is less reliable than IDCODE"],
            )

        return DetectionResult(success=False)

    async def _detect_by_chip_id(
        self,
        probe_serial: str | None,
        probes: list[dict[str, Any]],
    ) -> DetectionResult:
        """Detect using vendor-specific chip ID registers.

        Most ARM chips have chip ID registers at known addresses.
        This is a fallback for probes that can't read IDCODE.
        """
        # Common chip ID addresses:
        # STM32: 0xE0042000 (DBGMCU_IDCODE)
        # NXP:   0x40048000 (SIM_BASE)
        chip_id_addresses = [
            0xE0042000,  # STM32
            0x40048000,  # NXP
            0x5C002000,  # ESP32
        ]

        # This would require connecting to target and reading memory
        # Implementation depends on specific probe capabilities
        return DetectionResult(
            success=False,
            method=DetectionMethod.CHIP_ID,
            warnings=["Chip ID detection not implemented - requires target memory read"],
        )

    async def _detect_by_fallback(
        self,
        probe_serial: str | None,
        probes: list[dict[str, Any]],
    ) -> DetectionResult:
        """Fallback: Brute force through chip list.

        This is the last resort - try each known chip until we find a match.
        Should be used sparingly as it's slow.
        """
        # Common chip families to try
        common_families = [
            ChipFamily.STM32F1,
            ChipFamily.STM32F4,
            ChipFamily.STM32H7,
            ChipFamily.NRF52,
            ChipFamily.ESP32,
        ]

        for family in common_families:
            plugin = self._plugin_loader.find_plugin_for_chip(family)
            if plugin is None:
                continue

            # Try to connect and read a known register
            try:
                # This is a simplified check - real implementation would
                # try to halt and read memory at known addresses
                pass
            except Exception:
                continue

        return DetectionResult(
            success=False,
            method=DetectionMethod.FALLBACK,
            warnings=["Fallback detection not implemented"],
        )

    async def _publish_detection_event(self, result: DetectionResult) -> None:
        """Publish detection event to event bus."""
        if self._event_bus is None:
            return

        event = TargetDiscoveredEvent(
            target_id=result.detection_id,
            target_name=result.chip_description.part_number if result.chip_description else "Unknown",
            target_state="discovered",
            probe_serial=result.probe_serial,
            probe_type=result.probe_type.value if result.probe_type else "",
            chip_family=result.chip_description.family.value if result.chip_description else "",
            confidence=result.confidence,
        )

        await self._event_bus.publish(event)

    def clear_cache(self) -> None:
        """Clear detection cache."""
        self._cache.clear()

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return {
            "cache_size": len(self._cache),
            "cache_ttl_seconds": self._cache_ttl.total_seconds(),
        }

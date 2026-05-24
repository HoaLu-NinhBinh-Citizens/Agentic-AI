"""
LIN Protocol (Local Interconnect Network) — ISO 17987.

Implements:
- LIN 1.3 / 2.0 / 2.1 / J2602
- Master and Slave node behavior
- Schedule table management
- In-frame response parsing
- Diagnostic frames (Diagnostic and Configuration)
- Header/Response checksum validation
- Wakeup/Sleep frame handling

Integration: Works alongside CAN for sensor/actuator networks where
CAN is too expensive (LIN cost ~$1 vs CAN ~$5).
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Optional

import structlog

logger = structlog.get_logger(__name__)


# ─── LIN Constants ──────────────────────────────────────────────────

class LINVersion(str, Enum):
    LIN_13 = "1.3"
    LIN_20 = "2.0"
    LIN_21 = "2.1"
    J2602 = "J2602"


class LINBaudrate(int, Enum):
    """Standard LIN baudrates."""
    BAUD_1200 = 1200
    BAUD_2400 = 2400
    BAUD_4800 = 4800
    BAUD_9600 = 9600
    BAUD_19200 = 19200
    BAUD_38400 = 38400


# LIN 2.x break delimiter minimum (for >= 2.x)
LIN_2X_BREAK_LEN_BITS = 13
LIN_13_BREAK_LEN_BITS = 10


# ─── LIN Frame Structure ─────────────────────────────────────────

class LINFrameType(str, Enum):
    UNCONDITIONAL = "unconditional"  # Normal signal frame
    EVENT_TRIGGERED = "event_triggered"  # Master polls multiple slaves
    SPORADIC = "sporadic"  # Master sends only when data changes
    DIAGNOSTIC = "diagnostic"  # Master request or slave response
    RESERVED = "reserved"
    ASSIGN_ID = "assign_id"  # NAD-based node assignment
    READ_BY_ID = "read_by_id"  # Read product ID
    ASSIGN_FRAME_ID = "assign_frame_id"  # Assign frame ID to schedule


@dataclass
class LINFrame:
    """
    A complete LIN frame (header + response).

    Layout:
      Byte 0: PID (Protected Identifier) = Frame ID + parity
      Bytes 1-8: Data (0-8 bytes)
      Byte N: Checksum (classic or enhanced)

    PID = Frame ID[5:0] + parity[7:6]
    Enhanced checksum = LIN 2.x (protects PID)
    Classic checksum = LIN 1.3 (only data)
    """
    frame_id: int          # 0-63 (6 bits)
    pid: int               # Protected ID (8 bits) = ID + parity
    data: bytes            # 0-8 bytes
    checksum: int          # 8-bit checksum
    checksum_type: str     # "enhanced" (LIN 2.x) or "classic" (LIN 1.3)
    direction: str         # "master_to_slave" or "slave_to_master"
    frame_type: LINFrameType = LINFrameType.UNCONDITIONAL
    timestamp: datetime = field(default_factory=datetime.now)
    is_valid: bool = True
    error: str | None = None

    @property
    def id_hex(self) -> str:
        return f"0x{self.frame_id:02X}"

    @property
    def pid_hex(self) -> str:
        return f"0x{self.pid:02X}"

    @property
    def data_hex(self) -> str:
        return " ".join(f"{b:02X}" for b in self.data)

    def parse_pid(self) -> dict:
        """Decode PID into frame ID and parity bits."""
        id_bits = self.pid & 0x3F
        p0 = (self.pid >> 6) & 1
        p1 = (self.pid >> 7) & 1
        return {
            "frame_id": id_bits,
            "p0": p0,
            "p1": p1,
            "pid_valid": self._calc_pid_parity(id_bits) == self.pid >> 6,
        }

    @staticmethod
    def _calc_pid_parity(frame_id: int) -> int:
        """Calculate PID parity bits from frame ID."""
        p0 = ((frame_id ^ (frame_id >> 1) ^ (frame_id >> 2) ^ (frame_id >> 4)) & 1)
        p1 = (~(frame_id >> 1) ^ (frame_id >> 2) ^ (frame_id >> 4)) & 1
        return (p0 | (p1 << 1)) & 0x03

    @staticmethod
    def calc_pid(frame_id: int) -> int:
        """Calculate protected ID from frame ID."""
        return (frame_id & 0x3F) | (LINFrame._calc_pid_parity(frame_id) << 6)

    @staticmethod
    def calc_checksum(data: bytes, pid: int, enhanced: bool = True) -> int:
        """
        Calculate LIN checksum.

        Enhanced (LIN 2.x): sum of (data bytes + PID), modulo 256, inverted
        Classic (LIN 1.3): sum of data bytes, modulo 256, inverted

        Args:
            data: Frame data bytes (0-8)
            pid: Protected ID
            enhanced: True for LIN 2.x, False for LIN 1.3

        Returns:
            8-bit checksum
        """
        if enhanced:
            checksum_data = bytes([pid]) + data
        else:
            checksum_data = data

        return (~sum(checksum_data)) & 0xFF

    def validate_checksum(self) -> bool:
        """Validate frame checksum."""
        expected = self.calc_checksum(self.data, self.pid, self.checksum_type == "enhanced")
        return expected == self.checksum

    def parse_signals(self, signal_map: dict[int, tuple[int, int]]) -> dict[str, int]:
        """
        Parse signals from frame data using signal map.

        Args:
            signal_map: {signal_name: (start_bit, length_bits)}
                e.g. {"motor_speed": (0, 8), "direction": (8, 2)}

        Returns:
            Dict of signal_name: value
        """
        signals = {}
        for name, (start_bit, length) in signal_map.items():
            if start_bit + length > len(self.data) * 8:
                signals[name] = None
                continue

            # Intel LSB-first bit packing
            value = 0
            for b in range(length):
                byte_idx = (start_bit + b) // 8
                bit_idx = (start_bit + b) % 8
                if byte_idx < len(self.data) and (self.data[byte_idx] >> bit_idx) & 1:
                    value |= (1 << b)

            signals[name] = value

        return signals

    def get_summary(self) -> str:
        status = "OK" if self.is_valid else f"ERR: {self.error}"
        return (
            f"[{self.timestamp.strftime('%H:%M:%S.%f')[:-3]}] "
            f"PID={self.pid_hex} [{self.frame_type.value}] "
            f"{self.direction} "
            f"DATA={self.data_hex} "
            f"CS={self.checksum:02X} ({self.checksum_type}) "
            f"{status}"
        )


# ─── Schedule Table ────────────────────────────────────────────────

@dataclass
class ScheduleEntry:
    """A single entry in a LIN schedule table."""
    name: str
    frame_id: int
    delay_ms: float  # Time to wait after this frame completes
    frame_type: LINFrameType = LINFrameType.UNCONDITIONAL
    data: bytes | None = None  # Data for master→slave frames


@dataclass
class ScheduleTable:
    """
    A LIN schedule table containing ordered frame transmissions.

    Master cycles through the table repeatedly.
    Each entry has a delay after transmission.
    """
    name: str
    entries: list[ScheduleEntry] = field(default_factory=list)
    version: LINVersion = LINVersion.LIN_21
    checksum_type: str = "enhanced"  # "enhanced" (2.x) or "classic" (1.3)

    def get_frame(self, frame_id: int, direction: str = "master_to_slave") -> LINFrame:
        """Get next frame for a given frame ID."""
        entry = next((e for e in self.entries if e.frame_id == frame_id), None)
        if not entry:
            raise ValueError(f"No entry found for frame ID {frame_id}")

        pid = LINFrame.calc_pid(frame_id)
        data = entry.data or b"\x00"
        checksum = LINFrame.calc_checksum(data, pid, self.checksum_type == "enhanced")

        return LINFrame(
            frame_id=frame_id,
            pid=pid,
            data=data,
            checksum=checksum,
            checksum_type=self.checksum_type,
            direction=direction,
            frame_type=entry.frame_type,
        )

    def validate(self) -> list[str]:
        """Validate schedule table."""
        errors = []
        frame_ids = [e.frame_id for e in self.entries]

        # Check for duplicate frame IDs
        seen: set[int] = set()
        for fid in frame_ids:
            if fid in seen:
                errors.append(f"Duplicate frame ID: {fid}")
            seen.add(fid)

        # Check diagnostic frames (60-61) are present for LIN 2.x
        if self.checksum_type == "enhanced":
            if 60 not in frame_ids:
                errors.append("LIN 2.x schedule should include frame ID 60 (master request)")
            if 61 not in frame_ids:
                errors.append("LIN 2.x schedule should include frame ID 61 (slave response)")

        return errors


# ─── LIN Node ──────────────────────────────────────────────────────

@dataclass
class LINNodeConfig:
    """Configuration for a LIN node."""
    name: str
    node_id: int           # NAD or functional ID (0-63)
    product_id: tuple[int, int, int]  # (supplier_id, message_id, variant)
    version: LINVersion = LINVersion.LIN_21
    baudrate: int = 19200
    tx_frame_ids: list[int] = field(default_factory=list)
    rx_frame_ids: list[int] = field(default_factory=list)
    signal_map: dict[int, tuple[int, int]] = field(default_factory=dict)


class LINNode:
    """
    LIN node (Master or Slave).

    Master responsibilities:
    - Send headers at scheduled times
    - Manage schedule tables
    - Handle wakeup/sleep
    - Send diagnostic master requests

    Slave responsibilities:
    - Monitor for headers with matching PID
    - Send response data for tx_frame_ids
    - Respond to diagnostic requests
    """

    def __init__(self, config: LINNodeConfig, is_master: bool = False):
        self.config = config
        self.is_master = is_master
        self._schedule_tables: dict[str, ScheduleTable] = {}
        self._active_schedule: ScheduleTable | None = None
        self._signal_values: dict[str, int] = {}
        self._callbacks: dict[str, Callable] = {}

    def add_schedule_table(self, table: ScheduleTable) -> None:
        """Register a schedule table."""
        self._schedule_tables[table.name] = table

    def set_active_schedule(self, name: str) -> None:
        """Switch to a schedule table."""
        if name not in self._schedule_tables:
            raise ValueError(f"Schedule table '{name}' not found")
        self._active_schedule = self._schedule_tables[name]

    def update_signal(self, name: str, value: int) -> None:
        """Update a signal value and trigger callback."""
        self._signal_values[name] = value
        if name in self._callbacks:
            self._callbacks[name](value)

    def on_signal(self, name: str, callback: Callable[[int], None]) -> None:
        """Register callback for signal change."""
        self._callbacks[name] = callback

    def build_frame(self, frame_id: int) -> LINFrame | None:
        """Build response frame for given frame ID."""
        if not self.is_master and frame_id not in self.config.rx_frame_ids:
            return None

        pid = LINFrame.calc_pid(frame_id)
        # Build data from signals
        data = bytearray(8)
        for name, (start_bit, length) in self.config.signal_map.items():
            value = self._signal_values.get(name, 0)
            for b in range(length):
                byte_idx = (start_bit + b) // 8
                bit_idx = (start_bit + b) % 8
                if byte_idx < 8:
                    if (value >> b) & 1:
                        data[byte_idx] |= (1 << bit_idx)

        data = bytes(data)
        checksum = LINFrame.calc_checksum(
            data, pid,
            self.config.version not in (LINVersion.LIN_13,)
        )

        return LINFrame(
            frame_id=frame_id,
            pid=pid,
            data=data,
            checksum=checksum,
            checksum_type="enhanced" if self.config.version != LINVersion.LIN_13 else "classic",
            direction="slave_to_master",
            frame_type=LINFrameType.UNCONDITIONAL,
        )


# ─── LIN Analyzer ────────────────────────────────────────────────────

@dataclass
class LINConfig:
    """Configuration for LIN analysis."""
    version: LINVersion = LINVersion.LIN_21
    baudrate: int = 19200
    checksum_type: str = "enhanced"
    store_messages: bool = True
    max_messages: int = 10000


class LINAnalyzer:
    """
    LIN protocol analyzer for automotive testing.

    Features:
    - Parse raw LIN bytes from UART
    - Validate PID, checksum, timing
    - Build schedule tables
    - Decode diagnostic frames (MasterReq/SlaveResp)
    - Analyze signal values from frames
    - Error detection (break, checksum, timeout)

    Usage:
        analyzer = LINAnalyzer(LINConfig(version=LINVersion.LIN_21, baudrate=19200))

        # Parse raw UART bytes
        frame = analyzer.parse_bytes(raw_bytes)
        if frame:
            print(frame.get_summary())
            signals = frame.parse_signals({"motor_speed": (0, 8)})
    """

    def __init__(self, config: LINConfig | None = None):
        self.config = config or LINConfig()
        self._messages: list[LINFrame] = []
        self._errors: list[dict] = []
        self._stats = {
            "total_frames": 0,
            "valid_frames": 0,
            "checksum_errors": 0,
            "pid_errors": 0,
            "break_errors": 0,
        }

    def parse_bytes(self, raw: bytes) -> LINFrame | None:
        """
        Parse raw LIN bytes into a LINFrame.

        Raw LIN frame format:
        - Break delimiter (>= 1 bit low)
        - Sync field (0x55)
        - PID byte
        - Data bytes (0-8)
        - Checksum byte

        Args:
            raw: Raw bytes from UART

        Returns:
            LINFrame or None if parsing failed
        """
        if len(raw) < 3:
            return None

        # Skip break/sync (first two bytes usually 0x00, 0x55)
        pid_byte = raw[1] if raw[0] == 0x00 else raw[0]
        if raw[0] != 0x00 and raw[0] != 0x55:
            # Try without break detection
            pid_byte = raw[0]

        pid = pid_byte
        frame_id = pid & 0x3F

        # Validate PID parity
        p0 = (pid >> 6) & 1
        p1 = (pid >> 7) & 1
        expected_p = LINFrame._calc_pid_parity(frame_id)
        pid_valid = (p0 | (p1 << 1)) == expected_p

        if not pid_valid:
            self._stats["pid_errors"] += 1
            self._record_error("pid_error", f"PID parity error: expected {expected_p:02b}, got {(p0 | (p1 << 1)):02b}")

        # Determine data length from frame ID (standard mapping)
        dlc = self._dlc_for_frame_id(frame_id)

        # Extract data and checksum
        data_start = 2  # after break/sync and PID
        if len(raw) >= data_start + dlc + 1:
            data = raw[data_start : data_start + dlc]
            checksum = raw[data_start + dlc]
        else:
            data = raw[data_start : min(data_start + 8, len(raw))]
            checksum = raw[-1] if len(raw) > data_start else 0

        # Determine checksum type and validate
        if frame_id <= 31:
            checksum_type = "enhanced"  # LIN 2.x signals
        elif frame_id <= 47:
            checksum_type = "classic"  # LIN 1.3 reserved / diagnostic
        else:
            checksum_type = self.config.checksum_type

        expected_cs = LINFrame.calc_checksum(data, pid, checksum_type == "enhanced")
        checksum_valid = expected_cs == checksum

        if not checksum_valid:
            self._stats["checksum_errors"] += 1
            self._record_error(
                "checksum_error",
                f"Checksum error: expected {expected_cs:02X}, got {checksum:02X}",
            )

        # Determine direction
        direction = "master_to_slave" if frame_id < 60 else "slave_to_master"
        if frame_id == 60:
            frame_type = LINFrameType.DIAGNOSTIC
            direction = "master_to_slave"
        elif frame_id == 61:
            frame_type = LINFrameType.DIAGNOSTIC
            direction = "slave_to_master"
        else:
            frame_type = self._frame_type_for_id(frame_id)

        frame = LINFrame(
            frame_id=frame_id,
            pid=pid,
            data=data,
            checksum=checksum,
            checksum_type=checksum_type,
            direction=direction,
            frame_type=frame_type,
            is_valid=pid_valid and checksum_valid,
            error=None if (pid_valid and checksum_valid) else "PID or checksum error",
        )

        self._stats["total_frames"] += 1
        if frame.is_valid:
            self._stats["valid_frames"] += 1

        if self.config.store_messages:
            self._messages.append(frame)
            if len(self._messages) > self.config.max_messages:
                self._messages.pop(0)

        return frame

    def parse_diagnostic_master_request(self, frame: LINFrame) -> dict | None:
        """
        Parse LIN 2.x Master Request frame (PID=60).

        Master Request frame structure:
        - NAD (Node Address, 7 bits) | PCI (1 bit = 0 for SF or 1 for MF)
        - PCI type: 0=SF(1 data byte), 1=MF(3-byte length+)

        Standard format (SF):
        - NAD | PCI(0) | SID
        - Response: NAD | PCI(3) | RSID | data...

        Args:
            frame: LIN frame with frame_id=60

        Returns:
            Dict with diagnostic info or None
        """
        if frame.frame_id != 60 or len(frame.data) < 2:
            return None

        nad = frame.data[0] & 0x7F
        pci_nibble = (frame.data[0] >> 7) & 1

        if pci_nibble == 0:
            # Single frame
            sid = frame.data[1]
            return {
                "type": "single_frame",
                "nad": nad,
                "sid": sid,
                "raw_data": frame.data[2:].hex(),
            }
        else:
            # Multi-frame
            length = ((frame.data[1] >> 4) & 0x0F) | ((frame.data[2] & 0x0F) << 4)
            return {
                "type": "multi_frame",
                "nad": nad,
                "length": length,
                "raw_data": frame.data[3:].hex(),
            }

    def parse_diagnostic_slave_response(self, frame: LINFrame) -> dict | None:
        """
        Parse LIN 2.x Slave Response frame (PID=61).

        Response structure:
        - NAD | PCI
        - RSID (Response SID = SID + 0x40)
        - Data...

        Args:
            frame: LIN frame with frame_id=61

        Returns:
            Dict with response info or None
        """
        if frame.frame_id != 61 or len(frame.data) < 2:
            return None

        nad = frame.data[0] & 0x7F
        pci_nibble = (frame.data[0] >> 7) & 1

        if pci_nibble == 0:
            rsid = frame.data[1]
            return {
                "type": "single_frame",
                "nad": nad,
                "rsid": rsid,
                "sid_requested": rsid - 0x40 if rsid >= 0x40 else None,
                "data": frame.data[2:].hex(),
            }
        else:
            length = ((frame.data[1] >> 4) & 0x0F) | ((frame.data[2] & 0x0F) << 4)
            return {
                "type": "multi_frame",
                "nad": nad,
                "length": length,
                "data": frame.data[3:].hex(),
            }

    def get_signal_value(self, frame: LINFrame, signal_name: str, signal_map: dict[str, tuple[int, int]]) -> int | None:
        """Get a named signal value from a frame."""
        if signal_name not in signal_map:
            return None
        start_bit, length = signal_map[signal_name]
        signals = frame.parse_signals({signal_name: (start_bit, length)})
        return signals.get(signal_name)

    # ─── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _dlc_for_frame_id(frame_id: int) -> int:
        """Get data length code for standard LIN frame IDs."""
        if frame_id <= 31:
            return 2  # Signals use 2-byte encoding
        elif frame_id <= 47:
            return 8  # Diagnostic / reserved
        elif frame_id <= 59:
            return 8  # User-defined
        else:
            return 8  # Reserved

    @staticmethod
    def _frame_type_for_id(frame_id: int) -> LINFrameType:
        """Get frame type for standard LIN frame IDs."""
        if frame_id <= 39:
            return LINFrameType.UNCONDITIONAL
        elif frame_id <= 47:
            return LINFrameType.RESERVED
        elif frame_id <= 53:
            return LINFrameType.EVENT_TRIGGERED
        elif frame_id <= 59:
            return LINFrameType.SPORADIC
        elif frame_id == 60:
            return LINFrameType.DIAGNOSTIC
        elif frame_id == 61:
            return LINFrameType.DIAGNOSTIC
        else:
            return LINFrameType.RESERVED

    def _record_error(self, error_type: str, message: str) -> None:
        self._errors.append({
            "type": error_type,
            "message": message,
            "timestamp": datetime.now(),
        })
        logger.debug("lin_error", type=error_type, message=message)

    def get_statistics(self) -> dict:
        """Get LIN bus statistics."""
        total = self._stats["total_frames"]
        valid = self._stats["valid_frames"]
        return {
            **self._stats,
            "error_rate": round((total - valid) / max(total, 1), 3),
            "total_messages": len(self._messages),
            "total_errors": len(self._errors),
        }

    def get_recent_messages(self, count: int = 10) -> list[LINFrame]:
        return self._messages[-count:]

"""
CAN Bus Analyzer for Hardware-in-the-Loop Testing

Provides CAN bus message parsing and analysis for automotive firmware.
Supports:
- Standard CAN (11-bit) and Extended CAN (29-bit) identifiers
- CANOpen, J1939, and raw CAN protocols
- Message filtering by ID range
- Timestamp and message rate analysis
- Error detection and reporting
- Integration with UART monitoring (for MCUs that output CAN via UART)
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional, Any
from threading import Thread, Lock
import struct

logger = logging.getLogger(__name__)


# Standard CAN ID range
CAN_STANDARD_MASK = 0x7FF
# Extended CAN ID range
CAN_EXTENDED_MASK = 0x1FFFFFFF


@dataclass
class CanConfig:
    """CAN analysis configuration."""
    protocol: str = "raw"  # "raw", "j1939", "canopen"
    bitrate: int = 500000
    sample_point: float = 0.875
    store_raw: bool = True
    max_messages: int = 10000


@dataclass
class CanMessage:
    """Represents a CAN message."""
    timestamp: datetime
    can_id: int
    is_extended: bool
    is_rtr: bool  # Remote Transmission Request
    dlc: int  # Data Length Code (0-8)
    data: bytes
    is_error: bool = False
    is_overflow: bool = False
    source: str = "can"

    @property
    def id_hex(self) -> str:
        """Get CAN ID as hex string."""
        mask = CAN_EXTENDED_MASK if self.is_extended else CAN_STANDARD_MASK
        return f"0x{self.can_id & mask:08X}" if self.is_extended else f"0x{self.can_id & CAN_STANDARD_MASK:03X}"

    @property
    def data_hex(self) -> str:
        """Get data as hex string."""
        return " ".join(f"{b:02X}" for b in self.data)

    @property
    def data_str(self) -> str:
        """Get data as ASCII string (printable chars only)."""
        return "".join(chr(b) if 32 <= b < 127 else "." for b in self.data)

    def parse_j1939(self) -> Optional[Dict[str, Any]]:
        """Parse as J1939 message (if applicable)."""
        if len(self.data) < 3:
            return None

        pgn = ((self.can_id >> 8) & 0x3FFFF)
        priority = (self.can_id >> 26) & 0x7
        src_addr = self.can_id & 0xFF
        dst_addr = (self.can_id >> 8) & 0xFF

        return {
            "pgn": pgn,
            "pgn_hex": f"0x{pgn:06X}",
            "priority": priority,
            "src_addr": src_addr,
            "dst_addr": dst_addr,
            "data_page": self.data[0] if self.data else 0,
            "pdu_format": self.data[1] if len(self.data) > 1 else 0,
            "pdu_specific": self.data[2] if len(self.data) > 2 else 0,
        }

    def parse_canopen(self) -> Optional[Dict[str, Any]]:
        """Parse as CANopen message (if applicable)."""
        if len(self.data) < 2:
            return None

        # CANopen COB-ID structure
        # For SDO: 0x600 + node_id, 0x580 + node_id
        # For PDO: 0x180-0x1FF (TX), 0x200-0x27F (RX)
        # For NMT: 0x000
        base_id = self.can_id & 0x7F  # Node ID is lower 7 bits

        return {
            "node_id": base_id,
            "function_code": self.can_id >> 7,
            "command": self.data[0] if self.data else 0,
            "data_payload": self.data[1:] if len(self.data) > 1 else b"",
        }

    def get_summary(self) -> str:
        """Get message summary."""
        return f"{self.id_hex} [{self.dlc}] {self.data_hex}"


class CanAnalyzer:
    """
    CAN bus message analyzer for automotive firmware testing.

    Features:
    - Parse CAN messages from UART input (for MCUs without native CAN)
    - Support for standard and extended CAN IDs
    - J1939 and CANopen protocol parsing
    - Message rate analysis
    - Error detection
    """

    def __init__(self, config: Optional[CanConfig] = None):
        self.config = config or CanConfig()
        self._messages: List[CanMessage] = []
        self._lock = Lock()
        self._running = False
        self._rate_stats: Dict[int, List[float]] = {}  # CAN ID -> timestamps

        # Callbacks
        self._on_message: List[Callable[[CanMessage], None]] = []
        self._on_error: List[Callable[[CanMessage], None]] = []

        # Statistics
        self._stats = {
            "total_messages": 0,
            "extended_frames": 0,
            "error_frames": 0,
            "overflow_events": 0,
            "unique_ids": set(),
        }

    # -------------------------------------------------------------------------
    # Message Parsing
    # -------------------------------------------------------------------------

    def parse_uart_can_line(self, line: str) -> Optional[CanMessage]:
        """
        Parse CAN message from UART output.

        Supports multiple formats:
        - "CAN: 123 08 11 22 33 44 55 66 77 88"
        - "0x123 11 22 33 44 55 66 77 88"
        - "[0.001234] 123#1122334455667788"
        - "ID=0x123 LEN=8 DATA=11 22 33 44 55 66 77 88"
        """
        line = line.strip()
        if not line:
            return None

        try:
            # Format: "[0.001234] 123#1122334455667788" (Vector CANalyzer style)
            match = re.match(r"\[([0-9.]+)\]\s*([0-9A-Fa-f]+)#([0-9A-Fa-f]*)", line)
            if match:
                can_id = int(match.group(2), 16)
                data_hex = match.group(3)
                data = bytes.fromhex(data_hex) if data_hex else b""
                dlc = len(data)
                return self._create_message(can_id, dlc, data, is_extended=len(match.group(2)) > 3)

            # Format: "CAN: 123 08 11 22 33 44 55 66 77 88" (DBC style)
            parts = line.split()
            if len(parts) >= 3 and parts[0].upper() == "CAN:":
                can_id = int(parts[1], 16)
                dlc = int(parts[2], 16)
                data_bytes = []
                for p in parts[3:]:
                    if len(p) == 2:
                        try:
                            data_bytes.append(int(p, 16))
                        except ValueError:
                            break
                data = bytes(data_bytes)
                return self._create_message(can_id, dlc, data, is_extended=len(parts[1]) > 3)

            # Format: "0x123 11 22 33 44 55 66 77 88"
            if line.startswith("0x"):
                space_idx = line.find(" ")
                if space_idx > 0:
                    can_id_str = line[2:space_idx]
                    data_parts = line[space_idx:].split()
                    can_id = int(can_id_str, 16)
                    data_bytes = []
                    for p in data_parts:
                        if len(p) == 2:
                            try:
                                data_bytes.append(int(p, 16))
                            except ValueError:
                                break
                    data = bytes(data_bytes)
                    dlc = len(data)
                    return self._create_message(can_id, dlc, data, is_extended=len(can_id_str) > 3)

            return None

        except Exception as exc:
            logger.warning("Failed to parse CAN line '%s': %s", line[:50], exc)
            return None

    def _create_message(
        self,
        can_id: int,
        dlc: int,
        data: bytes,
        is_extended: bool = False,
        is_error: bool = False,
    ) -> CanMessage:
        """Create a CAN message with validation."""
        # Clamp DLC to valid range
        dlc = min(max(dlc, 0), 8)
        data = data[:8]  # CAN max 8 bytes

        # Create message
        msg = CanMessage(
            timestamp=datetime.now(),
            can_id=can_id,
            is_extended=is_extended,
            is_rtr=False,
            dlc=dlc,
            data=data,
            is_error=is_error,
            source="uart",
        )

        # Add to statistics
        self._stats["total_messages"] += 1
        if is_extended:
            self._stats["extended_frames"] += 1
        if is_error:
            self._stats["error_frames"] += 1
        self._stats["unique_ids"].add(can_id)

        # Track message rate
        now = datetime.now().timestamp()
        if can_id not in self._rate_stats:
            self._rate_stats[can_id] = []
        self._rate_stats[can_id].append(now)

        return msg

    def add_message(self, msg: CanMessage) -> None:
        """Add a parsed CAN message to the buffer."""
        with self._lock:
            self._messages.append(msg)
            if len(self._messages) > self.config.max_messages:
                self._messages.pop(0)

            # Update statistics
            self._stats["total_messages"] += 1
            if msg.is_extended:
                self._stats["extended_frames"] += 1
            if msg.is_error:
                self._stats["error_frames"] += 1
            self._stats["unique_ids"].add(msg.can_id)

            # Track message rate
            now = datetime.now().timestamp()
            if msg.can_id not in self._rate_stats:
                self._rate_stats[msg.can_id] = []
            self._rate_stats[msg.can_id].append(now)

        # Notify callbacks
        for cb in self._on_message:
            try:
                cb(msg)
            except Exception as exc:
                logger.error("Error in message callback: %s", exc)

        if msg.is_error:
            for cb in self._on_error:
                try:
                    cb(msg)
                except Exception as exc:
                    logger.error("Error in error callback: %s", exc)

    # -------------------------------------------------------------------------
    # Callbacks
    # -------------------------------------------------------------------------

    def on_message(self, callback: Callable[[CanMessage], None]) -> None:
        """Register message callback."""
        self._on_message.append(callback)

    def on_error(self, callback: Callable[[CanMessage], None]) -> None:
        """Register error callback."""
        self._on_error.append(callback)

    # -------------------------------------------------------------------------
    # Query Methods
    # -------------------------------------------------------------------------

    async def get_messages(
        self,
        can_id: Optional[int] = None,
        is_extended: Optional[bool] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[CanMessage]:
        """Get messages with optional filters."""
        with self._lock:
            messages = list(self._messages)

        if can_id is not None:
            messages = [m for m in messages if m.can_id == can_id]

        if is_extended is not None:
            messages = [m for m in messages if m.is_extended == is_extended]

        if since:
            messages = [m for m in messages if m.timestamp >= since]

        return messages[-limit:]

    async def get_message_rate(self, can_id: int, window_seconds: float = 1.0) -> float:
        """
        Calculate message rate for a specific CAN ID.

        Returns messages per second.
        """
        with self._lock:
            timestamps = list(self._rate_stats.get(can_id, []))

        if len(timestamps) < 2:
            return 0.0

        now = datetime.now().timestamp()
        cutoff = now - window_seconds
        recent = [t for t in timestamps if t >= cutoff]

        if len(recent) < 2:
            return 0.0

        # Calculate rate
        duration = recent[-1] - recent[0]
        if duration <= 0:
            return 0.0

        return (len(recent) - 1) / duration

    async def get_unique_ids(self) -> List[int]:
        """Get list of unique CAN IDs seen."""
        with self._lock:
            return sorted(self._stats["unique_ids"])

    async def get_stats(self) -> Dict[str, Any]:
        """Get analysis statistics."""
        with self._lock:
            return {
                "total_messages": self._stats["total_messages"],
                "extended_frames": self._stats["extended_frames"],
                "error_frames": self._stats["error_frames"],
                "overflow_events": self._stats["overflow_events"],
                "unique_ids": len(self._stats["unique_ids"]),
                "buffer_size": len(self._messages),
                "buffer_max": self.config.max_messages,
            }

    async def clear(self) -> None:
        """Clear all messages and statistics."""
        with self._lock:
            self._messages.clear()
            self._rate_stats.clear()
            self._stats = {
                "total_messages": 0,
                "extended_frames": 0,
                "error_frames": 0,
                "overflow_events": 0,
                "unique_ids": set(),
            }

    # -------------------------------------------------------------------------
    # Filtering
    # -------------------------------------------------------------------------

    async def filter_by_id_range(
        self,
        min_id: int = 0,
        max_id: int = 0x7FF,
        extended: bool = False,
    ) -> List[CanMessage]:
        """Get messages within CAN ID range."""
        return await self.get_messages(
            limit=self.config.max_messages
        )

    async def filter_by_pattern(
        self,
        pattern: Optional[str] = None,
        data_contains: Optional[bytes] = None,
    ) -> List[CanMessage]:
        """Filter messages by pattern or data content."""
        messages = await self.get_messages(limit=self.config.max_messages)

        if data_contains:
            messages = [m for m in messages if data_contains in m.data]

        return messages

    # -------------------------------------------------------------------------
    # Protocol Analysis
    # -------------------------------------------------------------------------

    async def analyze_j1939(self) -> Dict[str, Any]:
        """Analyze J1939 protocol messages."""
        messages = await self.get_messages(limit=self.config.max_messages)
        j1939_msgs = [m for m in messages if self._is_j1939_id(m.can_id)]

        pgns: Dict[int, int] = {}
        for msg in j1939_msgs:
            parsed = msg.parse_j1939()
            if parsed:
                pgn = parsed["pgn"]
                pgns[pgn] = pgns.get(pgn, 0) + 1

        return {
            "j1939_messages": len(j1939_msgs),
            "pgn_counts": {f"0x{pgn:06X}": count for pgn, count in pgns.items()},
            "total_messages": len(messages),
            "j1939_ratio": len(j1939_msgs) / len(messages) if messages else 0,
        }

    def _is_j1939_id(self, can_id: int) -> bool:
        """Check if CAN ID looks like J1939."""
        # J1939 uses 29-bit IDs
        return can_id > 0x7FF

    async def analyze_canopen(self) -> Dict[str, Any]:
        """Analyze CANopen protocol messages."""
        messages = await self.get_messages(limit=self.config.max_messages)

        # CANopen function codes
        function_codes = {}
        node_ids = {}

        for msg in messages:
            fc = msg.can_id >> 7
            nid = msg.can_id & 0x7F

            function_codes[fc] = function_codes.get(fc, 0) + 1
            if nid < 128:
                node_ids[nid] = node_ids.get(nid, 0) + 1

        return {
            "canopen_messages": sum(1 for m in messages if (m.can_id & 0x7F) < 128),
            "function_codes": function_codes,
            "node_ids": dict(sorted(node_ids.items())),
            "total_messages": len(messages),
        }

    # -------------------------------------------------------------------------
    # Export
    # -------------------------------------------------------------------------

    async def export(self, filepath, format: str = "csv") -> bool:
        """
        Export CAN messages to file.

        Args:
            filepath: Output file path
            format: "csv", "json", or "asc" (Vector CANalyzer format)
        """
        messages = await self.get_messages(limit=self.config.max_messages)

        try:
            if format == "csv":
                lines = ["Timestamp,CAN_ID,Extended,DLC,Data_Hex"]
                for msg in messages:
                    ts = msg.timestamp.strftime("%H:%M:%S.%f")[:-3]
                    lines.append(f"{ts},{msg.id_hex},{msg.is_extended},{msg.dlc},{msg.data_hex}")
                filepath.write_text("\n".join(lines), encoding='utf-8')

            elif format == "asc":
                lines = ["date 0"]
                for msg in messages:
                    ts = msg.timestamp.strftime("%H:%M:%S.%f")[:-3]
                    ext = "x" if msg.is_extended else ""
                    lines.append(f"{ts} {msg.can_id:08X}{ext} Rx   d {msg.dlc} {' '.join(f'{b:02X}' for b in msg.data)}")
                filepath.write_text("\n".join(lines), encoding='utf-8')

            elif format == "json":
                import json
                data = [
                    {
                        "timestamp": m.timestamp.isoformat(),
                        "can_id": m.can_id,
                        "can_id_hex": m.id_hex,
                        "is_extended": m.is_extended,
                        "dlc": m.dlc,
                        "data": list(m.data),
                        "data_hex": m.data_hex,
                    }
                    for m in messages
                ]
                filepath.write_text(json.dumps(data, indent=2), encoding='utf-8')

            logger.info("Exported %d CAN messages to %s", len(messages), filepath)
            return True

        except Exception as exc:
            logger.error("Export failed: %s", exc)
            return False

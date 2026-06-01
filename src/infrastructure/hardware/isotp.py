"""ISO-TP (ISO 15765-2) Transport Layer Implementation.

ISO-TP is used for diagnostics and parameter access over CAN/CAN-FD.
It handles multi-frame messages with flow control.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ISOTPFrameType(Enum):
    """ISO-TP N_PCI types."""
    SINGLE = 0x00  # Single frame (SF)
    FIRST = 0x10   # First frame (FF)
    CONSECUTIVE = 0x20  # Consecutive frame (CF)
    FLOW_CONTROL = 0x30  # Flow control (FC)


@dataclass
class ISOTPPacket:
    """Represents an ISO-TP packet."""
    pci_type: ISOTPFrameType
    data: bytes = b""

    @property
    def raw(self) -> bytes:
        """Get raw bytes."""
        return bytes([self.pci_type.value]) + self.data


@dataclass
class ISOTPMessage:
    """Represents a complete ISO-TP message."""
    can_id: int
    data: bytes = b""
    timestamp: float = 0.0
    is_complete: bool = False

    @property
    def len(self) -> int:
        return len(self.data)


class ISOTPSender:
    """ISO-TP sender (ECU side)."""

    # CAN max payload (Classic CAN = 8, CAN-FD = 64)
    MAX_BLOCK_SIZE = 8 if not True else 64  # Use True for CAN-FD
    CAN_FD_MAX_BLOCK_SIZE = 64
    DEFAULT_ST_MIN_US = 1000  # Minimum separation time in microseconds

    def __init__(self, can_id: int, use_canfd: bool = False):
        self.can_id = can_id
        self.use_canfd = use_canfd
        self.max_block_size = self.CAN_FD_MAX_BLOCK_SIZE if use_canfd else self.MAX_BLOCK_SIZE

    def create_single_frame(self, data: bytes) -> list[ISOTPPacket]:
        """Create a single-frame ISO-TP message."""
        if len(data) > (15 if not self.use_canfd else 4095):
            raise ValueError(f"Data too large for single frame: {len(data)} bytes")

        dlc = len(data)
        packet_data = bytes([dlc]) + data
        return [ISOTPPacket(ISOTPFrameType.SINGLE, packet_data)]

    def create_multi_frame(self, data: bytes) -> list[ISOTPPacket]:
        """Create a multi-frame ISO-TP message."""
        packets = []

        # First Frame (FF)
        total_len = len(data)
        if self.use_canfd:
            # CAN-FD: 16-bit length in first frame
            ff_data = struct.pack('>H', total_len) + data[:(self.max_block_size - 2)]
            packets.append(ISOTPPacket(ISOTPFrameType.FIRST, ff_data[:self.max_block_size]))
            data = data[(self.max_block_size - 2):]
        else:
            # Classic CAN: 12-bit length
            ff_data = bytes([(total_len >> 8) & 0x0F, total_len & 0xFF]) + data[:(self.max_block_size - 2)]
            packets.append(ISOTPPacket(ISOTPFrameType.FIRST, ff_data))
            data = data[(self.max_block_size - 2):]

        # Consecutive Frames (CF)
        sequence_number = 1
        while data:
            cf_data = bytes([sequence_number & 0x0F]) + data[:(self.max_block_size - 1)]
            packets.append(ISOTPPacket(ISOTPFrameType.CONSECUTIVE, cf_data))
            data = data[(self.max_block_size - 1):]
            sequence_number = (sequence_number + 1) & 0x0F

        return packets

    def send(self, data: bytes) -> list[ISOTPPacket]:
        """Create ISO-TP packets for data."""
        if self.use_canfd and len(data) > 4095:
            raise ValueError(f"CAN-FD data too large: {len(data)} bytes (max 4095)")

        if not self.use_canfd and len(data) > 4095:
            raise ValueError(f"Data too large: {len(data)} bytes (max 4095)")

        if len(data) <= (15 if not self.use_canfd else 63):
            return self.create_single_frame(data)
        else:
            return self.create_multi_frame(data)


class ISOTPReceiver:
    """ISO-TP receiver."""

    def __init__(self, can_id: int, use_canfd: bool = False):
        self.can_id = can_id
        self.use_canfd = use_canfd
        self.max_block_size = 8 if not use_canfd else 64
        self.messages: dict[int, ISOTPMessage] = {}
        self.pending_flow_control: dict[int, dict] = {}

    def receive(self, packet: ISOTPPacket) -> Optional[ISOTPMessage]:
        """Process incoming ISO-TP packet."""
        pci_type = packet.pci_type

        if pci_type == ISOTPFrameType.SINGLE:
            return self._handle_single_frame(packet)
        elif pci_type == ISOTPFrameType.FIRST:
            return self._handle_first_frame(packet)
        elif pci_type == ISOTPFrameType.CONSECUTIVE:
            return self._handle_consecutive_frame(packet)
        elif pci_type == ISOTPFrameType.FLOW_CONTROL:
            return self._handle_flow_control(packet)

        return None

    def _handle_single_frame(self, packet: ISOTPPacket) -> ISOTPMessage:
        """Handle single frame."""
        # First byte is length
        if len(packet.data) < 1:
            return ISOTPMessage(self.can_id, b"", is_complete=False)

        data_len = packet.data[0]
        data = packet.data[1:1 + data_len]

        return ISOTPMessage(
            can_id=self.can_id,
            data=data,
            is_complete=True
        )

    def _handle_first_frame(self, packet: ISOTPPacket) -> Optional[ISOTPMessage]:
        """Handle first frame of multi-frame message."""
        if len(packet.data) < 2:
            return None

        # Extract total length
        if self.use_canfd:
            total_len = struct.unpack('>H', packet.data[:2])[0]
            data = packet.data[2:]
        else:
            total_len = ((packet.data[0] & 0x0F) << 8) | packet.data[1]
            data = packet.data[2:]

        # Create new message
        msg = ISOTPMessage(
            can_id=self.can_id,
            data=data,
            is_complete=False
        )
        self.messages[self.can_id] = msg

        # Send flow control
        self.pending_flow_control[self.can_id] = {
            'block_size': 0,  # Continue to send
            'st_min': 0,       # No delay
        }

        return None  # Message not complete yet

    def _handle_consecutive_frame(self, packet: ISOTPPacket) -> Optional[ISOTPMessage]:
        """Handle consecutive frame."""
        if self.can_id not in self.messages:
            return None

        msg = self.messages[self.can_id]
        seq_num = packet.data[0] & 0x0F
        data = packet.data[1:]

        msg.data += data

        # Check if complete
        if len(msg.data) >= 4095:  # Max ISO-TP message size
            msg.is_complete = True
            return self.messages.pop(self.can_id, None)

        return None

    def _handle_flow_control(self, packet: ISOTPPacket) -> None:
        """Handle flow control (ignore for receiver)."""
        if len(packet.data) < 3:
            return

        # Flow status, block size, separation time
        fs = packet.data[0] & 0x0F
        bs = packet.data[1]
        st_min = packet.data[2]

        self.pending_flow_control[self.can_id] = {
            'flow_status': fs,
            'block_size': bs,
            'st_min': st_min,
        }


@dataclass
class UDSService:
    """UDS (ISO 14229) service identifiers."""
    # Diagnostic Session Control
    DIAGNOSTIC_SESSION_CONTROL = 0x10
    SESSION_TYPE_DEFAULT = 0x01
    SESSION_TYPE_PROGRAMMING = 0x02
    SESSION_TYPE_EXTENDED = 0x03

    # ECU Reset
    ECU_RESET = 0x11
    RESET_TYPE_HARD = 0x01
    RESET_TYPE_KEYOFFON = 0x02
    RESET_TYPE_SOFT = 0x03

    # Clear Diagnostic Information
    CLEAR_DIAGNOSTIC_INFO = 0x14

    # Read DTC Information
    READ_DTC_INFO = 0x19

    # Read Data By Identifier
    READ_DATA_BY_ID = 0x22

    # Read Memory By Address
    READ_MEMORY_BY_ADDRESS = 0x23

    # Security Access
    SECURITY_ACCESS = 0x27

    # Communication Control
    COMMUNICATION_CONTROL = 0x28

    # Tester Present
    TESTER_PRESENT = 0x3E

    # Control DTC Setting
    CONTROL_DTC_SETTING = 0x85

    # Write Data By Identifier
    WRITE_DATA_BY_ID = 0x2E

    # Routine Control
    ROUTINE_CONTROL = 0x31

    # Request Download
    REQUEST_DOWNLOAD = 0x34

    # Request Upload
    REQUEST_UPLOAD = 0x35

    # Transfer Data
    TRANSFER_DATA = 0x36

    # Request Transfer Exit
    REQUEST_TRANSFER_EXIT = 0x37


class UDSBuilder:
    """Builder for UDS diagnostic messages."""

    @staticmethod
    def build_read_did(did: int) -> bytes:
        """Build Read Data By Identifier request."""
        return bytes([UDSService.READ_DATA_BY_ID, (did >> 8) & 0xFF, did & 0xFF])

    @staticmethod
    def build_write_did(did: int, data: bytes) -> bytes:
        """Build Write Data By Identifier request."""
        return bytes([UDSService.WRITE_DATA_BY_ID, (did >> 8) & 0xFF, did & 0xFF]) + data

    @staticmethod
    def build_session_control(session_type: int) -> bytes:
        """Build Diagnostic Session Control request."""
        return bytes([UDSService.DIAGNOSTIC_SESSION_CONTROL, session_type])

    @staticmethod
    def build_security_access(request_seed: bool, key: Optional[int] = None) -> bytes:
        """Build Security Access request."""
        sub_function = 0x01 if request_seed else 0x02
        msg = bytes([UDSService.SECURITY_ACCESS, sub_function])
        if not request_seed and key is not None:
            msg += struct.pack('>I', key)
        return msg

    @staticmethod
    def build_tester_present() -> bytes:
        """Build Tester Present request."""
        return bytes([UDSService.TESTER_PRESENT, 0x00])

    @staticmethod
    def build_read_memory(address: int, size: int) -> bytes:
        """Build Read Memory By Address request."""
        # Address format: 3 bytes (24-bit) or 4 bytes (32-bit)
        if address <= 0xFFFFFF:
            return bytes([UDSService.READ_MEMORY_BY_ADDRESS, 0x14]) + struct.pack('>I', address)[:3] + bytes([size])
        else:
            return bytes([UDSService.READ_MEMORY_BY_ADDRESS, 0x24]) + struct.pack('>I', address) + bytes([size])

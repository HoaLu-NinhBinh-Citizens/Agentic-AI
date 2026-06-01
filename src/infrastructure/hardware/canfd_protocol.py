"""CAN-FD (Flexible Data-rate) Protocol Implementation.

CAN-FD allows up to 64 bytes per frame and higher bitrates.
This implementation supports:
- Standard and Extended CAN-FD frames
- Bitrate switching (BRS)
- Error detection
- Frame parsing
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class CANFDError:
    """CAN-FD error codes."""
    STUFF_ERROR = "Stuffing error"
    FORMAT_ERROR = "Frame format error"
    ACK_ERROR = "No acknowledgment received"
    BIT_ERROR = "Bit error"
    CRC_ERROR = "CRC error"


@dataclass
class CANFDFrame:
    """Represents a CAN-FD frame."""
    # Arbitration fields
    can_id: int  # 11-bit (standard) or 29-bit (extended)
    is_extended: bool = False
    is_rtr: bool = False  # Remote Transmission Request

    # Data fields
    dlc: int  # Data Length Code (0-15)
    data: bytes = b""

    # CAN-FD specific
    is_fd: bool = True  # Always True for CAN-FD
    is_esi: bool = False  # Error State Indicator
    is_brs: bool = False  # Bit Rate Switch

    # Control
    fdf: bool = True  # FD frame format (1 = FD, 0 = Classic CAN)
    res: bool = False  # Reserved bit (must be 0)

    @property
    def data_len(self) -> int:
        """Get actual data length from DLC."""
        if self.dlc <= 8:
            return self.dlc
        # CAN-FD DLC to bytes mapping
        dlc_to_len = {
            9: 12, 10: 16, 11: 20, 12: 24, 13: 32,
            14: 48, 15: 64
        }
        return dlc_to_len.get(self.dlc, 8)

    @property
    def is_valid(self) -> bool:
        """Check if frame is valid."""
        # Data length must match DLC
        if len(self.data) > self.data_len:
            return False
        # Extended ID range
        if self.is_extended and self.can_id > 0x1FFFFFFF:
            return False
        # Standard ID range
        if not self.is_extended and self.can_id > 0x7FF:
            return False
        return True

    @property
    def can_id_hex(self) -> str:
        """Get CAN ID as hex string."""
        if self.is_extended:
            return f"0x{self.can_id:08X}"
        return f"0x{self.can_id:03X}"

    @property
    def data_hex(self) -> str:
        """Get data as hex string."""
        return " ".join(f"{b:02X}" for b in self.data)


class CANFDParser:
    """Parser for CAN-FD frames."""

    # DLC to data length mapping
    DLC_TO_LEN = {
        0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8,
        9: 12, 10: 16, 11: 20, 12: 24, 13: 32, 14: 48, 15: 64
    }

    # Data length to DLC mapping
    LEN_TO_DLC = {v: k for k, v in DLC_TO_LEN.items()}

    @classmethod
    def parse_canfd(cls, raw_data: bytes) -> Optional[CANFDFrame]:
        """Parse raw CAN-FD frame bytes.

        Assumes standard CAN-FD format:
        - Arbitration: ID (11 or 29 bits) + RTR + IDE + FDF + RES + DLC
        - Data: up to 64 bytes
        - CRC: variable length
        """
        if len(raw_data) < 16:  # Minimum frame size
            return None

        try:
            # Parse arbitration field (first 32 bits)
            arb = struct.unpack('<I', raw_data[0:4])[0]

            # Extract fields
            # Bit 0: RTR (Remote Transmission Request)
            rtr = bool(arb & 0x40000000)

            # Bit 1: IDE (Identifier Extension)
            ide = bool(arb & 0x20000000)

            # Extract CAN ID
            if ide:
                can_id = arb & 0x1FFFFFFF
                is_extended = True
            else:
                can_id = arb & 0x7FF
                is_extended = False

            # FDF and RES bits
            fdf = bool(raw_data[4] & 0x40)  # Bit 6
            res = bool(raw_data[4] & 0x20)   # Bit 5

            # DLC (bits 0-3 of byte 4)
            dlc = raw_data[4] & 0x0F

            # ESI bit (bit 7 of byte 4)
            esi = bool(raw_data[4] & 0x80)

            # BRS bit (bit 7 of byte 5)
            brs = bool(raw_data[5] & 0x80)

            # Data starts at byte 6
            data_len = cls.DLC_TO_LEN.get(dlc, 8)
            data = raw_data[6:6 + data_len]

            return CANFDFrame(
                can_id=can_id,
                is_extended=is_extended,
                is_rtr=rtr,
                dlc=dlc,
                data=data,
                is_fd=True,
                is_esi=esi,
                is_brs=brs,
                fdf=fdf,
                res=res,
            )
        except Exception:
            return None

    @classmethod
    def encode_canfd(cls, frame: CANFDFrame) -> bytes:
        """Encode CAN-FD frame to bytes."""
        # Calculate DLC if not provided
        data_len = len(frame.data)
        dlc = frame.dlc if frame.dlc else cls.LEN_TO_DLC.get(data_len, 8)

        # Build arbitration field
        arb = frame.can_id & 0x1FFFFFFF if frame.is_extended else frame.can_id & 0x7FF

        if frame.is_rtr:
            arb |= 0x40000000
        if frame.is_extended:
            arb |= 0x20000000

        # Control field
        ctrl = dlc & 0x0F
        if frame.fdf:
            ctrl |= 0x40  # FDF
        if frame.res:
            ctrl |= 0x20  # RES
        if frame.is_esi:
            ctrl |= 0x80  # ESI

        # BRS
        brs = 0x80 if frame.is_brs else 0x00

        # Build frame
        result = struct.pack('<I', arb)  # Arbitration
        result += bytes([ctrl, brs])      # Control
        result += frame.data              # Data
        result += bytes(data_len - len(frame.data))  # Padding

        return result


class CANFDAnalyzer:
    """Analyzer for CAN-FD traffic."""

    def __init__(self):
        self.frames: list[CANFDFrame] = []
        self.stats = {
            'total_frames': 0,
            'extended_frames': 0,
            'brs_frames': 0,
            'esi_error': 0,
            'errors': 0,
        }

    def add_frame(self, frame: CANFDFrame) -> None:
        """Add a CAN-FD frame to analysis."""
        self.frames.append(frame)
        self.stats['total_frames'] += 1

        if frame.is_extended:
            self.stats['extended_frames'] += 1
        if frame.is_brs:
            self.stats['brs_frames'] += 1
        if frame.is_esi:
            self.stats['esi_error'] += 1

    def get_protocol_distribution(self) -> dict:
        """Get distribution of standard vs extended frames."""
        standard = sum(1 for f in self.frames if not f.is_extended)
        extended = sum(1 for f in self.frames if f.is_extended)
        return {
            'standard': standard,
            'extended': extended,
            'standard_percent': (standard / len(self.frames) * 100) if self.frames else 0,
            'extended_percent': (extended / len(self.frames) * 100) if self.frames else 0,
        }

    def get_data_length_distribution(self) -> dict:
        """Get distribution of data lengths."""
        lengths = {}
        for frame in self.frames:
            dlen = frame.data_len
            lengths[dlen] = lengths.get(dlen, 0) + 1
        return lengths

    def get_id_distribution(self, top_n: int = 10) -> list:
        """Get most common CAN IDs."""
        from collections import Counter
        ids = [f.can_id for f in self.frames]
        counter = Counter(ids)
        return counter.most_common(top_n)

    def detect_anomalies(self) -> list:
        """Detect anomalous CAN-FD patterns."""
        anomalies = []

        # Check for unusual data lengths
        for frame in self.frames:
            if frame.data_len > 32:
                anomalies.append({
                    'type': 'large_frame',
                    'can_id': frame.can_id_hex,
                    'data_len': frame.data_len,
                    'message': f'Unusually large CAN-FD frame: {frame.data_len} bytes',
                })

            # Check for potential bus-off due to many errors
            if frame.is_esi:
                anomalies.append({
                    'type': 'error_passive',
                    'can_id': frame.can_id_hex,
                    'message': 'Frame sent by error-passive node',
                })

        return anomalies

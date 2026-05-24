"""
UDS Protocol (Unified Diagnostic Services) — ISO 14229-1.

Implements the diagnostic communication protocol used in automotive ECUs:
- Diagnostic session management
- ECU reset and key-off
- Read/Write Data by Identifier (DID/RID)
- Read Memory by Address
- Routine Control (start/stop/results)
- IO Control by Identifier
- DTC (Diagnostic Trouble Code) management
- Security Access (seed/key)
- Communication Control

Transport layers: CAN (ISO 15765-2) or LIN

Integration: Works above CAN for diagnostic communication between
test equipment and ECU. Used for ECU programming, configuration, and fault diagnosis.
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


# ─── UDS Constants ──────────────────────────────────────────────────

# ISO 14229-1 Session Types
class DiagnosticSessionType(int, Enum):
    DEFAULT_SESSION = 0x01
    PROGRAMMING_SESSION = 0x02
    EXTENDED_DIAGNOSTIC = 0x03
    SAFETY_SYSTEM = 0x04


# ISO 14229-1 Response Codes
class UDSNegativeResponse(int, Enum):
    GENERAL_REJECT = 0x10
    SERVICE_NOT_SUPPORTED = 0x11
    SUB_FUNCTION_NOT_SUPPORTED = 0x12
    INCORRECT_MESSAGE_LENGTH = 0x13
    RESPONSE_TOO_LONG = 0x14
    BUSY_REPEAT_REQUEST = 0x21
    CONDITIONS_NOT_CORRECT = 0x22
    REQUEST_SEQUENCE_ERROR = 0x24
    NO_RESPONSE_FROM_SUBNET = 0x25
    FAILURE_PREVENTS_EXECUTION = 0x26
    REQUEST_OUT_OF_RANGE = 0x31
    SECURITY_ACCESS_DENIED = 0x33
    INVALID_KEY = 0x35
    EXCEEDED_NUMBER_OF_ATTEMPTS = 0x36
    REQUIRED_TIME_DELAY_NOT_EXPIRED = 0x37
    UPLOAD_DOWNLOAD_NOT_ACCEPTED = 0x70
    TRANSFER_DATA_SUSPENDED = 0x71
    GENERAL_PROGRAMMING_FAILURE = 0x72
    WRONG_BLOCK_SEQUENCE_COUNTER = 0x73
    REQUEST_CORRECTLY_RECEIVED_PENDING = 0x78
    SUB_FUNCTION_NOT_SUPPORTED_IN_SESSION = 0x7E
    SERVICE_NOT_SUPPORTED_IN_SESSION = 0x7F

    @property
    def description(self) -> str:
        descriptions = {
            0x10: "General Reject",
            0x11: "Service Not Supported",
            0x12: "Sub-Function Not Supported",
            0x13: "Incorrect Message Length/Invalid Format",
            0x14: "Response Too Long",
            0x21: "Busy — Repeat Request",
            0x22: "Conditions Not Correct",
            0x24: "Request Sequence Error",
            0x25: "No Response From Sub-Network Component",
            0x26: "Failure Prevents Execution",
            0x31: "Request Out Of Range",
            0x33: "Security Access Denied",
            0x35: "Invalid Key",
            0x36: "Exceeded Number Of Attempts",
            0x37: "Required Time Delay Not Expired",
            0x70: "Upload/Download Not Accepted",
            0x71: "Transfer Data Suspended",
            0x72: "General Programming Failure",
            0x73: "Wrong Block Sequence Counter",
            0x78: "Request Correctly Received — Response Pending",
            0x7E: "Sub-Function Not Supported In Active Session",
            0x7F: "Service Not Supported In Active Session",
        }
        return descriptions.get(self.value, "Unknown")


# Standard UDS Service IDs
class UDSServiceID(int, Enum):
    DIAGNOSTIC_SESSION_CONTROL = 0x10
    ECU_RESET = 0x11
    CLEAR_DIAGNOSTIC_INFORMATION = 0x14
    READ_DTC_INFORMATION = 0x19
    READ_DATA_BY_IDENTIFIER = 0x22
    READ_MEMORY_BY_ADDRESS = 0x23
    SECURITY_ACCESS = 0x27
    COMMUNICATION_CONTROL = 0x28
    READ_TIMEOUT = 0x29
    TESTER_PRESENT = 0x3E
    CONTROL_DTC_SETTING = 0x85
    RESPONSE_PENDING = 0x78
    POSITIVE_RESPONSE_BASE = 0x40  # SID + 0x40


# ─── UDS Messages ─────────────────────────────────────────────────

@dataclass
class UDSMessage:
    """
    A complete UDS diagnostic message.

    Request:
      SID [sub-function] [data...]

    Positive Response:
      (SID + 0x40) [sub-function] [data...]

    Negative Response:
      0x7F SID NRC [data...]
    """
    sid: int                    # Service ID
    sub_function: int | None    # Sub-function (7 bits, bit 7 = suppressPositiveResponse)
    data: bytes                 # Additional data
    is_response: bool
    is_negative: bool
    raw: bytes                  # Original raw bytes
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = "client"     # "client" or "ecu"
    session: int = 0x01         # Active diagnostic session

    @property
    def sid_name(self) -> str:
        try:
            return UDSServiceID(self.sid).name
        except ValueError:
            return f"Unknown(0x{self.sid:02X})"

    @property
    def sid_hex(self) -> str:
        return f"0x{self.sid:02X}"

    @property
    def data_hex(self) -> str:
        return " ".join(f"{b:02X}" for b in self.data)

    @property
    def summary(self) -> str:
        resp_type = ""
        if self.is_negative:
            try:
                nrc = UDSNegativeResponse(self.data[0])
                resp_type = f"NACK({nrc.name})"
            except ValueError:
                resp_type = f"NACK(0x{self.data[0]:02X})"
        elif self.is_response:
            resp_type = "ACK"

        sf = f" sf=0x{self.sub_function:02X}" if self.sub_function is not None else ""
        return (
            f"[{self.timestamp.strftime('%H:%M:%S')}] "
            f"{self.source.upper()} {self.sid_name}{sf} "
            f"{resp_type} DATA={self.data_hex if self.data else ''}"
        )


# ─── UDS Session ──────────────────────────────────────────────────

@dataclass
class UDSRequest:
    """A UDS client request."""
    service: UDSServiceID
    sub_function: int | None = None
    data: bytes = b""
    suppress_response: bool = False
    timeout_ms: float = 3000.0


@dataclass
class UDSResponse:
    """A response from the ECU."""
    request: UDSRequest
    success: bool
    positive: bool
    negative_code: UDSNegativeResponse | None
    data: bytes
    pending: bool = False
    error_message: str | None = None

    @property
    def is_positive(self) -> bool:
        return self.positive and not self.pending

    @property
    def dtc_count(self) -> int | None:
        """Extract DTC count if this is a ReadDTC response."""
        if self.request.service == UDSServiceID.READ_DTC_INFORMATION:
            if len(self.data) >= 2:
                return self.data[1]
        return None


# ─── DTC Management ────────────────────────────────────────────────

class DTCStatus:
    """DTC status byte (ISO 14229-1 Table 254)."""

    TEST_FAILED = 0x01           # DTC test failed this operation cycle
    TEST_FAILED_THIS_OP = 0x02    # DTC test failed this monitoring cycle
    PENDING_DTC = 0x04           # DTC test failed since last clear
    CONFIRMED_DTC = 0x08         # DTC confirmed (failed for N cycles)
    TEST_NOT_COMPLETED = 0x10    # DTC test not completed since last clear
    TEST_NOT_COMPLETED_SINCE_CLEAR = 0x20  # DTC test never completed since clear
    FAILED_THIS_OPERATION_CYCLE = 0x40  # DTC failed this operation cycle
    WARNING_INDICATOR = 0x80     # Warning indicator requested


@dataclass
class DTC:
    """
    Diagnostic Trouble Code.

    Format: 3 bytes (24-bit SAE J2012-DA)
    - High byte: Category (00=Powertrain, 01=Chassis, 10=Body, 11=Network)
    - Middle byte: Fault system
    - Low byte: Fault item
    """
    code: int         # 24-bit DTC
    status: int        # 8-bit status byte
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def code_hex(self) -> str:
        return f"0x{self.code:06X}"

    @property
    def category(self) -> str:
        categories = {0: "Powertrain", 1: "Chassis", 2: "Body", 3: "Network"}
        return categories.get((self.code >> 16) & 0x03, "Unknown")

    @property
    def is_active(self) -> bool:
        """DTC is active if test failed or pending."""
        return bool(self.status & (DTCStatus.TEST_FAILED | DTCStatus.PENDING_DTC))

    @property
    def is_confirmed(self) -> bool:
        return bool(self.status & DTCStatus.CONFIRMED_DTC)

    def status_bits(self) -> dict[str, bool]:
        return {
            "test_failed": bool(self.status & DTCStatus.TEST_FAILED),
            "failed_this_op": bool(self.status & DTCStatus.TEST_FAILED_THIS_OP),
            "pending": bool(self.status & DTCStatus.PENDING_DTC),
            "confirmed": bool(self.status & DTCStatus.CONFIRMED_DTC),
            "test_not_completed": bool(self.status & DTCStatus.TEST_NOT_COMPLETED),
            "failed_since_clear": bool(self.status & DTCStatus.TEST_NOT_COMPLETED_SINCE_CLEAR),
            "warning_indicator": bool(self.status & DTCStatus.WARNING_INDICATOR),
        }

    def get_summary(self) -> str:
        active = "ACTIVE" if self.is_active else "PASSIVE"
        confirmed = "CONFIRMED" if self.is_confirmed else ""
        return (
            f"DTC {self.code_hex} [{active}] [{confirmed}] "
            f"Status=0x{self.status:02X} "
            f"{self.category}"
        )


# ─── UDS Client ───────────────────────────────────────────────────

@dataclass
class UDSClientConfig:
    """Configuration for UDS client."""
    ecu_address: int = 0x01       # Target ECU address
    tester_address: int = 0xF4    # Diagnostic tester address
    session: DiagnosticSessionType = DiagnosticSessionType.DEFAULT_SESSION
    security_level: int = 0       # 0=locked, >0=unlocked
    p2_server_max_ms: int = 50    # Positive response timeout
    p2_star_max_ms: int = 5000    # Response pending timeout
    tx_can_id: int = 0x700 + 0x01  # CAN TX ID (functional or physical)


class UDSClient:
    """
    UDS diagnostic client for ECU communication.

    Implements ISO 14229-1 diagnostic sessions over CAN (ISO 15765-2).

    Usage:
        client = UDSClient(UDSClientConfig(ecu_address=0x01))
        await client.connect()

        # Switch to programming session
        resp = await client.diagnostic_session_control(DiagnosticSessionType.PROGRAMMING_SESSION)

        # Unlock security
        seed = await client.security_access(0x01)  # Request seed
        key = compute_key(seed)
        await client.security_access(0x02, key)   # Send key

        # Read DID
        resp = await client.read_data_by_id(0xF190)  # VIN
        print(resp.data.hex())

        # Read DTCs
        dtcs = await client.read_dtc_info(0x02)  # ReportDTCByStatusMask
        for dtc in dtcs:
            print(dtc.get_summary())

        await client.disconnect()
    """

    def __init__(self, config: UDSClientConfig | None = None):
        self.config = config or UDSClientConfig()
        self._session = self.config.session
        self._security = self.config.security_level
        self._connected = False

    async def connect(self) -> None:
        """Establish connection to ECU."""
        self._connected = True
        logger.info("uds_connected", ecu=self.config.ecu_address)

    async def disconnect(self) -> None:
        """Disconnect from ECU."""
        self._connected = False
        logger.info("uds_disconnected")

    # ─── Diagnostic Session Control (0x10) ──────────────────────────

    async def diagnostic_session_control(
        self,
        session_type: DiagnosticSessionType,
    ) -> UDSResponse:
        """
        Switch diagnostic session.

        Args:
            session_type: DEFAULT_SESSION, PROGRAMMING_SESSION, EXTENDED_DIAGNOSTIC

        Returns:
            UDSResponse
        """
        sid = UDSServiceID.DIAGNOSTIC_SESSION_CONTROL
        req = UDSRequest(service=sid, sub_function=session_type.value)

        raw = bytes([sid, session_type.value])
        msg = UDSMessage(
            sid=sid, sub_function=session_type.value,
            data=b"", is_response=False, is_negative=False, raw=raw,
            source="client",
        )

        response = await self._send_and_receive(msg, req)

        if response.positive:
            self._session = session_type

        return response

    # ─── ECU Reset (0x11) ───────────────────────────────────────────

    async def ecu_reset(self, reset_type: int = 0x01) -> UDSResponse:
        """
        Reset the ECU.

        Args:
            reset_type: 0x01=hardReset, 0x02=keyOffOn, 0x03=softReset,
                       0x04=enableRapidPowerShutdown, 0x05=disableRapidPowerShutdown

        Returns:
            UDSResponse
        """
        sid = UDSServiceID.ECU_RESET
        req = UDSRequest(service=sid, sub_function=reset_type)

        raw = bytes([sid, reset_type])
        msg = UDSMessage(
            sid=sid, sub_function=reset_type,
            data=b"", is_response=False, is_negative=False, raw=raw,
            source="client",
        )

        return await self._send_and_receive(msg, req)

    # ─── Read Data By Identifier (0x22) ────────────────────────────

    async def read_data_by_id(
        self,
        did: int,
    ) -> UDSResponse:
        """
        Read data by Data Identifier (DID).

        Standard DIDs:
        - 0xF190: Vehicle Identification Number (VIN)
        - 0xF191: Application Software Identification
        - 0xF192: ECU Hardware Number
        - 0xF194: System Supplier Identifier
        - 0xF198: System Name

        Args:
            did: 2-byte Data Identifier

        Returns:
            UDSResponse with data bytes
        """
        sid = UDSServiceID.READ_DATA_BY_IDENTIFIER
        did_bytes = struct.pack(">H", did)  # Big-endian

        req = UDSRequest(service=sid, data=did_bytes)
        msg = UDSMessage(
            sid=sid, sub_function=None,
            data=did_bytes, is_response=False, is_negative=False, raw=bytes([sid]) + did_bytes,
            source="client",
        )

        return await self._send_and_receive(msg, req)

    async def read_data_by_id_batch(
        self,
        dids: list[int],
    ) -> list[UDSResponse]:
        """Read multiple DIDs in parallel requests."""
        results = []
        for did in dids:
            resp = await self.read_data_by_id(did)
            results.append(resp)
        return results

    # ─── Write Data By Identifier (0x2E) ──────────────────────────

    async def write_data_by_id(
        self,
        did: int,
        data: bytes,
    ) -> UDSResponse:
        """
        Write data to a DID.

        Args:
            did: 2-byte Data Identifier
            data: Data bytes to write

        Returns:
            UDSResponse
        """
        sid = 0x2E  # Write DID (not in UDSServiceID enum)
        did_bytes = struct.pack(">H", did)
        payload = did_bytes + data

        req = UDSRequest(service=UDSServiceID.READ_DATA_BY_IDENTIFIER, data=payload)
        msg = UDSMessage(
            sid=sid, sub_function=None,
            data=payload, is_response=False, is_negative=False, raw=bytes([sid]) + payload,
            source="client",
        )

        return await self._send_and_receive(msg, req)

    # ─── Read Memory By Address (0x23) ─────────────────────────────

    async def read_memory_by_address(
        self,
        address: int,
        length: int,
        memory_size: int = 1,
    ) -> UDSResponse:
        """
        Read memory at a specific address.

        Args:
            address: Memory address (2-4 bytes, MSB first)
            length: Number of bytes to read
            memory_size: Address/length size in bytes (1, 2, or 3)

        Returns:
            UDSResponse with memory bytes
        """
        sid = UDSServiceID.READ_MEMORY_BY_ADDRESS

        if memory_size == 2:
            addr_bytes = struct.pack(">H", address)
        elif memory_size == 3:
            addr_bytes = bytes([(address >> 16) & 0xFF, (address >> 8) & 0xFF, address & 0xFF])
        else:
            addr_bytes = bytes([address & 0xFF])

        len_bytes = bytes([length])

        payload = addr_bytes + len_bytes
        req = UDSRequest(service=sid, data=payload)
        msg = UDSMessage(
            sid=sid, sub_function=None,
            data=payload, is_response=False, is_negative=False, raw=bytes([sid]) + payload,
            source="client",
        )

        return await self._send_and_receive(msg, req)

    # ─── Security Access (0x27) ────────────────────────────────────

    async def security_access(
        self,
        sub_function: int,
        key: int | None = None,
    ) -> UDSResponse:
        """
        Security access — request seed or send key.

        Args:
            sub_function: Odd (0x01, 0x03...) = request seed
                          Even (0x02, 0x04...) = send key
            key: Key to send (required for even sub_function)

        Returns:
            UDSResponse with seed (for odd) or success (for even)
        """
        sid = UDSServiceID.SECURITY_ACCESS
        payload = bytes([sub_function])
        if key is not None:
            payload += struct.pack(">I", key)  # 4-byte key

        req = UDSRequest(service=sid, sub_function=sub_function, data=payload if key else b"")
        msg = UDSMessage(
            sid=sid, sub_function=sub_function,
            data=payload, is_response=False, is_negative=False, raw=bytes([sid]) + payload,
            source="client",
        )

        resp = await self._send_and_receive(msg, req)

        if resp.positive and (sub_function & 0x01) == 1:
            # Request seed — extract seed from response
            pass

        if resp.positive and (sub_function & 0x01) == 0:
            self._security = sub_function // 2

        return resp

    # ─── DTC Operations ─────────────────────────────────────────────

    async def clear_dtc(
        self,
        dtc_mask: int = 0xFFFFFF,
        group: int = 0x01,
    ) -> UDSResponse:
        """
        Clear DTCs.

        Args:
            dtc_mask: DTC mask (0xFFFFFF = all DTCs)
            group: DTC group (0x01=all, 0x02=powertrain, 0x03=chassis, 0x04=body)

        Returns:
            UDSResponse
        """
        sid = UDSServiceID.CLEAR_DIAGNOSTIC_INFORMATION
        # 3-byte DTC mask + 1-byte group
        payload = struct.pack(">I", dtc_mask)[:3] + bytes([group])

        req = UDSRequest(service=sid, data=payload)
        msg = UDSMessage(
            sid=sid, sub_function=None,
            data=payload, is_response=False, is_negative=False, raw=bytes([sid]) + payload,
            source="client",
        )

        return await self._send_and_receive(msg, req)

    async def read_dtc_info(
        self,
        report_type: int = 0x02,
        dtc_status_mask: int = 0xFF,
    ) -> list[DTC]:
        """
        Read DTC information.

        Args:
            report_type: 0x01=numberOfDTCByStatusMask,
                         0x02=DTCByStatusMask,
                         0x04=DTCSnapshotIdentification,
                         0x06=DTCStoredData
            dtc_status_mask: Status mask to filter DTCs

        Returns:
            List of DTC objects
        """
        sid = UDSServiceID.READ_DTC_INFORMATION
        payload = bytes([report_type, dtc_status_mask])

        req = UDSRequest(service=sid, data=payload)
        msg = UDSMessage(
            sid=sid, sub_function=None,
            data=payload, is_response=False, is_negative=False, raw=bytes([sid]) + payload,
            source="client",
        )

        resp = await self._send_and_receive(msg, req)

        dtcs: list[DTC] = []
        if resp.positive:
            data = resp.data[1:]  # Skip first byte (reportType)
            offset = 0
            while offset + 4 <= len(data):
                dtc_code = int.from_bytes(data[offset:offset+3], "big")
                status = data[offset + 3]
                dtcs.append(DTC(code=dtc_code, status=status))
                offset += 4

        return dtcs

    # ─── Routine Control (0x31) ────────────────────────────────────

    async def routine_control(
        self,
        routine_type: int,  # 0x01=start, 0x02=stop, 0x03=requestResults
        routine_id: int,
        routine_data: bytes = b"",
    ) -> UDSResponse:
        """
        Control a routine (start/stop/check results).

        Args:
            routine_type: 0x01=start, 0x02=stop, 0x03=results
            routine_id: 2-byte routine identifier
            routine_data: Optional routine-specific data

        Returns:
            UDSResponse
        """
        sid = 0x31  # Routine Control
        id_bytes = struct.pack(">H", routine_id)
        payload = bytes([routine_type]) + id_bytes + routine_data

        req = UDSRequest(service=sid, sub_function=routine_type, data=id_bytes + routine_data)
        msg = UDSMessage(
            sid=sid, sub_function=routine_type,
            data=id_bytes + routine_data, is_response=False, is_negative=False,
            raw=bytes([sid]) + payload, source="client",
        )

        return await self._send_and_receive(msg, req)

    # ─── Tester Present (0x3E) ────────────────────────────────────

    async def tester_present(self, suppress: bool = True) -> UDSResponse:
        """
        Keep diagnostic session alive.

        Must be sent every ~2 seconds in non-default sessions.

        Args:
            suppress: True = don't wait for response (sub-function bit 7)

        Returns:
            UDSResponse
        """
        sid = UDSServiceID.TESTER_PRESENT
        sub_function = 0x80 if suppress else 0x00

        req = UDSRequest(service=sid, sub_function=sub_function)
        msg = UDSMessage(
            sid=sid, sub_function=sub_function,
            data=b"", is_response=False, is_negative=False, raw=bytes([sid, sub_function]),
            source="client",
        )

        return await self._send_and_receive(msg, req)

    # ─── Communication Control (0x28) ─────────────────────────────

    async def communication_control(
        self,
        control_type: int,  # 0=enableRx, 1=enableRxAndTx, 2=disableRx, 3=disableRxAndTx
        communication_type: int = 0x03,  # 0x01=normal, 0x02=network, 0x03=all
    ) -> UDSResponse:
        """
        Control ECU communication.

        Args:
            control_type: Enable/disable receive/transmit
            communication_type: Which communication to control

        Returns:
            UDSResponse
        """
        sid = UDSServiceID.COMMUNICATION_CONTROL
        payload = bytes([control_type, communication_type])

        req = UDSRequest(service=sid, sub_function=control_type, data=payload)
        msg = UDSMessage(
            sid=sid, sub_function=control_type,
            data=payload, is_response=False, is_negative=False, raw=bytes([sid]) + payload,
            source="client",
        )

        return await self._send_and_receive(msg, req)

    # ─── Internal ──────────────────────────────────────────────────

    async def _send_and_receive(
        self,
        msg: UDSMessage,
        req: UDSRequest,
    ) -> UDSResponse:
        """
        Send UDS message and receive response.

        In a real implementation, this would send CAN frames via ISO 15765-2
        and receive the response. Here we simulate the protocol structure.

        Args:
            msg: UDS message to send
            req: Original request

        Returns:
            UDSResponse
        """
        logger.info("uds_send", sid=msg.sid_name, data=msg.data_hex)

        # Simulate: build mock response
        # In real implementation: send CAN frames, wait for response
        sid = msg.sid
        response_data = b""

        if self._session == DiagnosticSessionType.PROGRAMMING_SESSION and sid == UDSServiceID.ECU_RESET:
            response_data = bytes([0x02])  # Reset type echo
            logger.info("uds_response_positive", sid=msg.sid_name, session="programming")
            return UDSResponse(
                request=req,
                success=True,
                positive=True,
                negative_code=None,
                data=response_data,
            )

        if sid == UDSServiceID.READ_DATA_BY_IDENTIFIER and len(msg.data) >= 2:
            did = struct.unpack(">H", msg.data[:2])[0]
            if did == 0xF190:
                response_data = bytes(msg.data) + b"1H2VB1234567890123"  # Mock VIN
            else:
                response_data = bytes(msg.data) + b"\x00\x00\x00\x00"
        elif sid == UDSServiceID.READ_DTC_INFORMATION:
            response_data = bytes([0x02, 0x03])  # Mock: 3 DTCs
        elif sid == UDSServiceID.DIAGNOSTIC_SESSION_CONTROL:
            response_data = bytes([msg.sub_function, 0x00, 0x32, 0x01])  # p2Server=50ms, p2*=5000ms
        else:
            response_data = b""

        logger.info("uds_response_positive", sid=msg.sid_name, data=" ".join(f"{b:02X}" for b in response_data))

        return UDSResponse(
            request=req,
            success=True,
            positive=True,
            negative_code=None,
            data=response_data,
        )

    def get_session_info(self) -> dict:
        """Get current session information."""
        session_names = {
            0x01: "Default",
            0x02: "Programming",
            0x03: "Extended",
            0x04: "Safety System",
        }
        return {
            "current_session": session_names.get(self._session.value, "Unknown"),
            "security_level": self._security,
            "connected": self._connected,
            "ecu_address": f"0x{self.config.ecu_address:02X}",
        }

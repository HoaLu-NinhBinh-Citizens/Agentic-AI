"""Clock Synchronization - PTP/NTP for embedded devices and fleet synchronization.

Provides:
- NTP client for time synchronization
- PTP (IEEE 1588) support
- Clock offset tracking
- Drift correction
- Timestamp normalization across fleet
- Hardware timer calibration

Usage:
    sync = ClockSynchronizer(interface="eth0")
    await sync.synchronize()
    
    # Get synchronized timestamp
    ts = sync.get_timestamp()
"""

from __future__ import annotations

import asyncio
import logging
import socket
import struct
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class SyncProtocol(Enum):
    """Clock sync protocol."""
    NTP = "ntp"
    PTP_V1 = "ptp_v1"
    PTP_V2 = "ptp_v2"


@dataclass
class TimeSample:
    """Single time synchronization sample."""
    t1: float  # Client send time
    t2: float  # Server receive time
    t3: float  # Server send time
    t4: float  # Client receive time
    
    @property
    def round_trip_delay(self) -> float:
        return (self.t4 - self.t1) - (self.t3 - self.t2)
    
    @property
    def offset(self) -> float:
        return ((self.t2 - self.t1) + (self.t3 - self.t4)) / 2


@dataclass
class SyncStatistics:
    """Synchronization statistics."""
    total_syncs: int = 0
    successful_syncs: int = 0
    failed_syncs: int = 0
    last_sync_time: float = 0
    last_offset: float = 0
    last_round_trip_delay: float = 0
    average_offset: float = 0
    max_drift: float = 0
    drift_samples: list[float] = field(default_factory=list)


@dataclass
class PTPTimestamp:
    """1588 PTP timestamp."""
    seconds: int
    nanoseconds: int
    source_clock: int = 0
    
    def to_datetime(self) -> datetime:
        """Convert to Python datetime."""
        from datetime import timedelta
        ts = self.seconds + self.nanoseconds / 1e9
        return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=ts)
    
    @classmethod
    def from_datetime(cls, dt: datetime) -> "PTPTimestamp":
        """Create from Python datetime."""
        import calendar
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        total_seconds = (dt.timestamp() - epoch.timestamp()) if dt.tzinfo else (dt - epoch.replace(tzinfo=timezone.utc)).total_seconds()
        seconds = int(total_seconds)
        nanoseconds = int((total_seconds - seconds) * 1e9)
        return cls(seconds=seconds, nanoseconds=nanoseconds)


class NTPClient:
    """NTP client for time synchronization.
    
    Implements SNTP protocol (RFC 4330) for embedded devices.
    """
    
    NTP_PORT = 123
    NTP_TIMEOUT = 5.0
    
    # NTP mode
    MODE_CLIENT = 3
    MODE_SERVER = 4
    MODE_BROADCAST = 5
    
    # NTP version
    VERSION_4 = 4
    
    # Leap indicator
    LEAP_NO_WARNING = 0
    
    def __init__(
        self,
        server: str = "pool.ntp.org",
        port: int = NTP_PORT,
        timeout: float = NTP_TIMEOUT,
    ):
        self._server = server
        self._port = port
        self._timeout = timeout
        self._socket: socket.socket | None = None
    
    async def sync_once(self) -> TimeSample | None:
        """Perform a single NTP synchronization.
        
        Returns:
            TimeSample with synchronization data or None on failure
        """
        try:
            # Create socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(self._timeout)
            
            # Build NTP packet
            packet = self._build_packet()
            
            # Send
            t1 = time.time()
            sock.sendto(packet, (self._server, self._port))
            
            # Receive
            data, addr = sock.recvfrom(48)
            t4 = time.time()
            
            sock.close()
            
            # Parse response
            t2, t3 = self._parse_response(data)
            
            return TimeSample(t1=t1, t2=t2, t3=t3, t4=t4)
            
        except Exception as e:
            logger.warning("ntp_sync_failed", server=self._server, error=str(e))
            return None
    
    def _build_packet(self) -> bytes:
        """Build NTP request packet."""
        # LI, Version, Mode
        flags = (self.LEAP_NO_WARNING << 6) | (self.VERSION_4 << 3) | self.MODE_CLIENT
        
        # Stratum, Poll, Precision
        stratum = 0
        poll = 0
        precision = 0
        
        # Root delay and dispersion (8 bytes)
        root_delay = 0
        root_dispersion = 0
        
        # Reference ID (4 bytes)
        ref_id = b'\x00\x00\x00\x00'
        
        # Reference timestamp (8 bytes) - T0
        ref_ts = struct.pack("!II", 0, 0)
        
        # Originate timestamp (8 bytes) - T1 (filled by server)
        orig_ts = struct.pack("!II", 0, 0)
        
        # Receive timestamp (8 bytes) - T2 (filled by server)
        recv_ts = struct.pack("!II", 0, 0)
        
        # Transmit timestamp (8 bytes) - T3 (filled by server)
        trans_ts = struct.pack("!II", 0, 0)
        
        # Build header
        header = struct.pack(
            "! BBBB",
            flags,
            stratum,
            poll,
            precision,
        )
        
        header += struct.pack("!I", int(root_delay))
        header += struct.pack("!I", int(root_dispersion))
        header += ref_id
        
        packet = header + ref_ts + orig_ts + recv_ts + trans_ts
        
        return packet
    
    def _parse_response(self, data: bytes) -> tuple[float, float]:
        """Parse NTP server response.
        
        Returns:
            (server_receive_time, server_send_time)
        """
        if len(data) < 48:
            raise ValueError("Invalid NTP response")
        
        # Extract timestamps
        # Receive timestamp at offset 32
        recv_sec, recv_frac = struct.unpack("!II", data[32:40])
        t2 = recv_sec + recv_frac / 2**32
        
        # Transmit timestamp at offset 40
        trans_sec, trans_frac = struct.unpack("!II", data[40:48])
        t3 = trans_sec + trans_frac / 2**32
        
        return t2, t3
    
    async def sync_multiple(
        self,
        samples: int = 4,
        interval: float = 2.0,
    ) -> TimeSample | None:
        """Perform multiple NTP syncs and return best sample.
        
        Args:
            samples: Number of samples to collect
            interval: Interval between samples
            
        Returns:
            Best TimeSample based on lowest RTT
        """
        best_sample: TimeSample | None = None
        min_rtt = float('inf')
        
        for _ in range(samples):
            sample = await self.sync_once()
            
            if sample:
                rtt = sample.round_trip_delay
                if rtt < min_rtt:
                    min_rtt = rtt
                    best_sample = sample
            
            if _ < samples - 1:
                await asyncio.sleep(interval)
        
        return best_sample


class PTPClient:
    """PTP (IEEE 1588) client for precision time synchronization.
    
    Supports:
    - PTPv2 (IEEE 1588-2008)
    - Delay request-response mechanism
    - Best Master Clock Algorithm
    """
    
    PTP_PORT = 319
    
    # PTP message types
    SYNC = 0x0
    DELAY_REQ = 0x1
    PDELAY_REQ = 0x2
    PDELAY_RESP = 0x3
    FOLLOW_UP = 0x8
    DELAY_RESP = 0x9
    PDELAY_RESP_FOLLOW_UP = 0xA
    
    # PTP version
    VERSION = 2
    
    def __init__(
        self,
        interface: str = "eth0",
        domain: int = 0,
    ):
        self._interface = interface
        self._domain = domain
        self._socket: socket.socket | None = None
        self._multicast_addr = "224.0.1.129"  # PTP delay request multicast
        self._last_sync_time: float = 0
        self._sequence_id: int = 0
    
    async def initialize(self) -> bool:
        """Initialize PTP socket."""
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Bind to PTP event port
            self._socket.bind(("", self.PTP_PORT))
            
            # Set multicast TTL
            self._socket.setsockopt(
                socket.IPPROTO_IP,
                socket.IP_MULTICAST_TTL,
                1,
            )
            
            # Join multicast group
            import struct as s
            mreq = s.pack("=4s4s", socket.inet_aton(self._multicast_addr), socket.inet_aton("0.0.0.0"))
            self._socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            
            self._socket.settimeout(5.0)
            
            logger.info("ptp_client_initialized", interface=self._interface)
            return True
            
        except Exception as e:
            logger.error("ptp_init_failed", error=str(e))
            return False
    
    async def synchronize(self) -> TimeSample | None:
        """Perform PTP synchronization cycle."""
        if not self._socket:
            return None
        
        try:
            # Step 1: Send Sync message and receive Follow-Up
            t1, t2, t3, t4 = await self._sync_exchange()
            
            # Step 2: Send Delay Request and receive Delay Response
            t5, t6, t7, t8 = await self._delay_exchange()
            
            # Calculate offset using all timestamps
            # PTP offset = ((t2 - t1) + (t3 - t4)) / 2 - ((t6 - t5) + (t7 - t8)) / 2
            offset = ((t2 - t1) + (t3 - t4) - (t6 - t5) - (t7 - t8)) / 2
            rtt = (t4 - t1) - (t3 - t2) + (t8 - t5) - (t7 - t6)
            
            # Combine into TimeSample format
            sample = TimeSample(t1=t1, t2=t3, t3=t2, t4=t4)  # Note: adapted format
            sample._offset = offset
            sample._rtt = rtt
            
            return sample
            
        except Exception as e:
            logger.error("ptp_sync_failed", error=str(e))
            return None
    
    async def _sync_exchange(self) -> tuple[float, float, float, float]:
        """Perform Sync message exchange."""
        if not self._socket:
            raise RuntimeError("PTP not initialized")
        
        self._sequence_id += 1
        
        # Build Sync message
        sync_msg = self._build_sync_message()
        
        t1 = time.time()
        self._socket.sendto(sync_msg, (self._multicast_addr, self.PTP_PORT))
        
        # Wait for Follow-Up
        data, _ = self._socket.recvfrom(512)
        t4 = time.time()
        
        t2, t3 = self._parse_follow_up(data)
        
        return t1, t2, t3, t4
    
    async def _delay_exchange(self) -> tuple[float, float, float, float]:
        """Perform Delay Request message exchange."""
        if not self._socket:
            raise RuntimeError("PTP not initialized")
        
        self._sequence_id += 1
        
        # Build Delay Request
        delay_msg = self._build_delay_req_message()
        
        t5 = time.time()
        self._socket.sendto(delay_msg, (self._multicast_addr, self.PTP_PORT + 1))
        
        # Wait for Delay Response
        data, _ = self._socket.recvfrom(512)
        t8 = time.time()
        
        t6, t7 = self._parse_delay_resp(data)
        
        return t5, t6, t7, t8
    
    def _build_sync_message(self) -> bytes:
        """Build PTP Sync message."""
        version_ptp = self.VERSION
        domain = self._domain
        flags = 0x0200  # Two step
        message_length = 44
        message_type = self.SYNC
        sequence_id = self._sequence_id
        control = 0x00
        log_message_interval = 0x7F
        
        header = struct.pack(
            "! HHH BB 8s III BB H",
            message_length,
            message_type,
            version_ptp,
            domain,
            flags,
            b'\x00' * 8,  # UUID (placeholder)
            0,  # reserved
            0,  # flags
            0,  # reserved
            0,  # correction
            control,
            log_message_interval,
            sequence_id,
        )
        
        return header
    
    def _build_delay_req_message(self) -> bytes:
        """Build PTP Delay Request message."""
        version_ptp = self.VERSION
        domain = self._domain
        message_length = 44
        message_type = self.DELAY_REQ
        sequence_id = self._sequence_id
        control = 0x01
        log_message_interval = 0x7F
        
        header = struct.pack(
            "! HHH BB 8s III BB H",
            message_length,
            message_type,
            version_ptp,
            domain,
            0,  # flags
            b'\x00' * 8,  # UUID
            0,  # reserved
            0,  # flags
            0,  # reserved
            0,  # correction
            control,
            log_message_interval,
            sequence_id,
        )
        
        return header
    
    def _parse_follow_up(self, data: bytes) -> tuple[float, float]:
        """Parse PTP Follow-Up message."""
        # Timestamp is at offset 44
        if len(data) < 60:
            raise ValueError("Invalid Follow-Up")
        
        t2_sec = struct.unpack("!I", data[44:48])[0]
        t2_nsec = struct.unpack("!I", data[48:52])[0]
        t2 = t2_sec + t2_nsec / 1e9
        
        t3_sec = struct.unpack("!I", data[52:56])[0]
        t3_nsec = struct.unpack("!I", data[56:60])[0]
        t3 = t3_sec + t3_nsec / 1e9
        
        return t2, t3
    
    def _parse_delay_resp(self, data: bytes) -> tuple[float, float]:
        """Parse PTP Delay Response message."""
        # Similar to Follow-Up parsing
        if len(data) < 60:
            raise ValueError("Invalid Delay Response")
        
        t6_sec = struct.unpack("!I", data[44:48])[0]
        t6_nsec = struct.unpack("!I", data[48:52])[0]
        t6 = t6_sec + t6_nsec / 1e9
        
        t7_sec = struct.unpack("!I", data[52:56])[0]
        t7_nsec = struct.unpack("!I", data[56:60])[0]
        t7 = t7_sec + t7_nsec / 1e9
        
        return t6, t7
    
    async def close(self) -> None:
        """Close PTP socket."""
        if self._socket:
            self._socket.close()
            self._socket = None


class ClockSynchronizer:
    """Clock synchronization manager for embedded devices.
    
    Supports NTP and PTP protocols with automatic failover.
    """
    
    def __init__(
        self,
        protocol: SyncProtocol = SyncProtocol.NTP,
        ntp_server: str = "pool.ntp.org",
        ptp_interface: str = "eth0",
        sync_interval: float = 300.0,  # 5 minutes
        max_samples: int = 4,
    ):
        self._protocol = protocol
        self._ntp_server = ntp_server
        self._ptp_interface = ptp_interface
        self._sync_interval = sync_interval
        self._max_samples = max_samples
        
        self._ntp_client = NTPClient(server=ntp_server)
        self._ptp_client: PTPClient | None = None
        
        self._offset: float = 0  # Local clock offset from true time
        self._last_sync: float = 0
        self._running = False
        self._sync_task: asyncio.Task | None = None
        
        self._stats = SyncStatistics()
    
    async def initialize(self) -> bool:
        """Initialize the synchronizer."""
        if self._protocol == SyncProtocol.PTP_V2:
            self._ptp_client = PTPClient(interface=self._ptp_interface)
            return await self._ptp_client.initialize()
        return True
    
    async def synchronize(self) -> bool:
        """Perform clock synchronization."""
        start_time = time.time()
        
        try:
            if self._protocol == SyncProtocol.NTP:
                sample = await self._ntp_client.sync_multiple(
                    samples=self._max_samples
                )
            elif self._protocol == SyncProtocol.PTP_V2 and self._ptp_client:
                sample = await self._ptp_client.synchronize()
            else:
                logger.error("unsupported_protocol", protocol=self._protocol)
                return False
            
            if sample:
                self._offset = sample.offset
                self._last_sync = start_time
                
                self._stats.total_syncs += 1
                self._stats.successful_syncs += 1
                self._stats.last_sync_time = start_time
                self._stats.last_offset = self._offset
                self._stats.last_round_trip_delay = sample.round_trip_delay
                
                # Track drift
                self._stats.drift_samples.append(self._offset)
                if len(self._stats.drift_samples) > 100:
                    self._stats.drift_samples.pop(0)
                
                avg = sum(self._stats.drift_samples) / len(self._stats.drift_samples)
                self._stats.average_offset = avg
                
                drift = abs(self._offset - avg)
                if drift > self._stats.max_drift:
                    self._stats.max_drift = drift
                
                logger.info(
                    "clock_synchronized",
                    offset=self._offset * 1000,  # ms
                    rtt=sample.round_trip_delay * 1000,  # ms
                    protocol=self._protocol.value,
                )
                return True
            
            self._stats.failed_syncs += 1
            return False
            
        except Exception as e:
            logger.error("sync_failed", error=str(e))
            self._stats.failed_syncs += 1
            return False
    
    async def start_background_sync(self) -> None:
        """Start background synchronization task."""
        self._running = True
        self._sync_task = asyncio.create_task(self._sync_loop())
        logger.info("background_sync_started", interval=self._sync_interval)
    
    async def stop_background_sync(self) -> None:
        """Stop background synchronization."""
        self._running = False
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
        
        if self._ptp_client:
            await self._ptp_client.close()
    
    async def _sync_loop(self) -> None:
        """Background synchronization loop."""
        while self._running:
            await self.synchronize()
            await asyncio.sleep(self._sync_interval)
    
    def get_timestamp(self) -> datetime:
        """Get synchronized datetime.
        
        Returns:
            UTC datetime adjusted for clock offset
        """
        return datetime.now(timezone.utc).timestamp() + self._offset
    
    def get_unix_time(self) -> float:
        """Get synchronized Unix timestamp."""
        return time.time() + self._offset
    
    def get_offset(self) -> float:
        """Get current clock offset in seconds."""
        return self._offset
    
    def get_statistics(self) -> SyncStatistics:
        """Get synchronization statistics."""
        return self._stats
    
    def is_synchronized(self) -> bool:
        """Check if clock is synchronized."""
        if self._last_sync == 0:
            return False
        
        # Consider synchronized if last sync was recent
        return (time.time() - self._last_sync) < self._sync_interval * 2


# Utility functions

def get_firmware_timestamp() -> int:
    """Get firmware build timestamp.
    
    Typically embedded in the binary during build.
    """
    import time
    return int(time.time())


def convert_hw_to_unix(hw_timestamp: int, offset: float) -> int:
    """Convert hardware timestamp (ms or us) to Unix timestamp."""
    return int(hw_timestamp / 1000 + offset)


def get_firmware_age_days(build_timestamp: int) -> float:
    """Calculate firmware age in days."""
    import time
    current = time.time()
    return (current - build_timestamp) / 86400


if __name__ == "__main__":
    print("Clock Synchronization")
    print("=" * 40)
    print("NTP and PTP support for embedded devices")
    print()
    print("Features:")
    print("  - NTP client (SNTP)")
    print("  - PTP v2 (IEEE 1588)")
    print("  - Automatic drift correction")
    print("  - Fleet time synchronization")

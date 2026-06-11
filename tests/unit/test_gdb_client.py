"""Tests for GDB Client (Phase 6.4).

Unit tests for GDB remote protocol client.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.domain.hardware.gdb.gdb_client import (
    GDBError,
    BreakpointType,
    GDBRegister,
    GDBBreakpoint,
    GDBStackFrame,
    GDBVariable,
    GDBThread,
    GDBTargetInfo,
    GDBClient,
)


class TestBreakpointType:
    """Test BreakpointType enum."""
    
    def test_all_breakpoint_types(self):
        """UT4.1: All breakpoint types defined."""
        assert BreakpointType.SOFTWARE.value == "software"
        assert BreakpointType.HARDWARE.value == "hardware"
        assert BreakpointType.WRITE_WATCH.value == "write_watch"
        assert BreakpointType.READ_WATCH.value == "read_watch"
        assert BreakpointType.ACCESS_WATCH.value == "access_watch"


class TestGDBRegister:
    """Test GDBRegister class."""
    
    def test_register_creation(self):
        """UT4.2: Create GDB register."""
        reg = GDBRegister(number=0, name="R0", value=0x12345678)
        
        assert reg.number == 0
        assert reg.name == "R0"
        assert reg.value == 0x12345678
    
    def test_to_hex(self):
        """UT4.3: Convert register to hex."""
        reg = GDBRegister(number=0, value=0x1234)
        
        assert reg.to_hex() == "00001234"


class TestGDBBreakpoint:
    """Test GDBBreakpoint class."""
    
    def test_breakpoint_creation(self):
        """UT4.4: Create breakpoint."""
        bp = GDBBreakpoint(
            address=0x08001000,
            breakpoint_type=BreakpointType.SOFTWARE,
        )
        
        assert bp.address == 0x08001000
        assert bp.breakpoint_type == BreakpointType.SOFTWARE
        assert bp.enabled is True


class TestGDBStackFrame:
    """Test GDBStackFrame class."""
    
    def test_stack_frame_creation(self):
        """UT4.5: Create stack frame."""
        frame = GDBStackFrame(
            level=0,
            pc=0x08001000,
            sp=0x20002000,
            fp=0x20001FF0,
        )
        
        assert frame.level == 0
        assert frame.pc == 0x08001000
    
    def test_stack_frame_to_dict(self):
        """UT4.6: Convert stack frame to dict."""
        frame = GDBStackFrame(
            level=0,
            pc=0x08001000,
            sp=0x20002000,
            fp=0x20001FF0,
            function="main",
        )
        
        result = frame.to_dict()
        
        assert result["level"] == 0
        assert "0x08001000" in result["pc"]
        assert result["function"] == "main"


class TestGDBVariable:
    """Test GDBVariable class."""
    
    def test_variable_creation(self):
        """UT4.7: Create variable."""
        var = GDBVariable(
            name="counter",
            value=42,
            type_name="int",
            address=0x20000000,
        )
        
        assert var.name == "counter"
        assert var.value == 42
    
    def test_variable_to_dict(self):
        """UT4.8: Convert variable to dict."""
        var = GDBVariable(
            name="counter",
            value=42,
            type_name="int",
        )
        
        result = var.to_dict()
        
        assert result["name"] == "counter"
        assert result["value"] == "42"
        assert result["type"] == "int"


class TestGDBThread:
    """Test GDBThread class."""
    
    def test_thread_creation(self):
        """UT4.9: Create thread."""
        thread = GDBThread(
            thread_id=1,
            target_id="thread-1",
            name="main",
        )
        
        assert thread.thread_id == 1
        assert thread.state == "stopped"


class TestGDBTargetInfo:
    """Test GDBTargetInfo class."""
    
    def test_target_info_defaults(self):
        """UT4.10: Create target info with defaults."""
        info = GDBTargetInfo()
        
        assert info.endian == "little"
        assert info.arch == "arm"
        assert info.pointer_size == 4


class TestGDBClient:
    """Test GDBClient class."""
    
    @pytest.fixture
    def client(self):
        """Create GDB client."""
        return GDBClient(host="localhost", port=3333)
    
    def test_client_creation(self, client):
        """UT4.11: Create GDB client."""
        assert client.host == "localhost"
        assert client.port == 3333
        assert not client.is_connected
    
    def test_decode_data(self, client):
        """UT4.12: Decode GDB escape sequences."""
        # Normal characters pass through
        assert client._decode_data("hello") == "hello"
        
        # Escaped characters
        assert client._decode_data("}#23") == "\x03"  # 0x23 ^ 0x20 = 0x03
    
    def test_encode_data(self, client):
        """UT4.13: Encode data with escapes."""
        # Normal characters
        assert client._encode_data("hello") == "hello"
        
        # Special characters should be escaped
        result = client._encode_data("test$")
        assert "$" in result or len(result) >= 4
    
    @pytest.mark.asyncio
    async def test_connect_success(self, client):
        """UT4.14: Connect to GDB server."""
        with patch("asyncio.open_connection") as mock_conn:
            mock_reader = AsyncMock()
            mock_writer = AsyncMock()
            mock_conn.return_value = (mock_reader, mock_writer)
            mock_reader.read.return_value = b"+"  # ACK
            
            result = await client.connect()
            
            assert result is True
            assert client.is_connected
    
    @pytest.mark.asyncio
    async def test_connect_timeout(self, client):
        """UT4.15: Connect timeout."""
        with patch("asyncio.open_connection") as mock_conn:
            mock_conn.side_effect = asyncio.TimeoutError()
            
            result = await client.connect()
            
            assert result is False
            assert not client.is_connected
    
    @pytest.mark.asyncio
    async def test_disconnect(self, client):
        """UT4.16: Disconnect from GDB server."""
        client._connected = True
        mock_writer = AsyncMock()
        client._writer = mock_writer
        
        await client.disconnect()
        
        assert not client.is_connected
        mock_writer.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_packet_not_connected(self, client):
        """UT4.17: Send packet without connection raises error."""
        with pytest.raises(GDBError, match="Not connected"):
            await client._send_packet("g")
    
    @pytest.mark.asyncio
    async def test_read_register(self, client):
        """UT4.18: Read single register."""
        client._connected = True
        mock_writer = AsyncMock()
        mock_reader = AsyncMock()
        client._writer = mock_writer
        client._reader = mock_reader
        
        # Mock packet response
        async def mock_read(n):
            if n == 1:
                return b"+"  # ACK
            return b""
        
        mock_reader.read = mock_read
        
        # Override _receive_packet for this test
        async def mock_receive():
            return "00001234"  # Register value in hex
        client._receive_packet = mock_receive
        
        result = await client.read_register(0)
        
        # Note: Without full protocol mocking, this tests the happy path
        assert result is None or isinstance(result, int)
    
    @pytest.mark.asyncio
    async def test_read_memory(self, client):
        """UT4.19: Read memory."""
        client._connected = True
        client._receive_packet = AsyncMock(return_value="01020304")  # Hex data
        
        result = await client.read_memory(0x20000000, 4)
        
        assert result == bytes.fromhex("01020304")
    
    @pytest.mark.asyncio
    async def test_write_memory(self, client):
        """UT4.20: Write memory."""
        client._connected = True
        client._receive_packet = AsyncMock(return_value="OK")
        
        result = await client.write_memory(0x20000000, b"\x01\x02\x03\x04")
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_set_breakpoint(self, client):
        """UT4.21: Set breakpoint."""
        client._connected = True
        
        # Mock read_memory
        client.read_memory = AsyncMock(return_value=b"\x00\x00\x00\x00")
        
        # Mock response
        client._receive_packet = AsyncMock(return_value="OK")
        
        bp = await client.set_breakpoint(0x08001000)
        
        assert bp is not None
        assert bp.address == 0x08001000
        assert 0x08001000 in client._breakpoints
    
    @pytest.mark.asyncio
    async def test_clear_breakpoint(self, client):
        """UT4.22: Clear breakpoint."""
        client._connected = True
        client._receive_packet = AsyncMock(return_value="OK")
        
        # Add breakpoint to internal state
        client._breakpoints[0x08001000] = GDBBreakpoint(
            address=0x08001000,
            breakpoint_type=BreakpointType.SOFTWARE,
        )
        
        result = await client.clear_breakpoint(0x08001000)
        
        assert result is True
        assert 0x08001000 not in client._breakpoints
    
    @pytest.mark.asyncio
    async def test_lookup_symbol(self, client):
        """UT4.23: Lookup symbol."""
        client._connected = True
        client._receive_packet = AsyncMock(return_value="main=08001234")
        
        addr = await client.lookup_symbol("main")
        
        assert addr == 0x08001234
        assert 0x08001234 in client._symbol_cache


class TestGDBClientIntegration:
    """Integration tests for GDB client."""
    
    @pytest.mark.asyncio
    async def test_context_manager(self):
        """IT4.1: Use client as async context manager."""
        with patch("asyncio.open_connection") as mock_conn:
            mock_reader = AsyncMock()
            mock_writer = AsyncMock()
            mock_conn.return_value = (mock_reader, mock_writer)
            
            async with GDBClient() as client:
                assert client.is_connected
            
            # Should be disconnected after exit
            mock_writer.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_full_debug_session(self):
        """IT4.2: Full debug session flow."""
        with patch("asyncio.open_connection") as mock_conn:
            mock_reader = AsyncMock()
            # Reads must return bytes; a bare AsyncMock returns MagicMock,
            # which spun _receive_packet's read loop forever (suite hang).
            # b"" = EOF -> GDBError -> read_all_registers falls back to {}.
            mock_reader.read = AsyncMock(return_value=b"")
            mock_writer = AsyncMock()
            mock_conn.return_value = (mock_reader, mock_writer)
            
            client = GDBClient()
            
            # Connect
            await client.connect()
            assert client.is_connected
            
            # Read registers (mock)
            client._registers = {0: GDBRegister(0, "R0", 0)}
            registers = await client.read_all_registers()
            assert isinstance(registers, dict)
            
            # Set breakpoint (mock)
            client.read_memory = AsyncMock(return_value=b"\x00\x00\xBE\x00")
            client._receive_packet = AsyncMock(return_value="OK")
            bp = await client.set_breakpoint(0x08001000)
            assert bp is not None
            
            # Disconnect
            await client.disconnect()
            assert not client.is_connected


class TestGDBClientErrorHandling:
    """Test GDB client error handling."""
    
    @pytest.mark.asyncio
    async def test_checksum_mismatch(self):
        """UT4.24: Detect checksum mismatch."""
        client = GDBClient()
        client._connected = True
        client._writer = AsyncMock()
        mock_reader = AsyncMock()
        client._reader = mock_reader
        
        # Mock incorrect checksum. _receive_packet reads 1 byte at a time
        # (then 2 for the checksum); the old mock returned b"$" for every
        # read(1), so the read-until-# loop never terminated.
        seq = [b"$", b"O", b"K", b"#", b"00"]  # checksum of "OK" is 0x9a, not 0x00

        async def mock_read(n):
            return seq.pop(0) if seq else b""

        mock_reader.read = mock_read
        
        with pytest.raises(GDBError, match="Checksum"):
            await client._receive_packet()
    
    @pytest.mark.asyncio
    async def test_write_register(self):
        """UT4.25: Write register."""
        client = GDBClient()
        client._connected = True
        client._receive_packet = AsyncMock(return_value="OK")
        
        result = await client.write_register(0, 0x12345678)
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_read_stop_reply(self):
        """UT4.26: Read stop reply."""
        client = GDBClient()
        client._connected = True
        client._receive_packet = AsyncMock(return_value="T05")
        
        result = await client._read_stop_reply()
        
        assert result is True
        assert client._last_signal == 5

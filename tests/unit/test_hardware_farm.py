"""Tests for hardware farm manager."""

import pytest
from src.infrastructure.hil.hardware_farm import (
    BoardHealth,
    BoardLease,
    BoardSpec,
    BoardState,
    BoardStatus,
    HardwareFarmManager,
)


class TestBoardSpec:
    def test_board_spec_creation(self):
        spec = BoardSpec(
            board_id="test_001",
            board_type="STM32F407VG",
            probe_type="J-Link",
        )
        assert spec.board_id == "test_001"
        assert spec.board_type == "STM32F407VG"
        assert spec.probe_type == "J-Link"


class TestBoardStatus:
    def test_board_status_default(self):
        status = BoardStatus(board_id="test_001")
        assert status.board_id == "test_001"
        assert status.state == BoardState.OFFLINE
        assert status.health == BoardHealth.UNKNOWN

    def test_success_rate(self):
        status = BoardStatus(
            board_id="test_001",
            successful_tests=8,
            failed_tests=2,
        )
        assert status.success_rate == 0.8

    def test_is_available(self):
        status = BoardStatus(
            board_id="test_001",
            state=BoardState.AVAILABLE,
            health=BoardHealth.HEALTHY,
        )
        assert status.is_available is True


class TestHardwareFarmManager:
    def test_register_board(self):
        farm = HardwareFarmManager()
        spec = BoardSpec(
            board_id="board_001",
            board_type="STM32F407VG",
            probe_type="J-Link",
        )
        
        farm.register_board(spec)
        assert farm.get_board("board_001") is not None
        assert farm.get_status("board_001") is not None

    def test_unregister_board(self):
        farm = HardwareFarmManager()
        spec = BoardSpec(board_id="board_001", board_type="STM32F407VG", probe_type="J-Link")
        
        farm.register_board(spec)
        assert farm.unregister_board("board_001") is True
        assert farm.get_board("board_001") is None

    def test_acquire_board(self):
        farm = HardwareFarmManager()
        spec = BoardSpec(board_id="board_001", board_type="STM32F407VG", probe_type="J-Link")
        
        farm.register_board(spec)
        farm._status["board_001"].state = BoardState.AVAILABLE
        farm._status["board_001"].health = BoardHealth.HEALTHY
        
        board = farm.acquire_board("user1", "test purpose")
        assert board is not None
        assert board.board_id == "board_001"

    def test_release_board(self):
        farm = HardwareFarmManager()
        spec = BoardSpec(board_id="board_001", board_type="STM32F407VG", probe_type="J-Link")
        
        farm.register_board(spec)
        farm._status["board_001"].state = BoardState.IN_USE
        
        assert farm.release_board("board_001") is True
        assert farm.get_status("board_001").state == BoardState.AVAILABLE

    def test_record_test_result(self):
        farm = HardwareFarmManager()
        spec = BoardSpec(board_id="board_001", board_type="STM32F407VG", probe_type="J-Link")
        
        farm.register_board(spec)
        farm.record_test_result("board_001", success=True, duration_minutes=5)
        
        status = farm.get_status("board_001")
        assert status.total_tests == 1
        assert status.successful_tests == 1

    def test_get_statistics(self):
        farm = HardwareFarmManager()
        farm.register_board(BoardSpec(board_id="b1", board_type="STM32", probe_type="J-Link"))
        
        stats = farm.get_statistics()
        assert "total_boards" in stats
        assert stats["total_boards"] == 1

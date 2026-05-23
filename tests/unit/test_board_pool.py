"""Tests for board pool."""

import pytest
from src.infrastructure.hil.board_pool import (
    BoardPool,
    BoardPoolConfig,
    PoolState,
    PoolStatistics,
)


class TestBoardPoolConfig:
    def test_default_config(self):
        config = BoardPoolConfig()
        assert config.min_boards == 2
        assert config.max_boards == 10
        assert config.auto_replacement_enabled is True


class TestBoardPool:
    def test_pool_creation(self):
        pool = BoardPool()
        assert pool.state == PoolState.HEALTHY
        assert pool.available_count == 0

    def test_add_board(self):
        pool = BoardPool()
        result = pool.add_board("board_001")
        assert result is True
        assert pool.available_count == 1

    def test_add_reserve_board(self):
        pool = BoardPool()
        result = pool.add_board("reserve_001", to_reserve=True)
        assert result is True

    def test_acquire_board(self):
        pool = BoardPool()
        pool.add_board("board_001")
        
        board_id = pool.acquire_board("user1", "test purpose")
        assert board_id == "board_001"
        assert pool.available_count == 0

    def test_acquire_no_boards_available(self):
        pool = BoardPool()
        board_id = pool.acquire_board("user1")
        assert board_id is None

    def test_release_board(self):
        pool = BoardPool()
        pool.add_board("board_001")
        pool.acquire_board("user1")
        
        result = pool.release_board("board_001")
        assert result is True
        assert pool.available_count == 1

    def test_mark_failed_with_replacement(self):
        pool = BoardPool()
        pool.add_board("board_001")
        pool.add_board("reserve_001", to_reserve=True)
        
        initial_available = pool.available_count
        pool.mark_failed("board_001", "Hardware failure")
        
        # Reserve should have been moved to available
        assert pool.available_count == initial_available

    def test_get_statistics(self):
        pool = BoardPool()
        pool.add_board("board_001")
        pool.add_board("board_002")
        
        stats = pool.get_statistics()
        assert isinstance(stats, PoolStatistics)
        assert stats.total_boards == 2
        assert stats.available == 2

    def test_remove_board(self):
        pool = BoardPool()
        pool.add_board("board_001")
        
        result = pool.remove_board("board_001")
        assert result is True
        assert pool.available_count == 0

    def test_pool_state(self):
        config = BoardPoolConfig(min_boards=3)
        pool = BoardPool(config)
        pool.add_board("board_001")
        
        stats = pool.get_statistics()
        assert stats.total_boards == 1

"""Unit tests for state machine."""

import asyncio
import pytest

from src.infrastructure.cache.tool.state_machine import KeyStateMachine, StateManager, TransitionError
from src.infrastructure.cache.tool.types import KeyState


class TestKeyStateMachine:
    """Tests for KeyStateMachine."""

    @pytest.fixture
    def machine(self):
        """Create a fresh state machine."""
        return KeyStateMachine("test_key")

    def test_initial_state(self, machine):
        """Test initial state is MISS."""
        assert machine.state == KeyState.MISS

    @pytest.mark.asyncio
    async def test_miss_to_loading(self):
        """Test transition from MISS to LOADING."""
        machine = KeyStateMachine("test_key")
        result = await machine.transition("request", KeyState.LOADING)
        assert result is True
        assert machine.state == KeyState.LOADING

    @pytest.mark.asyncio
    async def test_loading_to_fresh(self):
        """Test transition from LOADING to FRESH."""
        machine = KeyStateMachine("test_key")
        await machine.transition("request", KeyState.LOADING)
        result = await machine.transition("success", KeyState.FRESH)
        assert result is True
        assert machine.state == KeyState.FRESH

    @pytest.mark.asyncio
    async def test_fresh_to_stale(self):
        """Test transition from FRESH to STALE."""
        machine = KeyStateMachine("test_key")
        await machine.transition("request", KeyState.LOADING)
        await machine.transition("success", KeyState.FRESH)
        result = await machine.transition("expired", KeyState.STALE)
        assert result is True
        assert machine.state == KeyState.STALE

    @pytest.mark.asyncio
    async def test_stale_to_refreshing(self):
        """Test transition from STALE to REFRESHING."""
        machine = KeyStateMachine("test_key")
        await machine.transition("request", KeyState.LOADING)
        await machine.transition("success", KeyState.FRESH)
        await machine.transition("expired", KeyState.STALE)
        result = await machine.transition("refresh", KeyState.REFRESHING)
        assert result is True
        assert machine.state == KeyState.REFRESHING

    @pytest.mark.asyncio
    async def test_refreshing_to_fresh(self):
        """Test transition from REFRESHING to FRESH."""
        machine = KeyStateMachine("test_key")
        await machine.transition("request", KeyState.LOADING)
        await machine.transition("success", KeyState.FRESH)
        await machine.transition("expired", KeyState.STALE)
        await machine.transition("refresh", KeyState.REFRESHING)
        result = await machine.transition("success", KeyState.FRESH)
        assert result is True
        assert machine.state == KeyState.FRESH

    @pytest.mark.asyncio
    async def test_refreshing_to_stale_failure(self):
        """Test transition from REFRESHING to STALE (failure)."""
        machine = KeyStateMachine("test_key")
        await machine.transition("request", KeyState.LOADING)
        await machine.transition("success", KeyState.FRESH)
        await machine.transition("expired", KeyState.STALE)
        await machine.transition("refresh", KeyState.REFRESHING)
        result = await machine.transition("failure", KeyState.STALE)
        assert result is True
        assert machine.state == KeyState.STALE

    @pytest.mark.asyncio
    async def test_any_to_degraded(self):
        """Test transition to DEGRADED from FRESH."""
        machine = KeyStateMachine("test_key")
        await machine.transition("request", KeyState.LOADING)
        await machine.transition("success", KeyState.FRESH)
        result = await machine.transition("overload", KeyState.DEGRADED)
        assert result is True
        assert machine.state == KeyState.DEGRADED

    @pytest.mark.asyncio
    async def test_invalid_transition(self):
        """Test invalid transition raises error."""
        machine = KeyStateMachine("test_key")
        with pytest.raises(TransitionError):
            await machine.transition("invalid", KeyState.FRESH)

    @pytest.mark.asyncio
    async def test_try_transition_invalid(self):
        """Test try_transition returns False for invalid."""
        machine = KeyStateMachine("test_key")
        result = await machine.try_transition("invalid", KeyState.FRESH)
        assert result is False

    @pytest.mark.asyncio
    async def test_force_transition(self):
        """Test force transition bypasses validation."""
        machine = KeyStateMachine("test_key")
        result = await machine.transition("force", KeyState.FRESH, force=True)
        assert result is True
        assert machine.state == KeyState.FRESH

    @pytest.mark.asyncio
    async def test_state_change_callback(self):
        """Test state change callbacks."""
        transitions = []

        def callback(old, new):
            transitions.append((old, new))

        machine = KeyStateMachine("test_key")
        machine.on_state_change(callback)

        await machine.transition("request", KeyState.LOADING)

        assert len(transitions) == 1
        assert transitions[0] == (KeyState.MISS, KeyState.LOADING)


class TestStateManager:
    """Tests for StateManager."""

    @pytest.fixture
    def manager(self):
        """Create a fresh state manager."""
        return StateManager()

    @pytest.mark.asyncio
    async def test_get_machine(self, manager):
        """Test getting/creating state machine."""
        machine = await manager.get_machine("key1")
        assert machine is not None
        assert machine.key == "key1"

        machine2 = await manager.get_machine("key1")
        assert machine is machine2

    @pytest.mark.asyncio
    async def test_get_state(self, manager):
        """Test getting state for key."""
        state = await manager.get_state("key1")
        assert state == KeyState.MISS

    @pytest.mark.asyncio
    async def test_transition(self, manager):
        """Test transitioning state."""
        result = await manager.transition("key1", "request", KeyState.LOADING)
        assert result is True

        state = await manager.get_state("key1")
        assert state == KeyState.LOADING

    @pytest.mark.asyncio
    async def test_enter_degraded(self, manager):
        """Test entering degraded mode."""
        await manager.transition("key1", "request", KeyState.LOADING)
        await manager.transition("key1", "success", KeyState.FRESH)
        await manager.enter_degraded()

        assert manager.is_degraded

        state = await manager.get_state("key1")
        assert state == KeyState.DEGRADED

    @pytest.mark.asyncio
    async def test_try_exit_degraded(self, manager):
        """Test exiting degraded mode."""
        await manager.enter_degraded()
        assert manager.is_degraded

        result = await manager.try_exit_degraded(
            memory_pressure=0.3,
            pending_keys=10,
            error_rate=0.01,
        )
        assert result is True
        assert not manager.is_degraded

    @pytest.mark.asyncio
    async def test_cleanup(self):
        """Test cleanup of old state machines."""
        manager = StateManager()
        
        await manager.transition("key1", "request", KeyState.LOADING)
        await manager.transition("key1", "success", KeyState.FRESH)
        await manager.transition("key2", "request", KeyState.LOADING)
        await manager.transition("key2", "success", KeyState.FRESH)

        import time
        time.sleep(0.1)

        for machine in manager._machines.values():
            machine._last_transition = time.time() - 100

        cleaned = await manager.cleanup(max_age=10)
        assert cleaned == 2

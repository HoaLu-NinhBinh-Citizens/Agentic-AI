"""Recovery Infrastructure - Integration with Phase 6.1 snapshot system.

Phase 6.2: Implements recovery and replay integration:
- Pre-flash snapshot capture
- Rollback to snapshot on failure
- Integration with flash transactions
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PreFlashSnapshot:
    """Captures snapshot before flash operation.
    
    Integrates with Phase 6.1 SnapshotManager.
    Saves rollback capability for flash failures.
    """
    
    snapshot_manager: Any = None  # SnapshotManager from Phase 6.1
    event_bus: Any = None   # EventBus from Phase 6.1
    
    async def capture(
        self,
        target_name: str,
        target_id: str,
        transaction_id: str,
        capture_registers: bool = True,
        capture_memory: bool = True,
        capture_peripherals: bool = True,
    ) -> str | None:
        """Capture pre-flash snapshot.
        
        Args:
            target_name: Target name
            target_id: Target ID
            transaction_id: Associated transaction ID
            capture_registers: Capture CPU registers
            capture_memory: Capture memory regions
            capture_peripherals: Capture peripheral states
        
        Returns:
            Snapshot ID or None if failed
        """
        if not self.snapshot_manager:
            logger.warning("snapshot_manager_not_available")
            return None
        
        try:
            from ..snapshot_manager import RegisterSnapshot, MemoryRegionSnapshot
            
            # Capture registers
            registers = RegisterSnapshot() if capture_registers else None
            
            # Capture key memory regions
            memory_regions = []
            if capture_memory:
                memory_regions = await self._capture_memory_regions()
            
            # Capture peripherals
            peripherals = []
            if capture_peripherals:
                peripherals = await self._capture_peripherals()
            
            # Capture snapshot
            snapshot = await self.snapshot_manager.capture(
                target_name=target_name,
                target_id=target_id,
                registers=registers,
                memory_regions=memory_regions,
                peripherals=peripherals,
                name=f"pre_flash_{transaction_id}",
                captured_by="pre_flash_snapshot",
            )
            
            logger.info(
                "pre_flash_snapshot_captured",
                transaction_id=transaction_id,
                snapshot_id=snapshot.snapshot_id,
                size_bytes=snapshot.get_total_data_size(),
            )
            
            # Publish event
            if self.event_bus:
                from ..event import SnapshotCapturedEvent
                
                event = SnapshotCapturedEvent(
                    snapshot_id=snapshot.snapshot_id,
                    target_name=target_name,
                    capture_time_ms=snapshot.capture_duration_ms,
                    size_bytes=snapshot.get_total_data_size(),
                    is_incremental=False,
                )
                await self.event_bus.publish(event)
            
            return snapshot.snapshot_id
            
        except Exception as e:
            logger.error(
                "pre_flash_snapshot_failed",
                transaction_id=transaction_id,
                error=str(e),
            )
            return None
    
    async def _capture_memory_regions(self) -> list[Any]:
        """Capture key memory regions."""
        from ..snapshot_manager import MemoryRegionSnapshot
        
        regions = [
            MemoryRegionSnapshot(
                name="sram",
                base_address=0x20000000,
                size=128 * 1024,
            ),
        ]
        return regions
    
    async def _capture_peripherals(self) -> list[Any]:
        """Capture key peripheral states."""
        from ..snapshot_manager import PeripheralSnapshot
        
        # Would use probe to read peripheral registers
        return []


@dataclass
class RollbackToSnapshot:
    """Rolls back target to pre-flash snapshot.
    
    Integrates with Phase 6.1 SnapshotManager.restore().
    Used when flash fails to restore target state.
    """
    
    snapshot_manager: Any = None  # SnapshotManager from Phase 6.1
    event_bus: Any = None   # EventBus from Phase 6.1
    
    async def rollback(
        self,
        snapshot_id: str,
        target_name: str,
        reason: str = "",
    ) -> bool:
        """Rollback to snapshot.
        
        Args:
            snapshot_id: Snapshot ID to restore
            target_name: Target name
            reason: Reason for rollback
        
        Returns:
            True if successful
        """
        if not self.snapshot_manager:
            logger.error("snapshot_manager_not_available")
            return False
        
        try:
            # Restore using Phase 6.1 snapshot system
            await self.snapshot_manager.restore(
                snapshot_id=snapshot_id,
                target_name=target_name,
            )
            
            logger.info(
                "rollback_to_snapshot_completed",
                snapshot_id=snapshot_id,
                target_name=target_name,
                reason=reason,
            )
            
            # Publish event
            if self.event_bus:
                from ..event import DomainEvent
                
                event = DomainEvent(
                    event_type="flash.rollback.completed",
                    source="rollback_to_snapshot",
                    data={
                        "snapshot_id": snapshot_id,
                        "target_name": target_name,
                        "reason": reason,
                    },
                )
                await self.event_bus.publish(event)
            
            return True
            
        except Exception as e:
            logger.error(
                "rollback_to_snapshot_failed",
                snapshot_id=snapshot_id,
                target_name=target_name,
                error=str(e),
            )
            
            if self.event_bus:
                from ..event import DomainEvent
                
                event = DomainEvent(
                    event_type="flash.rollback.failed",
                    source="rollback_to_snapshot",
                    data={
                        "snapshot_id": snapshot_id,
                        "target_name": target_name,
                        "error": str(e),
                    },
                )
                await self.event_bus.publish(event)
            
            return False
    
    async def can_rollback(
        self,
        snapshot_id: str,
    ) -> tuple[bool, str]:
        """Check if rollback is possible.
        
        Returns:
            (can_rollback, reason)
        """
        if not self.snapshot_manager:
            return False, "Snapshot manager not available"
        
        try:
            snapshot = await self.snapshot_manager.storage.load(snapshot_id)
            if snapshot:
                return True, ""
            return False, "Snapshot not found"
        except Exception as e:
            return False, str(e)


@dataclass
class RecoveryOrchestrator:
    """Orchestrates recovery operations combining all Phase 6.1/6.2 components.
    
    Coordinates:
    - Pre-flash snapshot
    - Flash transaction
    - Rollback on failure
    - Event publishing
    """
    
    snapshot_manager: Any = None
    event_bus: Any = None
    
    pre_flash: PreFlashSnapshot | None = None
    rollback: RollbackToSnapshot | None = None
    
    def __post_init__(self) -> None:
        """Initialize recovery components."""
        if self.pre_flash is None and self.snapshot_manager:
            self.pre_flash = PreFlashSnapshot(
                snapshot_manager=self.snapshot_manager,
                event_bus=self.event_bus,
            )
        
        if self.rollback is None and self.snapshot_manager:
            self.rollback = RollbackToSnapshot(
                snapshot_manager=self.snapshot_manager,
                event_bus=self.event_bus,
            )
    
    async def prepare_recovery(
        self,
        target_name: str,
        target_id: str,
        transaction_id: str,
    ) -> str | None:
        """Prepare for recovery by capturing pre-flash snapshot.
        
        Returns:
            Snapshot ID
        """
        if not self.pre_flash:
            return None
        
        return await self.pre_flash.capture(
            target_name=target_name,
            target_id=target_id,
            transaction_id=transaction_id,
        )
    
    async def execute_rollback(
        self,
        snapshot_id: str,
        target_name: str,
        reason: str,
    ) -> bool:
        """Execute rollback to pre-flash state.
        
        Returns:
            True if successful
        """
        if not self.rollback:
            return False
        
        return await self.rollback.rollback(
            snapshot_id=snapshot_id,
            target_name=target_name,
            reason=reason,
        )
    
    async def is_recovery_possible(self, snapshot_id: str) -> bool:
        """Check if recovery is possible."""
        if not self.rollback:
            return False
        
        possible, _ = await self.rollback.can_rollback(snapshot_id)
        return possible


@dataclass
class FlashRecoveryWorkflow:
    """Complete flash workflow with recovery integration.
    
    Combines:
    - Lock acquisition
    - Pre-flash snapshot
    - Flash operation
    - Verification
    - Commit or rollback
    """
    
    transaction_manager: Any = None  # FlashTransactionManager
    lock_manager: Any = None  # LockManager
    recovery: RecoveryOrchestrator | None = None
    
    async def execute(
        self,
        target_name: str,
        owner_id: str,
        firmware_data: bytes,
        firmware_hash: str,
        firmware_version: str,
        flash_operation: Any,  # Callable that performs the flash
    ) -> dict[str, Any]:
        """Execute complete flash workflow with recovery.
        
        Returns:
            Result dictionary with status and details
        """
        result = {
            "success": False,
            "target_name": target_name,
            "transaction_id": None,
            "snapshot_id": None,
            "error": None,
        }
        
        # Acquire lock
        if self.lock_manager:
            lock = await self.lock_manager.acquire_and_publish(target_name, owner_id)
            if not lock:
                result["error"] = "Failed to acquire lock"
                return result
        
        try:
            # Create transaction
            if self.transaction_manager:
                transaction = await self.transaction_manager.create_transaction(
                    target_name=target_name,
                    target_id=target_name,
                    new_firmware_hash=firmware_hash,
                    new_firmware_version=firmware_version,
                    new_firmware_size=len(firmware_data),
                )
                result["transaction_id"] = transaction.transaction_id
            
            # Capture pre-flash snapshot
            if self.recovery:
                snapshot_id = await self.recovery.prepare_recovery(
                    target_name=target_name,
                    target_id=target_name,
                    transaction_id=result["transaction_id"] or "unknown",
                )
                result["snapshot_id"] = snapshot_id
            
            # Start transaction
            if self.transaction_manager and result["transaction_id"]:
                await self.transaction_manager.start_transaction(result["transaction_id"])
            
            # Execute flash operation
            flash_result = await flash_operation()
            
            if not flash_result.success:
                # Flash failed - rollback
                if self.recovery and result["snapshot_id"]:
                    await self.recovery.execute_rollback(
                        snapshot_id=result["snapshot_id"],
                        target_name=target_name,
                        reason=f"Flash failed: {flash_result.error_message}",
                    )
                
                if self.transaction_manager and result["transaction_id"]:
                    await self.transaction_manager.fail_transaction(
                        transaction_id=result["transaction_id"],
                        error_code=flash_result.error_code or "FLASH_FAILED",
                        error_message=flash_result.error_message or "Flash operation failed",
                    )
                
                result["error"] = flash_result.error_message
                return result
            
            # Verify and commit
            if self.transaction_manager and result["transaction_id"]:
                await self.transaction_manager.verify_transaction(result["transaction_id"])
                await self.transaction_manager.commit_transaction(result["transaction_id"])
            
            result["success"] = True
            return result
            
        except Exception as e:
            logger.exception("flash_workflow_error", error=str(e))
            
            # Rollback on exception
            if self.recovery and result["snapshot_id"]:
                await self.recovery.execute_rollback(
                    snapshot_id=result["snapshot_id"],
                    target_name=target_name,
                    reason=f"Exception: {e}",
                )
            
            if self.transaction_manager and result["transaction_id"]:
                await self.transaction_manager.fail_transaction(
                    transaction_id=result["transaction_id"],
                    error_code="WORKFLOW_ERROR",
                    error_message=str(e),
                )
            
            result["error"] = str(e)
            return result
            
        finally:
            # Release lock
            if self.lock_manager:
                await self.lock_manager.release_and_publish(target_name, owner_id)

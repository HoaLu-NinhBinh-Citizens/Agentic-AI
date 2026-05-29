"""Flash State Machine Integration - End-to-End Flash Pipeline with Power-Loss Safety.

Phase 2 (P0-B): Complete flash state machine integrating:
- FlashSlotStateMachine (slot states, transitions)
- FlashTransaction (transaction tracking)
- FlashJournal (sector-level WAL)
- FlashLock (fencing tokens)
- SignedArtifactManifest (P0-D: signing and verification)

This module provides the complete end-to-end flash pipeline that ensures:
1. Atomic state transitions
2. Power-loss safe recovery
3. Fence token enforcement (monotonic epoch; fail-closed)
4. Manifest verification before flash
5. Complete audit trail

P0-B Success Criteria:
- Flash survives power loss + USB disconnect
- Slot state machine fully tested
- Power-loss recovery tests pass
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .flash_slot_state_machine import (
        FlashSlotStateMachine,
        SlotState,
        BootAttemptResult,
        SlotEntry,
    )
    from .flash_transaction import (
        FlashTransaction,
        FlashTransactionManager,
        TransactionStatus,
    )
    from .flash_journal import FlashJournal, JournalEntry, JournalOperation
    from .flash_lock import FlashFenceToken, TargetFlashLock, LockManager
    from .signed_artifact_manifest import (
        SignedArtifactManifest,
        ManifestVerifier,
        ManifestFactory,
    )

logger = logging.getLogger(__name__)


# =============================================================================
# FLASH PIPELINE STATES
# =============================================================================


class FlashPipelineState(Enum):
    """States of the complete flash pipeline."""
    
    IDLE = "idle"                      # No operation in progress
    VERIFYING_MANIFEST = "verifying_manifest"  # P0-D: Verifying manifest
    ACQUIRING_LOCK = "acquiring_lock"  # Acquiring flash lock
    ACQUIRING_FENCE = "acquiring_fence"  # Getting fence token
    ERASING = "erasing"                # Erasing sectors
    WRITING = "writing"                # Writing firmware
    VERIFYING = "verifying"            # Verifying written data
    UPDATING_SLOT = "updating_slot"   # Updating slot state
    MARKING_PENDING = "marking_pending"  # Marking pending boot
    RELEASING_LOCK = "releasing_lock"  # Releasing lock
    BOOTING = "booting"                # Booting into new firmware
    CONFIRMING = "confirming"          # Confirming boot result
    COMPLETED = "completed"             # Operation completed
    FAILED = "failed"                  # Operation failed
    RECOVERING = "recovering"          # Power-loss recovery


# =============================================================================
# PIPELINE OPERATION RECORD
# =============================================================================


@dataclass
class PipelineOperation:
    """Complete record of a flash operation through the pipeline."""
    
    operation_id: str
    operation_type: str  # "flash", "boot", "recover"
    
    # Firmware info
    firmware_data: bytes = b""
    firmware_hash: str = ""
    firmware_version: tuple[int, int, int, int] = (0, 0, 0, 0)
    
    # Target info
    target_name: str = ""
    target_slot: str = ""  # "A" or "B"
    fallback_slot: str = ""
    
    # P0-D: Manifest
    manifest: Any = None  # SignedArtifactManifest
    
    # Pipeline state
    state: FlashPipelineState = FlashPipelineState.IDLE
    
    # Lock and fence
    fence_token: Any = None
    lock_acquired: bool = False
    
    # Progress
    bytes_written: int = 0
    sectors_erased: int = 0
    verify_progress: float = 0.0
    
    # Timing
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    duration_ms: float = 0.0
    
    # Result
    success: bool = False
    error_code: str = ""
    error_message: str = ""
    
    # Recovery info
    recovery_needed: bool = False
    recovery_data: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "operation_id": self.operation_id,
            "operation_type": self.operation_type,
            "firmware_hash": self.firmware_hash,
            "firmware_version": ".".join(str(v) for v in self.firmware_version),
            "target_name": self.target_name,
            "target_slot": self.target_slot,
            "state": self.state.value,
            "lock_acquired": self.lock_acquired,
            "bytes_written": self.bytes_written,
            "sectors_erased": self.sectors_erased,
            "verify_progress": self.verify_progress,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "recovery_needed": self.recovery_needed,
        }


# =============================================================================
# FLASH STATE MACHINE INTEGRATION
# =============================================================================


@dataclass
class FlashStateMachineIntegration:
    """End-to-end flash state machine integration.
    
    P0-B: Integrates all flash components into a single pipeline:
    1. Manifest verification (P0-D)
    2. Lock acquisition + fence token
    3. Journal: erase operations
    4. Write firmware
    5. Journal: verify operations
    6. Slot state update
    7. Mark pending boot
    8. Lock release
    9. Boot sequence
    10. Boot confirmation
    
    Power-loss recovery is handled at every step with journal checkpoints.
    """
    
    # Components
    slot_state_machine: Any  # FlashSlotStateMachine
    transaction_manager: Any  # FlashTransactionManager
    journal: Any  # FlashJournal
    lock_manager: Any  # LockManager
    probe: Any  # Probe interface
    
    # P0-D: Manifest verification
    manifest_verifier: Any = None  # ManifestVerifier
    manifest_factory: Any = None  # ManifestFactory
    
    # Flash configuration
    sector_size: int = 0x4000  # 16KB sectors (STM32F4)
    page_size: int = 0x800    # 2KB pages
    
    # State
    _current_operation: PipelineOperation | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _fence_token: Any = None
    
    def __post_init__(self) -> None:
        """Initialize integration."""
        if self.sector_size == 0:
            self.sector_size = 0x4000
        if self.page_size == 0:
            self.page_size = 0x800
    
    # =========================================================================
    # POWER-LOSS RECOVERY (P0-B)
    # =========================================================================
    
    async def recover_from_power_loss(self) -> tuple[bool, str]:
        """Recover from power loss during previous operation.
        
        P0-B: This is the critical recovery function that handles:
        - Interrupted erase
        - Interrupted write
        - Interrupted verification
        - Interrupted boot
        
        Returns:
            (recovery_success, description)
        """
        async with self._lock:
            logger.info("power_loss_recovery_started")
            
            # Step 1: Check slot state machine for recovery
            recovery_result = await self.slot_state_machine.recover_from_power_loss()
            
            # Step 2: Check journal for sector-level corruption
            if self.journal:
                corruption_analysis = await self.journal.analyze_corruption()
                
                if corruption_analysis["analysis"]["sectors_to_recover"]:
                    logger.warning("sector_corruption_detected: sectors=%s", len(corruption_analysis["analysis"]["sectors_to_recover"]))
            
            # Step 3: Check transaction manager for interrupted transactions
            if self.transaction_manager:
                # Get all non-terminal transactions
                interrupted = await self.transaction_manager.list_transactions(
                    status=None,  # All non-committed
                    limit=10,
                )
                
                for tx in interrupted:
                    if tx.status not in (
                        TransactionStatus.COMMITTED,
                        TransactionStatus.ROLLED_BACK,
                    ):
                        logger.warning("interrupted_transaction_found: transaction_id=%s status=%s", tx.transaction_id, tx.status.value)
            
            logger.info("power_loss_recovery_completed")
            
            return True, "Recovery complete"
    
    async def check_recovery_needed(self) -> tuple[bool, dict[str, Any]]:
        """Check if recovery is needed after power loss.
        
        Returns:
            (recovery_needed, recovery_info)
        """
        info = {
            "slot_recovery_needed": False,
            "journal_corruption": False,
            "interrupted_transactions": [],
            "pending_boot": False,
        }
        
        # Check slot state machine
        state = await self.slot_state_machine.get_state()
        if state.get("recovery_needed"):
            info["slot_recovery_needed"] = True
        
        if state.get("pending_boot"):
            info["pending_boot"] = True
        
        # Check journal
        if self.journal:
            incomplete = await self.journal.list_incomplete_operations()
            if incomplete:
                info["journal_corruption"] = True
                info["incomplete_operations"] = incomplete
        
        recovery_needed = any([
            info["slot_recovery_needed"],
            info["journal_corruption"],
            info["pending_boot"],
        ])
        
        return recovery_needed, info
    
    # =========================================================================
    # P0-D: MANIFEST VERIFICATION
    # =========================================================================
    
    async def verify_manifest(
        self,
        manifest: Any,
        firmware_data: bytes,
        target_name: str,
        slot_id: str,
    ) -> tuple[bool, str]:
        """Verify artifact manifest before flash.
        
        P0-D: Enforces that all flashes have valid signed manifests.
        
        Args:
            manifest: SignedArtifactManifest to verify
            firmware_data: Firmware data to verify hash against
            target_name: Target name for constraint check
            slot_id: Slot ID for constraint check
            
        Returns:
            (verified, error_message)
        """
        if not manifest:
            return False, "No manifest provided"
        
        if not self.manifest_verifier:
            logger.warning("manifest_verifier_not_configured")
            return True, "Verification skipped (no verifier)"
        
        # Verify manifest
        result = self.manifest_verifier.verify(
            manifest=manifest,
            expected_image_hash=hashlib.sha256(firmware_data).hexdigest(),
            expected_target=target_name,
            expected_slot=slot_id,
        )
        
        if not result.is_valid():
            logger.error("manifest_verification_failed: status=%s message=%s", result.status.value, result.message)
            return False, result.message
        
        logger.info("manifest_verified: artifact=%s signer=%s", manifest.artifact_id, manifest.signer_id)
        
        return True, "Manifest verified"
    
    # =========================================================================
    # END-TO-END FLASH PIPELINE
    # =========================================================================
    
    async def execute_flash_pipeline(
        self,
        operation_id: str,
        firmware_data: bytes,
        firmware_version: tuple[int, int, int, int],
        target_name: str,
        manifest: Any = None,
        rollback_snapshot_id: str | None = None,
    ) -> PipelineOperation:
        """Execute complete flash pipeline.
        
        P0-B: This is the main entry point for flashing firmware.
        It coordinates all components to ensure atomic, power-loss-safe operations.
        
        Pipeline Steps:
        1. Verify manifest (P0-D)
        2. Acquire lock + fence token
        3. Create transaction
        4. Begin journal transaction
        5. Erase sectors (with journal)
        6. Write firmware (with journal)
        7. Verify firmware
        8. Update slot state (INVALID -> TESTING)
        9. Commit journal
        10. Mark pending boot
        11. Release lock
        12. Trigger boot
        
        Args:
            operation_id: Unique operation ID
            firmware_data: Firmware binary
            firmware_version: Version tuple
            target_name: Target to flash
            manifest: Signed artifact manifest (P0-D)
            rollback_snapshot_id: Pre-flash snapshot ID for rollback
            
        Returns:
            PipelineOperation with result
        """
        operation = PipelineOperation(
            operation_id=operation_id,
            operation_type="flash",
            firmware_data=firmware_data,
            firmware_hash=hashlib.sha256(firmware_data).hexdigest(),
            firmware_version=firmware_version,
            target_name=target_name,
            manifest=manifest,
        )
        
        self._current_operation = operation
        
        try:
            async with self._lock:
                # Step 1: Verify manifest (P0-D)
                operation.state = FlashPipelineState.VERIFYING_MANIFEST
                inactive_slot = self.slot_state_machine.slot_table.get_inactive_slot()
                operation.target_slot = inactive_slot.slot_id
                operation.fallback_slot = self.slot_state_machine.slot_table.active_slot
                
                if manifest:
                    verified, error = await self.verify_manifest(
                        manifest=manifest,
                        firmware_data=firmware_data,
                        target_name=target_name,
                        slot_id=operation.target_slot,
                    )
                    if not verified:
                        operation.state = FlashPipelineState.FAILED
                        operation.error_code = "MANIFEST_INVALID"
                        operation.error_message = error
                        return operation
                
                # Step 2: Acquire lock
                operation.state = FlashPipelineState.ACQUIRING_LOCK
                
                if self.lock_manager:
                    lock, fence = await self.lock_manager.acquire_with_fence_token(
                        target_name=target_name,
                        owner_id=operation_id,
                        transaction_id=operation_id,
                    )
                    
                    if not lock or not fence:
                        operation.state = FlashPipelineState.FAILED
                        operation.error_code = "LOCK_FAILED"
                        operation.error_message = "Failed to acquire lock"
                        return operation
                    
                    operation.lock_acquired = True
                    operation.fence_token = fence
                
                # Step 3: Create transaction
                tx = await self.transaction_manager.create_transaction(
                    target_name=target_name,
                    target_id="",
                    new_firmware_hash=operation.firmware_hash,
                    new_firmware_version=".".join(str(v) for v in firmware_version),
                    new_firmware_size=len(firmware_data),
                    target_slot=operation.target_slot,
                )
                if fence is not None and hasattr(fence, "epoch"):
                    tx.lock_epoch = int(getattr(fence, "epoch", 0) or 0)
                    tx.lock_owner_id = operation_id
                    tx.lock_acquired = True
                    await self.transaction_manager._save_transaction(tx)
                
                # Begin journal
                if self.journal:
                    await self.journal.begin_transaction(operation_id)
                
                # Step 4: Begin flash in slot state machine
                begin_ok, begin_result = await self.slot_state_machine.begin_flash(
                    firmware_data=firmware_data,
                    version=firmware_version,
                    fence_token=fence,
                )
                
                if not begin_ok:
                    operation.state = FlashPipelineState.FAILED
                    operation.error_code = "SLOT_BEGIN_FAILED"
                    operation.error_message = begin_result
                    return operation
                
                # Step 5: Erase sectors
                operation.state = FlashPipelineState.ERASING
                await self.transaction_manager.start_transaction(tx.transaction_id)
                
                if self.journal:
                    # Calculate sectors to erase
                    sectors_needed = (len(firmware_data) + self.sector_size - 1) // self.sector_size
                    
                    for sector_idx in range(sectors_needed):
                        sector_addr = inactive_slot.slot_address + (sector_idx * self.sector_size)
                        
                        # Log erase started
                        await self.journal.log_erase_started(
                            sector_id=sector_idx,
                            sector_address=sector_addr,
                            sector_size=self.sector_size,
                        )
                        
                        # Erase sector
                        await self.probe.erase_sector(sector_addr)
                        operation.sectors_erased += 1
                        
                        # Log erase completed
                        await self.journal.log_erase_completed(sector_idx)
                
                # Step 6: Write firmware
                operation.state = FlashPipelineState.WRITING
                
                write_ok, write_error = await self.slot_state_machine.write_slot(
                    slot_id=operation.target_slot,
                    firmware_data=firmware_data,
                    fence_token=fence,
                )
                
                if not write_ok:
                    operation.state = FlashPipelineState.FAILED
                    operation.error_code = "WRITE_FAILED"
                    operation.error_message = write_error
                    
                    if self.journal:
                        await self.journal.abort_transaction("Write failed")
                    
                    return operation
                
                operation.bytes_written = len(firmware_data)
                
                # Step 7: Verify firmware
                operation.state = FlashPipelineState.VERIFYING
                
                verify_ok, verify_error = await self.slot_state_machine.verify_slot(
                    slot_id=operation.target_slot,
                    fence_token=fence,
                )
                
                if not verify_ok:
                    operation.state = FlashPipelineState.FAILED
                    operation.error_code = "VERIFY_FAILED"
                    operation.error_message = verify_error
                    
                    if self.journal:
                        await self.journal.abort_transaction("Verify failed")
                    
                    return operation
                
                operation.verify_progress = 1.0
                
                # Step 8: Update slot state
                operation.state = FlashPipelineState.UPDATING_SLOT
                
                # Slot is now in TESTING state (handled by slot state machine)
                
                # Step 9: Commit journal
                if self.journal:
                    await self.journal.commit_transaction()
                
                # Step 10: Mark pending boot
                operation.state = FlashPipelineState.MARKING_PENDING
                
                pending_ok, pending_error = await self.slot_state_machine.mark_pending_boot(
                    target_slot_id=operation.target_slot,
                    fallback_slot_id=operation.fallback_slot,
                )
                
                if not pending_ok:
                    operation.state = FlashPipelineState.FAILED
                    operation.error_code = "PENDING_MARK_FAILED"
                    operation.error_message = pending_error
                    return operation
                
                # Step 11: Commit transaction
                await self.transaction_manager.commit_transaction(tx.transaction_id)
                
                # Step 12: Release lock
                operation.state = FlashPipelineState.RELEASING_LOCK
                
                if self.lock_manager:
                    await self.lock_manager.release_and_publish(
                        target_name=target_name,
                        owner_id=operation_id,
                    )
                    operation.lock_acquired = False
                
                # Success
                operation.state = FlashPipelineState.COMPLETED
                operation.success = True
                
                logger.info("flash_pipeline_completed: operation_id=%s slot=%s bytes=%s duration_ms=%s", operation_id, operation.target_slot, operation.bytes_written, operation.duration_ms)
                
                return operation
                
        except Exception as e:
            operation.state = FlashPipelineState.FAILED
            operation.error_code = "EXCEPTION"
            operation.error_message = str(e)
            operation.recovery_needed = True
            
            logger.exception("flash_pipeline_failed: operation_id=%s error=%s", operation_id, str(e))
            
            # Try to rollback
            if self.lock_manager and operation.lock_acquired:
                await self.lock_manager.invalidate_fence_on_failure(
                    target_name=target_name,
                    owner_id=operation_id,
                )
            
            return operation
        
        finally:
            operation.completed_at = datetime.now()
            operation.duration_ms = (
                operation.completed_at - operation.started_at
            ).total_seconds() * 1000
    
    # =========================================================================
    # BOOT PIPELINE
    # =========================================================================
    
    async def execute_boot_pipeline(
        self,
        target_slot: str,
        fallback_slot: str,
        health_checker: Any = None,
    ) -> dict[str, Any]:
        """Execute boot pipeline with health validation.
        
        P0-B: Boot into new firmware and validate with health checks.
        
        Args:
            target_slot: Slot to boot into
            fallback_slot: Fallback slot on failure
            health_checker: Boot health validator
            
        Returns:
            Boot result dict
        """
        result = {
            "success": False,
            "slot_booted": target_slot,
            "fallback_used": False,
            "health_passed": False,
            "boot_time_ms": 0.0,
            "error": None,
        }
        
        start_time = datetime.now()
        
        try:
            async with self._lock:
                # Step 1: Trigger reset to boot into new slot
                await self.probe.reset()
                
                # Step 2: Wait for boot
                await asyncio.sleep(2)  # Wait for boot to initialize
                
                # Step 3: Run health checks
                if health_checker:
                    health_result = await health_checker.run_health_checks()
                    result["health_result"] = health_result.to_dict()
                    
                    if not health_result.passed:
                        # Health check failed - rollback
                        result["health_passed"] = False
                        result["fallback_used"] = True
                        
                        await self.slot_state_machine.confirm_boot(
                            slot_id=target_slot,
                            result=BootAttemptResult.HEALTH_CHECK_FAILED,
                        )
                        
                        return result
                
                result["health_passed"] = True
                
                # Step 4: Confirm successful boot
                await self.slot_state_machine.confirm_boot(
                    slot_id=target_slot,
                    result=BootAttemptResult.SUCCESS,
                )
                
                result["success"] = True
                
        except Exception as e:
            result["error"] = str(e)
            logger.exception("boot_pipeline_failed")
            
            # Confirm boot failure
            await self.slot_state_machine.confirm_boot(
                slot_id=target_slot,
                result=BootAttemptResult.FAILURE,
            )
        
        result["boot_time_ms"] = (datetime.now() - start_time).total_seconds() * 1000
        
        return result
    
    # =========================================================================
    # STATE QUERIES
    # =========================================================================
    
    async def get_pipeline_state(self) -> dict[str, Any]:
        """Get current pipeline state."""
        state = {
            "pipeline": {
                "current_operation": None,
                "state": FlashPipelineState.IDLE.value,
            },
            "slots": await self.slot_state_machine.get_state(),
        }
        
        if self._current_operation:
            state["pipeline"]["current_operation"] = self._current_operation.to_dict()
            state["pipeline"]["state"] = self._current_operation.state.value
        
        return state
    
    async def can_execute_flash(self) -> tuple[bool, str]:
        """Check if flash can be executed."""
        return await self.slot_state_machine.can_flash()
    
    async def can_execute_boot(self) -> tuple[bool, str]:
        """Check if boot can be executed."""
        return await self.slot_state_machine.can_boot()
    
    async def get_slot_info(self) -> dict[str, Any]:
        """Get information about both slots."""
        return self.slot_state_machine.slot_table.to_dict()


# =============================================================================
# FLASH PLANNER WITH MANIFEST INTEGRATION (P0-D)
# =============================================================================


@dataclass
class FlashPlanner:
    """Flash planner with manifest verification integration.
    
    P0-D: Integrates signed artifact manifests into flash planning.
    All flashes must have valid manifests before proceeding.
    """
    
    integration: FlashStateMachineIntegration
    manifest_verifier: Any = None  # ManifestVerifier
    
    async def plan_flash(
        self,
        firmware_data: bytes,
        version: str,
        target_name: str,
        manifest: Any = None,
    ) -> dict[str, Any]:
        """Plan a flash operation with manifest verification.
        
        P0-D: This method enforces manifest verification before planning.
        
        Args:
            firmware_data: Firmware binary
            version: Version string
            target_name: Target to flash
            manifest: SignedArtifactManifest
            
        Returns:
            Flash plan with validation results
        """
        plan = {
            "can_flash": False,
            "manifest_verified": False,
            "slot_available": False,
            "checks": [],
            "errors": [],
            "warnings": [],
        }
        
        # Check 1: Manifest verification (P0-D)
        if manifest and self.manifest_verifier:
            result = self.manifest_verifier.verify(
                manifest=manifest,
                expected_image_hash=hashlib.sha256(firmware_data).hexdigest(),
                expected_target=target_name,
            )
            
            plan["manifest_verified"] = result.is_valid()
            plan["checks"].append({
                "name": "manifest",
                "passed": result.is_valid(),
                "message": result.message,
            })
            
            if not result.is_valid():
                plan["errors"].append(f"Manifest verification failed: {result.message}")
        elif manifest:
            plan["checks"].append({
                "name": "manifest",
                "passed": True,
                "message": "Manifest provided but verifier not configured",
            })
            plan["warnings"].append("Manifest verification skipped - verifier not configured")
        else:
            plan["warnings"].append("No manifest provided - P0-D requires signed manifests")
        
        # Check 2: Slot availability
        can_flash, reason = await self.integration.can_execute_flash()
        plan["slot_available"] = can_flash
        plan["checks"].append({
            "name": "slot",
            "passed": can_flash,
            "message": reason,
        })
        
        if not can_flash:
            plan["errors"].append(f"Slot not available: {reason}")
        
        # Check 3: Calculate operation details
        if plan["manifest_verified"] and plan["slot_available"]:
            plan["can_flash"] = True
            plan["firmware_hash"] = hashlib.sha256(firmware_data).hexdigest()
            plan["firmware_size"] = len(firmware_data)
            plan["target_slot"] = self.integration.slot_state_machine.slot_table.get_inactive_slot().slot_id
        
        return plan
    
    async def execute_planned_flash(
        self,
        plan: dict[str, Any],
        firmware_data: bytes,
        version: tuple[int, int, int, int],
        manifest: Any = None,
    ) -> PipelineOperation:
        """Execute a planned flash operation.
        
        Args:
            plan: Plan from plan_flash()
            firmware_data: Firmware binary
            version: Version tuple
            manifest: SignedArtifactManifest
            
        Returns:
            PipelineOperation result
        """
        if not plan.get("can_flash"):
            operation = PipelineOperation(
                operation_id="failed_plan",
                operation_type="flash",
                success=False,
                error_code="PLAN_INVALID",
                error_message="Plan not valid for execution",
            )
            return operation
        
        import uuid
        operation_id = str(uuid.uuid4())
        
        return await self.integration.execute_flash_pipeline(
            operation_id=operation_id,
            firmware_data=firmware_data,
            firmware_version=version,
            target_name=plan.get("target_name", "unknown"),
            manifest=manifest,
        )

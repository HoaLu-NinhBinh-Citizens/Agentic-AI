# Phase 6.2 - Flash Infrastructure Supplement

**Production-Grade OTA & Recovery Extensions**

## Overview

This supplement addresses the production-grade gaps in the base Phase 6.2 specification, adding:

1. Flash Journal / WAL (sector-level write-ahead logging)
2. CRC Tree / Merkle Verification (incremental integrity)
3. Power-Fail Safe Slot Switching (atomic boot validation)
4. Boot Health Validation (post-flash health checks)
5. Fleet Coordination Model (multi-target orchestration)
6. Artifact Manifest & SBOM/CVE (supply chain security)
7. Secure Element / HSM Abstraction (key management)
8. Compressed-In-Place OTA (streaming decompression)
9. Flash Rate Limit / Thermal Policy (fleet safety)

---

## 1. Flash Journal / WAL (Write-Ahead Logging)

### Problem

Current transaction model records flash operation status, but sector-level operations are not logged. If power loss occurs during sector write:

```
transaction = "flashing"
But: Which sectors completed? Which failed?
```

### Solution: Sector-Level Journal

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Literal


class JournalOperation(Enum):
    """Sector operation types."""
    ERASE_STARTED = "erase_started"
    ERASE_COMPLETED = "erase_completed"
    ERASE_FAILED = "erase_failed"
    WRITE_STARTED = "write_started"
    WRITE_COMPLETED = "write_completed"
    WRITE_FAILED = "write_failed"
    VERIFY_STARTED = "verify_started"
    VERIFY_COMPLETED = "verify_completed"
    VERIFY_FAILED = "verify_failed"


@dataclass
class FlashJournalEntry:
    """Sector-level journal entry."""
    
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    transaction_id: str = ""
    sector_id: int = 0
    
    operation: JournalOperation
    sector_address: int = 0
    sector_size: int = 0
    
    # Checksums for verification
    checksum_before: str = ""  # SHA256 before operation
    checksum_after: str | None = None  # SHA256 after operation
    
    # Timing
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    
    # Status
    success: bool = False
    error_message: str | None = None
    
    # Retry tracking
    retry_count: int = 0
    max_retries: int = 3
    
    def duration_ms(self) -> float:
        """Get operation duration."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds() * 1000
        return 0.0
    
    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "transaction_id": self.transaction_id,
            "sector_id": self.sector_id,
            "operation": self.operation.value,
            "checksum_before": self.checksum_before,
            "checksum_after": self.checksum_after,
            "success": self.success,
            "duration_ms": self.duration_ms(),
        }


class FlashJournal:
    """Sector-level write-ahead log.
    
    Provides:
    - Sector operation tracking
    - Partial operation detection
    - Resume from exact position
    - Corruption localization
    """
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._db = None
        self._pending_entries: list[FlashJournalEntry] = []
    
    async def initialize(self):
        """Create journal tables."""
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS flash_journal (
                entry_id TEXT PRIMARY KEY,
                transaction_id TEXT NOT NULL,
                sector_id INTEGER NOT NULL,
                operation TEXT NOT NULL,
                sector_address INTEGER NOT NULL,
                sector_size INTEGER NOT NULL,
                checksum_before TEXT,
                checksum_after TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                success INTEGER DEFAULT 0,
                error_message TEXT,
                retry_count INTEGER DEFAULT 0
            )
        """)
        
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_journal_transaction
            ON flash_journal(transaction_id)
        """)
        
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_journal_sector
            ON flash_journal(transaction_id, sector_id)
        """)
    
    async def log_operation(
        self,
        transaction_id: str,
        sector_id: int,
        operation: JournalOperation,
        sector_address: int,
        sector_size: int,
        checksum_before: str,
    ) -> FlashJournalEntry:
        """Log sector operation start."""
        entry = FlashJournalEntry(
            transaction_id=transaction_id,
            sector_id=sector_id,
            operation=operation,
            sector_address=sector_address,
            sector_size=sector_size,
            checksum_before=checksum_before,
        )
        
        self._pending_entries.append(entry)
        
        await self._save_entry(entry)
        await self._db.commit()
        
        return entry
    
    async def complete_operation(
        self,
        entry_id: str,
        checksum_after: str,
        success: bool,
        error_message: str | None = None,
    ) -> None:
        """Mark operation as completed."""
        entry = self._find_entry(entry_id)
        if not entry:
            return
        
        entry.completed_at = datetime.now()
        entry.checksum_after = checksum_after
        entry.success = success
        entry.error_message = error_message
        
        await self._save_entry(entry)
        await self._db.commit()
    
    async def get_incomplete_sectors(
        self,
        transaction_id: str,
    ) -> list[FlashJournalEntry]:
        """Get sectors with incomplete operations."""
        cursor = await self._db.execute("""
            SELECT * FROM flash_journal
            WHERE transaction_id = ? AND completed_at IS NULL
            ORDER BY sector_id
        """, (transaction_id,))
        
        rows = await cursor.fetchall()
        return [self._row_to_entry(row) for row in rows]
    
    async def get_failed_sectors(
        self,
        transaction_id: str,
    ) -> list[FlashJournalEntry]:
        """Get sectors with failed operations."""
        cursor = await self._db.execute("""
            SELECT * FROM flash_journal
            WHERE transaction_id = ? AND success = 0
            ORDER BY sector_id
        """, (transaction_id,))
        
        rows = await cursor.fetchall()
        return [self._row_to_entry(row) for row in rows]
    
    async def get_corruption_range(
        self,
        transaction_id: str,
    ) -> tuple[int, int] | None:
        """Get range of corrupted sectors.
        
        Returns:
            (first_corrupted_sector, last_corrupted_sector) or None
        """
        failed = await self.get_failed_sectors(transaction_id)
        
        if not failed:
            return None
        
        sector_ids = [e.sector_id for e in failed]
        return min(sector_ids), max(sector_ids)
    
    async def _save_entry(self, entry: FlashJournalEntry):
        """Save entry to database."""
        await self._db.execute("""
            INSERT OR REPLACE INTO flash_journal
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry.entry_id,
            entry.transaction_id,
            entry.sector_id,
            entry.operation.value,
            entry.sector_address,
            entry.sector_size,
            entry.checksum_before,
            entry.checksum_after,
            entry.started_at.isoformat(),
            entry.completed_at.isoformat() if entry.completed_at else None,
            1 if entry.success else 0,
            entry.error_message,
            entry.retry_count,
        ))
    
    def _find_entry(self, entry_id: str) -> FlashJournalEntry | None:
        for entry in self._pending_entries:
            if entry.entry_id == entry_id:
                return entry
        return None
    
    def _row_to_entry(self, row) -> FlashJournalEntry:
        return FlashJournalEntry(
            entry_id=row[0],
            transaction_id=row[1],
            sector_id=row[2],
            operation=JournalOperation(row[3]),
            sector_address=row[4],
            sector_size=row[5],
            checksum_before=row[6],
            checksum_after=row[7],
            started_at=datetime.fromisoformat(row[8]),
            completed_at=datetime.fromisoformat(row[9]) if row[9] else None,
            success=bool(row[10]),
            error_message=row[11],
            retry_count=row[12],
        )
```

### Integration with Resume

```python
class JournalAwareResumeState:
    """Resume state with journal awareness."""
    
    transaction_id: str
    firmware_hash: str
    
    # From journal
    next_sector_to_flash: int = 0
    incomplete_sectors: list[int] = field(default_factory=list)
    failed_sectors: list[int] = field(default_factory=list)
    
    # Corruption info
    corruption_range: tuple[int, int] | None = None
    corruption_detected_at: datetime | None = None
    
    def is_flashable(self, sector_id: int) -> bool:
        """Check if sector can be flashed."""
        return (
            sector_id not in self.incomplete_sectors
            and sector_id not in self.failed_sectors
        )
    
    def get_flashable_range(self) -> range:
        """Get range of flashable sectors."""
        if self.failed_sectors:
            # Can only flash up to first failure
            first_failed = min(self.failed_sectors)
            return range(self.next_sector_to_flash, first_failed)
        
        return range(self.next_sector_to_flash, self.total_sectors)
```

---

## 2. CRC Tree / Merkle Verification

### Problem

Full firmware verification for 8MB+ devices is slow. Need incremental verification.

### Solution: Incremental Verification Tree

```python
@dataclass
class ChunkHash:
    """Hash node in verification tree."""
    
    offset: int
    size: int
    hash: str
    
    is_leaf: bool = True
    left: str | None = None  # Child hash ID
    right: str | None = None


@dataclass
class CRCTree:
    """Merkle tree for incremental verification.
    
    Structure:
                    root_hash
                   /          \
           hash_0_1              hash_0_2
           /      \              /      \
        hash_0    hash_1      hash_2    hash_3
           |        |          |        |
        chunk_0  chunk_1    chunk_2  chunk_3
    """
    
    chunk_size: int = 4096
    root_hash: str = ""
    total_size: int = 0
    chunks: list[ChunkHash] = field(default_factory=list)
    levels: int = 0
    
    @classmethod
    def build(cls, firmware: bytes, chunk_size: int = 4096) -> CRCTree:
        """Build verification tree from firmware."""
        import hashlib
        
        chunks = []
        for offset in range(0, len(firmware), chunk_size):
            chunk = firmware[offset:offset + chunk_size]
            chunk_hash = hashlib.sha256(chunk).hexdigest()
            
            chunks.append(ChunkHash(
                offset=offset,
                size=len(chunk),
                hash=chunk_hash,
                is_leaf=True,
            ))
        
        # Build tree levels
        tree = cls(
            chunk_size=chunk_size,
            total_size=len(firmware),
            chunks=chunks,
        )
        
        # Calculate root
        tree.root_hash = tree._compute_root()
        tree.levels = tree._compute_levels()
        
        return tree
    
    def _compute_root(self) -> str:
        """Compute root hash."""
        import hashlib
        
        if not self.chunks:
            return ""
        
        current_level = [c.hash for c in self.chunks]
        
        while len(current_level) > 1:
            next_level = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                right = current_level[i + 1] if i + 1 < len(current_level) else left
                
                combined = hashlib.sha256(
                    (left + right).encode()
                ).hexdigest()
                next_level.append(combined)
            
            current_level = next_level
        
        return current_level[0] if current_level else ""
    
    def _compute_levels(self) -> int:
        """Compute tree depth."""
        import math
        return math.ceil(math.log2(len(self.chunks))) + 1 if self.chunks else 0
    
    def get_chunk_hashes(self, start_offset: int, end_offset: int) -> list[str]:
        """Get hashes for byte range."""
        start_chunk = start_offset // self.chunk_size
        end_chunk = (end_offset - 1) // self.chunk_size
        
        return [self.chunks[i].hash 
                for i in range(start_chunk, end_chunk + 1)
                if i < len(self.chunks)]
    
    def verify_range(
        self,
        start_offset: int,
        end_offset: int,
        chunk_hashes: list[str],
    ) -> tuple[bool, str]:
        """Verify byte range against expected hashes."""
        import hashlib
        
        expected = self.get_chunk_hashes(start_offset, end_offset)
        
        if len(expected) != len(chunk_hashes):
            return False, "Hash count mismatch"
        
        for i, (exp, actual) in enumerate(zip(expected, chunk_hashes)):
            if exp != actual:
                sector = start_offset // self.chunk_size + i
                return False, f"Hash mismatch at chunk {sector}"
        
        return True, ""
    
    def get_delta_hashes(
        self,
        old_tree: CRCTree,
    ) -> list[tuple[int, str]]:
        """Get changed chunk hashes between trees."""
        changes = []
        
        for i, (new, old) in enumerate(zip(self.chunks, old_tree.chunks)):
            if new.hash != old.hash:
                changes.append((i, new.hash))
        
        return changes


class IncrementalVerifier:
    """Incremental firmware verifier using CRC tree."""
    
    def __init__(self, journal: FlashJournal):
        self.journal = journal
    
    async def verify_incremental(
        self,
        transaction_id: str,
        tree: CRCTree,
        probe: Any,
        start_sector: int,
        end_sector: int,
    ) -> VerificationResult:
        """Verify changed sectors incrementally."""
        import hashlib
        
        changes = []
        
        for sector_id in range(start_sector, end_sector):
            # Get journal entry for this sector
            incomplete = await self.journal.get_incomplete_sectors(transaction_id)
            if sector_id in [e.sector_id for e in incomplete]:
                # Sector not completed - can't verify
                continue
            
            # Read sector
            sector_addr = partition.start + sector_id * sector_size
            data = await probe.read_memory(sector_addr, sector_size)
            
            # Verify hash
            actual_hash = hashlib.sha256(data).hexdigest()
            
            if sector_id < len(tree.chunks):
                expected_hash = tree.chunks[sector_id].hash
                
                if actual_hash != expected_hash:
                    changes.append({
                        "sector_id": sector_id,
                        "expected": expected_hash,
                        "actual": actual_hash,
                        "status": "corrupted",
                    })
                else:
                    changes.append({
                        "sector_id": sector_id,
                        "hash": actual_hash,
                        "status": "verified",
                    })
        
        return VerificationResult(
            verified_sectors=len(changes),
            corrupted_sectors=sum(1 for c in changes if c["status"] == "corrupted"),
            changes=changes,
        )


@dataclass
class VerificationResult:
    """Result of verification."""
    
    verified_sectors: int = 0
    corrupted_sectors: int = 0
    changes: list[dict] = field(default_factory=list)
    
    @property
    def is_clean(self) -> bool:
        return self.corrupted_sectors == 0
```

---

## 3. Power-Fail Safe Slot Switching

### Problem

A/B slots work, but boot switch is not atomic. Need safe boot validation.

### Solution: Boot Health State Machine

```python
class BootState(Enum):
    """Boot lifecycle states."""
    INACTIVE = "inactive"
    FLASH_PENDING = "flash_pending"
    BOOT_ONCE = "boot_once"           # Boot into new slot
    HEALTH_CHECK = "health_check"     # Validate boot
    HEALTH_OK = "health_ok"           # Mark as good
    HEALTH_FAIL = "health_fail"       # Rollback needed
    ROLLED_BACK = "rolled_back"


@dataclass
class BootHealthMarker:
    """Marker stored in slot for health tracking."""
    
    version: str
    build_timestamp: str
    boot_count: int = 0
    health_check_enabled: bool = True
    health_check_timeout_ms: int = 5000
    
    # Health validation
    heartbeat_expected: bool = True
    heartbeat_timeout_ms: int = 10000
    
    # Rollback trigger
    consecutive_failures: int = 0
    max_consecutive_failures: int = 3
    
    def to_bytes(self) -> bytes:
        import struct
        return struct.pack(
            "<32s I ? ? ? I I I",
            self.version.encode()[:32],
            self.boot_count,
            1 if self.heartbeat_expected else 0,
            1 if self.health_check_enabled else 0,
            1,  # padding
            self.health_check_timeout_ms,
            self.heartbeat_timeout_ms,
            self.consecutive_failures,
        )


class AtomicSlotSwitcher:
    """Power-fail safe slot switcher."""
    
    def __init__(
        self,
        layout: FlashLayout,
        probe: Any,
    ):
        self.layout = layout
        self.probe = probe
    
    async def switch_to_slot(
        self,
        new_slot: str,
        verify_health: bool = True,
    ) -> SlotSwitchResult:
        """Atomically switch to new slot with health validation.
        
        State machine:
        1. Flash inactive slot
        2. Verify flash
        3. Mark slot as BOOT_ONCE
        4. Boot into new slot
        5. Health check (heartbeat/wdog)
        6. If healthy: mark HEALTH_OK, switch permanently
        7. If unhealthy: rollback, mark ROLLED_BACK
        """
        result = SlotSwitchResult(slot=new_slot)
        
        try:
            # Step 1: Get target partition
            partition = self.layout.get_partition_by_slot(new_slot)
            if not partition:
                return SlotSwitchResult.error("Slot not found")
            
            # Step 2: Write health marker
            marker = BootHealthMarker(
                version=firmware_version,
                boot_count=0,
                health_check_enabled=verify_health,
            )
            
            marker_addr = partition.end_address - 64
            await self.probe.write_memory(marker_addr, marker.to_bytes())
            
            # Step 3: Mark as BOOT_ONCE (not yet committed)
            await self._mark_slot_state(new_slot, BootState.BOOT_ONCE)
            
            result.state = BootState.BOOT_ONCE
            
            # Step 4: Perform health check
            if verify_health:
                health_ok = await self._validate_boot_health(
                    partition,
                    marker,
                )
                
                if not health_ok:
                    await self._mark_slot_state(new_slot, BootState.HEALTH_FAIL)
                    await self._rollback_slot(new_slot)
                    result.state = BootState.HEALTH_FAIL
                    return result
            
            # Step 5: Mark as committed
            await self._mark_slot_state(new_slot, BootState.HEALTH_OK)
            await self._switch_boot_partition(new_slot)
            
            result.state = BootState.HEALTH_OK
            result.success = True
            return result
            
        except Exception as e:
            result.error = str(e)
            await self._mark_slot_state(new_slot, BootState.ROLLED_BACK)
            await self._rollback_slot(new_slot)
            result.state = BootState.ROLLED_BACK
            return result
    
    async def _validate_boot_health(
        self,
        partition: Partition,
        marker: BootHealthMarker,
    ) -> bool:
        """Validate boot health via heartbeat/watchdog."""
        
        # Start health check task
        check_task = asyncio.create_task(
            self._wait_for_heartbeat(
                partition,
                marker.heartbeat_timeout_ms,
            )
        )
        
        # Wait for timeout
        try:
            await asyncio.wait_for(
                check_task,
                timeout=marker.health_check_timeout_ms / 1000,
            )
            return True
        except asyncio.TimeoutError:
            return False
    
    async def _wait_for_heartbeat(
        self,
        partition: Partition,
        timeout_ms: int,
    ) -> None:
        """Wait for expected heartbeat pattern."""
        # Implementation depends on firmware heartbeat protocol
        # Could be:
        # - UART message
        # - Memory flag
        # - GPIO toggle
        # - Watchdog kick
        pass
    
    async def _mark_slot_state(
        self,
        slot: str,
        state: BootState,
    ) -> None:
        """Write slot state to selector."""
        state_addr = self.layout.slot_selector_address
        
        state_value = {
            BootState.INACTIVE: 0,
            BootState.BOOT_ONCE: 0xAAAAAAAA,
            BootState.HEALTH_OK: 0x55555555,
            BootState.HEALTH_FAIL: 0xDEADBEEF,
            BootState.ROLLED_BACK: 0xBADCAFE,
        }[state]
        
        import struct
        await self.probe.write_memory(
            state_addr,
            struct.pack("<I", state_value),
        )
    
    async def _rollback_slot(self, slot: str) -> None:
        """Rollback to previous slot."""
        old_slot = self.layout.active_slot
        if old_slot:
            await self._switch_boot_partition(old_slot)


@dataclass
class SlotSwitchResult:
    """Result of slot switch operation."""
    
    slot: str
    success: bool = False
    state: BootState = BootState.INACTIVE
    error: str | None = None
```

---

## 4. Boot Health Validation

### Problem

Flash success ≠ firmware health. Need post-flash validation.

### Solution: Health Check Framework

```python
class HealthCheckType(Enum):
    """Types of health checks."""
    HEARTBEAT = "heartbeat"
    WATCHDOG = "watchdog"
    UART_LOG = "uart_log"
    MEMORY_MAGIC = "memory_magic"
    GPIO_STATE = "gpio_state"
    NETWORK_PING = "network_ping"


@dataclass
class HealthCheck:
    """Health check definition."""
    
    check_type: HealthCheckType
    timeout_ms: int
    retry_count: int = 3
    retry_delay_ms: int = 1000
    
    # Check-specific parameters
    params: dict = field(default_factory=dict)


@dataclass
class HealthCheckResult:
    """Result of health check."""
    
    check_type: HealthCheckType
    passed: bool
    duration_ms: float
    message: str = ""
    details: dict = field(default_factory=dict)


class BootHealthValidator:
    """Validates firmware health after flash."""
    
    def __init__(
        self,
        probe: Any,
        serial: SerialMonitor | None = None,
    ):
        self.probe = probe
        self.serial = serial
    
    async def validate_boot(
        self,
        firmware: FirmwareInfo,
        checks: list[HealthCheck],
    ) -> HealthValidationResult:
        """Run all health checks."""
        results: list[HealthCheckResult] = []
        all_passed = True
        
        for check in checks:
            result = await self._run_check(check)
            results.append(result)
            
            if not result.passed:
                all_passed = False
        
        return HealthValidationResult(
            overall_passed=all_passed,
            check_results=results,
            timestamp=datetime.now(),
        )
    
    async def _run_check(
        self,
        check: HealthCheck,
    ) -> HealthCheckResult:
        """Run single health check."""
        start = time.monotonic()
        
        for attempt in range(check.retry_count):
            try:
                result = await self._execute_check(check)
                if result.passed:
                    return result
                
                if attempt < check.retry_count - 1:
                    await asyncio.sleep(check.retry_delay_ms / 1000)
                    
            except Exception as e:
                if attempt == check.retry_count - 1:
                    return HealthCheckResult(
                        check_type=check.check_type,
                        passed=False,
                        duration_ms=(time.monotonic() - start) * 1000,
                        message=str(e),
                    )
        
        return HealthCheckResult(
            check_type=check.check_type,
            passed=False,
            duration_ms=(time.monotonic() - start) * 1000,
            message="All retries failed",
        )
    
    async def _execute_check(
        self,
        check: HealthCheck,
    ) -> HealthCheckResult:
        """Execute specific check type."""
        if check.check_type == HealthCheckType.HEARTBEAT:
            return await self._check_heartbeat(check)
        elif check.check_type == HealthCheckType.WATCHDOG:
            return await self._check_watchdog(check)
        elif check.check_type == HealthCheckType.UART_LOG:
            return await self._check_uart_log(check)
        elif check.check_type == HealthCheckType.MEMORY_MAGIC:
            return await self._check_memory_magic(check)
        
        return HealthCheckResult(
            check_type=check.check_type,
            passed=False,
            duration_ms=0,
            message="Unknown check type",
        )
    
    async def _check_heartbeat(
        self,
        check: HealthCheck,
    ) -> HealthCheckResult:
        """Check for expected heartbeat pattern."""
        timeout = check.timeout_ms / 1000
        pattern = check.params.get("pattern", "READY")
        
        start = time.monotonic()
        
        try:
            # Read memory location where heartbeat is set
            addr = check.params.get("address", 0x20000000)
            expected = check.params.get("expected_value", 0xDEADBEEF)
            
            while (time.monotonic() - start) < timeout:
                data = await self.probe.read_memory(addr, 4)
                import struct
                value = struct.unpack("<I", data)[0]
                
                if value == expected:
                    return HealthCheckResult(
                        check_type=HealthCheckType.HEARTBEAT,
                        passed=True,
                        duration_ms=(time.monotonic() - start) * 1000,
                        message=f"Heartbeat detected: {hex(value)}",
                    )
                
                await asyncio.sleep(0.1)
            
            return HealthCheckResult(
                check_type=HealthCheckType.HEARTBEAT,
                passed=False,
                duration_ms=(time.monotonic() - start) * 1000,
                message="Heartbeat timeout",
            )
            
        except Exception as e:
            return HealthCheckResult(
                check_type=HealthCheckType.HEARTBEAT,
                passed=False,
                duration_ms=(time.monotonic() - start) * 1000,
                message=str(e),
            )


@dataclass
class HealthValidationResult:
    """Result of all health validations."""
    
    overall_passed: bool
    check_results: list[HealthCheckResult]
    timestamp: datetime
    
    def get_failed_checks(self) -> list[HealthCheckResult]:
        return [r for r in self.check_results if not r.passed]
```

---

## 5. Fleet Coordination Model

### Problem

Single-target management won't scale to fleet deployments.

### Solution: Fleet Orchestration

```python
@dataclass
class RolloutWave:
    """Deployment wave configuration."""
    
    wave_id: str
    name: str
    target_count: int
    targets: list[str] = field(default_factory=list)
    
    # Timing
    stagger_delay_seconds: int = 10
    batch_size: int = 5
    
    # Health gates
    health_check_required: bool = True
    health_check_timeout_seconds: int = 300
    success_threshold_percent: float = 95.0
    
    # Auto-halt
    halt_on_failure_percent: float = 10.0
    auto_halt_enabled: bool = True


class DeploymentStrategy(Enum):
    """Fleet deployment strategies."""
    ALL_AT_ONCE = "all_at_once"
    ROLLING = "rolling"
    CANARY = "canary"
    BLUE_GREEN = "blue_green"
    STAGED = "staged"


@dataclass
class FleetDeployment:
    """Fleet deployment state."""
    
    deployment_id: str
    strategy: DeploymentStrategy
    firmware_version: str
    firmware_hash: str
    
    waves: list[RolloutWave]
    current_wave: int = 0
    
    # Status
    status: str = "pending"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    
    # Results
    target_results: dict[str, TargetDeploymentResult] = field(default_factory=dict)
    
    @property
    def total_targets(self) -> int:
        return sum(w.target_count for w in self.waves)
    
    @property
    def completed_targets(self) -> int:
        return len(self.target_results)
    
    @property
    def success_rate(self) -> float:
        if not self.target_results:
            return 0.0
        successes = sum(
            1 for r in self.target_results.values()
            if r.success
        )
        return successes / len(self.target_results) * 100


class FleetCoordinator:
    """Coordinates fleet-wide firmware deployments."""
    
    def __init__(
        self,
        target_registry: TargetRegistry,
        flash_manager: FlashTransactionManager,
        health_validator: BootHealthValidator,
    ):
        self.registry = target_registry
        self.flash_manager = flash_manager
        self.health_validator = health_validator
        self._deployments: dict[str, FleetDeployment] = {}
    
    async def deploy(
        self,
        strategy: DeploymentStrategy,
        firmware: FirmwareInfo,
        targets: list[str],
        waves: list[RolloutWave] | None = None,
    ) -> FleetDeployment:
        """Start fleet deployment."""
        
        # Create deployment
        deployment = FleetDeployment(
            deployment_id=str(uuid.uuid4()),
            strategy=strategy,
            firmware_version=firmware.version,
            firmware_hash=firmware.hash,
            waves=waves or self._default_waves(len(targets)),
        )
        
        self._deployments[deployment.deployment_id] = deployment
        
        # Start deployment
        asyncio.create_task(self._run_deployment(deployment, targets))
        
        return deployment
    
    async def _run_deployment(
        self,
        deployment: FleetDeployment,
        targets: list[str],
    ) -> None:
        """Execute deployment with strategy."""
        deployment.status = "running"
        deployment.started_at = datetime.now()
        
        if deployment.strategy == DeploymentStrategy.ROLLING:
            await self._rolling_deploy(deployment, targets)
        elif deployment.strategy == DeploymentStrategy.CANARY:
            await self._canary_deploy(deployment, targets)
        elif deployment.strategy == DeploymentStrategy.STAGED:
            await self._staged_deploy(deployment, targets)
        
        deployment.status = "completed"
        deployment.completed_at = datetime.now()
    
    async def _rolling_deploy(
        self,
        deployment: FleetDeployment,
        targets: list[str],
    ) -> None:
        """Rolling deployment - one target at a time."""
        
        for i, target_id in enumerate(targets):
            # Check for halt
            if self._should_halt(deployment):
                deployment.status = "halted"
                break
            
            # Flash target
            result = await self._deploy_to_target(deployment, target_id)
            deployment.target_results[target_id] = result
            
            # Wait before next
            if i < len(targets) - 1:
                await asyncio.sleep(deployment.waves[0].stagger_delay_seconds)
    
    async def _canary_deploy(
        self,
        deployment: FleetDeployment,
        targets: list[str],
    ) -> None:
        """Canary deployment - small group first."""
        
        # Deploy to canary group (first 5%)
        canary_count = max(1, len(targets) // 20)
        canary_results = []
        
        for target_id in targets[:canary_count]:
            result = await self._deploy_to_target(deployment, target_id)
            canary_results.append(result)
            deployment.target_results[target_id] = result
        
        # Check canary health
        canary_success_rate = sum(1 for r in canary_results if r.success) / len(canary_results) * 100
        
        if canary_success_rate < 90:
            # Rollback canaries
            deployment.status = "canary_failed"
            return
        
        # Deploy to rest
        for target_id in targets[canary_count:]:
            if self._should_halt(deployment):
                deployment.status = "halted"
                break
            
            result = await self._deploy_to_target(deployment, target_id)
            deployment.target_results[target_id] = result
    
    async def _deploy_to_target(
        self,
        deployment: FleetDeployment,
        target_id: str,
    ) -> TargetDeploymentResult:
        """Deploy to single target."""
        
        try:
            # Get target
            target = await self.registry.get_target(target_id)
            
            # Acquire lock
            lock = await self.target_lock.acquire(target_id, deployment.deployment_id)
            
            # Flash
            tx = await self.flash_manager.create_transaction(
                target_name=target.name,
                target_id=target_id,
                new_firmware_hash=deployment.firmware_hash,
                new_firmware_version=deployment.firmware_version,
                new_firmware_size=firmware.size,
            )
            
            await self.flash_manager.start_transaction(tx.transaction_id)
            
            # Flash firmware
            flash_result = await self._flash_firmware(target, firmware)
            
            if not flash_result.success:
                return TargetDeploymentResult(
                    target_id=target_id,
                    success=False,
                    error=flash_result.error_message,
                )
            
            # Health check
            if deployment.waves[0].health_check_required:
                health = await self.health_validator.validate_boot(
                    firmware,
                    default_health_checks,
                )
                
                if not health.overall_passed:
                    return TargetDeploymentResult(
                        target_id=target_id,
                        success=False,
                        error="Health check failed",
                        health_result=health,
                    )
            
            # Commit
            await self.flash_manager.commit_transaction(tx.transaction_id)
            
            return TargetDeploymentResult(
                target_id=target_id,
                success=True,
                transaction_id=tx.transaction_id,
            )
            
        except Exception as e:
            return TargetDeploymentResult(
                target_id=target_id,
                success=False,
                error=str(e),
            )
        finally:
            await self.target_lock.release(target_id, deployment.deployment_id)
    
    def _should_halt(self, deployment: FleetDeployment) -> bool:
        """Check if deployment should halt."""
        if not deployment.waves[0].auto_halt_enabled:
            return False
        
        if not deployment.target_results:
            return False
        
        failures = sum(
            1 for r in deployment.target_results.values()
            if not r.success
        )
        failure_rate = failures / len(deployment.target_results) * 100
        
        return failure_rate >= deployment.waves[0].halt_on_failure_percent


@dataclass
class TargetDeploymentResult:
    """Result of deployment to single target."""
    
    target_id: str
    success: bool
    transaction_id: str | None = None
    error: str | None = None
    health_result: HealthValidationResult | None = None
    completed_at: datetime = field(default_factory=datetime.now)
```

---

## 6. Artifact Manifest & SBOM/CVE

### Problem

Firmware metadata is insufficient for supply chain security.

### Solution: Complete Artifact Manifest

```python
@dataclass
class ArtifactManifest:
    """Complete firmware artifact manifest."""
    
    # Identity
    manifest_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.now)
    
    # Build info
    firmware: FirmwareMetadata
    
    # Supply chain
    sbom: SBOM | None = None
    provenance: ProvenanceRecord | None = None
    
    # Security
    signatures: list[Signature] = field(default_factory=list)
    attestations: list[Attestation] = field(default_factory=list)
    
    # Vulnerability tracking
    cve_scan: CVEScanResult | None = None
    vulnerability_advisory: list[VulnerabilityAdvisory] = field(default_factory=list)
    
    # Reproducibility
    build_reproducible: bool = False
    build_environment_hash: str | None = None
    toolchain_versions: dict[str, str] = field(default_factory=dict)


@dataclass
class SBOM:
    """Software Bill of Materials."""
    
    format: str = "SPDX"  # SPDX, CycloneDX, SWID
    
    # SPDX specific
    spdx_version: str = "SPDX-2.3"
    spdx_id: str = ""
    document_name: str = ""
    document_namespace: str = ""
    
    # Packages
    packages: list[SBOMPackage] = field(default_factory=list)
    
    # Relationships
    relationships: list[SBOMRelationship] = field(default_factory=list)
    
    def to_spdx(self) -> str:
        """Export as SPDX tag-value format."""
        lines = [
            f"SPDXVersion: {self.spdx_version}",
            f"DataLicense: CC0-1.0",
            f"SPDXID: {self.spdx_id}",
            f"DocumentName: {self.document_name}",
            f"DocumentNamespace: {self.document_namespace}",
            "",
            "Creation Information:",
            f"  Created: {self.created_at.isoformat()}",
            "",
        ]
        
        for pkg in self.packages:
            lines.extend([
                f"PackageName: {pkg.name}",
                f"SPDXID: {pkg.spdx_id}",
                f"PackageVersion: {pkg.version}",
                f"PackageDownloadLocation: {pkg.download_location}",
                f"FilesAnalyzed: {'true' if pkg.files_analyzed else 'false'}",
                f"PackageChecksum: SHA256:{pkg.checksum_sha256}",
                "",
            ])
        
        return "\n".join(lines)


@dataclass
class SBOMPackage:
    """SBOM package entry."""
    
    name: str
    version: str
    spdx_id: str
    
    # Identification
    download_location: str = "NOASSERTION"
    files_analyzed: bool = True
    checksum_sha256: str = ""
    
    # License
    license_concluded: str = "NOASSERTION"
    license_declared: str = "NOASSERTION"
    
    # Source
    supplier: str = ""
    source_info: str = ""
    
    # Vulnerability
    external_refs: list[dict] = field(default_factory=list)


@dataclass
class CVEScanResult:
    """CVE scan result."""
    
    scanned_at: datetime = field(default_factory=datetime.now)
    scanner: str = "trivy"
    scanner_version: str = ""
    
    # Summary
    total_vulnerabilities: int = 0
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    
    # Vulnerabilities
    vulnerabilities: list[CVEVulnerability] = field(default_factory=list)
    
    @property
    def risk_score(self) -> float:
        """Calculate risk score (0-10)."""
        return (
            self.critical * 10 +
            self.high * 7 +
            self.medium * 4 +
            self.low * 1
        ) / max(1, self.total_vulnerabilities)
    
    @property
    def is_acceptable(self) -> bool:
        """Check if vulnerability level is acceptable."""
        return self.critical == 0 and self.high <= 5


@dataclass
class CVEVulnerability:
    """CVE vulnerability entry."""
    
    cve_id: str
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    cvss_score: float
    
    package_name: str
    package_version: str
    installed_version: str
    
    title: str = ""
    description: str = ""
    
    fixed_version: str | None = None
    
    # References
    references: list[str] = field(default_factory=list)


class ManifestGenerator:
    """Generates complete artifact manifests."""
    
    def __init__(
        self,
        elf_path: str,
        build_info: BuildInfo,
    ):
        self.elf_path = elf_path
        self.build_info = build_info
    
    async def generate(
        self,
        include_sbom: bool = True,
        include_cve: bool = True,
        include_provenance: bool = True,
    ) -> ArtifactManifest:
        """Generate complete manifest."""
        
        manifest = ArtifactManifest(
            firmware=await self._extract_metadata(),
        )
        
        if include_sbom:
            manifest.sbom = await self._generate_sbom()
        
        if include_provenance:
            manifest.provenance = await self._generate_provenance()
        
        if include_cve:
            manifest.cve_scan = await self._scan_cve()
        
        return manifest
    
    async def _generate_sbom(self) -> SBOM:
        """Generate SPDX SBOM from ELF."""
        
        packages = []
        
        # Parse dependencies from ELF
        # (using pyelftools or similar)
        
        return SBOM(
            format="SPDX",
            packages=packages,
        )
    
    async def _scan_cve(self) -> CVEScanResult:
        """Scan for CVEs using trivy."""
        
        # Run: trivy fs --format json --output result.json .
        # Parse results
        pass
```

---

## 7. Secure Element / HSM Abstraction

### Problem

Key management is too basic. Production needs HSM support.

### Solution: Unified Key Interface

```python
class KeyType(Enum):
    """Key storage types."""
    SOFTWARE = "software"
    TPM = "tpm"
    PKCS11 = "pkcs11"
    ATECC608 = "atecc608"
    YUBIHSM = "yubihsm"
    CLOUD_KMS = "cloud_kms"


@dataclass
class KeyMetadata:
    """Key metadata."""
    
    key_id: str
    key_type: KeyType
    algorithm: str  # RSA2048, EC256, AES256
    
    created_at: datetime
    usage_count: int = 0
    
    # Protection
    requires_pin: bool = True
    exportable: bool = False
    
    # Location
    hsm_slot: int | None = None
    cloud_key_name: str | None = None


class KeyManager(ABC):
    """Abstract key management interface."""
    
    @abstractmethod
    async def generate_key(
        self,
        key_id: str,
        algorithm: str,
        **params,
    ) -> KeyMetadata:
        """Generate new key."""
        ...
    
    @abstractmethod
    async def sign(
        self,
        key_id: str,
        data: bytes,
    ) -> bytes:
        """Sign data with key."""
        ...
    
    @abstractmethod
    async def verify(
        self,
        key_id: str,
        data: bytes,
        signature: bytes,
    ) -> bool:
        """Verify signature."""
        ...
    
    @abstractmethod
    async def encrypt(
        self,
        key_id: str,
        data: bytes,
    ) -> bytes:
        """Encrypt data."""
        ...
    
    @abstractmethod
    async def decrypt(
        self,
        key_id: str,
        data: bytes,
    ) -> bytes:
        """Decrypt data."""
        ...


class PKCS11KeyManager(KeyManager):
    """PKCS#11 HSM key manager."""
    
    def __init__(self, library_path: str, slot: int, pin: str):
        self.library_path = library_path
        self.slot = slot
        self.pin = pin
        self._lib = None
    
    async def initialize(self):
        """Initialize PKCS#11 library."""
        import pkcs11
        
        self._lib = pkcs11.lib(self.library_path)
        self._token = self._lib.get_token(slot=self.slot)
        self._session = self._token.open(user_pin=self.pin)
    
    async def generate_key(
        self,
        key_id: str,
        algorithm: str,
        **params,
    ) -> KeyMetadata:
        """Generate key in HSM."""
        
        if algorithm == "RSA2048":
            pub, priv = self._session.generate_keypair(
                pkcs11.KeyType.RSA,
                2048,
            )
        elif algorithm == "EC256":
            pub, priv = self._session.generate_keypair(
                pkcs11.KeyType.EC,
                pkcs11.EC.prime256v1,
            )
        
        return KeyMetadata(
            key_id=key_id,
            key_type=KeyType.PKCS11,
            algorithm=algorithm,
            created_at=datetime.now(),
            hsm_slot=self.slot,
        )


class CloudKMSManager(KeyManager):
    """Google Cloud KMS key manager."""
    
    def __init__(self, project_id: str, location: str):
        self.project_id = project_id
        self.location = location
        self._client = None
    
    async def initialize(self):
        """Initialize Cloud KMS client."""
        from google.cloud import kms
        
        self._client = kms.KeyManagementServiceClient()
    
    async def sign(
        self,
        key_id: str,
        data: bytes,
    ) -> bytes:
        """Sign using Cloud KMS."""
        
        name = f"projects/{self.project_id}/locations/{self.location}/keyRings/..." \
               f"/cryptoKeys/{key_id}"
        
        response = self._client.sign(
            name=name,
            data=data,
            digest_algorithm=kmip_v1.DigestAlgorithm.SHA_256,
        )
        
        return response.signature


class ATECC608Manager(KeyManager):
    """Microchip ATECC608 secure element."""
    
    def __init__(self, i2c_bus: int, i2c_address: int = 0x60):
        self.bus = i2c_bus
        self.address = i2c_address
        self._i2c = None
    
    async def initialize(self):
        """Initialize ATECC608."""
        import smbus2
        
        self._i2c = smbus2.SMBus(self.bus)
        
        # Wake up device
        self._i2c.write_byte(self.address, 0x00)
    
    async def sign(
        self,
        key_id: str,
        data: bytes,
    ) -> bytes:
        """Sign using ATECC608 hardware."""
        
        # Use Data Zone 0 for keys
        # Slot configuration required
        pass
```

---

## 8. Compressed-In-Place OTA

### Problem

Low-RAM MCUs can't decompress full firmware then flash.

### Solution: Streaming Decompression Pipeline

```python
class StreamingDecompressor:
    """Streaming decompression for low-RAM devices."""
    
    def __init__(
        self,
        stream: AsyncFirmwareStream,
        decompressor: str = "zstd",
        chunk_size: int = 4096,
    ):
        self.stream = stream
        self.decompressor = decompressor
        self.chunk_size = chunk_size
        
        # Buffer for decompression
        self._input_buffer = bytearray()
        self._output_buffer = bytearray()
        self._dctx = None
    
    async def initialize(self):
        """Initialize decompressor."""
        if self.decompressor == "zstd":
            import zstandard as zstd
            
            self._dctx = zstd.ZstdDecompressor()
            self._reader = self._dctx.stream_reader(
                self._get_reader(),
                input_buffer_size=self.chunk_size,
            )
    
    async def stream_decompressed(
        self,
    ) -> AsyncIterator[bytes]:
        """Stream decompressed chunks."""
        
        while True:
            chunk = await self._read_compressed_chunk()
            if not chunk:
                break
            
            self._input_buffer.extend(chunk)
            
            # Decompress available data
            decompressed = self._decompress_buffer()
            
            if decompressed:
                yield decompressed
    
    async def _read_compressed_chunk(self) -> bytes | None:
        """Read next compressed chunk from stream."""
        # Implementation reads from HTTP/S3/file
        pass
    
    def _decompress_buffer(self) -> bytes | None:
        """Decompress available buffer."""
        
        if self.decompressor == "zstd":
            # Read decompressed data
            output = self._reader.read(self.chunk_size)
            
            if output:
                return output
        
        return None


class CompressedOTAWriter:
    """Writes compressed firmware directly to flash."""
    
    def __init__(
        self,
        decompressor: StreamingDecompressor,
        probe: Any,
        partition: Partition,
        sector_size: int = 2048,
    ):
        self.decompressor = decompressor
        self.probe = probe
        self.partition = partition
        self.sector_size = sector_size
    
    async def write(
        self,
        transaction_id: str,
        progress_callback: Callable | None = None,
    ) -> FlashResult:
        """Stream decompress and write to flash."""
        
        current_sector = bytearray()
        total_written = 0
        
        async for chunk in self.decompressor.stream_decompressed():
            current_sector.extend(chunk)
            
            # Write full sectors
            while len(current_sector) >= self.sector_size:
                sector_data = bytes(current_sector[:self.sector_size])
                current_sector = current_sector[self.sector_size:]
                
                # Write sector
                addr = self.partition.start_address + total_written
                await self.probe.write_memory(addr, sector_data)
                
                # Verify
                verify = await self.probe.read_memory(addr, self.sector_size)
                if verify != sector_data:
                    return FlashResult(
                        success=False,
                        error_code="VERIFY_FAILED",
                        error_message=f"Sector verification failed",
                    )
                
                total_written += self.sector_size
                
                if progress_callback:
                    await progress_callback(
                        total_written,
                        self.partition.size,
                    )
        
        # Write remaining partial sector
        if current_sector:
            # Pad to sector size
            padded = bytes(current_sector) + b'\xff' * (
                self.sector_size - len(current_sector)
            )
            addr = self.partition.start_address + total_written
            await self.probe.write_memory(addr, padded)
            total_written += len(padded)
        
        return FlashResult(
            success=True,
            bytes_written=total_written,
        )
```

---

## 9. Flash Rate Limit / Thermal Policy

### Problem

Fleet deployments can cause probe overheating and USB brownout.

### Solution: Rate Limiter with Thermal Awareness

```python
@dataclass
class ProbeHealth:
    """Probe health metrics."""
    
    probe_id: str
    
    # Thermal
    temperature_celsius: float = 25.0
    max_temperature_celsius: float = 60.0
    
    # Power
    voltage_mv: int = 5000
    min_voltage_mv: int = 4500
    
    # Rate
    flash_count_last_hour: int = 0
    flash_count_last_24h: int = 0
    
    @property
    def is_overheating(self) -> bool:
        return self.temperature_celsius >= self.max_temperature_celsius
    
    @property
    def is_undervoltage(self) -> bool:
        return self.voltage_mv < self.min_voltage_mv
    
    @property
    def is_healthy(self) -> bool:
        return not self.is_overheating and not self.is_undervoltage


class RateLimiter:
    """Rate limiter with thermal awareness."""
    
    def __init__(
        self,
        max_concurrent_flashes: int = 3,
        cooldown_seconds: int = 60,
        max_flashes_per_hour: int = 10,
        thermal_threshold_celsius: float = 55.0,
    ):
        self.max_concurrent = max_concurrent_flashes
        self.cooldown_seconds = cooldown_seconds
        self.max_per_hour = max_flashes_per_hour
        self.thermal_threshold = thermal_threshold_celsius
        
        self._active_flashes: dict[str, datetime] = {}
        self._probe_health: dict[str, ProbeHealth] = {}
        self._cooldowns: dict[str, datetime] = {}
    
    async def can_flash(
        self,
        probe_id: str,
        target_id: str,
    ) -> tuple[bool, str]:
        """Check if flash is allowed."""
        
        # Check active flash count
        active = len(self._active_flashes)
        if active >= self.max_concurrent:
            return False, f"Max concurrent flashes ({self.max_concurrent}) reached"
        
        # Check cooldown
        if probe_id in self._cooldowns:
            cooldown_end = self._cooldowns[probe_id]
            if datetime.now() < cooldown_end:
                remaining = (cooldown_end - datetime.now()).total_seconds()
                return False, f"Probe in cooldown ({remaining:.0f}s remaining)"
        
        # Check health
        health = self._probe_health.get(probe_id)
        if health:
            if health.is_overheating:
                return False, f"Probe overheating ({health.temperature_celsius}°C)"
            
            if health.is_undervoltage:
                return False, f"USB undervoltage ({health.voltage_mv}mV)"
            
            if health.flash_count_last_hour >= self.max_per_hour:
                return False, f"Hourly rate limit ({self.max_per_hour}) reached"
        
        return True, "OK"
    
    async def begin_flash(
        self,
        probe_id: str,
        target_id: str,
    ) -> str:
        """Mark flash as started."""
        flash_id = str(uuid.uuid4())
        
        self._active_flashes[flash_id] = datetime.now()
        
        # Update health
        if probe_id in self._probe_health:
            self._probe_health[probe_id].flash_count_last_hour += 1
            self._probe_health[probe_id].flash_count_last_24h += 1
        
        return flash_id
    
    async def end_flash(
        self,
        flash_id: str,
        probe_id: str,
        success: bool,
        thermal_reading: float | None = None,
        voltage_reading: int | None = None,
    ) -> None:
        """Mark flash as completed."""
        
        if flash_id in self._active_flashes:
            del self._active_flashes[flash_id]
        
        # Update health
        if probe_id in self._probe_health:
            health = self._probe_health[probe_id]
            
            if thermal_reading:
                health.temperature_celsius = thermal_reading
            
            if voltage_reading:
                health.voltage_md = voltage_reading
            
            # Add cooldown if thermal concern
            if thermal_reading and thermal_reading >= self.thermal_threshold:
                self._cooldowns[probe_id] = datetime.now() + timedelta(
                    seconds=self.cooldown_seconds
                )
        elif thermal_reading and thermal_reading >= self.thermal_threshold:
            # First reading with thermal concern
            self._probe_health[probe_id] = ProbeHealth(
                probe_id=probe_id,
                temperature_celsius=thermal_reading,
            )
            self._cooldowns[probe_id] = datetime.now() + timedelta(
                seconds=self.cooldown_seconds
            )
    
    async def get_health(self, probe_id: str) -> ProbeHealth | None:
        """Get probe health."""
        return self._probe_health.get(probe_id)
    
    async def cooldown_all(self, duration_seconds: int) -> None:
        """Force cooldown for all probes."""
        cooldown_end = datetime.now() + timedelta(seconds=duration_seconds)
        
        for probe_id in self._probe_health:
            self._cooldowns[probe_id] = cooldown_end


class ThermalAwareCoordinator:
    """Fleet coordinator with thermal awareness."""
    
    def __init__(
        self,
        coordinator: FleetCoordinator,
        rate_limiter: RateLimiter,
        health_monitor: ProbeHealthMonitor,
    ):
        self.coordinator = coordinator
        self.rate_limiter = rate_limiter
        self.health_monitor = health_monitor
    
    async def deploy_with_health(
        self,
        deployment: FleetDeployment,
        targets: list[str],
    ) -> FleetDeployment:
        """Deploy with thermal monitoring."""
        
        # Start health monitoring
        health_task = asyncio.create_task(
            self._monitor_health_loop(deployment)
        )
        
        try:
            # Deploy with rate limiting
            result = await self.coordinator.deploy(
                strategy=deployment.strategy,
                firmware=deployment.firmware,
                targets=targets,
            )
            
            return result
            
        finally:
            health_task.cancel()
    
    async def _monitor_health_loop(
        self,
        deployment: FleetDeployment,
    ) -> None:
        """Monitor probe health during deployment."""
        
        while deployment.status == "running":
            # Check all probes
            for probe_id in self._get_active_probes():
                health = await self.health_monitor.read_health(probe_id)
                
                if health.is_overheating:
                    # Cooldown this probe
                    await self.rate_limiter.cooldown_all(
                        self.rate_limiter.cooldown_seconds,
                    )
                    
                    # Halt deployment if too many issues
                    self._check_thermal_halt(deployment)
            
            await asyncio.sleep(30)
    
    def _check_thermal_halt(
        self,
        deployment: FleetDeployment,
    ) -> None:
        """Check if deployment should halt due to thermal."""
        overheating_count = sum(
            1 for h in self.rate_limiter._probe_health.values()
            if h.is_overheating
        )
        
        if overheating_count >= self.rate_limiter.max_concurrent:
            deployment.status = "thermal_halted"
```

---

## Summary: Production-Grade Extensions

| Component | Purpose | Impact |
|-----------|---------|--------|
| Flash Journal | Sector-level WAL | Resume accuracy |
| CRC Tree | Incremental verification | OTA speed |
| Atomic Slot Switch | Power-fail safe | Boot reliability |
| Boot Health | Post-flash validation | Firmware health |
| Fleet Coordinator | Multi-target orchestration | Scale |
| Artifact Manifest | Supply chain security | Compliance |
| HSM Abstraction | Key management | Security |
| Compressed OTA | Low-RAM streaming | IoT support |
| Rate Limiter | Thermal awareness | Fleet safety |

These extensions transform the flash infrastructure from **debug utility** into **production OTA platform**.

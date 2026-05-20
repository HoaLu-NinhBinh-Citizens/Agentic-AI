"""Phase 6.2 - Flash Infrastructure Module.

This module implements production-grade firmware flash infrastructure:
- Flash transactions with rollback support
- A/B firmware layout awareness
- Erase policy and wear leveling
- Flash resume capability
- Streaming flash from remote sources
- Symbol indexing for crash analysis
- Memory map validation
- Secure boot integration
- Probe transport capabilities
- Concurrency locking
- Recovery and replay integration

All components integrate with Phase 6.1 snapshot system for recovery.
"""

from .flash_transaction import (
    TransactionStatus,
    FlashTransaction,
    FlashTransactionManager,
    PartialFlashDetector,
    PartialFlashInfo,
)

from .flash_layout import (
    LayoutType,
    Partition,
    FlashLayout,
    ActiveSlotDetector,
    SlotSelector,
)

from .erase_policy import (
    EraseMode,
    ErasePolicy,
    SectorStats,
    WearLevelingMonitor,
    WearingWarning,
)

from .flash_resume import (
    FlashResumeState,
    ResumableFlashWriter,
    FlashResult,
)

from .streaming_flash import (
    AsyncFirmwareStream,
    StreamingFlashEngine,
)

from .symbol_index import (
    SymbolInfo,
    SourceLocation,
    SymbolIndex,
    SymbolIndexUpdater,
    SourceMapper,
)

from .memory_map_validator import (
    ValidationResult,
    ELFSection,
    MemoryMapValidator,
    ProtectedRegionManager,
)

from .secure_boot import (
    BootState,
    SecureBootPolicy,
    AntiRollbackChecker,
    MonotonicCounterUpdater,
)

from .flash_transport import (
    ProbeType,
    FlashTransportCapabilities,
    FlashStrategy,
    AdaptiveFlashStrategy,
)

from .flash_lock import (
    FlashLock,
    TargetFlashLock,
    LockManager,
)

from .recovery_infra import (
    PreFlashSnapshot,
    RollbackToSnapshot,
)


__all__ = [
    # Transaction
    "TransactionStatus",
    "FlashTransaction",
    "FlashTransactionManager",
    "PartialFlashDetector",
    "PartialFlashInfo",
    
    # Layout
    "LayoutType",
    "Partition",
    "FlashLayout",
    "ActiveSlotDetector",
    "SlotSelector",
    
    # Erase
    "EraseMode",
    "ErasePolicy",
    "SectorStats",
    "WearLevelingMonitor",
    "WearingWarning",
    
    # Resume
    "FlashResumeState",
    "ResumableFlashWriter",
    "FlashResult",
    
    # Streaming
    "AsyncFirmwareStream",
    "StreamingFlashEngine",
    
    # Symbol
    "SymbolInfo",
    "SourceLocation",
    "SymbolIndex",
    "SymbolIndexUpdater",
    "SourceMapper",
    
    # Validation
    "ValidationResult",
    "ELFSection",
    "MemoryMapValidator",
    "ProtectedRegionManager",
    
    # Secure Boot
    "BootState",
    "SecureBootPolicy",
    "AntiRollbackChecker",
    "MonotonicCounterUpdater",
    
    # Transport
    "ProbeType",
    "FlashTransportCapabilities",
    "FlashStrategy",
    "AdaptiveFlashStrategy",
    
    # Locking
    "FlashLock",
    "TargetFlashLock",
    "LockManager",
    
    # Recovery
    "PreFlashSnapshot",
    "RollbackToSnapshot",
]

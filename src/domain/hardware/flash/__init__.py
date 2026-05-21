"""Flash Hardware Domain - All flash-related components.

Phase 6.2: Complete flash infrastructure for embedded firmware operations.

Components:
- Flash Transaction Model (flash_transaction.py)
- Flash Resume (flash_resume.py)
- Flash Layout / A/B Slots (flash_layout.py)
- Recovery Infrastructure (recovery_infra.py)
- Secure Boot / Anti-rollback (secure_boot.py)
- Streaming Flash (streaming_flash.py)
- Symbol Index (symbol_index.py)
- Memory Map Validator (memory_map_validator.py)
- Flash Lock (flash_lock.py)
- Erase Policy (erase_policy.py)

NEW: Production-grade components:
- Flash Journal (flash_journal.py) - Sector-level WAL
- CRC Tree / Merkle Verification (crc_tree.py) - Incremental verification
- Power-Fail Safe Slot Switching (safe_slot_switch.py) - Atomic boot
- Boot Health Validator (boot_health.py) - Runtime health checks
- Fleet Coordinator (fleet_coordinator.py) - Multi-device rollout
- Artifact Manifest (artifact_manifest.py) - SBOM and metadata
- HSM Abstraction (hsm_abstraction.py) - Secure element support
- Streaming Decompression (streaming_decompress.py) - Low-RAM OTA
- Flash Rate Limit (flash_rate_limit.py) - Fleet safety
"""

from __future__ import annotations

# Core flash components
from .flash_transaction import (
    TransactionStatus,
    FlashTransaction,
    FlashTransactionManager,
    PartialFlashDetector,
    PartialFlashInfo,
)

from .flash_resume import (
    FlashResumeState,
    FlashResult,
    ResumableFlashWriter,
)

from .flash_layout import (
    LayoutType,
    Partition,
    FlashLayout,
    ActiveSlotDetector,
    SlotSelector,
)

from .memory_map_validator import (
    ValidationResult,
    ELFSection,
    MemoryRegion,
    MemoryMapValidator,
    ProtectedRegionManager,
)

from .secure_boot import (
    BootState,
    SecureBootPolicy,
    AntiRollbackChecker,
    MonotonicCounterUpdater,
    SecureBootValidator,
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

from .flash_lock import (
    FlashLock,
    TargetFlashLock,
    LockManager,
)

from .erase_policy import (
    EraseMode,
    ErasePolicy,
    SectorStats,
    WearingWarning,
    WearLevelingMonitor,
)

from .recovery_infra import (
    PreFlashSnapshot,
    RollbackToSnapshot,
    RecoveryOrchestrator,
    FlashRecoveryWorkflow,
)

# NEW: Production-grade components
from .flash_journal import (
    JournalOperation,
    SectorChecksum,
    JournalEntry,
    FlashJournal,
    JournalRecoveryPlanner,
)

from .crc_tree import (
    ChunkInfo,
    MerkleNode,
    VerificationTree,
    IncrementalVerifier,
    FirmwareManifest,
    DeltaVerifier,
)

from .safe_slot_switch import (
    BootState as SlotBootState,
    SlotBootContext,
    BootHealthConfig,
    HealthCheckResult,
    SlotBootRecord,
    PendingBootMarker,
    SafeSlotSwitcher,
    BootHealthValidator,
    SlotSwitchingWorkflow,
)

from .boot_health import (
    HealthStatus,
    HealthCheckType,
    HeartbeatConfig,
    WatchdogInfo,
    HealthMetric,
    BootHealthReport,
    BootHealthMonitor,
    HealthTimeoutManager,
    BootSuccessValidator,
    RuntimeHealthWatcher,
)

from .fleet_coordinator import (
    RolloutStrategy,
    RolloutState,
    DeploymentTarget,
    RolloutWave,
    RolloutConfig,
    FleetRollout,
    FleetCoordinator,
    RolloutHistory,
    CanaryAnalyzer,
)

from .artifact_manifest import (
    BuildInfo,
    GitInfo,
    DependencyInfo,
    SBOMEntry,
    CycloneDXComponent,
    VulnerabilityReference,
    FirmwareArtifact,
    ArtifactManifestBuilder,
    ReproducibleBuildVerifier,
    ArtifactRegistry,
)

from .hsm_abstraction import (
    HSMType,
    KeyInfo,
    SignatureResult,
    HSMOperationResult,
    SecureElement,
    PKCS11Config,
    PKCS11SecureElement,
    TPMConfig,
    TPMSecureElement,
    ATECCConfig,
    ATECCSecureElement,
    SoftwareSecureElement,
    KeyManager,
    create_hsm,
)

from .streaming_decompress import (
    DecompressionConfig,
    CompressionType,
    ChunkInfo as DecompressChunkInfo,
    DecompressionResult,
    StreamingDecompressor,
    ZstdStreamingDecompressor,
    DeltaDecompressor,
    FlashDecompressionPipeline,
    DecompressionResumeManager,
    ChunkPipelineConfig,
    ChunkProcessor,
)

from .flash_rate_limit import (
    ThermalState,
    ThermalConfig,
    PowerConfig,
    RateLimitConfig,
    DeviceThermalState,
    FlashRateLimiter,
    ThermalMonitor,
    PowerBudgetManager,
    FleetSafetyController,
    CooldownScheduler,
)

__all__ = [
    # Transaction & Resume
    "TransactionStatus",
    "FlashTransaction",
    "FlashTransactionManager",
    "PartialFlashDetector",
    "PartialFlashInfo",
    "FlashResumeState",
    "FlashResult",
    "ResumableFlashWriter",
    
    # Layout & Slots
    "LayoutType",
    "Partition",
    "FlashLayout",
    "ActiveSlotDetector",
    "SlotSelector",
    
    # Validation
    "ValidationResult",
    "ELFSection",
    "MemoryRegion",
    "MemoryMapValidator",
    "ProtectedRegionManager",
    
    # Security
    "BootState",
    "SecureBootPolicy",
    "AntiRollbackChecker",
    "MonotonicCounterUpdater",
    "SecureBootValidator",
    
    # Streaming
    "AsyncFirmwareStream",
    "StreamingFlashEngine",
    
    # Symbols
    "SymbolInfo",
    "SourceLocation",
    "SymbolIndex",
    "SymbolIndexUpdater",
    "SourceMapper",
    
    # Lock
    "FlashLock",
    "TargetFlashLock",
    "LockManager",
    
    # Erase
    "EraseMode",
    "ErasePolicy",
    "SectorStats",
    "WearingWarning",
    "WearLevelingMonitor",
    
    # Recovery
    "PreFlashSnapshot",
    "RollbackToSnapshot",
    "RecoveryOrchestrator",
    "FlashRecoveryWorkflow",
    
    # NEW: Flash Journal
    "JournalOperation",
    "SectorChecksum",
    "JournalEntry",
    "FlashJournal",
    "JournalRecoveryPlanner",
    
    # NEW: CRC Tree / Merkle
    "ChunkInfo",
    "MerkleNode",
    "VerificationTree",
    "IncrementalVerifier",
    "FirmwareManifest",
    "DeltaVerifier",
    
    # NEW: Safe Slot Switch
    "SlotBootState",
    "SlotBootContext",
    "BootHealthConfig",
    "HealthCheckResult",
    "SlotBootRecord",
    "PendingBootMarker",
    "SafeSlotSwitcher",
    "BootHealthValidator",
    "SlotSwitchingWorkflow",
    
    # NEW: Boot Health
    "HealthStatus",
    "HealthCheckType",
    "HeartbeatConfig",
    "WatchdogInfo",
    "HealthMetric",
    "BootHealthReport",
    "BootHealthMonitor",
    "HealthTimeoutManager",
    "BootSuccessValidator",
    "RuntimeHealthWatcher",
    
    # NEW: Fleet Coordinator
    "RolloutStrategy",
    "RolloutState",
    "DeploymentTarget",
    "RolloutWave",
    "RolloutConfig",
    "FleetRollout",
    "FleetCoordinator",
    "RolloutHistory",
    "CanaryAnalyzer",
    
    # NEW: Artifact Manifest
    "BuildInfo",
    "GitInfo",
    "DependencyInfo",
    "SBOMEntry",
    "CycloneDXComponent",
    "VulnerabilityReference",
    "FirmwareArtifact",
    "ArtifactManifestBuilder",
    "ReproducibleBuildVerifier",
    "ArtifactRegistry",
    
    # NEW: HSM Abstraction
    "HSMType",
    "KeyInfo",
    "SignatureResult",
    "HSMOperationResult",
    "SecureElement",
    "PKCS11Config",
    "PKCS11SecureElement",
    "TPMConfig",
    "TPMSecureElement",
    "ATECCConfig",
    "ATECCSecureElement",
    "SoftwareSecureElement",
    "KeyManager",
    "create_hsm",
    
    # NEW: Streaming Decompression
    "DecompressionConfig",
    "CompressionType",
    "DecompressChunkInfo",
    "DecompressionResult",
    "StreamingDecompressor",
    "ZstdStreamingDecompressor",
    "DeltaDecompressor",
    "FlashDecompressionPipeline",
    "DecompressionResumeManager",
    "ChunkPipelineConfig",
    "ChunkProcessor",
    
    # NEW: Flash Rate Limit
    "ThermalState",
    "ThermalConfig",
    "PowerConfig",
    "RateLimitConfig",
    "DeviceThermalState",
    "FlashRateLimiter",
    "ThermalMonitor",
    "PowerBudgetManager",
    "FleetSafetyController",
    "CooldownScheduler",
]

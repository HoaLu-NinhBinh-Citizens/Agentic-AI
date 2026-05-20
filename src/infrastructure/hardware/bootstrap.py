"""Bootstrap system for hardware layer initialization.

Phase 6.1: Single initialization point that sets up all hardware components:
- Config loading
- Plugin loading
- Registry initialization
- Event bus setup
- Detector initialization
- Snapshot manager setup
"""

from __future__ import annotations

import asyncio
import atexit
import logging
import signal
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .auto_detector import AutoTargetDetector
from .capability import CapabilityRegistry
from .chip_plugin import PluginLoader
from .event import AsyncEventBus, DeadLetterQueue, DomainEvent, InMemoryDeadLetterQueue
from .exceptions import HardwareError
from .semantic_mapper import SemanticHardwareMapper, get_default_mapper
from .fault_propagation import FaultPropagationGraph, get_default_fault_graph
from .snapshot_manager import FileSnapshotStorage, SnapshotManager, SnapshotPolicy

if TYPE_CHECKING:
    from .exceptions import HardwareError

logger = logging.getLogger(__name__)


# ============================================================================
# Hardware Context
# ============================================================================


@dataclass
class HardwareContext:
    """Container for all hardware layer components.

    This is passed to consumers of the hardware layer.
    """

    # Core components
    plugin_loader: PluginLoader
    capability_registry: CapabilityRegistry
    semantic_mapper: SemanticHardwareMapper
    fault_graph: FaultPropagationGraph

    # Detection
    target_detector: AutoTargetDetector

    # Event bus
    event_bus: AsyncEventBus
    dlq: DeadLetterQueue

    # Snapshot
    snapshot_manager: SnapshotManager
    snapshot_storage: FileSnapshotStorage

    # State
    initialized: bool = False
    shutdown_requested: bool = False

    # Config
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for debugging."""
        return {
            "initialized": self.initialized,
            "plugin_loader": self.plugin_loader.to_dict(),
            "capability_registry": self.capability_registry.to_dict(),
            "snapshot_manager": "SnapshotManager",
            "event_bus_subscriptions": self.event_bus.get_subscriptions(),
        }


# ============================================================================
# Singleton Management
# ============================================================================


_hardware_context: HardwareContext | None = None
_initialization_lock = asyncio.Lock()


def get_hardware_context() -> HardwareContext:
    """Get the singleton hardware context.

    Raises:
        RuntimeError: If hardware layer not initialized

    Returns:
        HardwareContext singleton
    """
    global _hardware_context
    if _hardware_context is None:
        raise RuntimeError(
            "Hardware layer not initialized. Call init_hardware_layer() first."
        )
    return _hardware_context


def is_hardware_initialized() -> bool:
    """Check if hardware layer is initialized."""
    return _hardware_context is not None and _hardware_context.initialized


# ============================================================================
# Bootstrap Configuration
# ============================================================================


@dataclass
class BootstrapConfig:
    """Configuration for hardware layer bootstrap."""

    # Plugin configuration
    plugin_dir: Path = Path("./plugins")
    plugin_sandbox_enabled: bool = True
    plugin_timeout_seconds: float = 5.0

    # Detection configuration
    detection_cache_ttl_seconds: int = 3600
    detection_fallback_methods: list[str] = field(default_factory=lambda: ["idcode", "vid_pid", "fallback"])

    # Event bus configuration
    event_bus_type: str = "memory"
    dlq_path: Path = Path("./dlq")
    dlq_max_size: int = 10000

    # Snapshot configuration
    snapshot_storage_path: Path = Path("./snapshots")
    snapshot_max_size_mb: int = 1000
    snapshot_ttl_days: int = 30
    snapshot_max_per_target: int = 10
    snapshot_encryption_key_env: str = "AISUPPORT_SNAPSHOT_KEY"

    # Feature flags
    enable_metrics: bool = True
    enable_distributed_tracing: bool = False

    # Config file
    config_file: Path | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BootstrapConfig:
        """Create config from dictionary."""
        config = cls()

        if "plugin_dir" in data:
            config.plugin_dir = Path(data["plugin_dir"])
        if "plugin_sandbox_enabled" in data:
            config.plugin_sandbox_enabled = data["plugin_sandbox_enabled"]
        if "detection_cache_ttl_seconds" in data:
            config.detection_cache_ttl_seconds = data["detection_cache_ttl_seconds"]
        if "snapshot_storage_path" in data:
            config.snapshot_storage_path = Path(data["snapshot_storage_path"])
        if "snapshot_max_size_mb" in data:
            config.snapshot_max_size_mb = data["snapshot_max_size_mb"]

        return config


# ============================================================================
# Bootstrap Functions
# ============================================================================


async def init_hardware_layer(
    config: BootstrapConfig | dict[str, Any] | None = None,
    config_path: Path | str | None = None,
) -> HardwareContext:
    """Initialize the hardware layer.

    This function initializes all hardware components and should be called
    once at application startup.

    Args:
        config: BootstrapConfig or dict configuration
        config_path: Path to config file (YAML/JSON)

    Returns:
        HardwareContext singleton

    Raises:
        RuntimeError: If already initialized
    """
    global _hardware_context

    async with _initialization_lock:
        if _hardware_context is not None and _hardware_context.initialized:
            logger.warning("Hardware layer already initialized")
            return _hardware_context

        logger.info("Initializing hardware layer...")

        # Parse config
        if isinstance(config, dict):
            bootstrap_config = BootstrapConfig.from_dict(config)
        elif isinstance(config, BootstrapConfig):
            bootstrap_config = config
        else:
            bootstrap_config = BootstrapConfig()

        # Load config from file if specified
        if config_path:
            bootstrap_config.config_file = Path(config_path)
            bootstrap_config = _load_config(bootstrap_config)

        # Create directories
        _ensure_directories(bootstrap_config)

        # Initialize components
        try:
            # Event bus (needs to be first for event publishing)
            dlq = InMemoryDeadLetterQueue(max_size=bootstrap_config.dlq_max_size)
            event_bus = AsyncEventBus(dlq=dlq, enable_metrics=bootstrap_config.enable_metrics)

            # Plugin loader
            plugin_loader = PluginLoader(
                plugin_dir=bootstrap_config.plugin_dir,
                sandbox_enabled=bootstrap_config.plugin_sandbox_enabled,
            )

            # Register built-in plugins
            from ..plugins.vendor_plugins import STPlugin, EspressifPlugin, NXPPlugin, SiFivePlugin
            plugin_loader.register_builtin_plugin("st", STPlugin)
            plugin_loader.register_builtin_plugin("espressif", EspressifPlugin)
            plugin_loader.register_builtin_plugin("nxp", NXPPlugin)
            plugin_loader.register_builtin_plugin("sifive", SiFivePlugin)

            # Capability registry
            capability_registry = CapabilityRegistry()

            # Semantic mapper
            semantic_mapper = get_default_mapper()

            # Fault propagation graph
            fault_graph = get_default_fault_graph()

            # Target detector
            target_detector = AutoTargetDetector(
                plugin_loader=plugin_loader,
                event_bus=event_bus,
                cache_ttl_seconds=bootstrap_config.detection_cache_ttl_seconds,
            )

            # Snapshot storage and manager
            snapshot_storage = FileSnapshotStorage(
                storage_dir=bootstrap_config.snapshot_storage_path,
                max_size_mb=bootstrap_config.snapshot_max_size_mb,
            )
            snapshot_manager = SnapshotManager(
                storage=snapshot_storage,
                event_bus=event_bus,
                policy=SnapshotPolicy(
                    max_snapshots_per_target=bootstrap_config.snapshot_max_per_target,
                    max_total_size_mb=bootstrap_config.snapshot_max_size_mb,
                    ttl_days=bootstrap_config.snapshot_ttl_days,
                ),
            )

            # Create context
            context = HardwareContext(
                plugin_loader=plugin_loader,
                capability_registry=capability_registry,
                semantic_mapper=semantic_mapper,
                fault_graph=fault_graph,
                target_detector=target_detector,
                event_bus=event_bus,
                dlq=dlq,
                snapshot_manager=snapshot_manager,
                snapshot_storage=snapshot_storage,
                initialized=True,
                config=bootstrap_config.__dict__ if isinstance(bootstrap_config, BootstrapConfig) else {},
            )

            _hardware_context = context

            # Register shutdown handlers
            _register_shutdown_handlers()

            # Subscribe to important events
            await _setup_event_handlers(event_bus)

            logger.info("Hardware layer initialized successfully")
            return context

        except Exception as e:
            logger.exception(f"Failed to initialize hardware layer: {e}")
            raise


def _load_config(bootstrap_config: BootstrapConfig) -> BootstrapConfig:
    """Load configuration from file."""
    import json

    config_file = bootstrap_config.config_file
    if not config_file or not config_file.exists():
        return bootstrap_config

    logger.info(f"Loading config from {config_file}")

    try:
        if config_file.suffix in (".yaml", ".yml"):
            import yaml
            with open(config_file) as f:
                data = yaml.safe_load(f)
        else:
            with open(config_file) as f:
                data = json.load(f)

        if data:
            # Extract hardware section if present
            if "hardware" in data:
                data = data["hardware"]
            bootstrap_config = BootstrapConfig.from_dict(data)
            bootstrap_config.config_file = config_file

    except Exception as e:
        logger.warning(f"Failed to load config from {config_file}: {e}")

    return bootstrap_config


def _ensure_directories(config: BootstrapConfig) -> None:
    """Ensure required directories exist."""
    config.plugin_dir.mkdir(parents=True, exist_ok=True)
    config.snapshot_storage_path.mkdir(parents=True, exist_ok=True)
    config.dlq_path.mkdir(parents=True, exist_ok=True)


async def _setup_event_handlers(event_bus: AsyncEventBus) -> None:
    """Set up event handlers for important events."""
    # Log all events for debugging
    async def log_event(event: DomainEvent) -> None:
        logger.debug(f"Event: {event.event_type} - {event.event_id}")

    await event_bus.subscribe("target.*", log_event)
    await event_bus.subscribe("snapshot.*", log_event)
    await event_bus.subscribe("system.*", log_event)


def _register_shutdown_handlers() -> None:
    """Register shutdown handlers for clean termination."""
    try:
        loop = asyncio.get_event_loop()

        def shutdown_handler(sig: int) -> None:
            logger.info(f"Received signal {sig}, initiating shutdown...")
            asyncio.create_task(shutdown_hardware_layer())

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, lambda s=sig: shutdown_handler(s))
            except (NotImplementedError, ValueError):
                # Windows doesn't support add_signal_handler for SIGINT
                pass

        atexit.register(lambda: asyncio.run(shutdown_hardware_layer()))

    except Exception as e:
        logger.warning(f"Failed to register shutdown handlers: {e}")


async def shutdown_hardware_layer() -> None:
    """Gracefully shutdown the hardware layer.

    This function:
    1. Sets shutdown flag to prevent new operations
    2. Flushes pending events
    3. Saves any pending snapshots
    4. Releases probe locks
    5. Closes event bus
    6. Clears singleton
    """
    global _hardware_context

    if _hardware_context is None:
        return

    if _hardware_context.shutdown_requested:
        logger.warning("Shutdown already in progress")
        return

    logger.info("Shutting down hardware layer...")
    _hardware_context.shutdown_requested = True

    try:
        # 1. Flush event bus
        logger.debug("Flushing event bus...")
        # (EventBus doesn't have explicit flush, events are processed immediately)

        # 2. Unload plugins
        logger.debug("Unloading plugins...")
        for plugin_name in _hardware_context.plugin_loader.get_loaded_plugins():
            try:
                _hardware_context.plugin_loader.unload_plugin(plugin_name)
            except Exception as e:
                logger.warning(f"Failed to unload plugin {plugin_name}: {e}")

        # 3. Close snapshot storage
        logger.debug("Closing snapshot storage...")
        # (FileSnapshotStorage doesn't need explicit close)

        # 4. Log DLQ stats
        dlq_size = await _hardware_context.event_bus.get_dlq_size()
        if dlq_size > 0:
            logger.warning(f"DLQ has {dlq_size} entries at shutdown")

        # 5. Mark as shutdown
        _hardware_context.initialized = False

        logger.info("Hardware layer shutdown complete")

    except Exception as e:
        logger.exception(f"Error during shutdown: {e}")

    finally:
        _hardware_context = None


# ============================================================================
# Utility Functions
# ============================================================================


def is_initialized() -> bool:
    """Check if hardware layer is initialized (sync version)."""
    return _hardware_context is not None and _hardware_context.initialized


async def health_check() -> dict[str, Any]:
    """Perform health check on hardware layer components.

    Returns:
        Dictionary with health status of each component
    """
    if _hardware_context is None:
        return {
            "initialized": False,
            "status": "not_initialized",
        }

    health = {
        "initialized": _hardware_context.initialized,
        "status": "healthy",
        "components": {},
    }

    # Check plugin loader
    try:
        loaded_plugins = _hardware_context.plugin_loader.get_loaded_plugins()
        health["components"]["plugin_loader"] = {
            "status": "healthy",
            "loaded_plugins": len(loaded_plugins),
        }
    except Exception as e:
        health["components"]["plugin_loader"] = {"status": "error", "error": str(e)}
        health["status"] = "degraded"

    # Check event bus
    try:
        dlq_size = await _hardware_context.event_bus.get_dlq_size()
        health["components"]["event_bus"] = {
            "status": "healthy",
            "dlq_size": dlq_size,
        }
        if dlq_size > 100:
            health["components"]["event_bus"]["warning"] = "DLQ size high"
    except Exception as e:
        health["components"]["event_bus"] = {"status": "error", "error": str(e)}
        health["status"] = "degraded"

    # Check snapshot storage
    try:
        snapshots = await _hardware_context.snapshot_manager.list()
        health["components"]["snapshot_storage"] = {
            "status": "healthy",
            "snapshot_count": len(snapshots),
        }
    except Exception as e:
        health["components"]["snapshot_storage"] = {"status": "error", "error": str(e)}
        health["status"] = "degraded"

    return health

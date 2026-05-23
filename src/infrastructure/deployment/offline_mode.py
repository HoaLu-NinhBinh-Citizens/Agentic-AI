"""Offline mode core (Phase 15.3).

Provides offline operation capabilities:
- Local-first architecture
- Offline data storage
- Manual update system
- USB approval workflow
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SyncStatus(Enum):
    """Sync status."""
    SYNCED = "synced"
    PENDING = "pending"
    CONFLICT = "conflict"
    OFFLINE = "offline"


@dataclass
class OfflineConfig:
    """Offline mode configuration."""
    data_dir: Path = Path("data/offline")
    sync_enabled: bool = False
    require_usb_approval: bool = True
    auto_backup: bool = True
    max_local_storage_gb: int = 100


@dataclass
class LocalData:
    """Local data entry."""
    data_id: str
    data_type: str  # firmware, config, model, patch
    
    # Content
    content_hash: str = ""
    content_size: int = 0
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    source: str = "local"  # local, sync, usb
    
    # Sync
    sync_status: SyncStatus = SyncStatus.SYNCED
    sync_timestamp: datetime | None = None
    
    # Approval
    approved: bool = False
    approved_by: str = ""
    approved_at: datetime | None = None


@dataclass
class UpdatePackage:
    """Offline update package."""
    package_id: str
    version: str
    
    # Content
    content_path: Path | None = None
    content_hash: str = ""
    
    # Approval
    requires_approval: bool = True
    approved: bool = False
    
    # Status
    applied: bool = False
    applied_at: datetime | None = None


class LocalStorage:
    """Local storage manager."""
    
    def __init__(self, config: OfflineConfig) -> None:
        self._config = config
        self._data: dict[str, LocalData] = {}
        config.data_dir.mkdir(parents=True, exist_ok=True)
    
    def store(
        self,
        data_id: str,
        data_type: str,
        content: bytes,
        source: str = "local",
    ) -> LocalData:
        """Store data locally."""
        import hashlib
        
        content_hash = hashlib.sha256(content).hexdigest()
        
        data = LocalData(
            data_id=data_id,
            data_type=data_type,
            content_hash=content_hash,
            content_size=len(content),
            source=source,
            sync_status=SyncStatus.OFFLINE,
        )
        
        self._data[data_id] = data
        
        # Save to disk
        self._save_to_disk(data_id, content)
        
        logger.info("Data stored locally", data_id=data_id, size=len(content))
        return data
    
    def _save_to_disk(self, data_id: str, content: bytes) -> None:
        """Save content to disk."""
        file_path = self._config.data_dir / f"{data_id}.bin"
        file_path.write_bytes(content)
    
    def retrieve(self, data_id: str) -> bytes | None:
        """Retrieve data."""
        data = self._data.get(data_id)
        if not data:
            return None
        
        file_path = self._config.data_dir / f"{data_id}.bin"
        if file_path.exists():
            return file_path.read_bytes()
        
        return None
    
    def get_metadata(self, data_id: str) -> LocalData | None:
        """Get data metadata."""
        return self._data.get(data_id)


class OfflineManager:
    """Offline mode manager.
    
    Phase 15.3: Offline mode core
    """
    
    def __init__(self, config: OfflineConfig | None = None) -> None:
        self._config = config or OfflineConfig()
        self._storage = LocalStorage(self._config)
        self._update_queue: list[UpdatePackage] = []
        self._online = False
    
    def set_online_status(self, online: bool) -> None:
        """Set online status."""
        self._online = online
        logger.info("Online status changed", online=online)
    
    @property
    def is_online(self) -> bool:
        """Check if online."""
        return self._online
    
    def store_firmware(
        self,
        firmware_id: str,
        content: bytes,
        version: str,
    ) -> LocalData:
        """Store firmware offline."""
        return self._storage.store(firmware_id, "firmware", content, "usb")
    
    def store_config(
        self,
        config_id: str,
        content: bytes,
    ) -> LocalData:
        """Store configuration offline."""
        return self._storage.store(config_id, "config", content)
    
    def get_firmware(self, firmware_id: str) -> bytes | None:
        """Get firmware."""
        return self._storage.retrieve(firmware_id)
    
    def import_update(
        self,
        package: UpdatePackage,
        content: bytes,
    ) -> str:
        """Import update from USB."""
        # Store content
        data = self._storage.store(
            package.package_id,
            "update",
            content,
            source="usb",
        )
        
        # Add to queue
        self._update_queue.append(package)
        
        logger.info("Update imported", package_id=package.package_id)
        return package.package_id
    
    def approve_update(self, package_id: str, approved_by: str) -> bool:
        """Approve update for installation."""
        for package in self._update_queue:
            if package.package_id == package_id:
                if not self._config.require_usb_approval:
                    package.approved = True
                else:
                    package.requires_approval = True
                    package.approved = True
                
                package.approved_by = approved_by
                logger.info("Update approved", package_id=package_id, by=approved_by)
                return True
        
        return False
    
    def apply_update(self, package_id: str) -> bool:
        """Apply approved update."""
        for package in self._update_queue:
            if package.package_id == package_id:
                if self._config.require_usb_approval and not package.approved:
                    logger.warning("Update not approved", package_id=package_id)
                    return False
                
                # Apply update
                package.applied = True
                package.applied_at = datetime.now()
                
                logger.info("Update applied", package_id=package_id)
                return True
        
        return False
    
    def get_pending_updates(self) -> list[UpdatePackage]:
        """Get pending updates."""
        return [p for p in self._update_queue if not p.applied]
    
    def get_storage_stats(self) -> dict[str, Any]:
        """Get storage statistics."""
        total_size = sum(d.content_size for d in self._storage._data.values())
        return {
            "total_items": len(self._storage._data),
            "total_size_mb": total_size / (1024 * 1024),
            "max_storage_gb": self._config.max_local_storage_gb,
            "pending_updates": len(self.get_pending_updates()),
            "online": self._online,
        }


# Global manager
_offline_manager: OfflineManager | None = None


def get_offline_manager(config: OfflineConfig | None = None) -> OfflineManager:
    """Get global offline manager."""
    global _offline_manager
    if _offline_manager is None:
        _offline_manager = OfflineManager(config)
    return _offline_manager


if __name__ == "__main__":
    manager = get_offline_manager(OfflineConfig(
        data_dir=Path("data/test_offline"),
        require_usb_approval=True,
    ))
    
    print("Offline Mode")
    print("=" * 40)
    print(f"Online: {manager.is_online}")
    
    # Store firmware
    firmware = manager.store_firmware("fw_v1", b"firmware content", "1.0.0")
    print(f"Stored firmware: {firmware.data_id}")
    
    # Import update
    update = UpdatePackage(
        package_id="update_001",
        version="1.1.0",
    )
    manager.import_update(update, b"update content")
    
    # Stats
    stats = manager.get_storage_stats()
    print(f"\nStorage: {stats['total_items']} items, {stats['total_size_mb']:.2f} MB")
    print(f"Pending updates: {stats['pending_updates']}")

"""Deployment modes and configuration (Phase 15.1).

Supports multiple deployment modes:
- SaaS (cloud)
- On-premise
- Hybrid
- Air-gapped (offline)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class DeploymentMode(Enum):
    """Deployment mode types."""
    SAAS = "saas"           # Cloud-hosted
    ON_PREMISE = "on_premise" # On-premise installation
    HYBRID = "hybrid"       # Mixed cloud/on-prem
    AIR_GAPPED = "air_gapped"  # Fully offline


class DataResidency(Enum):
    """Data residency requirements."""
    CLOUD = "cloud"           # Data in cloud
    REGIONAL = "regional"     # Data in specific region
    LOCAL = "local"          # Data stays local
    NONE = "none"            # No data persistence


class NetworkMode(Enum):
    """Network connectivity mode."""
    ONLINE = "online"         # Full internet
    PARTIAL = "partial"       # Limited connectivity
    OFFLINE = "offline"       # No internet


@dataclass
class DeploymentConfig:
    """Deployment configuration."""
    mode: DeploymentMode
    data_residency: DataResidency
    network_mode: NetworkMode
    
    # Features
    enable_telemetry: bool = True
    enable_cloud_sync: bool = True
    enable_remote_update: bool = True
    
    # Security
    require_encryption: bool = True
    require_auth: bool = True
    audit_enabled: bool = True
    
    # Storage
    storage_backend: str = "local"  # "local", "s3", "gcs", "azure"
    cache_backend: str = "memory"  # "memory", "redis", "disk"


@dataclass
class SaaSConfig(DeploymentConfig):
    """SaaS-specific configuration."""
    mode = DeploymentMode.SAAS
    data_residency = DataResidency.REGIONAL
    network_mode = NetworkMode.ONLINE
    
    api_endpoint: str = ""
    region: str = "us-east-1"
    multi_tenant: bool = True
    enable_beta_features: bool = False


@dataclass
class OnPremiseConfig(DeploymentConfig):
    """On-premise configuration."""
    mode = DeploymentMode.ON_PREMISE
    data_residency = DataResidency.LOCAL
    network_mode = NetworkMode.PARTIAL
    
    license_key: str = ""
    admin_email: str = ""
    max_agents: int = 10
    storage_path: str = "/data/aisupport"


@dataclass
class HybridConfig(DeploymentConfig):
    """Hybrid configuration."""
    mode = DeploymentMode.HYBRID
    data_residency = DataResidency.REGIONAL
    network_mode = NetworkMode.PARTIAL
    
    cloud_endpoint: str = ""
    local_endpoint: str = ""
    sync_interval_minutes: int = 15


@dataclass
class AirGappedConfig(DeploymentConfig):
    """Air-gapped configuration."""
    mode = DeploymentMode.AIR_GAPPED
    data_residency = DataResidency.LOCAL
    network_mode = NetworkMode.OFFLINE
    
    enable_manual_update: bool = True
    require_usb_approval: bool = True
    offline_updates_path: str = "/updates"


class DeploymentManager:
    """Manages deployment configurations.
    
    Phase 15.1: Deployment modes
    """
    
    def __init__(self, config: DeploymentConfig | None = None) -> None:
        self._config = config or self._detect_config()
    
    def _detect_config(self) -> DeploymentConfig:
        """Auto-detect deployment configuration."""
        import os
        
        if os.getenv("AI_SUPPORT_AIR_GAPPED"):
            return AirGappedConfig()
        elif os.getenv("AI_SUPPORT_HYBRID"):
            return HybridConfig()
        elif os.getenv("AI_SUPPORT_ON_PREMISE"):
            return OnPremiseConfig()
        else:
            return SaaSConfig()
    
    def get_config(self) -> DeploymentConfig:
        """Get current deployment configuration."""
        return self._config
    
    def set_config(self, config: DeploymentConfig) -> None:
        """Set deployment configuration."""
        self._config = config
        logger.info("Deployment config updated", mode=config.mode.value)
    
    def is_feature_enabled(self, feature: str) -> bool:
        """Check if feature is enabled for this deployment."""
        if self._config.mode == DeploymentMode.AIR_GAPPED:
            # Air-gapped has limited features
            disabled_features = {"cloud_sync", "remote_update", "telemetry"}
            return feature not in disabled_features
        
        if self._config.mode == DeploymentMode.ON_PREMISE:
            # On-prem may have limitations
            if feature in ["cloud_sync", "remote_update"]:
                return self._config.enable_cloud_sync
        
        return True
    
    def get_storage_backend(self) -> dict[str, Any]:
        """Get storage backend configuration."""
        return {
            "backend": self._config.storage_backend,
            "requires_auth": self._config.require_auth,
            "encryption": self._config.require_encryption,
        }
    
    def validate_config(self) -> tuple[bool, list[str]]:
        """Validate deployment configuration."""
        errors = []
        
        if isinstance(self._config, OnPremiseConfig):
            if not self._config.license_key:
                errors.append("License key required for on-premise deployment")
        
        if isinstance(self._config, SaaSConfig):
            if not self._config.api_endpoint:
                errors.append("API endpoint required for SaaS deployment")
        
        return len(errors) == 0, errors


# Global singleton
_manager: DeploymentManager | None = None


def get_deployment_manager() -> DeploymentManager:
    """Get global deployment manager."""
    global _manager
    if _manager is None:
        _manager = DeploymentManager()
    return _manager


# Offline sync manager for air-gapped deployments
class OfflineSyncManager:
    """Manages offline sync for air-gapped deployments.
    
    Phase 15.3a: Offline sync
    """
    
    def __init__(self, sync_path: str = "/sync") -> None:
        self._sync_path = sync_path
        self._pending_sync: list[dict] = []
    
    def prepare_sync_package(self) -> dict[str, Any]:
        """Prepare data for offline sync."""
        return {
            "timestamp": None,
            "data_type": "sync_package",
            "version": "1.0",
        }
    
    def import_sync_package(self, package: dict[str, Any]) -> bool:
        """Import sync package from offline source."""
        # Validate and import
        return True


if __name__ == "__main__":
    # Test deployment modes
    modes = [
        SaaSConfig(api_endpoint="https://api.aisupport.io"),
        OnPremiseConfig(license_key="XXX-YYY-ZZZ"),
        HybridConfig(cloud_endpoint="https://cloud.aisupport.io"),
        AirGappedConfig(),
    ]
    
    for config in modes:
        manager = DeploymentManager(config)
        print(f"\n{config.mode.value.upper()}:")
        print(f"  Data residency: {config.data_residency.value}")
        print(f"  Network: {config.network_mode.value}")
        print(f"  Encryption: {config.require_encryption}")

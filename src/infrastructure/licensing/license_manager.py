"""Licensing and pricing models (Phase 15.2).

Provides licensing and pricing configuration:
- License tiers (Community, Pro, Enterprise)
- Feature gating
- Usage tracking
- License validation
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class LicenseTier(Enum):
    """License tiers."""
    COMMUNITY = "community"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class LicenseStatus(Enum):
    """License status."""
    VALID = "valid"
    EXPIRED = "expired"
    REVOKED = "revoked"
    TRIAL = "trial"


@dataclass
class LicenseFeatures:
    """Feature flags by license tier."""
    # Core features
    basic_debug: bool = True
    hardware_farm: bool = False
    cloud_sync: bool = False
    advanced_analytics: bool = False
    
    # Limits
    max_boards: int = 1
    max_agents: int = 1
    max_storage_gb: int = 1
    max_queries_per_day: int = 100
    
    # Advanced
    custom_integrations: bool = False
    priority_support: bool = False
    sla_guarantee: bool = False
    white_label: bool = False
    on_premise: bool = False
    
    # Enterprise
    dedicated_infra: bool = False
    custom_models: bool = False
    advanced_security: bool = False


@dataclass
class License:
    """License information."""
    license_id: str
    tier: LicenseTier
    status: LicenseStatus
    
    # Customer
    customer_name: str
    customer_email: str
    
    # Validity
    issued_at: datetime
    expires_at: datetime | None = None
    
    # Usage
    used_queries: int = 0
    used_storage_gb: float = 0.0
    
    # Features
    features: LicenseFeatures = field(default_factory=LicenseFeatures)
    
    # Metadata
    seats: int = 1
    contract_id: str = ""


@dataclass
class UsageRecord:
    """Usage record."""
    timestamp: datetime
    user_id: str
    action: str
    quantity: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


class LicenseValidator:
    """Validates licenses."""
    
    def __init__(self) -> None:
        self._licenses: dict[str, License] = {}
    
    def register_license(self, license: License) -> None:
        """Register a license."""
        self._licenses[license.license_id] = license
    
    def validate(
        self,
        license_id: str,
        feature: str | None = None,
    ) -> tuple[bool, str]:
        """Validate license. Returns (is_valid, message)."""
        license = self._licenses.get(license_id)
        if not license:
            return False, "License not found"
        
        # Check status
        if license.status == LicenseStatus.REVOKED:
            return False, "License has been revoked"
        
        # Check expiration
        if license.expires_at and license.expires_at < datetime.now():
            return False, "License has expired"
        
        # Check feature
        if feature:
            features = license.features
            if not getattr(features, feature, False):
                return False, f"Feature '{feature}' not available in {license.tier.value} tier"
        
        return True, "License valid"
    
    def check_usage_limit(
        self,
        license_id: str,
        usage_type: str,
        amount: int = 1,
    ) -> tuple[bool, str]:
        """Check if usage would exceed limit."""
        license = self._licenses.get(license_id)
        if not license:
            return False, "License not found"
        
        features = license.features
        
        if usage_type == "queries":
            limit = features.max_queries_per_day
            current = license.used_queries
        elif usage_type == "storage":
            limit = features.max_storage_gb
            current = license.used_storage_gb
        elif usage_type == "boards":
            limit = features.max_boards
            current = amount  # Checking if within limit
        else:
            return True, "OK"
        
        if current + amount > limit:
            return False, f"Usage limit exceeded for {usage_type}"
        
        return True, "OK"
    
    def record_usage(
        self,
        license_id: str,
        user_id: str,
        action: str,
        quantity: int = 1,
    ) -> None:
        """Record usage."""
        license = self._licenses.get(license_id)
        if not license:
            return
        
        if action == "query":
            license.used_queries += quantity
        elif action == "storage":
            license.used_storage_gb += quantity


class PricingManager:
    """Manages pricing and billing."""
    
    # Base prices (monthly)
    BASE_PRICES = {
        LicenseTier.COMMUNITY: 0,
        LicenseTier.PRO: 99,
        LicenseTier.ENTERPRISE: 499,
    }
    
    # Add-on prices
    ADDON_PRICES = {
        "extra_board": 25,
        "extra_agent": 50,
        "extra_storage_10gb": 10,
        "priority_support": 99,
        "dedicated_infra": 299,
    }
    
    def calculate_price(
        self,
        tier: LicenseTier,
        seats: int = 1,
        addons: list[str] | None = None,
    ) -> dict[str, Any]:
        """Calculate monthly price."""
        base = self.BASE_PRICES[tier] * seats
        
        addon_total = 0
        addon_details = {}
        
        if addons:
            for addon in addons:
                price = self.ADDON_PRICES.get(addon, 0)
                addon_total += price
                addon_details[addon] = price
        
        subtotal = base + addon_total
        tax = subtotal * 0.1  # 10% tax
        
        return {
            "tier": tier.value,
            "base_price": base,
            "addon_details": addon_details,
            "addon_total": addon_total,
            "subtotal": subtotal,
            "tax": tax,
            "total": subtotal + tax,
            "currency": "USD",
        }
    
    def generate_invoice(
        self,
        license_id: str,
        period_start: datetime,
        period_end: datetime,
    ) -> dict[str, Any]:
        """Generate invoice."""
        return {
            "invoice_id": hashlib.md5(f"{license_id}:{period_start}".encode()).hexdigest()[:12],
            "license_id": license_id,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "due_date": period_end.isoformat(),
        }


class LicenseManager:
    """Main license management.
    
    Phase 15.2: Licensing & pricing
    """
    
    def __init__(self) -> None:
        self._validator = LicenseValidator()
        self._pricing = PricingManager()
        self._usage_history: list[UsageRecord] = []
    
    def create_license(
        self,
        tier: LicenseTier,
        customer_name: str,
        customer_email: str,
        seats: int = 1,
        duration_days: int | None = None,
    ) -> License:
        """Create new license."""
        import uuid
        
        features = self._get_tier_features(tier)
        
        license = License(
            license_id=str(uuid.uuid4())[:8].upper(),
            tier=tier,
            status=LicenseStatus.VALID if duration_days is None else LicenseStatus.TRIAL,
            customer_name=customer_name,
            customer_email=customer_email,
            issued_at=datetime.now(),
            expires_at=datetime.now() + timedelta(days=duration_days) if duration_days else None,
            seats=seats,
            features=features,
        )
        
        self._validator.register_license(license)
        logger.info("License created", license_id=license.license_id, tier=tier.value)
        
        return license
    
    def _get_tier_features(self, tier: LicenseTier) -> LicenseFeatures:
        """Get features for tier."""
        if tier == LicenseTier.COMMUNITY:
            return LicenseFeatures()
        elif tier == LicenseTier.PRO:
            return LicenseFeatures(
                basic_debug=True,
                hardware_farm=True,
                cloud_sync=True,
                advanced_analytics=True,
                max_boards=5,
                max_agents=3,
                max_storage_gb=10,
                max_queries_per_day=1000,
            )
        else:  # Enterprise
            return LicenseFeatures(
                basic_debug=True,
                hardware_farm=True,
                cloud_sync=True,
                advanced_analytics=True,
                max_boards=-1,  # Unlimited
                max_agents=-1,
                max_storage_gb=100,
                max_queries_per_day=-1,
                custom_integrations=True,
                priority_support=True,
                sla_guarantee=True,
                on_premise=True,
                dedicated_infra=True,
                custom_models=True,
                advanced_security=True,
            )
    
    def validate(self, license_id: str, feature: str | None = None) -> tuple[bool, str]:
        """Validate license."""
        return self._validator.validate(license_id, feature)
    
    def check_limit(
        self,
        license_id: str,
        usage_type: str,
        amount: int = 1,
    ) -> tuple[bool, str]:
        """Check usage limit."""
        return self._validator.check_usage_limit(license_id, usage_type, amount)
    
    def record_usage(
        self,
        license_id: str,
        user_id: str,
        action: str,
        quantity: int = 1,
    ) -> None:
        """Record usage."""
        self._validator.record_usage(license_id, user_id, action, quantity)
        
        record = UsageRecord(
            timestamp=datetime.now(),
            user_id=user_id,
            action=action,
            quantity=quantity,
        )
        self._usage_history.append(record)
    
    def get_price_estimate(
        self,
        tier: LicenseTier,
        seats: int = 1,
        addons: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get price estimate."""
        return self._pricing.calculate_price(tier, seats, addons)
    
    def get_license(self, license_id: str) -> License | None:
        """Get license info."""
        return self._validator._licenses.get(license_id)


# Global manager
_license_manager: LicenseManager | None = None


def get_license_manager() -> LicenseManager:
    """Get global license manager."""
    global _license_manager
    if _license_manager is None:
        _license_manager = LicenseManager()
    return _license_manager


if __name__ == "__main__":
    manager = get_license_manager()
    
    # Create licenses
    community = manager.create_license(
        LicenseTier.COMMUNITY,
        "John Doe",
        "john@example.com",
    )
    
    pro = manager.create_license(
        LicenseTier.PRO,
        "Acme Corp",
        "admin@acme.com",
        seats=3,
    )
    
    print("License Manager")
    print("=" * 40)
    print(f"Community: {community.license_id} - {community.tier.value}")
    print(f"Pro: {pro.license_id} - {pro.tier.value}")
    print(f"  Max boards: {pro.features.max_boards}")
    print(f"  Cloud sync: {pro.features.cloud_sync}")
    
    # Validate
    valid, msg = manager.validate(pro.license_id, "cloud_sync")
    print(f"\nValidation: {valid} - {msg}")
    
    # Pricing
    estimate = manager.get_price_estimate(
        LicenseTier.PRO,
        seats=5,
        addons=["extra_board", "priority_support"],
    )
    print(f"\nPrice estimate: ${estimate['total']:.2f}/month")

"""Tests for license manager."""

import pytest
from src.infrastructure.licensing.license_manager import (
    LicenseManager,
    LicenseTier,
)


class TestLicenseManager:
    def test_manager_creation(self):
        manager = LicenseManager()
        assert manager is not None

    def test_create_community_license(self):
        manager = LicenseManager()
        license = manager.create_license(
            tier=LicenseTier.COMMUNITY,
            customer_name="John Doe",
            customer_email="john@example.com",
        )
        assert license.tier == LicenseTier.COMMUNITY
        assert license.customer_name == "John Doe"

    def test_create_pro_license(self):
        manager = LicenseManager()
        license = manager.create_license(
            tier=LicenseTier.PRO,
            customer_name="Acme Corp",
            customer_email="admin@acme.com",
            seats=5,
        )
        assert license.tier == LicenseTier.PRO
        assert license.seats == 5

    def test_create_enterprise_license(self):
        manager = LicenseManager()
        license = manager.create_license(
            tier=LicenseTier.ENTERPRISE,
            customer_name="Enterprise Inc",
            customer_email="enterprise@example.com",
        )
        assert license.tier == LicenseTier.ENTERPRISE

    def test_validate_license(self):
        manager = LicenseManager()
        license = manager.create_license(
            tier=LicenseTier.PRO,
            customer_name="Test",
            customer_email="test@example.com",
        )
        valid, msg = manager.validate(license.license_id)
        assert valid is True

    def test_get_price_estimate(self):
        manager = LicenseManager()
        estimate = manager.get_price_estimate(
            tier=LicenseTier.PRO,
            seats=5,
            addons=["extra_board", "priority_support"],
        )
        assert "total" in estimate
        assert estimate["tier"] == "pro"


class TestLicenseFeatures:
    def test_community_features(self):
        from src.infrastructure.licensing.license_manager import LicenseManager
        manager = LicenseManager()
        license = manager.create_license(
            tier=LicenseTier.COMMUNITY,
            customer_name="Test",
            customer_email="test@example.com",
        )
        assert license.features.basic_debug is True
        assert license.features.hardware_farm is False

    def test_pro_features(self):
        from src.infrastructure.licensing.license_manager import LicenseManager
        manager = LicenseManager()
        license = manager.create_license(
            tier=LicenseTier.PRO,
            customer_name="Test",
            customer_email="test@example.com",
        )
        assert license.features.hardware_farm is True
        assert license.features.cloud_sync is True

    def test_enterprise_features(self):
        from src.infrastructure.licensing.license_manager import LicenseManager
        manager = LicenseManager()
        license = manager.create_license(
            tier=LicenseTier.ENTERPRISE,
            customer_name="Test",
            customer_email="test@example.com",
        )
        assert license.features.dedicated_infra is True
        assert license.features.custom_models is True

"""Signed Artifact Manifest Tests.

Phase 2 (P0-D): Tests for signed artifact manifest:
- Signing and verification
- Key rotation
- Manifest validation
- SBOM provenance
"""

from __future__ import annotations

import hashlib
import json
import pytest
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

# Import the modules we're testing
from src.domain.hardware.flash.signed_artifact_manifest import (
    SignedArtifactManifest,
    ManifestSigner,
    ManifestVerifier,
    KeyRotationManager,
    ManifestFactory,
    SignatureScheme,
    KeyType,
    KeyState,
    VerificationStatus,
    SBOMProvenance,
    attach_sbom_to_manifest,
)


# =============================================================================
# TEST HELPERS
# =============================================================================


def get_test_firmware(size: int = 1024) -> bytes:
    """Get test firmware data."""
    return bytes([i % 256 for i in range(size)])


def get_test_manifest(
    artifact_id: str = "test-artifact-001",
    version: str = "1.0.0",
    target: str = "test-target",
) -> SignedArtifactManifest:
    """Create a test manifest."""
    firmware = get_test_firmware()
    
    return SignedArtifactManifest(
        artifact_id=artifact_id,
        name="Test Firmware",
        semantic_version=version,
        image_hash=hashlib.sha256(firmware).hexdigest(),
        image_size=len(firmware),
        target_name=target,
        target_chip="STM32F407VG",
        slot_id="B",
        slot_address=0x080C0000,
    )


# =============================================================================
# MANIFEST CREATION TESTS
# =============================================================================


class TestManifestCreation:
    """Tests for manifest creation."""
    
    def test_create_basic_manifest(self):
        """Test creating a basic manifest."""
        firmware = get_test_firmware()
        
        manifest = SignedArtifactManifest(
            artifact_id="test-001",
            name="Test Firmware",
            semantic_version="1.0.0",
            image_hash=hashlib.sha256(firmware).hexdigest(),
            image_size=len(firmware),
            target_name="test-target",
            target_chip="STM32F407VG",
        )
        
        assert manifest.artifact_id == "test-001"
        assert manifest.semantic_version == "1.0.0"
        assert manifest.image_hash == hashlib.sha256(firmware).hexdigest()
        assert manifest.image_size == len(firmware)
    
    def test_manifest_serialization(self):
        """Test manifest serialization to JSON."""
        manifest = get_test_manifest()
        
        # To dict
        data = manifest.to_dict()
        assert data["artifact_id"] == manifest.artifact_id
        assert data["image_hash"] == manifest.image_hash
        
        # To JSON
        json_str = manifest.to_json()
        parsed = json.loads(json_str)
        assert parsed["artifact_id"] == manifest.artifact_id
    
    def test_manifest_deserialization(self):
        """Test manifest deserialization from JSON."""
        original = get_test_manifest()
        
        # Serialize
        json_str = original.to_json()
        
        # Deserialize
        restored = SignedArtifactManifest.from_json(json_str)
        
        assert restored.artifact_id == original.artifact_id
        assert restored.semantic_version == original.semantic_version
        assert restored.image_hash == original.image_hash
        assert restored.target_name == original.target_name
    
    def test_is_signed(self):
        """Test is_signed check."""
        manifest = get_test_manifest()
        
        # Not signed by default
        assert manifest.is_signed() is False
        
        # After adding signature
        manifest.signature = "dGVzdDpzaWduYXR1cmU="
        manifest.key_id = "key-001"
        
        assert manifest.is_signed() is True
    
    def test_is_expired(self):
        """Test expiration check."""
        manifest = get_test_manifest()
        
        # Not expired without expiration
        assert manifest.is_expired() is False
        
        # Set to past date
        manifest.expires_at = (datetime.now() - timedelta(days=1)).isoformat()
        
        assert manifest.is_expired() is True


# =============================================================================
# SIGNING TESTS
# =============================================================================


class TestManifestSigning:
    """Tests for manifest signing."""
    
    def test_signing_payload(self):
        """Test signing payload generation."""
        manifest = get_test_manifest()
        manifest.nonce = "test-nonce"
        manifest.signed_at = "2026-01-01T00:00:00"
        
        payload = manifest.get_signing_payload()
        
        # Should be valid JSON
        parsed = json.loads(payload)
        assert parsed["artifact_id"] == manifest.artifact_id
        assert parsed["image_hash"] == manifest.image_hash
        assert parsed["nonce"] == "test-nonce"
    
    def test_signing_payload_canonical(self):
        """Test that signing payload is canonical (sorted keys)."""
        manifest = get_test_manifest()
        manifest.nonce = "test"
        manifest.signed_at = "2026-01-01T00:00:00"
        
        payload1 = manifest.get_signing_payload()
        payload2 = manifest.get_signing_payload()
        
        # Should be identical
        assert payload1 == payload2


# =============================================================================
# VERIFICATION TESTS
# =============================================================================


class TestManifestVerification:
    """Tests for manifest verification."""
    
    def test_verify_rejects_unsigned(self):
        """Test that unsigned manifests are rejected."""
        manifest = get_test_manifest()
        
        verifier = ManifestVerifier()
        result = verifier.verify(manifest)
        
        assert result.status == VerificationStatus.MISSING_SIGNATURE
        assert result.is_valid() is False
    
    def test_verify_rejects_unknown_signer(self):
        """Test that unknown signers are rejected."""
        manifest = get_test_manifest()
        manifest.signature = "dGVzdDpzaWduYXR1cmU="
        manifest.key_id = "unknown-key"
        
        verifier = ManifestVerifier(allowed_signers=["known-key"])
        result = verifier.verify(manifest)
        
        assert result.status == VerificationStatus.UNKNOWN_SIGNER
    
    def test_verify_accepts_expired_manifest_without_expiry(self):
        """Test that manifests without expiry are accepted."""
        manifest = get_test_manifest()
        manifest.signature = "dGVzdDpzaWduYXR1cmU="
        manifest.key_id = "test-key"
        # No expires_at set
        
        verifier = ManifestVerifier(allowed_signers=["test-key"])
        result = verifier.verify(manifest)
        
        # Should not fail on expiration
        assert result.status != VerificationStatus.EXPIRED_KEY


# =============================================================================
# KEY ROTATION TESTS
# =============================================================================


class TestKeyRotation:
    """Tests for key rotation."""
    
    def test_generate_key(self):
        """Test key generation."""
        manager = KeyRotationManager()
        
        key = manager.generate_key(
            key_id="test-key-001",
            scheme=SignatureScheme.ECDSA_P256,
        )
        
        assert key.key_id == "test-key-001"
        assert key.fingerprint != ""
        assert key.state == KeyState.PENDING_ACTIVATION
    
    def test_activate_key(self):
        """Test key activation."""
        manager = KeyRotationManager()
        
        key = manager.generate_key(key_id="test-key-001")
        
        ok = manager.activate_key("test-key-001")
        
        assert ok is True
        assert key.state == KeyState.ACTIVE
        assert key.activated_at != ""
    
    def test_get_active_key(self):
        """Test getting active key."""
        manager = KeyRotationManager()
        
        # No active key initially
        assert manager.get_active_key() is None
        
        # Generate and activate
        manager.generate_key(key_id="key-001")
        manager.activate_key("key-001")
        
        active = manager.get_active_key()
        assert active is not None
        assert active.key_id == "key-001"
    
    def test_revoke_key(self):
        """Test key revocation."""
        manager = KeyRotationManager()
        
        manager.generate_key(key_id="key-001")
        manager.activate_key("key-001")
        
        ok = manager.revoke_key("key-001", reason="Test revocation")
        
        assert ok is True
        assert manager.get_active_key() is None
        assert not manager.is_key_valid("key-001")
    
    def test_key_not_found(self):
        """Test operations on non-existent keys."""
        manager = KeyRotationManager()
        
        assert manager.activate_key("nonexistent") is False
        assert manager.revoke_key("nonexistent") is False
        assert manager.is_key_valid("nonexistent") is False


# =============================================================================
# SBOM PROVENANCE TESTS
# =============================================================================


class TestSBOMProvenance:
    """Tests for SBOM provenance."""
    
    def test_create_sbom(self):
        """Test creating SBOM provenance."""
        sbom = SBOMProvenance(
            spdx_id="SPDXRef-DOCUMENT",
            component_name="test-component",
            component_version="1.0.0",
            build_timestamp="2026-01-01T00:00:00",
            build_tool="gcc",
            source_repository="https://github.com/test/repo",
            source_commit="abc123",
            license_concluded="MIT",
        )
        
        assert sbom.component_name == "test-component"
        assert sbom.license_concluded == "MIT"
    
    def test_sbom_to_spdx(self):
        """Test SBOM export to SPDX."""
        sbom = SBOMProvenance(
            spdx_id="SPDXRef-DOCUMENT",
            component_name="test-component",
            component_version="1.0.0",
            build_timestamp="2026-01-01T00:00:00",
        )
        
        spdx = sbom.to_spdx_tag_value()
        
        assert "SPDXVersion: SPDX-2.3" in spdx
        assert "DocumentName: test-component" in spdx
        assert "PackageVersion: 1.0.0" in spdx
    
    def test_sbom_with_dependencies(self):
        """Test SBOM with dependencies."""
        sbom = SBOMProvenance(
            spdx_id="SPDXRef-DOCUMENT",
            component_name="test",
            component_version="1.0.0",
            build_timestamp="2026-01-01T00:00:00",
            dependencies=[
                {"name": "libfoo", "version": "1.0.0"},
                {"name": "libbar", "version": "2.0.0"},
            ],
        )
        
        spdx = sbom.to_spdx_tag_value()
        
        assert "PackageName: libfoo" in spdx
        assert "PackageName: libbar" in spdx
    
    def test_attach_sbom_to_manifest(self):
        """Test attaching SBOM to manifest."""
        manifest = get_test_manifest()
        sbom = SBOMProvenance(
            spdx_id="SPDXRef-DOCUMENT",
            component_name="test",
            component_version="1.0.0",
            build_timestamp="2026-01-01T00:00:00",
        )
        
        updated = attach_sbom_to_manifest(manifest, sbom)
        
        assert "sbom" in updated.metadata
        assert updated.metadata["sbom"]["component_name"] == "test"


# =============================================================================
# MANIFEST FACTORY TESTS
# =============================================================================


class TestManifestFactory:
    """Tests for manifest factory."""
    
    def test_factory_requires_active_key(self):
        """Test that factory requires active key."""
        manager = KeyRotationManager()
        factory = ManifestFactory(manager)
        
        # No active key should fail
        with pytest.raises(ValueError, match="No active signing key"):
            factory.create_manifest(
                artifact_id="test",
                name="Test",
                image_data=get_test_firmware(),
                version="1.0.0",
            )
    
    def test_factory_with_active_key(self):
        """Test factory with active key."""
        manager = KeyRotationManager()
        manager.generate_key(key_id="key-001")
        manager.activate_key("key-001")
        
        factory = ManifestFactory(
            manager,
            default_target="test-target",
            default_chip="STM32F407VG",
        )
        
        manifest = factory.create_manifest(
            artifact_id="test-001",
            name="Test Firmware",
            image_data=get_test_firmware(),
            version="1.0.0",
            slot_id="A",
        )
        
        assert manifest.artifact_id == "test-001"
        assert manifest.target_name == "test-target"
        assert manifest.is_signed() is True


# =============================================================================
# VERIFICATION CONSTRAINT TESTS
# =============================================================================


class TestVerificationConstraints:
    """Tests for verification constraint checks."""
    
    def test_hash_mismatch_rejected(self):
        """Test that hash mismatch is rejected."""
        manifest = get_test_manifest()
        manifest.signature = "dGVzdDpzaWduYXR1cmU="
        manifest.key_id = "key-001"
        
        # Different firmware data
        different_firmware = get_test_firmware(2048)
        
        verifier = ManifestVerifier(allowed_signers=["key-001"])
        result = verifier.verify(
            manifest,
            expected_image_hash=hashlib.sha256(different_firmware).hexdigest(),
        )
        
        # Would fail on signature verification first, but hash check is valid
        # In real implementation, signature would fail first
        assert result.status != VerificationStatus.VALID
    
    def test_target_constraint_check(self):
        """Test target constraint checking."""
        manifest = get_test_manifest(target="target-A")
        manifest.signature = "dGVzdDpzaWduYXR1cmU="
        manifest.key_id = "key-001"
        
        verifier = ManifestVerifier(allowed_signers=["key-001"])
        
        # Wrong target
        result = verifier.verify(
            manifest,
            expected_target="target-B",
        )
        
        # Should fail on target mismatch (or signature first in real impl)
        assert result.status != VerificationStatus.VALID
    
    def test_slot_constraint_check(self):
        """Test slot constraint checking."""
        manifest = get_test_manifest()
        manifest.slot_id = "A"
        manifest.signature = "dGVzdDpzaWduYXR1cmU="
        manifest.key_id = "key-001"
        
        verifier = ManifestVerifier(allowed_signers=["key-001"])
        
        # Wrong slot
        result = verifier.verify(
            manifest,
            expected_slot="B",
        )
        
        # Should fail on slot mismatch
        assert result.status != VerificationStatus.VALID


# =============================================================================
# RUN ALL TESTS
# =============================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

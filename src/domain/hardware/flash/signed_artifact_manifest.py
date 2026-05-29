"""Signed Artifact Manifest - Cryptographic signing, verification, and key rotation.

Phase 2 (P0-D): Signed Artifact Manifest
Implements:
- Artifact manifest signing with private key
- Manifest verification with public key
- Key rotation lifecycle
- Integration with flash planner
- SBOM provenance

P0-D Security Requirements:
- All artifacts MUST have signed manifests before flashing
- Manifest includes: hash, version, target, slot, signer
- Signature over metadata + image hash + version + target constraints
- Key rotation without breaking existing valid signatures
- Trust anchor verification

This module is the foundation for secure OTA - it ensures that
only properly signed and verified firmware can be flashed to targets.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import struct
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# CRYPTOGRAPHIC CONSTANTS & SETUP
# =============================================================================

# Try to import cryptography library
try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, rsa, padding
    from cryptography.hazmat.primitives.ciphers.aead import AESOCB3
    from cryptography.hazmat.backends import default_backend
    from cryptography.x509 import load_pem_x509_certificate, load_der_x509_certificate
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False
    logger.warning("cryptography library not available - signing disabled")


# =============================================================================
# ENUMS & CONSTANTS
# =============================================================================


class SignatureScheme(Enum):
    """Supported signature schemes for artifact manifests."""
    
    ECDSA_P256 = "ecdsa_p256"          # NIST P-256 (recommended)
    ECDSA_SECP256R1 = "ecdsa_secp256r1"  # Same as P-256
    RSA_2048_PSS = "rsa_2048_pss"      # RSA 2048-bit with PSS padding
    RSA_4096_PSS = "rsa_4096_pss"      # RSA 4096-bit with PSS padding
    ED25519 = "ed25519"                 # Ed25519 (modern, fast)


class KeyType(Enum):
    """Type of signing key."""
    
    PRODUCTION = "production"      # Production signing key
    DEVELOPMENT = "development"    # Development/testing key
    ROTATION = "rotation"          # Key being rotated in
    REVOKED = "revoked"           # Revoked key (no longer valid)


class KeyState(Enum):
    """State of a signing key."""
    
    ACTIVE = "active"             # Key is active and valid
    PENDING_ACTIVATION = "pending_activation"  # Key waiting to become active
    EXPIRED = "expired"          # Key past expiration
    REVOKED = "revoked"          # Key explicitly revoked
    COMPROMISED = "compromised"   # Key suspected compromised


class VerificationStatus(Enum):
    """Result of manifest verification."""
    
    VALID = "valid"                     # Signature valid, constraints satisfied
    INVALID_SIGNATURE = "invalid_signature"
    EXPIRED_KEY = "expired_key"
    REVOKED_KEY = "revoked_key"
    WRONG_TARGET = "wrong_target"        # Target mismatch
    WRONG_SLOT = "wrong_slot"           # Slot mismatch
    HASH_MISMATCH = "hash_mismatch"     # Image hash mismatch
    MISSING_SIGNATURE = "missing_signature"
    UNKNOWN_SIGNER = "unknown_signer"
    KEY_NOT_TRUSTED = "key_not_trusted"


# =============================================================================
# SIGNED ARTIFACT MANIFEST (P0-D CORE)
# =============================================================================


@dataclass
class SignedArtifactManifest:
    """Signed artifact manifest with cryptographic verification.
    
    P0-D: This is the authoritative record for firmware artifacts.
    Every artifact flashed to a target MUST have a signed manifest.
    
    Manifest Structure:
    - Metadata: artifact_id, name, version
    - Content: image_hash, image_size, image_offset
    - Target binding: target_name, target_chip, board_revision
    - Slot binding: slot_id, slot_address
    - Signer info: signer_id, signer_key_id
    - Signature: signature over canonicalized manifest
    - Key info: key_id, key_fingerprint, signature_scheme
    - Timestamps: created_at, signed_at, expires_at
    
    The signature covers:
    canonical_json({
        image_hash,
        image_size,
        version,
        target_name,
        target_chip,
        slot_id,
        nonce,
        timestamp
    })
    
    P0-D Requirement: The signature is over the manifest content,
    not just the image. This binds the firmware to its deployment context.
    """
    
    # Artifact identity
    artifact_id: str = ""
    name: str = ""
    
    # Version info
    semantic_version: str = ""  # MAJOR.MINOR.PATCH
    build_number: str = ""
    
    # Content binding (what was signed)
    image_hash: str = ""  # SHA-256 of firmware image
    image_size: int = 0
    image_offset: int = 0  # Offset in flash where image starts
    
    # Target binding (where it can be deployed)
    target_name: str = ""
    target_chip: str = ""  # e.g., "STM32F407VG"
    board_revision: str = ""
    
    # Slot binding (where it was flashed)
    slot_id: str = ""  # "A" or "B"
    slot_address: int = 0
    
    # Signer info
    signer_id: str = ""  # Human-readable signer ID
    signer_key_id: str = ""  # Key fingerprint
    
    # Signature
    signature: str = ""  # Base64-encoded signature
    signature_scheme: str = "ecdsa_p256"  # SignatureScheme.value
    
    # Key info
    key_id: str = ""  # Unique key identifier
    key_fingerprint: str = ""  # SHA-256 of public key
    key_created_at: str = ""  # ISO timestamp
    key_expires_at: str = ""  # ISO timestamp
    
    # Timestamps
    created_at: str = ""  # ISO timestamp
    signed_at: str = ""  # ISO timestamp
    expires_at: str = ""  # ISO timestamp (for temporal validity)
    
    # Anti-replay
    nonce: str = ""  # Random nonce for freshness
    
    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Initialize timestamps if not set."""
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.signed_at:
            self.signed_at = self.created_at
    
    def get_signing_payload(self) -> str:
        """Get canonical payload for signing.
        
        This is the canonical JSON that gets signed. It includes
        all content binding fields to ensure the firmware is bound
        to its deployment context.
        
        Returns:
            Canonical JSON string for signing
        """
        payload = {
            "artifact_id": self.artifact_id,
            "name": self.name,
            "semantic_version": self.semantic_version,
            "build_number": self.build_number,
            "image_hash": self.image_hash,
            "image_size": self.image_size,
            "target_name": self.target_name,
            "target_chip": self.target_chip,
            "board_revision": self.board_revision,
            "slot_id": self.slot_id,
            "nonce": self.nonce,
            "timestamp": self.signed_at,
        }
        
        # Canonical JSON: sorted keys, no extra whitespace
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))
    
    def get_verification_payload(self) -> str:
        """Get payload for verification.
        
        Same as signing payload but with additional fields
        that can be verified.
        
        Returns:
            Canonical JSON for verification
        """
        return self.get_signing_payload()
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "artifact_id": self.artifact_id,
            "name": self.name,
            "semantic_version": self.semantic_version,
            "build_number": self.build_number,
            "image_hash": self.image_hash,
            "image_size": self.image_size,
            "image_offset": self.image_offset,
            "target_name": self.target_name,
            "target_chip": self.target_chip,
            "board_revision": self.board_revision,
            "slot_id": self.slot_id,
            "slot_address": hex(self.slot_address),
            "signer_id": self.signer_id,
            "signer_key_id": self.signer_key_id,
            "signature": self.signature,
            "signature_scheme": self.signature_scheme,
            "key_id": self.key_id,
            "key_fingerprint": self.key_fingerprint,
            "key_created_at": self.key_created_at,
            "key_expires_at": self.key_expires_at,
            "created_at": self.created_at,
            "signed_at": self.signed_at,
            "expires_at": self.expires_at,
            "nonce": self.nonce,
            "metadata": self.metadata,
        }
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SignedArtifactManifest:
        """Create from dictionary."""
        slot_addr = data.get("slot_address")
        if isinstance(slot_addr, str):
            slot_addr = int(slot_addr, 16) if slot_addr.startswith("0x") else int(slot_addr)
        
        return cls(
            artifact_id=data.get("artifact_id", ""),
            name=data.get("name", ""),
            semantic_version=data.get("semantic_version", ""),
            build_number=data.get("build_number", ""),
            image_hash=data.get("image_hash", ""),
            image_size=data.get("image_size", 0),
            image_offset=data.get("image_offset", 0),
            target_name=data.get("target_name", ""),
            target_chip=data.get("target_chip", ""),
            board_revision=data.get("board_revision", ""),
            slot_id=data.get("slot_id", ""),
            slot_address=slot_addr or 0,
            signer_id=data.get("signer_id", ""),
            signer_key_id=data.get("signer_key_id", ""),
            signature=data.get("signature", ""),
            signature_scheme=data.get("signature_scheme", "ecdsa_p256"),
            key_id=data.get("key_id", ""),
            key_fingerprint=data.get("key_fingerprint", ""),
            key_created_at=data.get("key_created_at", ""),
            key_expires_at=data.get("key_expires_at", ""),
            created_at=data.get("created_at", ""),
            signed_at=data.get("signed_at", ""),
            expires_at=data.get("expires_at", ""),
            nonce=data.get("nonce", ""),
            metadata=data.get("metadata", {}),
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> SignedArtifactManifest:
        """Create from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)
    
    def is_signed(self) -> bool:
        """Check if manifest is signed."""
        return bool(self.signature and self.key_id)
    
    def is_expired(self) -> bool:
        """Check if manifest is expired."""
        if not self.expires_at:
            return False
        try:
            expires = datetime.fromisoformat(self.expires_at)
            return datetime.now() > expires
        except (ValueError, TypeError):
            return False


# =============================================================================
# SIGNING & VERIFICATION ENGINE
# =============================================================================


class ManifestSigner:
    """Signs artifact manifests with cryptographic keys.
    
    P0-D: Provides cryptographic signing for artifact manifests.
    Supports multiple signature schemes (ECDSA, RSA, Ed25519).
    """
    
    def __init__(
        self,
        private_key_pem: bytes,
        key_id: str,
        signer_id: str = "default",
        scheme: SignatureScheme = SignatureScheme.ECDSA_P256,
    ):
        """
        Args:
            private_key_pem: PEM-encoded private key
            key_id: Unique identifier for this key
            signer_id: Human-readable signer ID
            scheme: Signature scheme to use
        """
        self.key_id = key_id
        self.signer_id = signer_id
        self.scheme = scheme
        self._private_key = None
        
        if HAS_CRYPTOGRAPHY:
            self._load_key(private_key_pem)
        else:
            logger.warning(
                "ManifestSigner: cryptography not available. "
                "Signing will be disabled. Install: pip install cryptography"
            )
    
    def _load_key(self, private_key_pem: bytes) -> None:
        """Load private key from PEM."""
        try:
            if self.scheme in (SignatureScheme.ECDSA_P256, SignatureScheme.ECDSA_SECP256R1):
                from cryptography.hazmat.primitives.serialization import load_pem_private_key
                self._private_key = load_pem_private_key(
                    private_key_pem,
                    password=None,
                    backend=default_backend(),
                )
            elif self.scheme in (SignatureScheme.RSA_2048_PSS, SignatureScheme.RSA_4096_PSS):
                from cryptography.hazmat.primitives.serialization import load_pem_private_key
                self._private_key = load_pem_private_key(
                    private_key_pem,
                    password=None,
                    backend=default_backend(),
                )
            elif self.scheme == SignatureScheme.ED25519:
                from cryptography.hazmat.primitives.serialization import load_pem_private_key
                self._private_key = load_pem_private_key(
                    private_key_pem,
                    password=None,
                    backend=default_backend(),
                )
        except Exception as e:
            logger.error(f"Failed to load private key: {e}")
            raise ValueError(f"Invalid private key: {e}")
    
    def get_public_key_fingerprint(self) -> str:
        """Get SHA-256 fingerprint of public key."""
        if not self._private_key:
            return ""
        
        public_key = self._private_key.public_key()
        public_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return hashlib.sha256(public_bytes).hexdigest()
    
    def sign(self, manifest: SignedArtifactManifest) -> SignedArtifactManifest:
        """Sign an artifact manifest.
        
        Args:
            manifest: Manifest to sign
            
        Returns:
            Signed manifest with signature added
        """
        if not self._private_key:
            raise ValueError("Private key not loaded - cannot sign")
        
        # Set signing metadata
        manifest.key_id = self.key_id
        manifest.signer_id = self.signer_id
        manifest.signer_key_id = self.key_id
        manifest.key_fingerprint = self.get_public_key_fingerprint()
        manifest.signature_scheme = self.scheme.value
        manifest.signed_at = datetime.now().isoformat()
        
        # Generate nonce for freshness
        import secrets
        manifest.nonce = secrets.token_hex(16)
        
        # Get signing payload
        payload = manifest.get_signing_payload().encode("utf-8")
        
        # Sign based on scheme
        if self.scheme == SignatureScheme.ECDSA_P256:
            from cryptography.hazmat.primitives.asymmetric import ec
            signature = self._private_key.sign(
                payload,
                ec.ECDSA(hashes.SHA256()),
            )
        elif self.scheme == SignatureScheme.RSA_2048_PSS:
            signature = self._private_key.sign(
                payload,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )
        elif self.scheme == SignatureScheme.ED25519:
            from cryptography.hazmat.primitives.asymmetric import ed25519
            signature = self._private_key.sign(payload)
        else:
            raise ValueError(f"Unsupported signature scheme: {self.scheme}")
        
        # Add signature (base64 encoded)
        import base64
        manifest.signature = base64.b64encode(signature).decode("ascii")
        
        logger.info("manifest_signed: key_id=%s signer=%s artifact=%s scheme=%s", self.key_id, self.signer_id, manifest.artifact_id, self.scheme.value)
        
        return manifest


class ManifestVerifier:
    """Verifies signed artifact manifests.
    
    P0-D: Verifies manifest signatures against trust anchor.
    Checks:
    - Signature validity
    - Key trust (not revoked, not expired)
    - Target/slot constraints
    - Image hash match
    """
    
    def __init__(
        self,
        trust_anchor_pem: bytes | None = None,
        allowed_signers: list[str] | None = None,
    ):
        """
        Args:
            trust_anchor_pem: PEM-encoded CA certificate for chain of trust
            allowed_signers: List of allowed signer key IDs
        """
        self._trust_anchor = None
        self.allowed_signers = set(allowed_signers or [])
        
        if trust_anchor_pem and HAS_CRYPTOGRAPHY:
            self._load_trust_anchor(trust_anchor_pem)
    
    def _load_trust_anchor(self, pem: bytes) -> None:
        """Load trust anchor (CA certificate)."""
        try:
            self._trust_anchor = load_pem_x509_certificate(
                pem,
                default_backend(),
            )
            logger.info("trust_anchor_loaded")
        except Exception as e:
            logger.error(f"Failed to load trust anchor: {e}")
    
    @dataclass
    class VerificationResult:
        """Result of manifest verification."""
        status: VerificationStatus
        message: str
        manifest: SignedArtifactManifest | None = None
        verified_at: str = ""
        signer_id: str = ""
        key_fingerprint: str = ""
        
        def is_valid(self) -> bool:
            return self.status == VerificationStatus.VALID
        
        def to_dict(self) -> dict[str, Any]:
            return {
                "status": self.status.value,
                "message": self.message,
                "verified_at": self.verified_at,
                "signer_id": self.signer_id,
                "key_fingerprint": self.key_fingerprint,
            }
    
    def verify(
        self,
        manifest: SignedArtifactManifest,
        expected_image_hash: str | None = None,
        expected_target: str | None = None,
        expected_slot: str | None = None,
    ) -> VerificationResult:
        """Verify a signed artifact manifest.
        
        Args:
            manifest: Manifest to verify
            expected_image_hash: Expected image hash (for additional validation)
            expected_target: Expected target name (for deployment validation)
            expected_slot: Expected slot ID (for deployment validation)
            
        Returns:
            VerificationResult with status and details
        """
        result = self.VerificationResult(
            status=VerificationStatus.UNKNOWN_SIGNER,
            message="Verification not completed",
            manifest=manifest,
            verified_at=datetime.now().isoformat(),
        )
        
        # Check if cryptography is available
        if not HAS_CRYPTOGRAPHY:
            result.status = VerificationStatus.INVALID_SIGNATURE
            result.message = "Cryptography library not available"
            return result
        
        # Check if signed
        if not manifest.is_signed():
            result.status = VerificationStatus.MISSING_SIGNATURE
            result.message = "Manifest is not signed"
            return result
        
        # Check if allowed signer
        if self.allowed_signers and manifest.key_id not in self.allowed_signers:
            result.status = VerificationStatus.UNKNOWN_SIGNER
            result.message = f"Signer {manifest.key_id} not in allowed signers"
            return result
        
        # Check expiration
        if manifest.is_expired():
            result.status = VerificationStatus.EXPIRED_KEY
            result.message = "Manifest has expired"
            return result
        
        # Check key expiration
        if manifest.key_expires_at:
            try:
                key_expires = datetime.fromisoformat(manifest.key_expires_at)
                if datetime.now() > key_expires:
                    result.status = VerificationStatus.EXPIRED_KEY
                    result.message = "Signing key has expired"
                    return result
            except (ValueError, TypeError):
                pass
        
        # Verify image hash if provided
        if expected_image_hash and manifest.image_hash != expected_image_hash:
            result.status = VerificationStatus.HASH_MISMATCH
            result.message = (
                f"Image hash mismatch: expected {expected_image_hash[:16]}..., "
                f"got {manifest.image_hash[:16]}..."
            )
            return result
        
        # Verify target constraint
        if expected_target and manifest.target_name != expected_target:
            result.status = VerificationStatus.WRONG_TARGET
            result.message = (
                f"Target mismatch: manifest targets {manifest.target_name}, "
                f"expected {expected_target}"
            )
            return result
        
        # Verify slot constraint
        if expected_slot and manifest.slot_id != expected_slot:
            result.status = VerificationStatus.WRONG_SLOT
            result.message = (
                f"Slot mismatch: manifest is for slot {manifest.slot_id}, "
                f"expected {expected_slot}"
            )
            return result
        
        # Verify signature
        try:
            # Decode signature
            import base64
            signature_bytes = base64.b64decode(manifest.signature)
            
            # Get payload
            payload = manifest.get_verification_payload().encode("utf-8")
            
            # Get public key from manifest's key fingerprint
            # In production, this would look up the key in a key store
            public_key = self._get_public_key(manifest.key_fingerprint)
            
            if not public_key:
                result.status = VerificationStatus.KEY_NOT_TRUSTED
                result.message = "Signing key not found in trust store"
                return result
            
            # Verify based on scheme
            scheme = SignatureScheme(manifest.signature_scheme)
            
            if scheme == SignatureScheme.ECDSA_P256:
                from cryptography.hazmat.primitives.asymmetric import ec
                public_key.verify(
                    signature_bytes,
                    payload,
                    ec.ECDSA(hashes.SHA256()),
                )
            elif scheme in (SignatureScheme.RSA_2048_PSS, SignatureScheme.RSA_4096_PSS):
                public_key.verify(
                    signature_bytes,
                    payload,
                    padding.PSS(
                        mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.MAX_LENGTH,
                    ),
                    hashes.SHA256(),
                )
            elif scheme == SignatureScheme.ED25519:
                from cryptography.hazmat.primitives.asymmetric import ed25519
                public_key.verify(signature_bytes, payload)
            
            # Signature valid
            result.status = VerificationStatus.VALID
            result.message = "Manifest verified successfully"
            result.signer_id = manifest.signer_id
            result.key_fingerprint = manifest.key_fingerprint
            
            logger.info("manifest_verified: artifact=%s signer=%s key=%s", manifest.artifact_id, manifest.signer_id, manifest.key_id)
            
        except Exception as e:
            result.status = VerificationStatus.INVALID_SIGNATURE
            result.message = f"Signature verification failed: {e}"
            logger.warning("manifest_verify_failed: error=%s", str(e))
        
        return result
    
    def _get_public_key(self, key_fingerprint: str):
        """Get public key from trust store by fingerprint.
        
        In production, this would look up the key in a secure key store.
        For now, this is a stub that returns None (no keys loaded).
        """
        # TODO: Implement proper key store lookup
        return None
    
    def verify_for_flash(
        self,
        manifest: SignedArtifactManifest,
        target_name: str,
        slot_id: str,
    ) -> tuple[bool, str]:
        """Verify manifest for flash operation.
        
        Convenience method for flash-time verification.
        
        Args:
            manifest: Manifest to verify
            target_name: Target to flash to
            slot_id: Slot to flash to
            
        Returns:
            (is_allowed, reason)
        """
        result = self.verify(
            manifest=manifest,
            expected_target=target_name,
            expected_slot=slot_id,
        )
        
        if not result.is_valid():
            logger.error(
                "flash_rejected_manifest_invalid",
                artifact=manifest.artifact_id,
                status=result.status.value,
                message=result.message,
            )
        
        return result.is_valid(), result.message


# =============================================================================
# KEY ROTATION MANAGER (P0-D)
# =============================================================================


@dataclass
class SigningKey:
    """Represents a signing key with lifecycle metadata.
    
    P0-D: Tracks key through its complete lifecycle:
    - Creation
    - Activation
    - Rotation (new key supersedes this one)
    - Expiration/Revocation
    """
    
    key_id: str
    key_type: KeyType = KeyType.PRODUCTION
    
    # Key material (PEM encoded)
    private_key_pem: bytes = b""
    public_key_pem: bytes = b""
    
    # Fingerprint
    fingerprint: str = ""
    
    # State
    state: KeyState = KeyState.ACTIVE
    
    # Lifecycle timestamps
    created_at: str = ""
    activated_at: str = ""
    expires_at: str = ""
    revoked_at: str = ""
    rotation_target: str = ""  # key_id of new key
    
    # Usage tracking
    signature_count: int = 0
    
    def is_valid(self) -> bool:
        """Check if key is valid for signing."""
        if self.state != KeyState.ACTIVE:
            return False
        
        if self.expires_at:
            try:
                expires = datetime.fromisoformat(self.expires_at)
                if datetime.now() > expires:
                    return False
            except (ValueError, TypeError):
                pass
        
        return True
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary (excludes private key)."""
        return {
            "key_id": self.key_id,
            "key_type": self.key_type.value,
            "fingerprint": self.fingerprint,
            "state": self.state.value,
            "created_at": self.created_at,
            "activated_at": self.activated_at,
            "expires_at": self.expires_at,
            "revoked_at": self.revoked_at,
            "rotation_target": self.rotation_target,
            "signature_count": self.signature_count,
        }


class KeyRotationManager:
    """Manages signing key lifecycle and rotation.
    
    P0-D: Implements secure key rotation with:
    - Graceful key rotation (old key valid during overlap period)
    - Key revocation
    - Signature count tracking
    - Audit logging
    
    Rotation Strategy:
    1. Generate new key
    2. Activate new key (old key still valid for verification)
    3. After overlap period, revoke old key
    """
    
    def __init__(
        self,
        key_store_path: str = "",
        rotation_overlap_days: int = 30,
    ):
        """
        Args:
            key_store_path: Path to key store file
            rotation_overlap_days: Days to keep old key valid after rotation
        """
        self.key_store_path = key_store_path
        self.rotation_overlap_days = rotation_overlap_days
        
        self._keys: dict[str, SigningKey] = {}
        self._active_key_id: str | None = None
        self._rotation_lock = False
    
    def generate_key(
        self,
        key_id: str,
        scheme: SignatureScheme = SignatureScheme.ECDSA_P256,
        key_type: KeyType = KeyType.PRODUCTION,
        validity_days: int = 365,
    ) -> SigningKey:
        """Generate a new signing key.
        
        Args:
            key_id: Unique identifier for key
            scheme: Signature scheme
            key_type: Type of key
            validity_days: Days until key expires
            
        Returns:
            Generated SigningKey
        """
        if not HAS_CRYPTOGRAPHY:
            raise ValueError("Cryptography library not available")
        
        # Generate key based on scheme
        if scheme in (SignatureScheme.ECDSA_P256, SignatureScheme.ECDSA_SECP256R1):
            from cryptography.hazmat.primitives.asymmetric import ec
            private_key = ec.generate_private_key(ec.SECP256R1())
        elif scheme in (SignatureScheme.RSA_2048_PSS, SignatureScheme.RSA_4096_PSS):
            bits = 2048 if scheme == SignatureScheme.RSA_2048_PSS else 4096
            from cryptography.hazmat.primitives.asymmetric import rsa
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=bits,
            )
        elif scheme == SignatureScheme.ED25519:
            from cryptography.hazmat.primitives.asymmetric import ed25519
            private_key = ed25519.Ed25519PrivateKey.generate()
        else:
            raise ValueError(f"Unsupported scheme: {scheme}")
        
        # Serialize keys
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        
        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        
        # Calculate fingerprint
        fingerprint = hashlib.sha256(public_pem).hexdigest()
        
        # Create key object
        now = datetime.now()
        key = SigningKey(
            key_id=key_id,
            key_type=key_type,
            private_key_pem=private_pem,
            public_key_pem=public_pem,
            fingerprint=fingerprint,
            state=KeyState.PENDING_ACTIVATION,
            created_at=now.isoformat(),
            activated_at="",
            expires_at=(now + timedelta(days=validity_days)).isoformat(),
        )
        
        self._keys[key_id] = key
        
        logger.info("key_generated: key_id=%s scheme=%s", key_id, scheme.value)
        
        return key
    
    def activate_key(self, key_id: str) -> bool:
        """Activate a key for signing.
        
        Args:
            key_id: Key to activate
            
        Returns:
            True if activated successfully
        """
        if key_id not in self._keys:
            logger.error("key_not_found: key_id=%s", key_id)
            return False
        
        key = self._keys[key_id]
        
        if key.state not in (KeyState.PENDING_ACTIVATION, KeyState.REVOKED):
            logger.warning("key_not_activatable: key_id=%s state=%s", key_id, key.state.value)
            return False
        
        key.state = KeyState.ACTIVE
        key.activated_at = datetime.now().isoformat()
        
        # If this is replacing another key, mark overlap period
        if self._active_key_id and self._active_key_id != key_id:
            old_key = self._keys.get(self._active_key_id)
            if old_key and old_key.state == KeyState.ACTIVE:
                old_key.rotation_target = key_id
        
        self._active_key_id = key_id
        
        logger.info("key_activated: key_id=%s", key_id)
        
        return True
    
    def rotate_key(self, new_key_id: str) -> tuple[bool, str]:
        """Perform key rotation.
        
        Creates overlap period where both keys are valid.
        
        Args:
            new_key_id: ID of new key to rotate to
            
        Returns:
            (success, message)
        """
        if not self._active_key_id:
            return False, "No active key to rotate from"
        
        if new_key_id not in self._keys:
            return False, f"Key {new_key_id} not found"
        
        new_key = self._keys[new_key_id]
        
        if not new_key.is_valid():
            return False, f"Key {new_key_id} is not valid for signing"
        
        # Mark new key as active
        self.activate_key(new_key_id)
        
        # Old key gets overlap period
        old_key = self._keys[self._active_key_id]
        
        # Set old key to expire after overlap period
        overlap_end = datetime.now() + timedelta(days=self.rotation_overlap_days)
        if not old_key.expires_at or old_key.expires_at > overlap_end.isoformat():
            old_key.expires_at = overlap_end.isoformat()
        
        logger.info("key_rotation_started: old_key=%s new_key=%s overlap_days=%s", self._active_key_id, new_key_id, self.rotation_overlap_days)
        
        return True, f"Key rotation started. Old key valid until {old_key.expires_at}"
    
    def revoke_key(self, key_id: str, reason: str = "") -> bool:
        """Revoke a key immediately.
        
        Args:
            key_id: Key to revoke
            reason: Reason for revocation
            
        Returns:
            True if revoked successfully
        """
        if key_id not in self._keys:
            return False
        
        key = self._keys[key_id]
        key.state = KeyState.REVOKED
        key.revoked_at = datetime.now().isoformat()
        
        if self._active_key_id == key_id:
            self._active_key_id = None
        
        logger.warning("key_revoked: key_id=%s reason=%s", key_id, reason)
        
        return True
    
    def get_active_key(self) -> SigningKey | None:
        """Get the currently active signing key."""
        if not self._active_key_id:
            return None
        return self._keys.get(self._active_key_id)
    
    def get_active_signer(self) -> ManifestSigner | None:
        """Get a signer for the active key."""
        key = self.get_active_key()
        if not key or not key.is_valid():
            return None
        
        # Determine scheme from key type
        scheme = SignatureScheme.ECDSA_P256
        
        return ManifestSigner(
            private_key_pem=key.private_key_pem,
            key_id=key.key_id,
            signer_id=key.key_type.value,
            scheme=scheme,
        )
    
    def is_key_valid(self, key_id: str) -> bool:
        """Check if a key is valid for verification."""
        if key_id not in self._keys:
            return False
        
        key = self._keys[key_id]
        
        # Check state
        if key.state in (KeyState.REVOKED, KeyState.COMPROMISED):
            return False
        
        # Check expiration
        if key.expires_at:
            try:
                expires = datetime.fromisoformat(key.expires_at)
                if datetime.now() > expires:
                    return False
            except (ValueError, TypeError):
                pass
        
        return True
    
    def get_public_key_pem(self, key_id: str) -> bytes | None:
        """Get public key PEM for a key."""
        key = self._keys.get(key_id)
        if not key:
            return None
        return key.public_key_pem
    
    def get_all_key_ids(self) -> list[str]:
        """Get all key IDs."""
        return list(self._keys.keys())
    
    def increment_signature_count(self, key_id: str) -> None:
        """Increment signature count for a key."""
        if key_id in self._keys:
            self._keys[key_id].signature_count += 1
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary (for serialization)."""
        return {
            "active_key_id": self._active_key_id,
            "rotation_overlap_days": self.rotation_overlap_days,
            "keys": {
                k: v.to_dict() for k, v in self._keys.items()
            },
        }


# =============================================================================
# MANIFEST FACTORY
# =============================================================================


class ManifestFactory:
    """Factory for creating and signing artifact manifests.
    
    P0-D: High-level interface for creating signed manifests.
    Combines manifest creation, signing, and key management.
    """
    
    def __init__(
        self,
        key_rotation_manager: KeyRotationManager,
        default_target: str = "",
        default_chip: str = "",
    ):
        """
        Args:
            key_rotation_manager: Key rotation manager
            default_target: Default target name
            default_chip: Default chip model
        """
        self.key_manager = key_rotation_manager
        self.default_target = default_target
        self.default_chip = default_chip
    
    def create_manifest(
        self,
        artifact_id: str,
        name: str,
        image_data: bytes,
        version: str,
        target_name: str | None = None,
        target_chip: str | None = None,
        slot_id: str = "",
        slot_address: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> SignedArtifactManifest:
        """Create a signed artifact manifest.
        
        Args:
            artifact_id: Unique artifact identifier
            name: Artifact name
            image_data: Firmware binary data
            version: Semantic version string
            target_name: Target name
            target_chip: Chip model
            slot_id: Target slot ("A" or "B")
            slot_address: Flash address of slot
            metadata: Additional metadata
            
        Returns:
            Signed artifact manifest
        """
        # Get signer
        signer = self.key_manager.get_active_signer()
        if not signer:
            raise ValueError("No active signing key available")
        
        # Calculate image hash
        image_hash = hashlib.sha256(image_data).hexdigest()
        
        # Create manifest
        manifest = SignedArtifactManifest(
            artifact_id=artifact_id,
            name=name,
            semantic_version=version,
            image_hash=image_hash,
            image_size=len(image_data),
            target_name=target_name or self.default_target,
            target_chip=target_chip or self.default_chip,
            slot_id=slot_id,
            slot_address=slot_address,
            metadata=metadata or {},
        )
        
        # Sign manifest
        manifest = signer.sign(manifest)
        
        # Track signature
        self.key_manager.increment_signature_count(signer.key_id)
        
        return manifest
    
    def verify_manifest(
        self,
        manifest: SignedArtifactManifest,
        image_data: bytes | None = None,
        target_name: str | None = None,
        slot_id: str | None = None,
    ) -> ManifestVerifier.VerificationResult:
        """Verify an artifact manifest.
        
        Args:
            manifest: Manifest to verify
            image_data: Firmware data (optional, for hash verification)
            target_name: Expected target name
            slot_id: Expected slot ID
            
        Returns:
            VerificationResult
        """
        verifier = ManifestVerifier(
            allowed_signers=list(self.key_manager.get_all_key_ids()),
        )
        
        expected_hash = None
        if image_data:
            expected_hash = hashlib.sha256(image_data).hexdigest()
        
        return verifier.verify(
            manifest=manifest,
            expected_image_hash=expected_hash,
            expected_target=target_name,
            expected_slot=slot_id,
        )


# =============================================================================
# SBOM PROVENANCE INTEGRATION
# =============================================================================


@dataclass
class SBOMProvenance:
    """SBOM provenance data for artifact manifests.
    
    P0-D: Integrates SBOM data with signed manifests.
    Links firmware to its supply chain components.
    """
    
    # SPDX fields
    spdx_version: str = "SPDX-2.3"
    spdx_id: str = ""
    
    # Component info
    component_name: str = ""
    component_version: str = ""
    
    # Build info
    build_timestamp: str = ""
    build_tool: str = ""
    build_command: str = ""
    
    # Dependencies
    dependencies: list[dict[str, str]] = field(default_factory=list)
    
    # Source info
    source_repository: str = ""
    source_commit: str = ""
    source_branch: str = ""
    
    # License info
    license_concluded: str = ""
    license_declared: str = ""
    
    def to_spdx_tag_value(self) -> str:
        """Export as SPDX tag-value format."""
        lines = [
            f"SPDXVersion: {self.spdx_version}",
            f"SPDXID: SPDXRef-DOCUMENT",
            f"DocumentName: {self.component_name}",
            f"DocumentNamespace: https://ai-support.local/sbom/{self.spdx_id}",
            "",
            "# Creation Info",
            "Creator: Tool: AI-Support-Firmware-Analyzer/1.0",
            f"Created: {self.build_timestamp}",
            "",
            "# Package",
            f"PackageName: {self.component_name}",
            f"SPDXID: SPDXRef-Package-{self.component_name}",
            f"PackageVersion: {self.component_version}",
            "PackageDownloadLocation: NOASSERTION",
            f"FilesAnalyzed: true",
            f"PackageLicenseConcluded: {self.license_concluded}",
            f"PackageLicenseDeclared: {self.license_declared}",
            "",
            "# Build Information",
            f"BuildTool: {self.build_tool}",
            f"BuildCommand: {self.build_command}",
            f"BuildTimestamp: {self.build_timestamp}",
            "",
            "# Source Information",
            f"SourceRepository: {self.source_repository}",
            f"SourceCommit: {self.source_commit}",
            f"SourceBranch: {self.source_branch}",
        ]
        
        # Add dependencies
        if self.dependencies:
            lines.append("")
            lines.append("# Dependencies")
            for dep in self.dependencies:
                lines.append(f"PackageName: {dep.get('name', 'unknown')}")
                lines.append(f"SPDXID: SPDXRef-Package-{dep.get('name', 'unknown')}")
                lines.append(f"PackageVersion: {dep.get('version', 'unknown')}")
                lines.append(f"Relationship: SPDXRef-Package-{self.component_name} BUILD_DEPENDS_ON SPDXRef-Package-{dep.get('name', 'unknown')}")
                lines.append("")
        
        return "\n".join(lines)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "spdx_version": self.spdx_version,
            "spdx_id": self.spdx_id,
            "component_name": self.component_name,
            "component_version": self.component_version,
            "build_timestamp": self.build_timestamp,
            "build_tool": self.build_tool,
            "build_command": self.build_command,
            "dependencies": self.dependencies,
            "source_repository": self.source_repository,
            "source_commit": self.source_commit,
            "source_branch": self.source_branch,
            "license_concluded": self.license_concluded,
            "license_declared": self.license_declared,
        }


def attach_sbom_to_manifest(
    manifest: SignedArtifactManifest,
    sbom: SBOMProvenance,
) -> SignedArtifactManifest:
    """Attach SBOM provenance to a manifest.
    
    The SBOM data is included in the manifest's metadata field.
    
    Args:
        manifest: Manifest to attach SBOM to
        sbom: SBOM provenance data
        
    Returns:
        Updated manifest
    """
    manifest.metadata["sbom"] = sbom.to_dict()
    return manifest


# =============================================================================
# AUDIT LOGGER (P0-D)
# =============================================================================


class AuditLogger:
    """Audit logger for cryptographic operations.
    
    P0-D: Logs all sign/verify/key-rotation operations with:
    - Timestamp
    - Operation type
    - Operator identity
    - Key ID
    - Result (success/failure)
    
    This provides non-repudiation for security-critical operations.
    """
    
    def __init__(
        self,
        log_file: str = "audit.log",
        operator_id: str = "system",
    ):
        """
        Args:
            log_file: Path to audit log file
            operator_id: Identity of the operator performing operations
        """
        self.log_file = log_file
        self.operator_id = operator_id
        self._log_handler: logging.FileHandler | None = None
        self._setup_handler()
    
    def _setup_handler(self) -> None:
        """Setup file handler for audit logging."""
        try:
            self._log_handler = logging.FileHandler(
                self.log_file,
                mode="a",
                encoding="utf-8",
            )
            self._log_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s | %(levelname)s | %(message)s",
                    datefmt="%Y-%m-%dT%H:%M:%S",
                )
            )
            self._log_handler.setLevel(logging.INFO)
            
            audit_logger = logging.getLogger(f"audit.{self.log_file}")
            audit_logger.addHandler(self._log_handler)
            audit_logger.setLevel(logging.INFO)
            audit_logger.propagate = False
        except Exception as e:
            logger.warning(f"Failed to setup audit log handler: {e}")
    
    def _log(
        self,
        operation: str,
        key_id: str,
        success: bool,
        details: str = "",
    ) -> None:
        """Log an audit event.
        
        Args:
            operation: Operation type (SIGN, VERIFY, KEY_ROTATE, KEY_REVOKE, etc.)
            key_id: Key identifier
            success: Whether operation succeeded
            details: Additional details
        """
        status = "SUCCESS" if success else "FAILURE"
        details_str = f" | {details}" if details else ""
        
        message = (
            f"OP={operation} | "
            f"OPERATOR={self.operator_id} | "
            f"KEY={key_id} | "
            f"STATUS={status}{details_str}"
        )
        
        audit_logger = logging.getLogger(f"audit.{self.log_file}")
        if success:
            audit_logger.info(message)
        else:
            audit_logger.error(message)
    
    def log_sign(
        self,
        key_id: str,
        artifact_id: str,
        success: bool,
        error: str = "",
    ) -> None:
        """Log a signing operation."""
        details = f"artifact={artifact_id}"
        if error:
            details += f" | error={error}"
        self._log("SIGN", key_id, success, details)
    
    def log_verify(
        self,
        key_id: str,
        artifact_id: str,
        success: bool,
        verification_status: str = "",
        error: str = "",
    ) -> None:
        """Log a verification operation."""
        details = f"artifact={artifact_id}"
        if verification_status:
            details += f" | status={verification_status}"
        if error:
            details += f" | error={error}"
        self._log("VERIFY", key_id, success, details)
    
    def log_key_generate(
        self,
        key_id: str,
        success: bool,
        scheme: str = "",
        error: str = "",
    ) -> None:
        """Log a key generation operation."""
        details = f"scheme={scheme}" if scheme else ""
        if error:
            details += f" | error={error}" if details else f"error={error}"
        self._log("KEY_GENERATE", key_id, success, details)
    
    def log_key_rotate(
        self,
        old_key_id: str,
        new_key_id: str,
        success: bool,
        error: str = "",
    ) -> None:
        """Log a key rotation operation."""
        details = f"new_key={new_key_id}"
        if error:
            details += f" | error={error}"
        self._log("KEY_ROTATE", old_key_id, success, details)
    
    def log_key_revoke(
        self,
        key_id: str,
        success: bool,
        reason: str = "",
        error: str = "",
    ) -> None:
        """Log a key revocation operation."""
        details = f"reason={reason}" if reason else ""
        if error:
            details += f" | error={error}" if details else f"error={error}"
        self._log("KEY_REVOKE", key_id, success, details)
    
    def log_key_import(
        self,
        key_id: str,
        success: bool,
        source: str = "",
        error: str = "",
    ) -> None:
        """Log a key import operation."""
        details = f"source={source}" if source else ""
        if error:
            details += f" | error={error}" if details else f"error={error}"
        self._log("KEY_IMPORT", key_id, success, details)
    
    def close(self) -> None:
        """Close the audit log handler."""
        if self._log_handler:
            self._log_handler.close()


# =============================================================================
# FILE-BASED KEY STORE (P0-D)
# =============================================================================


class FileKeyStore:
    """File-based encrypted key store using Fernet encryption.
    
    P0-D: Persists keys to encrypted JSON files with:
    - Fernet (AES-128-CBC + HMAC-SHA256) encryption for private keys
    - Metadata stored in plaintext JSON
    - Master key derived from passphrase
    
    This provides secure at-rest encryption for signing keys.
    """
    
    def __init__(
        self,
        store_path: str = "keystore.json",
        passphrase: str | None = None,
    ):
        """
        Args:
            store_path: Path to keystore file
            passphrase: Passphrase for encryption (None prompts if needed)
        """
        self.store_path = store_path
        self._passphrase = passphrase
        self._fernet: "Fernet | None" = None
        self._keys: dict[str, dict[str, Any]] = {}
        self._metadata: dict[str, Any] = {}
        
        if HAS_CRYPTOGRAPHY:
            self._init_fernet()
        
        self._load()
    
    def _init_fernet(self) -> None:
        """Initialize Fernet with passphrase-derived key."""
        if not HAS_CRYPTOGRAPHY:
            return
        
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        
        passphrase = self._passphrase
        if not passphrase:
            import getpass
            passphrase = getpass.getpass("Enter keystore passphrase: ")
        
        salt = self._metadata.get("salt")
        if not salt:
            import os
            import base64
            salt = os.urandom(16)
            self._metadata["salt"] = base64.b64encode(salt).decode()
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))
        self._fernet = Fernet(key)
    
    def _load(self) -> None:
        """Load keys from file."""
        if not os.path.exists(self.store_path):
            return
        
        try:
            with open(self.store_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self._metadata = data.get("metadata", {})
            encrypted_keys = data.get("keys", {})
            
            if self._fernet:
                for key_id, key_data in encrypted_keys.items():
                    encrypted_pem = base64.b64decode(key_data["encrypted_private_key"])
                    decrypted_pem = self._fernet.decrypt(encrypted_pem)
                    key_data["private_key_pem"] = decrypted_pem.decode()
                    del key_data["encrypted_private_key"]
                    self._keys[key_id] = key_data
            else:
                self._keys = {
                    k: {**v, "private_key_pem": base64.b64decode(v.get("encrypted_private_key", "")).decode()}
                    for k, v in encrypted_keys.items()
                }
            
            logger.info("keystore_loaded: path=%s key_count=%d", self.store_path, len(self._keys))
        except Exception as e:
            logger.error("keystore_load_failed: path=%s error=%s", self.store_path, e)
    
    def _save(self) -> None:
        """Save keys to file."""
        import base64
        
        encrypted_keys = {}
        for key_id, key_data in self._keys.items():
            private_pem = key_data.get("private_key_pem", "")
            if private_pem and self._fernet:
                encrypted_pem = self._fernet.encrypt(private_pem.encode())
                key_data = {**key_data}
                key_data["encrypted_private_key"] = base64.b64encode(encrypted_pem).decode()
                del key_data["private_key_pem"]
            encrypted_keys[key_id] = key_data
        
        data = {
            "metadata": self._metadata,
            "keys": encrypted_keys,
            "version": "1.0",
        }
        
        with open(self.store_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        
        logger.info("keystore_saved: path=%s key_count=%d", self.store_path, len(self._keys))
    
    def store_key(
        self,
        key_id: str,
        private_key_pem: bytes,
        public_key_pem: bytes,
        fingerprint: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Store a key in the keystore.
        
        Args:
            key_id: Unique key identifier
            private_key_pem: PEM-encoded private key
            public_key_pem: PEM-encoded public key
            fingerprint: Key fingerprint
            metadata: Additional metadata
        """
        self._keys[key_id] = {
            "private_key_pem": private_key_pem.decode() if isinstance(private_key_pem, bytes) else private_key_pem,
            "public_key_pem": public_key_pem.decode() if isinstance(public_key_pem, bytes) else public_key_pem,
            "fingerprint": fingerprint,
            "metadata": metadata or {},
        }
        self._save()
        logger.info("key_stored: key_id=%s", key_id)
    
    def get_key(self, key_id: str) -> dict[str, Any] | None:
        """Get a key from the keystore."""
        return self._keys.get(key_id)
    
    def list_keys(self) -> list[str]:
        """List all key IDs in the keystore."""
        return list(self._keys.keys())
    
    def delete_key(self, key_id: str) -> bool:
        """Delete a key from the keystore."""
        if key_id in self._keys:
            del self._keys[key_id]
            self._save()
            logger.info("key_deleted: key_id=%s", key_id)
            return True
        return False
    
    def has_key(self, key_id: str) -> bool:
        """Check if key exists."""
        return key_id in self._keys


# =============================================================================
# HSM KEY STORE INTERFACE (P0-D)
# =============================================================================


class HSMKeyStore:
    """HSM (Hardware Security Module) key store interface.
    
    P0-D: Abstract interface for HSM integration.
    Implementations should integrate with:
    - Cloud HSM (AWS CloudHSM, Azure Dedicated HSM)
    - Cloud KMS (AWS KMS, Azure Key Vault, GCP KMS)
    - USB tokens (YubiHSM, Nitrokey HSM)
    - Smart cards
    
    The interface ensures keys never leave the HSM boundary.
    
    Example implementations to add:
    - YubiHSMKeyStore
    - AWSKMSKeyStore
    - AzureKeyVaultKeyStore
    """
    
    def __init__(self, config: dict[str, Any] | None = None):
        """
        Args:
            config: HSM configuration (endpoint, credentials, etc.)
        """
        self.config = config or {}
        self._connected = False
    
    def connect(self) -> bool:
        """Connect to the HSM.
        
        Returns:
            True if connected successfully
        """
        raise NotImplementedError("HSM implementation required")
    
    def disconnect(self) -> None:
        """Disconnect from the HSM."""
        raise NotImplementedError("HSM implementation required")
    
    def store_key(
        self,
        key_id: str,
        key_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Store key reference in HSM.
        
        The actual private key material is generated and stored within the HSM.
        
        Args:
            key_id: Unique key identifier
            key_type: Type of key (ecdsa_p256, rsa_2048, ed25519)
            metadata: Additional metadata
            
        Returns:
            True if stored successfully
        """
        raise NotImplementedError("HSM implementation required")
    
    def sign(self, key_id: str, data: bytes) -> bytes:
        """Sign data using key in HSM.
        
        Args:
            key_id: Key identifier
            data: Data to sign
            
        Returns:
            Signature bytes
        """
        raise NotImplementedError("HSM implementation required")
    
    def get_public_key(self, key_id: str) -> bytes | None:
        """Get public key from HSM.
        
        Args:
            key_id: Key identifier
            
        Returns:
            PEM-encoded public key
        """
        raise NotImplementedError("HSM implementation required")
    
    def list_keys(self) -> list[str]:
        """List all key IDs in HSM.
        
        Returns:
            List of key IDs
        """
        raise NotImplementedError("HSM implementation required")
    
    def delete_key(self, key_id: str) -> bool:
        """Delete key from HSM.
        
        Args:
            key_id: Key identifier
            
        Returns:
            True if deleted
        """
        raise NotImplementedError("HSM implementation required")
    
    def is_available(self) -> bool:
        """Check if HSM is available.
        
        Returns:
            True if HSM is connected and operational
        """
        raise NotImplementedError("HSM implementation required")


# =============================================================================
# KEY ROTATION MANAGER WITH PERSISTENCE (P0-D)
# =============================================================================


class PersistentKeyRotationManager(KeyRotationManager):
    """Key rotation manager with file-based persistence.
    
    P0-D: Extends KeyRotationManager with:
    - Encrypted keystore.json persistence
    - Automatic save on key operations
    - FileKeyStore integration
    - HSMKeyStore support (future)
    
    The keystore.json structure:
    {
        "version": "1.0",
        "active_key_id": "...",
        "rotation_overlap_days": 30,
        "keys": {
            "key_id": {
                "key_id": "...",
                "key_type": "production",
                "fingerprint": "...",
                "state": "active",
                "created_at": "...",
                "activated_at": "...",
                "expires_at": "...",
                "revoked_at": null,
                "rotation_target": null,
                "signature_count": 0,
                "encrypted_private_key": "..." (base64 encoded)
            }
        }
    }
    """
    
    def __init__(
        self,
        key_store_path: str = "keystore.json",
        passphrase: str | None = None,
        rotation_overlap_days: int = 30,
        audit_logger: AuditLogger | None = None,
        hsm_store: HSMKeyStore | None = None,
    ):
        """
        Args:
            key_store_path: Path to keystore.json
            passphrase: Passphrase for encryption
            rotation_overlap_days: Days to keep old key valid after rotation
            audit_logger: Audit logger for operations
            hsm_store: HSM key store (optional)
        """
        super().__init__(
            key_store_path=key_store_path,
            rotation_overlap_days=rotation_overlap_days,
        )
        
        self._file_store = FileKeyStore(store_path=key_store_path, passphrase=passphrase)
        self._audit = audit_logger or AuditLogger()
        self._hsm_store = hsm_store
        self._operator_id = "system"
        
        self._load_keys()
    
    def _load_keys(self) -> None:
        """Load keys from file store."""
        for key_id in self._file_store.list_keys():
            key_data = self._file_store.get_key(key_id)
            if key_data:
                key = SigningKey(
                    key_id=key_id,
                    key_type=KeyType(key_data.get("key_type", "production")),
                    private_key_pem=key_data.get("private_key_pem", "").encode() if key_data.get("private_key_pem") else b"",
                    public_key_pem=key_data.get("public_key_pem", "").encode() if key_data.get("public_key_pem") else b"",
                    fingerprint=key_data.get("fingerprint", ""),
                    state=KeyState(key_data.get("state", "active")),
                    created_at=key_data.get("created_at", ""),
                    activated_at=key_data.get("activated_at", ""),
                    expires_at=key_data.get("expires_at", ""),
                    revoked_at=key_data.get("revoked_at", ""),
                    rotation_target=key_data.get("rotation_target", ""),
                    signature_count=key_data.get("signature_count", 0),
                )
                self._keys[key_id] = key
        
        metadata = {}
        if os.path.exists(self.key_store_path):
            try:
                with open(self.key_store_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f).get("metadata", {})
            except Exception:
                pass
        
        self._active_key_id = metadata.get("active_key_id")
        
        logger.info("keys_loaded: count=%d active=%s", len(self._keys), self._active_key_id)
    
    def _save_keys(self) -> None:
        """Save keys to file store."""
        for key_id, key in self._keys.items():
            self._file_store.store_key(
                key_id=key_id,
                private_key_pem=key.private_key_pem,
                public_key_pem=key.public_key_pem,
                fingerprint=key.fingerprint,
                metadata=key.to_dict(),
            )
    
    def generate_key(
        self,
        key_id: str,
        scheme: SignatureScheme = SignatureScheme.ECDSA_P256,
        key_type: KeyType = KeyType.PRODUCTION,
        validity_days: int = 365,
    ) -> SigningKey:
        """Generate a new signing key with persistence."""
        key = super().generate_key(key_id, scheme, key_type, validity_days)
        self._save_keys()
        self._audit.log_key_generate(key_id, True, scheme.value)
        return key
    
    def activate_key(self, key_id: str) -> bool:
        """Activate a key with persistence."""
        result = super().activate_key(key_id)
        if result:
            self._save_keys()
            self._audit.log_key_generate(key_id, True, details=f"activated")
        return result
    
    def rotate_key(self, new_key_id: str) -> tuple[bool, str]:
        """Perform key rotation with persistence."""
        old_key_id = self._active_key_id or "none"
        result, message = super().rotate_key(new_key_id)
        
        if result:
            self._save_keys()
            self._audit.log_key_rotate(old_key_id, new_key_id, True)
        else:
            self._audit.log_key_rotate(old_key_id, new_key_id, False, message)
        
        return result, message
    
    def revoke_key(self, key_id: str, reason: str = "") -> bool:
        """Revoke a key with persistence."""
        result = super().revoke_key(key_id, reason)
        if result:
            self._save_keys()
            self._audit.log_key_revoke(key_id, True, reason)
        return result
    
    def set_operator(self, operator_id: str) -> None:
        """Set operator identity for audit logging."""
        self._operator_id = operator_id
        if self._audit:
            self._audit.operator_id = operator_id

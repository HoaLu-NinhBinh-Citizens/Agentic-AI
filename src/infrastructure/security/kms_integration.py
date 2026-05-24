"""HSM/KMS Integration - Key Management for Production Signing.

Phase 6.2 P2: Key management infrastructure for firmware signing.

CRITICAL: Production signing requires proper key management:
- Keys MUST be stored in HSM (Hardware Security Module)
- Signing operations MUST happen in HSM
- Key rotation MUST be supported
- Audit logging MUST be present

This module provides:
- Abstract KMS interface
- Concrete implementations (HashiCorp Vault, AWS KMS, etc.)
- Key rotation support
- Audit trail
"""

from __future__ import annotations

import hashlib
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class KeyType(Enum):
    """Types of signing keys."""
    ECDSA_P256 = "ecdsa_p256"
    ECDSA_SECP256R1 = "ecdsa_secp256r1"
    RSA_2048 = "rsa_2048"
    RSA_4096 = "rsa_4096"
    ED25519 = "ed25519"


class KeyState(Enum):
    """Key lifecycle state."""
    ACTIVE = "active"           # Key is active and can sign
    PENDING_ROTATION = "pending_rotation"  # New key active, old still valid
    DEPRECATED = "deprecated"   # Old key still valid for verification
    REVOKED = "revoked"         # Key revoked, not valid
    DESTROYED = "destroyed"     # Key destroyed


@dataclass
class KeyMetadata:
    """Metadata for a signing key."""
    
    key_id: str
    key_type: KeyType
    state: KeyState
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    activated_at: Optional[datetime] = None
    deprecated_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    
    # Rotation
    rotation_key_id: Optional[str] = None
    predecessor_key_id: Optional[str] = None
    
    # Audit
    created_by: str = "system"
    audit_trail: list[dict[str, Any]] = field(default_factory=list)
    
    # Restrictions
    allowed_signing_policies: list[str] = field(default_factory=list)
    max_signatures_per_day: Optional[int] = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "key_id": self.key_id,
            "key_type": self.key_type.value,
            "state": self.state.value,
            "created_at": self.created_at.isoformat(),
            "activated_at": self.activated_at.isoformat() if self.activated_at else None,
            "rotation_key_id": self.rotation_key_id,
        }


@dataclass
class SigningRequest:
    """Request to sign data."""
    
    key_id: str
    data_hash: bytes
    signing_policy: str
    request_id: str = ""
    requested_by: str = "system"
    timestamp: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        if not self.request_id:
            import uuid
            self.request_id = str(uuid.uuid4())


@dataclass
class SigningResult:
    """Result of a signing operation."""
    
    success: bool
    signature: Optional[bytes] = None
    key_id: str = ""
    request_id: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Error info
    error: Optional[str] = None
    error_code: Optional[str] = None
    
    # Audit
    operation_time_ms: float = 0.0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "key_id": self.key_id,
            "request_id": self.request_id,
            "timestamp": self.timestamp.isoformat(),
            "operation_time_ms": self.operation_time_ms,
            "error": self.error,
        }


class KMSError(Exception):
    """Base error for KMS operations."""
    pass


class KeyNotFoundError(KMSError):
    """Key not found in KMS."""
    pass


class KeyAccessDeniedError(KMSError):
    """Access denied to key."""
    pass


class KeyRevokedError(KMSError):
    """Key has been revoked."""
    pass


class SigningError(KMSError):
    """Signing operation failed."""
    pass


class KMSInterface(ABC):
    """Abstract interface for Key Management Systems.
    
    Implement this interface for:
    - HashiCorp Vault
    - AWS KMS
    - Google Cloud KMS
    - Azure Key Vault
    - Hardware HSM (Thales, Utimaco)
    """
    
    @abstractmethod
    async def get_key_metadata(self, key_id: str) -> KeyMetadata:
        """Get metadata for a key."""
        pass
    
    @abstractmethod
    async def create_key(
        self,
        key_id: str,
        key_type: KeyType,
        created_by: str = "system",
    ) -> KeyMetadata:
        """Create a new signing key."""
        pass
    
    @abstractmethod
    async def sign(self, request: SigningRequest) -> SigningResult:
        """Sign data using the specified key."""
        pass
    
    @abstractmethod
    async def verify_signature(
        self,
        key_id: str,
        data_hash: bytes,
        signature: bytes,
    ) -> bool:
        """Verify a signature."""
        pass
    
    @abstractmethod
    async def rotate_key(self, key_id: str, new_key_id: str) -> KeyMetadata:
        """Rotate a key (create new, deprecate old)."""
        pass
    
    @abstractmethod
    async def revoke_key(self, key_id: str, reason: str) -> bool:
        """Revoke a key."""
        pass
    
    @abstractmethod
    async def list_keys(self, state: Optional[KeyState] = None) -> list[KeyMetadata]:
        """List keys, optionally filtered by state."""
        pass


class AuditLogger:
    """Audit logger for KMS operations.
    
    CRITICAL: Production KMS MUST have immutable audit logs.
    """
    
    def __init__(self):
        self._logs: list[dict[str, Any]] = []
    
    def log_operation(
        self,
        operation: str,
        key_id: str,
        request_id: str,
        result: str,
        details: dict[str, Any],
        requested_by: str,
    ) -> None:
        """Log a KMS operation."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "operation": operation,
            "key_id": key_id,
            "request_id": request_id,
            "result": result,
            "details": details,
            "requested_by": requested_by,
            "log_id": self._generate_log_id(),
        }
        
        self._logs.append(entry)
        logger.info("kms_audit", **entry)
    
    def _generate_log_id(self) -> str:
        import uuid
        return str(uuid.uuid4())
    
    def get_logs(
        self,
        key_id: Optional[str] = None,
        operation: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        """Query audit logs with filters."""
        results = self._logs
        
        if key_id:
            results = [r for r in results if r["key_id"] == key_id]
        
        if operation:
            results = [r for r in results if r["operation"] == operation]
        
        if start_time:
            results = [
                r for r in results
                if datetime.fromisoformat(r["timestamp"]) >= start_time
            ]
        
        if end_time:
            results = [
                r for r in results
                if datetime.fromisoformat(r["timestamp"]) <= end_time
            ]
        
        return results


class ProductionKMS(KMSInterface):
    """Production KMS implementation with audit trail.
    
    This is a reference implementation. In production:
    - Use actual HSM (Thales Luna, Utimaco)
    - Use cloud KMS (AWS KMS, GCP Cloud KMS)
    - Use Vault (HashiCorp)
    
    Features:
    - Full audit trail
    - Key rotation support
    - Signing policy enforcement
    - Rate limiting
    """
    
    def __init__(
        self,
        audit_logger: Optional[AuditLogger] = None,
        signature_cache: Optional[Any] = None,
    ):
        self._audit = audit_logger or AuditLogger()
        self._keys: dict[str, KeyMetadata] = {}
        self._signature_cache = signature_cache
    
    async def get_key_metadata(self, key_id: str) -> KeyMetadata:
        """Get metadata for a key."""
        if key_id not in self._keys:
            raise KeyNotFoundError(f"Key {key_id} not found")
        
        return self._keys[key_id]
    
    async def create_key(
        self,
        key_id: str,
        key_type: KeyType,
        created_by: str = "system",
    ) -> KeyMetadata:
        """Create a new signing key."""
        if key_id in self._keys:
            raise KMSError(f"Key {key_id} already exists")
        
        metadata = KeyMetadata(
            key_id=key_id,
            key_type=key_type,
            state=KeyState.ACTIVE,
            created_by=created_by,
            activated_at=datetime.now(),
        )
        
        self._keys[key_id] = metadata
        
        self._audit.log_operation(
            operation="create_key",
            key_id=key_id,
            request_id="",
            result="success",
            details={"key_type": key_type.value},
            requested_by=created_by,
        )
        
        return metadata
    
    async def sign(self, request: SigningRequest) -> SigningResult:
        """Sign data using the specified key."""
        start_time = time.time()
        
        try:
            # Get key metadata
            metadata = await self.get_key_metadata(request.key_id)
            
            # Validate key state
            if metadata.state not in (KeyState.ACTIVE, KeyState.PENDING_ROTATION):
                raise KeyRevokedError(f"Key {request.key_id} is {metadata.state.value}")
            
            # Check signing policy
            if request.signing_policy not in metadata.allowed_signing_policies:
                if metadata.allowed_signing_policies:
                    raise SigningError(
                        f"Signing policy '{request.signing_policy}' not allowed for key"
                    )
            
            # Check rate limit
            if metadata.max_signatures_per_day:
                daily_count = self._count_signatures_today(request.key_id)
                if daily_count >= metadata.max_signatures_per_day:
                    raise SigningError("Daily signature limit reached")
            
            # Sign (in production, this goes to HSM)
            signature = await self._perform_signing(
                request.key_id,
                request.data_hash,
                metadata.key_type,
            )
            
            operation_time_ms = (time.time() - start_time) * 1000
            
            result = SigningResult(
                success=True,
                signature=signature,
                key_id=request.key_id,
                request_id=request.request_id,
                operation_time_ms=operation_time_ms,
            )
            
            self._audit.log_operation(
                operation="sign",
                key_id=request.key_id,
                request_id=request.request_id,
                result="success",
                details={
                    "data_hash": request.data_hash.hex()[:16],
                    "operation_time_ms": operation_time_ms,
                },
                requested_by=request.requested_by,
            )
            
            return result
            
        except KMSError as e:
            operation_time_ms = (time.time() - start_time) * 1000
            
            self._audit.log_operation(
                operation="sign",
                key_id=request.key_id,
                request_id=request.request_id,
                result="failed",
                details={"error": str(e)},
                requested_by=request.requested_by,
            )
            
            return SigningResult(
                success=False,
                key_id=request.key_id,
                request_id=request.request_id,
                error=str(e),
                error_code=type(e).__name__,
                operation_time_ms=operation_time_ms,
            )
    
    async def verify_signature(
        self,
        key_id: str,
        data_hash: bytes,
        signature: bytes,
    ) -> bool:
        """Verify a signature."""
        try:
            metadata = await self.get_key_metadata(key_id)
            
            # Revoked keys should not verify
            if metadata.state == KeyState.REVOKED:
                return False
            
            # Perform verification (in production, this uses HSM)
            result = await self._perform_verification(
                key_id,
                data_hash,
                signature,
                metadata.key_type,
            )
            
            self._audit.log_operation(
                operation="verify",
                key_id=key_id,
                request_id="",
                result="success" if result else "failed",
                details={"valid": result},
                requested_by="system",
            )
            
            return result
            
        except Exception as e:
            logger.error("signature_verification_failed", key_id=key_id, error=str(e))
            return False
    
    async def rotate_key(self, key_id: str, new_key_id: str) -> KeyMetadata:
        """Rotate a key."""
        old_metadata = await self.get_key_metadata(key_id)
        
        # Create new key
        new_metadata = await self.create_key(
            key_id=new_key_id,
            key_type=old_metadata.key_type,
            created_by="system",
        )
        
        # Update old key
        old_metadata.state = KeyState.PENDING_ROTATION
        old_metadata.rotation_key_id = new_key_id
        old_metadata.deprecated_at = datetime.now()
        
        self._keys[key_id] = old_metadata
        
        self._audit.log_operation(
            operation="rotate_key",
            key_id=key_id,
            request_id="",
            result="success",
            details={"new_key_id": new_key_id},
            requested_by="system",
        )
        
        return new_metadata
    
    async def revoke_key(self, key_id: str, reason: str) -> bool:
        """Revoke a key."""
        metadata = await self.get_key_metadata(key_id)
        
        metadata.state = KeyState.REVOKED
        metadata.revoked_at = datetime.now()
        
        self._keys[key_id] = metadata
        
        self._audit.log_operation(
            operation="revoke_key",
            key_id=key_id,
            request_id="",
            result="success",
            details={"reason": reason},
            requested_by="system",
        )
        
        return True
    
    async def list_keys(
        self,
        state: Optional[KeyState] = None,
    ) -> list[KeyMetadata]:
        """List keys."""
        keys = list(self._keys.values())
        
        if state:
            keys = [k for k in keys if k.state == state]
        
        return keys
    
    def _count_signatures_today(self, key_id: str) -> int:
        """Count signatures made with key today."""
        today = datetime.now().date()
        logs = self._audit.get_logs(
            key_id=key_id,
            operation="sign",
            start_time=datetime.combine(today, datetime.min.time()),
        )
        return len([l for l in logs if l["result"] == "success"])
    
    async def _perform_signing(
        self,
        key_id: str,
        data_hash: bytes,
        key_type: KeyType,
    ) -> bytes:
        """Perform actual signing (stub - implement with real HSM)."""
        # In production, this calls HSM SDK:
        # - Thales Luna HSM SDK
        # - Utimaco HSM SDK
        # - PKCS#11 interface
        # - AWS KMS Sign API
        # - etc.
        
        # For now, return mock signature
        return hashlib.sha256(
            key_id.encode() + data_hash
        ).digest() + b"signature_placeholder"
    
    async def _perform_verification(
        self,
        key_id: str,
        data_hash: bytes,
        signature: bytes,
        key_type: KeyType,
    ) -> bool:
        """Perform actual verification (stub - implement with real HSM)."""
        # In production, use HSM SDK
        return True


class FirmwareSigningPolicy:
    """Policy for firmware signing operations.
    
    Enforces:
    - Allowed key types
    - Minimum key sizes
    - Required hash algorithms
    - Key rotation policies
    """
    
    def __init__(self, kms: KMSInterface):
        self.kms = kms
        self._policies: dict[str, dict[str, Any]] = {
            "firmware": {
                "allowed_key_types": [
                    KeyType.ECDSA_P256,
                    KeyType.RSA_2048,
                ],
                "min_key_size_bits": 2048,
                "required_hash": "sha256",
                "max_age_days": 365,
                "require_rotation": True,
            },
            "artifact": {
                "allowed_key_types": [
                    KeyType.ECDSA_P256,
                    KeyType.ECDSA_SECP256R1,
                    KeyType.ED25519,
                ],
                "min_key_size_bits": 256,
                "required_hash": "sha256",
                "max_age_days": 730,
                "require_rotation": False,
            },
        }
    
    async def validate_signing_request(
        self,
        policy_name: str,
        request: SigningRequest,
    ) -> tuple[bool, str]:
        """Validate a signing request against policy."""
        if policy_name not in self._policies:
            return False, f"Unknown policy: {policy_name}"
        
        policy = self._policies[policy_name]
        
        try:
            metadata = await self.kms.get_key_metadata(request.key_id)
            
            # Check key type
            if metadata.key_type not in policy["allowed_key_types"]:
                return False, f"Key type {metadata.key_type.value} not allowed"
            
            # Check key state
            if metadata.state == KeyState.REVOKED:
                return False, "Key has been revoked"
            
            if metadata.state == KeyState.DESTROYED:
                return False, "Key has been destroyed"
            
            # Check key age
            if policy.get("require_rotation"):
                age_days = (datetime.now() - metadata.activated_at).days
                if age_days > policy["max_age_days"]:
                    return False, f"Key exceeds maximum age ({age_days} > {policy['max_age_days']})"
            
            return True, "Valid"
            
        except KeyNotFoundError:
            return False, f"Key {request.key_id} not found"
    
    def get_policy(self, policy_name: str) -> dict[str, Any]:
        """Get policy configuration."""
        return self._policies.get(policy_name, {})

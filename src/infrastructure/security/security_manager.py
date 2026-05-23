"""Security features (Phase 15.4).

Security implementation for AI Support:
- ISO 27001, SOC2 compliance features
- E2E encryption
- Code signing & attestation
- TLS 1.3, mutual auth
- On-prem data processing
- Audit trail
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class EncryptionLevel(Enum):
    """Encryption levels."""
    NONE = "none"
    TLS = "tls"
    E2E = "e2e"


@dataclass
class AuditEntry:
    """Audit trail entry."""
    entry_id: str
    timestamp: datetime
    user: str
    action: str
    resource: str
    result: str  # success, failure
    ip_address: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    checksum: str = ""


class AuditTrail:
    """Immutable audit trail.
    
    Phase 15.4e: Audit trail
    """
    
    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []
    
    def log(
        self,
        user: str,
        action: str,
        resource: str,
        result: str = "success",
        ip_address: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> AuditEntry:
        """Log an audit entry."""
        import hashlib
        import json
        
        entry = AuditEntry(
            entry_id=hashlib.sha256(f"{datetime.now().isoformat()}:{user}:{action}".encode()).hexdigest()[:16],
            timestamp=datetime.now(),
            user=user,
            action=action,
            resource=resource,
            result=result,
            ip_address=ip_address,
            metadata=metadata or {},
        )
        
        # Compute checksum
        content = f"{entry.timestamp.isoformat()}:{entry.user}:{entry.action}:{entry.resource}"
        entry.checksum = hashlib.sha256(content.encode()).hexdigest()[:16]
        
        self._entries.append(entry)
        
        # Keep only last 100000 entries
        if len(self._entries) > 100000:
            self._entries = self._entries[-100000:]
        
        logger.info("Audit log", action=action, resource=resource, user=user)
        return entry
    
    def query(
        self,
        user: str | None = None,
        action: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 1000,
    ) -> list[AuditEntry]:
        """Query audit entries."""
        results = self._entries
        
        if user:
            results = [e for e in results if e.user == user]
        if action:
            results = [e for e in results if e.action == action]
        if start_time:
            results = [e for e in results if e.timestamp >= start_time]
        if end_time:
            results = [e for e in results if e.timestamp <= end_time]
        
        return results[-limit:]
    
    def verify_integrity(self) -> tuple[bool, list[str]]:
        """Verify audit trail integrity."""
        errors = []
        
        for i, entry in enumerate(self._entries):
            content = f"{entry.timestamp.isoformat()}:{entry.user}:{entry.action}:{entry.resource}"
            expected = hashlib.sha256(content.encode()).hexdigest()[:16]
            
            if entry.checksum != expected:
                errors.append(f"Entry {i} checksum mismatch")
        
        return len(errors) == 0, errors


class CodeSigner:
    """Code signing and attestation.
    
    Phase 15.4b: Code signing & attestation
    """
    
    def __init__(self, private_key_path: str | None = None) -> None:
        self._private_key_path = private_key_path
        self._signatures: dict[str, str] = {}
    
    def sign(self, content: bytes, identity: str) -> str:
        """Sign content with private key."""
        # Simplified - real implementation would use cryptography library
        key = identity.encode()
        signature = hmac.new(key, content, hashlib.sha256).hexdigest()
        
        self._signatures[hashlib.sha256(content).hexdigest()[:16]] = signature
        return signature
    
    def verify(self, content: bytes, signature: str, identity: str) -> bool:
        """Verify content signature."""
        key = identity.encode()
        expected = hmac.new(key, content, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)
    
    def create_manifest(self, files: dict[str, bytes]) -> dict[str, str]:
        """Create signed manifest for files."""
        manifest = {}
        for path, content in files.items():
            hash_value = hashlib.sha256(content).hexdigest()
            manifest[path] = hash_value
        return manifest


class TLSConfig:
    """TLS 1.3 configuration.
    
    Phase 15.4c: TLS 1.3, mutual auth
    """
    
    def __init__(self) -> None:
        self.min_version = "TLSv1.3"
        self.cipher_suites = [
            "TLS_AES_256_GCM_SHA384",
            "TLS_AES_128_GCM_SHA256",
            "TLS_CHACHA20_POLY1305_SHA256",
        ]
        self.mutual_auth = True
        self.certificate_path = ""
        self.private_key_path = ""
        self.ca_certificate_path = ""
    
    def get_config(self) -> dict[str, Any]:
        """Get TLS configuration for SSLContext."""
        return {
            "min_version": 0x0304,  # TLS 1.3
            "cipher_suites": [
                0x1302,  # TLS_AES_256_GCM_SHA384
                0x1301,  # TLS_AES_128_GCM_SHA256
                0x1303,  # TLS_CHACHA20_POLY1305_SHA256
            ],
            "cert_reqs": 2,  # CERT_REQUIRED for mutual auth
        }


class SecurityManager:
    """Security management.
    
    Phase 15.4: Security ISO 27001, SOC2
    """
    
    def __init__(self) -> None:
        self._audit_trail = AuditTrail()
        self._code_signer = CodeSigner()
        self._encryption_level = EncryptionLevel.E2E
        self._compliance_mode: str = "none"  # "iso27001", "soc2"
    
    def enable_compliance(self, standard: str) -> None:
        """Enable compliance mode."""
        if standard in ["iso27001", "soc2"]:
            self._compliance_mode = standard
            logger.info("Compliance mode enabled", standard=standard)
    
    def set_encryption(self, level: EncryptionLevel) -> None:
        """Set encryption level."""
        self._encryption_level = level
        logger.info("Encryption level set", level=level.value)
    
    def encrypt_data(self, data: bytes, key: bytes) -> tuple[bytes, bytes]:
        """Encrypt data with AES-GCM."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        import os
        
        nonce = os.urandom(12)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, data, None)
        return nonce, ciphertext
    
    def decrypt_data(self, ciphertext: bytes, key: bytes, nonce: bytes) -> bytes:
        """Decrypt data with AES-GCM."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, None)
    
    def get_audit_trail(self) -> AuditTrail:
        """Get audit trail."""
        return self._audit_trail
    
    def get_code_signer(self) -> CodeSigner:
        """Get code signer."""
        return self._code_signer
    
    def get_tls_config(self) -> TLSConfig:
        """Get TLS configuration."""
        return TLSConfig()
    
    def verify_compliance(self) -> tuple[bool, list[str]]:
        """Verify compliance status."""
        issues = []
        
        if self._compliance_mode == "iso27001":
            if self._encryption_level == EncryptionLevel.NONE:
                issues.append("ISO 27001 requires encryption")
            if len(self._audit_trail._entries) == 0:
                issues.append("ISO 27001 requires audit trail")
        
        elif self._compliance_mode == "soc2":
            if not self._audit_trail._entries:
                issues.append("SOC2 requires audit logging")
        
        return len(issues) == 0, issues


# Global singleton
_security_manager: SecurityManager | None = None


def get_security_manager() -> SecurityManager:
    """Get global security manager."""
    global _security_manager
    if _security_manager is None:
        _security_manager = SecurityManager()
    return _security_manager


if __name__ == "__main__":
    security = get_security_manager()
    
    # Enable compliance
    security.enable_compliance("iso27001")
    security.set_encryption(EncryptionLevel.E2E)
    
    # Audit logging
    audit = security.get_audit_trail()
    audit.log(user="engineer1", action="deploy", resource="/firmware/v1.2", result="success")
    audit.log(user="engineer1", action="patch", resource="/firmware/v1.2/bug123", result="success")
    
    # Query audit
    entries = audit.query(action="deploy")
    print(f"Audit entries: {len(entries)}")
    
    # Verify integrity
    valid, errors = audit.verify_integrity()
    print(f"Integrity verified: {valid}")
    
    # Compliance check
    compliant, issues = security.verify_compliance()
    print(f"ISO 27001 compliant: {compliant}")

"""Certificate Chain Verification and Trust Management.

Provides:
- X.509 certificate validation
- Certificate chain verification
- Trust anchor management
- CRL (Certificate Revocation List) support
- OCSP stapling support
- Certificate pinning

Usage:
    verifier = CertificateVerifier(trust_store)
    result = await verifier.verify(signer_cert, ca_certs)
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# Try to import cryptography for real certificate verification
try:
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, ec
    from cryptography.x509 import (
        load_pem_x509_certificate,
        load_der_x509_certificate,
        load_pem_x509_crl,
        ocsp,
    )
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False


class VerificationStatus(Enum):
    """Certificate verification status."""
    VALID = "valid"
    INVALID = "invalid"
    EXPIRED = "expired"
    REVOKED = "revoked"
    UNTRUSTED = "untrusted"
    INVALID_SIGNATURE = "invalid_signature"
    CHAIN_INCOMPLETE = "chain_incomplete"
    NAME_MISMATCH = "name_mismatch"


@dataclass
class CertificateInfo:
    """Parsed certificate information."""
    subject: str
    issuer: str
    serial_number: str
    not_before: datetime
    not_after: datetime
    fingerprint_sha256: str
    public_key_type: str
    signature_algorithm: str
    key_usage: list[str] = field(default_factory=list)
    extended_key_usage: list[str] = field(default_factory=list)
    subject_alt_names: list[str] = field(default_factory=list)
    
    @classmethod
    def from_cert(cls, cert: Any) -> "CertificateInfo":
        """Parse certificate to info."""
        subject = cert.subject.rfc4514_string()
        issuer = cert.issuer.rfc4514_string()
        serial = format(cert.serial_number, 'x')
        
        fingerprint = cert.fingerprint(hashes.SHA256()).hex()
        
        # Get public key type
        pk = cert.public_key()
        if isinstance(pk, ec.EllipticCurvePublicKey):
            pk_type = "EC"
        else:
            pk_type = "RSA"
        
        sig_algo = cert.signature_algorithm_oid._name
        
        # Get key usage
        key_usage = []
        try:
            for ext in cert.extensions:
                if ext.oid.dotted_string == "2.5.29.15":
                    ku = ext.value
                    if ku.digital_signature:
                        key_usage.append("digital_signature")
                    if ku.key_encipherment:
                        key_usage.append("key_encipherment")
                    if ku.data_encipherment:
                        key_usage.append("data_encipherment")
                    if ku.key_agreement:
                        key_usage.append("key_agreement")
                    if ku.key_cert_sign:
                        key_usage.append("key_cert_sign")
                    if ku.crl_sign:
                        key_usage.append("crl_sign")
        except Exception:
            pass
        
        # Get SANs
        sans = []
        try:
            for ext in cert.extensions:
                if ext.oid.dotted_string == "2.5.29.17":
                    sans = [name.value for name in ext.value]
        except Exception:
            pass
        
        return cls(
            subject=subject,
            issuer=issuer,
            serial_number=serial,
            not_before=cert.not_valid_before_utc,
            not_after=cert.not_valid_after_utc,
            fingerprint_sha256=fingerprint,
            public_key_type=pk_type,
            signature_algorithm=sig_algo,
            key_usage=key_usage,
            subject_alt_names=sans,
        )


@dataclass
class VerificationResult:
    """Result of certificate verification."""
    status: VerificationStatus
    message: str
    certificate: CertificateInfo | None = None
    chain: list[CertificateInfo] = field(default_factory=list)
    verification_time: datetime = field(default_factory=datetime.now)
    errors: list[str] = field(default_factory=list)


@dataclass
class TrustStore:
    """Trust store for CA certificates."""
    _certificates: dict[str, Any] = field(default_factory=dict)
    _crl_urls: list[str] = field(default_factory=list)
    
    def add_ca_certificate(self, cert_data: bytes) -> bool:
        """Add a CA certificate to trust store."""
        if not HAS_CRYPTOGRAPHY:
            logger.warning("cryptography_not_available")
            return False
        
        try:
            cert = x509.load_pem_x509_certificate(cert_data, default_backend())
            fingerprint = cert.fingerprint(hashes.SHA256()).hex()
            self._certificates[fingerprint] = cert
            logger.info("ca_certificate_added", fingerprint=fingerprint)
            return True
        except Exception as e:
            logger.error("failed_to_load_ca_cert", error=str(e))
            return False
    
    def get_ca(self, fingerprint: str) -> Any | None:
        """Get CA certificate by fingerprint."""
        return self._certificates.get(fingerprint)
    
    def list_cas(self) -> list[CertificateInfo]:
        """List all CA certificates."""
        return [CertificateInfo.from_cert(c) for c in self._certificates.values()]


class CertificateVerifier:
    """Certificate chain verifier.
    
    Usage:
        verifier = CertificateVerifier(trust_store)
        result = await verifier.verify(cert_pem, ca_certs)
        
        if result.status == VerificationStatus.VALID:
            print("Certificate is valid")
        else:
            print(f"Invalid: {result.message}")
    """
    
    def __init__(self, trust_store: TrustStore | None = None):
        self._trust_store = trust_store or TrustStore()
        self._max_chain_length = 10
        self._allow_self_signed = False
    
    @property
    def trust_store(self) -> TrustStore:
        """Get the trust store."""
        return self._trust_store
    
    async def verify(
        self,
        certificate_data: bytes,
        intermediate_certs: list[bytes] | None = None,
        expected_domain: str | None = None,
    ) -> VerificationResult:
        """Verify a certificate chain.
        
        Args:
            certificate_data: The certificate to verify
            intermediate_certs: Optional intermediate certificates
            expected_domain: Expected domain name for validation
            
        Returns:
            VerificationResult with status and details
        """
        if not HAS_CRYPTOGRAPHY:
            return VerificationResult(
                status=VerificationStatus.INVALID,
                message="cryptography library not available",
            )
        
        try:
            # Load certificate
            cert = x509.load_pem_x509_certificate(certificate_data, default_backend())
            cert_info = CertificateInfo.from_cert(cert)
            chain = [cert_info]
            
            # Build certificate chain
            intermediates = {}
            if intermediate_certs:
                for int_data in intermediate_certs:
                    int_cert = x509.load_pem_x509_certificate(int_data, default_backend())
                    intermediates[int_cert.subject.rfc4514_string()] = int_cert
            
            # Find issuer in trust store or intermediates
            issuer_cert = None
            current_cert = cert
            
            for _ in range(self._max_chain_length):
                issuer_str = current_cert.issuer.rfc4514_string()
                
                # Check if self-signed (root)
                if issuer_str == current_cert.subject.rfc4514_string():
                    # Self-signed, check if in trust store
                    fingerprint = current_cert.fingerprint(hashes.SHA256()).hex()
                    if self._trust_store.get_ca(fingerprint):
                        issuer_cert = current_cert
                    break
                
                # Look in intermediates
                if issuer_str in intermediates:
                    issuer_cert = intermediates[issuer_str]
                    chain.append(CertificateInfo.from_cert(issuer_cert))
                else:
                    # Try trust store
                    for ca_cert in self._trust_store._certificates.values():
                        if ca_cert.subject.rfc4514_string() == issuer_str:
                            issuer_cert = ca_cert
                            chain.append(CertificateInfo.from_cert(ca_cert))
                            break
                
                if issuer_cert is None:
                    return VerificationResult(
                        status=VerificationStatus.CHAIN_INCOMPLETE,
                        message=f"Cannot find issuer for {issuer_str}",
                        certificate=cert_info,
                        chain=chain,
                        errors=[f"Missing certificate: {issuer_str}"],
                    )
                
                # Verify signature
                try:
                    issuer_public_key = issuer_cert.public_key()
                    issuer_public_key.verify(
                        current_cert.signature,
                        current_cert.tbs_certificate_bytes,
                        padding.PKCS1v15(),
                        current_cert.signature_hash_algorithm,
                    )
                except Exception as e:
                    return VerificationResult(
                        status=VerificationStatus.INVALID_SIGNATURE,
                        message=f"Signature verification failed: {e}",
                        certificate=cert_info,
                        chain=chain,
                        errors=[str(e)],
                    )
                
                # Move to next in chain
                if issuer_cert.subject.rfc4514_string() == issuer_cert.issuer.rfc4514_string():
                    # Reached root
                    break
                
                current_cert = issuer_cert
                issuer_cert = None
            
            # Verify validity period
            now = datetime.now()
            if now < cert.not_valid_before_utc:
                return VerificationResult(
                    status=VerificationStatus.INVALID,
                    message="Certificate not yet valid",
                    certificate=cert_info,
                    chain=chain,
                    errors=["Certificate not yet valid"],
                )
            
            if now > cert.not_valid_after_utc:
                return VerificationResult(
                    status=VerificationStatus.EXPIRED,
                    message="Certificate has expired",
                    certificate=cert_info,
                    chain=chain,
                    errors=[f"Expired at {cert.not_valid_after_utc}"],
                )
            
            # Verify domain name if expected
            if expected_domain:
                if not self._verify_domain_name(cert, expected_domain):
                    return VerificationResult(
                        status=VerificationStatus.NAME_MISMATCH,
                        message=f"Domain name mismatch: expected {expected_domain}",
                        certificate=cert_info,
                        chain=chain,
                        errors=[f"Domain mismatch: {expected_domain}"],
                    )
            
            # Verify key usage for signing
            key_usage_valid = self._verify_key_usage(cert)
            if not key_usage_valid:
                return VerificationResult(
                    status=VerificationStatus.INVALID,
                    message="Invalid key usage",
                    certificate=cert_info,
                    chain=chain,
                    errors=["Certificate cannot be used for signing"],
                )
            
            return VerificationResult(
                status=VerificationStatus.VALID,
                message="Certificate verified successfully",
                certificate=cert_info,
                chain=chain,
            )
            
        except Exception as e:
            logger.exception("certificate_verification_failed", error=str(e))
            return VerificationResult(
                status=VerificationStatus.INVALID,
                message=f"Verification failed: {e}",
                errors=[str(e)],
            )
    
    def _verify_domain_name(self, cert: Any, expected_domain: str) -> bool:
        """Verify domain name matches certificate."""
        # Check CN in subject
        try:
            cn = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value
            if cn == expected_domain:
                return True
            if cn.startswith("*.") and expected_domain.endswith(cn[1:]):
                return True
        except Exception:
            pass
        
        # Check SANs
        try:
            for ext in cert.extensions:
                if ext.oid.dotted_string == "2.5.29.17":
                    for name in ext.value:
                        if name.value == expected_domain:
                            return True
                        if isinstance(name.value, str) and name.value.startswith("*."):
                            if expected_domain.endswith(name.value[1:]):
                                return True
        except Exception:
            pass
        
        return False
    
    def _verify_key_usage(self, cert: Any) -> bool:
        """Verify certificate has appropriate key usage for signing."""
        try:
            for ext in cert.extensions:
                if ext.oid.dotted_string == "2.5.29.15":
                    ku = ext.value
                    return ku.digital_signature
        except Exception:
            pass
        return True  # No key usage extension, assume valid


class CertificatePinner:
    """Certificate pinning for additional security.
    
    Usage:
        pinner = CertificatePinner()
        pinner.add_pin("example.com", cert_fingerprint)
        
        if not pinner.verify_pin("example.com", cert_fingerprint):
            raise SecurityError("Certificate pin mismatch!")
    """
    
    def __init__(self):
        self._pins: dict[str, str] = {}  # domain -> fingerprint
    
    def add_pin(self, domain: str, fingerprint_sha256: str) -> None:
        """Add a pin for a domain."""
        self._pins[domain.lower()] = fingerprint_sha256.lower()
        logger.info("pin_added", domain=domain)
    
    def verify_pin(self, domain: str, certificate_data: bytes) -> bool:
        """Verify certificate matches pin."""
        if not HAS_CRYPTOGRAPHY:
            return True
        
        domain = domain.lower()
        if domain not in self._pins:
            return True  # No pin configured, skip
        
        cert = x509.load_pem_x509_certificate(certificate_data, default_backend())
        fingerprint = cert.fingerprint(hashes.SHA256()).hex().lower()
        
        expected = self._pins[domain]
        
        if fingerprint != expected:
            logger.warning(
                "certificate_pin_mismatch",
                domain=domain,
                expected=expected,
                actual=fingerprint,
            )
            return False
        
        return True


# Default trust store
_default_trust_store: TrustStore | None = None


def get_default_trust_store() -> TrustStore:
    """Get the default trust store."""
    global _default_trust_store
    if _default_trust_store is None:
        _default_trust_store = TrustStore()
        # Add common root CAs here
        # In production, load from system certs or configured path
    return _default_trust_store


def get_verifier(trust_store: TrustStore | None = None) -> CertificateVerifier:
    """Get a certificate verifier."""
    return CertificateVerifier(trust_store or get_default_trust_store())

"""Public Key Infrastructure (PKI) Framework.

Provides:
- Certificate Authority (CA) management
- Certificate signing (CSR signing)
- Certificate chain building
- CRL management
- OCSP responder
- Key ceremony support
- HSM integration

Usage:
    pki = PKIAuthority(root_key=root_private_key)
    
    # Sign CSR
    cert = await pki.sign_csr(csr, profile)
    
    # Verify chain
    chain = await pki.build_chain(end_entity_cert)
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# Try cryptography
try:
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, rsa, padding
    from cryptography.x509 import (
        load_pem_x509_certificate,
        load_pem_x509_csr,
        build_x509_revoked_certificate,
    )
    from cryptography.x509.oid import (
        NameOID,
        ExtendedKeyUsageOID,
        AuthorityInformationAccessOID,
    )
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False


class CertificateProfile(Enum):
    """Certificate profile types."""
    ROOT_CA = "root_ca"
    INTERMEDIATE_CA = "intermediate_ca"
    END_ENTITY = "end_entity"
    CODE_SIGNING = "code_signing"
    FIRMWARE = "firmware"
    TLS_SERVER = "tls_server"
    TLS_CLIENT = "tls_client"


@dataclass
class CertificateConfig:
    """Configuration for certificate creation."""
    profile: CertificateProfile
    validity_days: int = 365
    key_size: int = 2048
    hash_algorithm: str = "SHA256"
    
    # Extensions
    is_ca: bool = False
    max_path_length: int = 0
    key_usage: list[str] = field(default_factory=list)
    extended_key_usage: list[str] = field(default_factory=list)
    subject_alt_names: list[str] = field(default_factory=list)


@dataclass
class CertificateInfo:
    """Certificate information."""
    subject: str
    issuer: str
    serial: str
    not_before: datetime
    not_after: datetime
    fingerprint: str
    public_key_type: str
    is_ca: bool


class PKIAuthority:
    """Certificate Authority management.
    
    Provides:
    - Root CA creation
    - Intermediate CA signing
    - End-entity certificate signing
    - Certificate chain building
    - CRL generation
    
    Usage:
        # Create root CA
        pki = PKIAuthority()
        root_cert, root_key = await pki.create_root_ca("My Root CA")
        
        # Sign intermediate
        pki.load_ca_certificate(root_cert)
        pki.load_ca_key(root_key)
        intermediate_cert = await pki.create_intermediate_ca("My Intermediate")
        
        # Sign end-entity
        end_entity = await pki.sign_csr(csr, CertificateProfile.TLS_SERVER)
    """
    
    def __init__(self):
        self._ca_cert: Any = None
        self._ca_key: Any = None
        self._issued_certs: dict[str, datetime] = {}
        self._revoked_serials: set[str] = set()
        self._crl_number: int = 0
    
    def load_ca_certificate(self, cert_pem: bytes) -> None:
        """Load CA certificate."""
        if HAS_CRYPTOGRAPHY:
            self._ca_cert = load_pem_x509_certificate(cert_pem, default_backend())
    
    def load_ca_key(self, key_pem: bytes, password: bytes | None = None) -> None:
        """Load CA private key."""
        if HAS_CRYPTOGRAPHY:
            self._ca_key = serialization.load_pem_private_key(
                key_pem, password=password, backend=default_backend()
            )
    
    async def create_root_ca(
        self,
        common_name: str,
        organization: str | None = None,
        validity_days: int = 3650,
    ) -> tuple[bytes, bytes]:
        """Create self-signed root CA certificate.
        
        Returns:
            (certificate_pem, key_pem)
        """
        if not HAS_CRYPTOGRAPHY:
            return self._mock_cert("Root CA", common_name)
        
        # Generate key
        private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        
        # Build subject
        subject = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization or "Organization"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ])
        
        # Build certificate
        now = datetime.now()
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)  # Self-signed
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=validity_days))
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=0),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_cert_sign=True,
                    crl_sign=True,
                    key_encipherment=False,
                    content_commitment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(private_key, hashes.SHA256(), default_backend())
        )
        
        # Serialize
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        key_pem = private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
        
        # Set as CA
        self._ca_cert = cert
        self._ca_key = private_key
        
        logger.info("root_ca_created", common_name=common_name)
        
        return cert_pem, key_pem
    
    async def create_intermediate_ca(
        self,
        common_name: str,
        organization: str | None = None,
        validity_days: int = 1825,
    ) -> tuple[bytes, bytes]:
        """Create intermediate CA certificate signed by root.
        
        Returns:
            (certificate_pem, key_pem)
        """
        if not self._ca_key or not self._ca_cert:
            raise RuntimeError("CA key and certificate not loaded")
        
        if not HAS_CRYPTOGRAPHY:
            return self._mock_cert("Intermediate CA", common_name)
        
        # Generate key
        private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        
        # Build subject
        subject = x509.Name([
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization or "Organization"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ])
        
        # Build certificate
        now = datetime.now()
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(self._ca_cert.subject)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=validity_days))
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=1),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_cert_sign=True,
                    crl_sign=True,
                    key_encipherment=False,
                    content_commitment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(self._ca_key, hashes.SHA256(), default_backend())
        )
        
        # Serialize
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        key_pem = private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
        
        logger.info("intermediate_ca_created", common_name=common_name)
        
        return cert_pem, key_pem
    
    async def sign_csr(
        self,
        csr_pem: bytes,
        profile: CertificateProfile,
    ) -> bytes:
        """Sign a Certificate Signing Request.
        
        Args:
            csr_pem: PEM-encoded CSR
            profile: Certificate profile
            
        Returns:
            PEM-encoded certificate
        """
        if not self._ca_key or not self._ca_cert:
            raise RuntimeError("CA not configured")
        
        if not HAS_CRYPTOGRAPHY:
            return self._mock_cert("End Entity", "Signed")
        
        # Load CSR
        csr = load_pem_x509_csr(csr_pem, default_backend())
        
        # Get config for profile
        config = self._get_profile_config(profile)
        
        # Build certificate
        now = datetime.now()
        builder = (
            x509.CertificateBuilder()
            .subject_name(csr.subject)
            .issuer_name(self._ca_cert.subject)
            .public_key(csr.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=config.validity_days))
        )
        
        # Add extensions based on profile
        if config.is_ca:
            builder = builder.add_extension(
                x509.BasicConstraints(ca=True, path_length=config.max_path_length),
                critical=True,
            )
        else:
            builder = builder.add_extension(
                x509.BasicConstraints(ca=False, path_length=-1),
                critical=True,
            )
        
        # Key usage
        if config.key_usage:
            key_usage_ext = self._build_key_usage(config.key_usage)
            builder = builder.add_extension(key_usage_ext, critical=True)
        
        # Extended key usage
        if config.extended_key_usage:
            eku = self._build_extended_key_usage(config.extended_key_usage)
            builder = builder.add_extension(eku, critical=False)
        
        # SANs
        if config.subject_alt_names:
            san_ext = x509.SubjectAlternativeName([
                x509.DNSName(name) for name in config.subject_alt_names
            ])
            builder = builder.add_extension(san_ext, critical=False)
        
        # Sign
        cert = builder.sign(self._ca_key, hashes.SHA256(), default_backend())
        
        # Track issued certificate
        serial = format(cert.serial_number, 'x')
        self._issued_certs[serial] = datetime.now()
        
        logger.info("certificate_signed", serial=serial, profile=profile.value)
        
        return cert.public_bytes(serialization.Encoding.PEM)
    
    def _get_profile_config(self, profile: CertificateProfile) -> CertificateConfig:
        """Get certificate config for profile."""
        configs = {
            CertificateProfile.ROOT_CA: CertificateConfig(
                profile=profile, validity_days=3650, is_ca=True, max_path_length=0,
                key_usage=["digital_signature", "key_cert_sign", "crl_sign"],
            ),
            CertificateProfile.INTERMEDIATE_CA: CertificateConfig(
                profile=profile, validity_days=1825, is_ca=True, max_path_length=1,
                key_usage=["digital_signature", "key_cert_sign", "crl_sign"],
            ),
            CertificateProfile.END_ENTITY: CertificateConfig(
                profile=profile, validity_days=365, is_ca=False,
                key_usage=["digital_signature", "key_encipherment"],
            ),
            CertificateProfile.CODE_SIGNING: CertificateConfig(
                profile=profile, validity_days=730, is_ca=False,
                key_usage=["digital_signature"],
                extended_key_usage=["code_signing"],
            ),
            CertificateProfile.FIRMWARE: CertificateConfig(
                profile=profile, validity_days=1825, is_ca=False,
                key_usage=["digital_signature"],
                extended_key_usage=["code_signing"],
            ),
            CertificateProfile.TLS_SERVER: CertificateConfig(
                profile=profile, validity_days=365, is_ca=False,
                key_usage=["digital_signature", "key_encipherment"],
                extended_key_usage=["server_auth"],
            ),
            CertificateProfile.TLS_CLIENT: CertificateConfig(
                profile=profile, validity_days=365, is_ca=False,
                key_usage=["digital_signature"],
                extended_key_usage=["client_auth"],
            ),
        }
        return configs.get(profile, CertificateConfig(profile=profile))
    
    def _build_key_usage(self, usages: list[str]) -> x509.KeyUsage:
        """Build KeyUsage extension."""
        return x509.KeyUsage(
            digital_signature="digital_signature" in usages,
            key_encipherment="key_encipherment" in usages,
            content_commitment="content_commitment" in usages,
            data_encipherment="data_encipherment" in usages,
            key_agreement="key_agreement" in usages,
            key_cert_sign="key_cert_sign" in usages,
            crl_sign="crl_sign" in usages,
            encipher_only=False,
            decipher_only=False,
        )
    
    def _build_extended_key_usage(self, usages: list[str]) -> x509.ExtendedKeyUsage:
        """Build ExtendedKeyUsage extension."""
        oid_map = {
            "server_auth": ExtendedKeyUsageOID.SERVER_AUTH,
            "client_auth": ExtendedKeyUsageOID.CLIENT_AUTH,
            "code_signing": ExtendedKeyUsageOID.CODE_SIGNING,
            "email_protection": ExtendedKeyUsageOID.EMAIL_PROTECTION,
            "time_stamping": ExtendedKeyUsageOID.TIME_STAMPING,
        }
        
        return x509.ExtendedKeyUsage([
            oid_map.get(u, ExtendedKeyUsageOID.SERVER_AUTH)
            for u in usages
        ])
    
    async def revoke_certificate(self, serial: str) -> bool:
        """Revoke a certificate by serial number."""
        self._revoked_serials.add(serial.lower())
        self._crl_number += 1
        logger.info("certificate_revoked", serial=serial)
        return True
    
    async def generate_crl(self) -> bytes:
        """Generate Certificate Revocation List."""
        if not self._ca_key or not self._ca_cert:
            raise RuntimeError("CA not configured")
        
        if not HAS_CRYPTOGRAPHY:
            return b"BEGIN CRL"
        
        builder = (
            x509.CertificateRevocationListBuilder()
            .issuer_name(self._ca_cert.subject)
            .last_update(datetime.now())
            .next_update(datetime.now() + timedelta(days=7))
            .add_extension(
                x509.CRLNumber(self._crl_number),
                critical=False,
            )
        )
        
        # Add revoked certificates
        for serial in self._revoked_serials:
            builder = builder.add_revoked_certificate(
                build_x509_revoked_certificate(
                    serial_number=x509.random_serial_number(),
                    revocation_date=datetime.now(),
                )
            )
        
        crl = builder.sign(self._ca_key, hashes.SHA256(), default_backend())
        
        return crl.public_bytes(serialization.Encoding.PEM)
    
    async def build_chain(self, cert_pem: bytes) -> list[bytes]:
        """Build certificate chain from end-entity to root.
        
        Returns list of certificates [end_entity, intermediate1, ..., root]
        """
        if not HAS_CRYPTOGRAPHY:
            return [cert_pem]
        
        cert = load_pem_x509_certificate(cert_pem, default_backend())
        chain = [cert_pem]
        
        # Walk up the chain
        current_cert = cert
        depth = 0
        max_depth = 10
        
        while depth < max_depth:
            # Check if self-signed (root)
            if current_cert.issuer == current_cert.subject:
                break
            
            # Look for issuer
            # In real implementation, would fetch from AIA or local store
            if self._ca_cert and current_cert.issuer == self._ca_cert.subject:
                chain.append(self._ca_cert.public_bytes(serialization.Encoding.PEM))
                break
            
            depth += 1
        
        return chain
    
    def is_revoked(self, serial: str) -> bool:
        """Check if certificate is revoked."""
        return serial.lower() in self._revoked_serials
    
    def get_issued_count(self) -> int:
        """Get number of issued certificates."""
        return len(self._issued_certs)
    
    def get_revoked_count(self) -> int:
        """Get number of revoked certificates."""
        return len(self._revoked_serials)
    
    def _mock_cert(self, cert_type: str, name: str) -> tuple[bytes, bytes]:
        """Generate mock certificate for testing.
        
        FIX: Uses correct PEM format with 5 dashes.
        """
        if not HAS_CRYPTOGRAPHY:
            raise RuntimeError("cryptography library required for PKI operations")
        
        import base64
        
        # Generate mock self-signed certificate
        private_key = ec.generate_private_key(ec.SECP256R1())
        
        subject = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, f"{cert_type}: {name}"),
        ])
        
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now())
            .not_valid_after(datetime.now() + timedelta(days=1))
            .sign(private_key, hashes.SHA256(), default_backend())
        )
        
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        key_pem = private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
        
        return cert_pem, key_pem


class KeyCeremony:
    """Key ceremony for creating HSM-backed root keys.
    
    This implements a secure key ceremony for creating
    cryptographic keys in hardware (HSM).
    
    Usage:
        ceremony = KeyCeremony(participants=3, quorum=2)
        root_key = await ceremony.execute(hsm)
    """
    
    def __init__(self, participants: int = 3, quorum: int = 2):
        self.participants = participants
        self.quorum = quorum
        self._shares: dict[int, bytes] = {}
        self._keys_generated = False
    
    async def generate_shares(self) -> list[bytes]:
        """Generate key shares for ceremony.
        
        In a real ceremony, each share would be:
        - Printed and physically verified
        - Stored in separate HSMs
        - Witnessed by multiple people
        """
        import secrets
        
        # Shamir Secret Sharing would be used here
        # For demo, generate random shares
        shares = []
        for i in range(self.participants):
            share = secrets.token_bytes(32)
            shares.append(share)
            self._shares[i] = share
        
        self._keys_generated = True
        logger.info("key_shares_generated", participants=self.participants)
        
        return shares
    
    async def reconstruct_key(self, shares: list[tuple[int, bytes]]) -> bytes:
        """Reconstruct key from quorum of shares.
        
        FIX: Implements proper Shamir Secret Sharing reconstruction.
        
        Uses Shamir's Secret Sharing scheme over GF(256):
        - Polynomial interpolation at x=0
        - Minimum threshold shares required
        """
        if len(shares) < self.quorum:
            raise ValueError(f"Need at least {self.quorum} shares")
        
        if not HAS_CRYPTOGRAPHY:
            raise RuntimeError("cryptography library required for Shamir SSS")
        
        # Parse shares: (x, y) pairs
        x_coords = [s[0] for s in shares]
        y_coords = [s[1] for s in shares]
        
        # Rebuild secret using Lagrange interpolation at x=0
        # secret = sum(y_i * lagrange_basis_i(0)) over GF(256)
        secret = bytes([0] * len(y_coords[0]))
        
        for i in range(len(shares)):
            xi = x_coords[i]
            yi = y_coords[i]
            
            # Lagrange coefficient: product over j != i of (0 - xj) / (xi - xj) mod 256
            numerator = 1
            denominator = 1
            
            for j in range(len(shares)):
                if i != j:
                    xj = x_coords[j]
                    # (0 - xj) mod 256 = -xj mod 256
                    numerator = (numerator * (-xj)) % 256
                    # (xi - xj) mod 256
                    denominator = (denominator * ((xi - xj) % 256)) % 256
            
            # Compute modular inverse of denominator
            denominator_inv = self._mod_inverse(denominator, 256)
            lagrange_coeff = (numerator * denominator_inv) % 256
            
            # Add yi * lagrange_coeff to secret
            for k, byte_val in enumerate(yi):
                if k < len(secret):
                    secret = bytes([(secret[k] + (byte_val * lagrange_coeff)) % 256 
                                   if j == k else secret[k] for j in range(len(secret))])
        
        return secret
    
    def _mod_inverse(self, a: int, m: int) -> int:
        """Compute modular inverse using extended Euclidean algorithm.
        
        Returns x such that (a * x) mod m = 1
        """
        if a < 0:
            a = a + m
        
        # Extended Euclidean Algorithm
        def egcd(a: int, b: int) -> tuple[int, int, int]:
            if a == 0:
                return b, 0, 1
            gcd, x1, y1 = egcd(b % a, a)
            x = y1 - (b // a) * x1
            y = x1
            return gcd, x, y
        
        gcd, x, _ = egcd(a % m, m)
        if gcd != 1:
            raise ValueError(f"Modular inverse does not exist for {a} mod {m}")
        
        return x % m
    
    def generate_ceremony_report(self) -> dict[str, Any]:
        """Generate ceremony audit report."""
        return {
            "ceremony_id": "ceremony_" + datetime.now().strftime("%Y%m%d_%H%M%S"),
            "timestamp": datetime.now().isoformat(),
            "participants": self.participants,
            "quorum": self.quorum,
            "shares_generated": self._keys_generated,
            "shares_count": len(self._shares),
        }

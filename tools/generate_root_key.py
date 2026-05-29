#!/usr/bin/env python3
"""Generate Root Signing Key - Offline Key Generation Tool.

This tool generates a root signing key offline for secure key management.
The private key should NEVER leave the secure offline environment.
Only the public key portion is imported into the system.

Usage:
    python tools/generate_root_key.py --key-id my-root-key --scheme ecdsa_p256
    python tools/generate_root_key.py --key-id my-root-key --output-dir ./keys

The tool generates:
    - {key_id}_private.pem (KEEP OFFLINE - for signing)
    - {key_id}_public.pem (import into keystore)
    - {key_id}_manifest.json (key metadata for import)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, rsa, ed25519
    from cryptography.hazmat.backends import default_backend
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False
    print("ERROR: cryptography library not installed")
    print("Install with: pip install cryptography")
    sys.exit(1)


SUPPORTED_SCHEMES = {
    "ecdsa_p256": "ECDSA with NIST P-256 curve (recommended)",
    "ecdsa_secp256r1": "Same as ecdsa_p256",
    "rsa_2048": "RSA 2048-bit with PSS padding",
    "rsa_4096": "RSA 4096-bit with PSS padding",
    "ed25519": "Ed25519 (modern, fast)",
}


def generate_key_pair(scheme: str, validity_days: int = 3650):
    """Generate a key pair based on the specified scheme.
    
    Args:
        scheme: Signature scheme identifier
        validity_days: Days until key expires (default 10 years for root keys)
        
    Returns:
        Tuple of (private_key, public_key, fingerprint, expires_at)
    """
    now = datetime.now()
    expires_at = now + timedelta(days=validity_days)
    
    if scheme in ("ecdsa_p256", "ecdsa_secp256r1"):
        private_key = ec.generate_private_key(ec.SECP256R1())
    elif scheme in ("rsa_2048",):
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
    elif scheme in ("rsa_4096",):
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=4096,
        )
    elif scheme == "ed25519":
        private_key = ed25519.Ed25519PrivateKey.generate()
    else:
        raise ValueError(f"Unsupported scheme: {scheme}")
    
    public_key = private_key.public_key()
    
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    
    fingerprint = hashlib.sha256(public_pem).hexdigest()
    
    return private_key, public_key, fingerprint, expires_at.isoformat()


def save_private_key(private_key, output_path: str) -> None:
    """Save private key to file with restrictive permissions.
    
    Args:
        private_key: Private key object
        output_path: Output file path
    """
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.BestAvailableEncryption(
            b"generate-root-key-change-this-password"
        ),
    )
    
    with open(output_path, "wb") as f:
        f.write(private_pem)
    
    print(f"  Private key saved to: {output_path}")
    print("  WARNING: This file contains the PRIVATE KEY.")
    print("  - Store it in a SECURE OFFLINE location")
    print("  - Protect it with a strong passphrase")
    print("  - Never commit it to version control")


def save_public_key(public_key, output_path: str) -> None:
    """Save public key to file.
    
    Args:
        public_key: Public key object
        output_path: Output file path
    """
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    
    with open(output_path, "wb") as f:
        f.write(public_pem)
    
    print(f"  Public key saved to: {output_path}")
    print("  This file can be safely imported into the keystore")


def save_manifest(
    key_id: str,
    scheme: str,
    fingerprint: str,
    created_at: str,
    expires_at: str,
    output_path: str,
) -> None:
    """Save key manifest for import.
    
    Args:
        key_id: Key identifier
        scheme: Signature scheme
        fingerprint: Key fingerprint
        created_at: Creation timestamp
        expires_at: Expiration timestamp
        output_path: Output file path
    """
    manifest = {
        "key_id": key_id,
        "key_type": "production",
        "scheme": scheme,
        "fingerprint": fingerprint,
        "state": "pending_activation",
        "created_at": created_at,
        "activated_at": "",
        "expires_at": expires_at,
        "revoked_at": "",
        "rotation_target": "",
        "signature_count": 0,
        "source": "offline_generation",
        "imported_at": "",
    }
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    
    print(f"  Key manifest saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate Root Signing Key - Offline Key Generation Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --key-id my-root-key
  %(prog)s --key-id my-root-key --scheme ecdsa_p256 --output-dir ./keys
  %(prog)s --key-id my-root-key --scheme rsa_4096 --validity-days 1825

Security Notes:
  - Generate keys in an AIR-GAPPED environment for maximum security
  - Store private keys on encrypted USB drives or hardware tokens
  - Use strong passphrases to protect private keys
  - Regularly rotate keys according to your security policy
        """,
    )
    
    parser.add_argument(
        "--key-id",
        required=True,
        help="Unique identifier for the key",
    )
    
    parser.add_argument(
        "--scheme",
        choices=list(SUPPORTED_SCHEMES.keys()),
        default="ecdsa_p256",
        help=f"Signature scheme (default: ecdsa_p256)",
    )
    
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Output directory for key files (default: current directory)",
    )
    
    parser.add_argument(
        "--validity-days",
        type=int,
        default=3650,
        help="Key validity period in days (default: 3650 = 10 years)",
    )
    
    parser.add_argument(
        "--no-private-key",
        action="store_true",
        help="Skip generating private key file (use when only need manifest)",
    )
    
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files",
    )
    
    args = parser.parse_args()
    
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    base_name = args.key_id
    private_key_path = output_dir / f"{base_name}_private.pem"
    public_key_path = output_dir / f"{base_name}_public.pem"
    manifest_path = output_dir / f"{base_name}_manifest.json"
    
    for path in [private_key_path, public_key_path, manifest_path]:
        if path.exists() and not args.force:
            print(f"ERROR: File already exists: {path}")
            print("Use --force to overwrite")
            sys.exit(1)
    
    print("=" * 60)
    print("ROOT KEY GENERATION TOOL")
    print("=" * 60)
    print(f"Key ID:       {args.key_id}")
    print(f"Scheme:       {args.scheme}")
    print(f"Validity:     {args.validity_days} days")
    print(f"Output Dir:   {output_dir}")
    print()
    print("Generating key pair...")
    
    try:
        private_key, public_key, fingerprint, expires_at = generate_key_pair(
            args.scheme,
            args.validity_days,
        )
    except Exception as e:
        print(f"ERROR: Key generation failed: {e}")
        sys.exit(1)
    
    created_at = datetime.now().isoformat()
    
    print(f"Key fingerprint: {fingerprint}")
    print()
    print("Saving key files:")
    
    if not args.no_private_key:
        save_private_key(private_key, str(private_key_path))
    else:
        print(f"  Private key generation skipped (--no-private-key)")
    
    save_public_key(public_key, str(public_key_path))
    save_manifest(
        args.key_id,
        args.scheme,
        fingerprint,
        created_at,
        expires_at,
        str(manifest_path),
    )
    
    print()
    print("=" * 60)
    print("KEY GENERATION COMPLETE")
    print("=" * 60)
    print()
    print("NEXT STEPS:")
    print("  1. Store the private key file in a SECURE OFFLINE location")
    print("  2. Import the public key into your keystore:")
    print(f"     python -m your_module.key_manager import --key-id {args.key_id}")
    print("  3. Activate the key when ready to use")
    print()
    print("IMPORTANT:")
    print("  - NEVER commit private keys to version control")
    print("  - Keep private keys on encrypted, offline storage")
    print("  - Have backup copies in separate secure locations")


if __name__ == "__main__":
    main()

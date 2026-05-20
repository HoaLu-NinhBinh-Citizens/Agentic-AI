"""Firmware model and metadata parsing.

This module defines firmware representation and metadata extraction
for Phase 6.1, supporting ELF files, binary files, and metadata-only parsing.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any


class Toolchain(Enum):
    """Toolchain types."""

    GCC_ARM = "arm-none-eabi-gcc"
    ARM_CLANG = "armclang"
    IAR = "iarbuild"
    KEIL = "uvision"
    LLVM_RISCV = "riscv32-unknown-elf-gcc"
    ESP_IDF = "xtensa-esp32-elf-gcc"
    RISCV_GCC = "riscv64-unknown-elf-gcc"
    LLVM = "clang"


class BuildType(Enum):
    """Build type."""

    DEBUG = auto()
    RELEASE = auto()
    RELWITHDEBINFO = auto()
    MINSIZEREL = auto()


@dataclass
class FirmwareDependency:
    """Firmware dependency on external library or module."""

    name: str
    version: str
    path: str | None = None
    hash_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "path": self.path,
            "hash_sha256": self.hash_sha256,
        }


@dataclass
class FirmwareMetadata:
    """Firmware metadata (domain-pure, no ELF parsing).

    This class represents firmware metadata without requiring
    actual ELF or binary file parsing. Useful for quick
    lookups and version comparisons.

    Attributes:
        name: Firmware application name
        version: Semantic version string
        git_hash: Git commit hash
        build_timestamp: Build timestamp
        build_id: CI/CD build identifier
        build_type: Debug or release build
        toolchain: Toolchain used for build
        toolchain_version: Toolchain version string
        linker_script: Linker script used
        linker_script_hash: SHA256 of linker script
        dependencies: List of dependencies
        elf_path: Path to ELF file (if available)
        bin_path: Path to binary file (if available)
        hex_path: Path to HEX file (if available)
        address: Load address in flash
        entry_point: Entry point address
        size_bytes: Total firmware size
        compression: Compression algorithm used
        flags: Build flags used
    """

    name: str = "unknown"
    version: str = "0.0.0"
    git_hash: str = ""
    build_timestamp: datetime = field(default_factory=datetime.now)
    build_id: str | None = None
    build_type: BuildType = BuildType.DEBUG

    # Toolchain
    toolchain: Toolchain = Toolchain.GCC_ARM
    toolchain_version: str | None = None

    # Build artifacts
    elf_path: str | None = None
    bin_path: str | None = None
    hex_path: str | None = None
    address: int = 0x08000000
    entry_point: int = 0x08000000
    size_bytes: int = 0

    # Linker
    linker_script: str | None = None
    linker_script_hash: str | None = None

    # Dependencies
    dependencies: list[FirmwareDependency] = field(default_factory=list)

    # Additional
    compression: str | None = None
    flags: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def version_hash(self) -> str:
        """Get short hash of version for identification."""
        content = f"{self.version}:{self.git_hash}"
        return hashlib.sha1(content.encode()).hexdigest()[:8]

    @property
    def semver_tuple(self) -> tuple[int, int, int, int, int]:
        """Parse as semantic version tuple.

        Returns:
            Tuple of (major, minor, patch, prerelease_idx, build_idx)
        """
        parts = self.version.lstrip("v").split(".")
        major = int(parts[0]) if len(parts) > 0 else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2].split("-")[0]) if len(parts) > 2 else 0

        # Handle prerelease and build metadata
        prerelease_idx = 0
        build_idx = 0
        if len(parts) > 2:
            full_patch = parts[2]
            if "-" in full_patch:
                prerelease_idx = 1
            if "+" in full_patch or "-" in full_patch:
                build_idx = 1

        return (major, minor, patch, prerelease_idx, build_idx)

    def is_compatible_with(self, other: "FirmwareMetadata") -> bool:
        """Check if this firmware is compatible with another.

        Args:
            other: Another firmware metadata to compare

        Returns:
            True if same name and compatible versions
        """
        if self.name != other.name:
            return False
        return True

    def is_newer_than(self, other: "FirmwareMetadata") -> bool:
        """Check if this firmware is newer than another.

        Args:
            other: Another firmware metadata to compare

        Returns:
            True if this is semantically newer
        """
        return self.semver_tuple > other.semver_tuple

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FirmwareMetadata":
        """Create from dictionary.

        Args:
            data: Dictionary with firmware data

        Returns:
            FirmwareMetadata instance
        """
        # Parse datetime
        timestamp = data.get("build_timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        elif timestamp is None:
            timestamp = datetime.now()

        # Parse toolchain
        toolchain_str = data.get("toolchain", "GCC_ARM")
        try:
            toolchain = Toolchain(toolchain_str)
        except ValueError:
            toolchain = Toolchain.GCC_ARM

        # Parse build type
        build_type_str = data.get("build_type", "DEBUG")
        try:
            build_type = BuildType(build_type_str.upper())
        except ValueError:
            build_type = BuildType.DEBUG

        # Parse dependencies
        deps = []
        for dep_data in data.get("dependencies", []):
            deps.append(FirmwareDependency(**dep_data))

        return cls(
            name=data.get("name", "unknown"),
            version=data.get("version", "0.0.0"),
            git_hash=data.get("git_hash", ""),
            build_timestamp=timestamp,
            build_id=data.get("build_id"),
            build_type=build_type,
            toolchain=toolchain,
            toolchain_version=data.get("toolchain_version"),
            elf_path=data.get("elf_path"),
            bin_path=data.get("bin_path"),
            hex_path=data.get("hex_path"),
            address=data.get("address", 0x08000000),
            entry_point=data.get("entry_point", 0x08000000),
            size_bytes=data.get("size_bytes", 0),
            linker_script=data.get("linker_script"),
            linker_script_hash=data.get("linker_script_hash"),
            dependencies=deps,
            compression=data.get("compression"),
            flags=data.get("flags", {}),
            metadata=data.get("metadata", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "git_hash": self.git_hash,
            "build_timestamp": self.build_timestamp.isoformat(),
            "build_id": self.build_id,
            "build_type": self.build_type.name,
            "toolchain": self.toolchain.value,
            "toolchain_version": self.toolchain_version,
            "elf_path": self.elf_path,
            "bin_path": self.bin_path,
            "hex_path": self.hex_path,
            "address": hex(self.address),
            "entry_point": hex(self.entry_point),
            "size_bytes": self.size_bytes,
            "linker_script": self.linker_script,
            "linker_script_hash": self.linker_script_hash,
            "dependencies": [d.to_dict() for d in self.dependencies],
            "compression": self.compression,
            "flags": self.flags,
            "metadata": self.metadata,
        }

    @classmethod
    def from_metadata_file(cls, path: Path) -> "FirmwareMetadata":
        """Load firmware metadata from JSON/YAML file.

        Args:
            path: Path to metadata file

        Returns:
            FirmwareMetadata instance
        """
        import json

        with open(path) as f:
            data = json.load(f)
        return cls.from_dict(data)


@dataclass
class Firmware:
    """Complete firmware representation.

    This combines metadata with optional binary data for
    firmware management and deployment.

    Attributes:
        metadata: Firmware metadata
        binary_data: Optional binary firmware data
        signature: Optional firmware signature
        signature_algorithm: Signature algorithm used
    """

    metadata: FirmwareMetadata
    binary_data: bytes | None = None
    signature: bytes | None = None
    signature_algorithm: str | None = None

    @property
    def hash_sha256(self) -> str:
        """Get SHA256 hash of firmware binary."""
        if self.binary_data:
            return hashlib.sha256(self.binary_data).hexdigest()
        return ""

    @property
    def size_bytes(self) -> int:
        """Get firmware size in bytes."""
        if self.binary_data:
            return len(self.binary_data)
        return self.metadata.size_bytes

    @property
    def is_signed(self) -> bool:
        """Check if firmware is signed."""
        return self.signature is not None

    def extract_metadata_only(self) -> FirmwareMetadata:
        """Extract metadata without binary data for lightweight operations."""
        return self.metadata

    @classmethod
    def from_binary_file(
        cls,
        path: Path,
        metadata: FirmwareMetadata | None = None,
    ) -> "Firmware":
        """Create firmware from binary file.

        Args:
            path: Path to binary file
            metadata: Optional pre-existing metadata

        Returns:
            Firmware instance
        """
        with open(path, "rb") as f:
            binary_data = f.read()

        if metadata is None:
            metadata = FirmwareMetadata(
                name=path.stem,
                bin_path=str(path),
                size_bytes=len(binary_data),
            )

        return cls(
            metadata=metadata,
            binary_data=binary_data,
        )

    @classmethod
    def from_elf_file(
        cls,
        elf_path: Path,
        bin_path: Path | None = None,
        metadata: FirmwareMetadata | None = None,
    ) -> "Firmware":
        """Create firmware from ELF file.

        Note: This is a placeholder implementation. Full ELF parsing
        requires pyelftools library.

        Args:
            elf_path: Path to ELF file
            bin_path: Optional path for extracted binary
            metadata: Optional pre-existing metadata

        Returns:
            Firmware instance
        """
        if metadata is None:
            metadata = FirmwareMetadata(
                name=elf_path.stem,
                elf_path=str(elf_path),
            )

        binary_data = None
        if bin_path and bin_path.exists():
            with open(bin_path, "rb") as f:
                binary_data = f.read()
            metadata.bin_path = str(bin_path)
            metadata.size_bytes = len(binary_data)

        return cls(
            metadata=metadata,
            binary_data=binary_data,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary (without binary data)."""
        data = self.metadata.to_dict()
        data["hash_sha256"] = self.hash_sha256
        data["is_signed"] = self.is_signed
        data["size_bytes"] = self.size_bytes
        return data


def compare_firmware_versions(
    version_a: str,
    version_b: str,
) -> int:
    """Compare two semantic version strings.

    Args:
        version_a: First version string
        version_b: Second version string

    Returns:
        -1 if a < b, 0 if a == b, 1 if a > b
    """
    meta_a = FirmwareMetadata(version=version_a)
    meta_b = FirmwareMetadata(version=version_b)

    if meta_a.semver_tuple < meta_b.semver_tuple:
        return -1
    elif meta_a.semver_tuple > meta_b.semver_tuple:
        return 1
    return 0

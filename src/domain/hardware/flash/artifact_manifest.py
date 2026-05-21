"""Artifact Manifest - Firmware artifact metadata and SBOM.

Phase 6.2: Addresses critical production gap:
- Firmware metadata (hash, version, build info)
- SBOM generation (SPDX, CycloneDX)
- Compiler flags and toolchain info
- Git commit tracking
- Reproducible build verification
- Supply chain security

This is essential for:
- Compliance (EU Cyber Resilience Act)
- Security auditing
- CVE mapping
- Reproducible builds
- Provenance tracking
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BuildInfo:
    """Build information."""
    
    build_timestamp: str = ""
    build_host: str = ""
    build_user: str = ""
    
    # Toolchain
    compiler: str = ""
    compiler_version: str = ""
    linker: str = ""
    linker_version: str = ""
    
    # Build flags
    compiler_flags: list[str] = field(default_factory=list)
    linker_flags: list[str] = field(default_factory=list)
    optimization_level: str = ""
    
    # Build artifacts
    output_file: str = ""
    output_size: int = 0
    
    # Reproducibility
    reproducible: bool = False
    build_env_hash: str = ""


@dataclass
class GitInfo:
    """Git repository information."""
    
    commit_hash: str = ""
    commit_message: str = ""
    commit_author: str = ""
    commit_timestamp: str = ""
    
    branch: str = ""
    tag: str = ""
    
    dirty: bool = False
    status_hash: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "commit_hash": self.commit_hash,
            "commit_message": self.commit_message[:100] if self.commit_message else "",
            "commit_author": self.commit_author,
            "commit_timestamp": self.commit_timestamp,
            "branch": self.branch,
            "tag": self.tag,
            "dirty": self.dirty,
        }


@dataclass
class DependencyInfo:
    """Dependency information."""
    
    name: str
    version: str
    license: str = ""
    
    # For firmware: libraries, SDKs
    source: str = ""  # internal, third_party, external
    url: str = ""


@dataclass
class SBOMEntry:
    """SBOM entry (SPDX format)."""
    
    # SPDX fields
    spdx_id: str
    name: str
    version: str = ""
    supplier: str = ""
    download_location: str = ""
    
    # License
    license_concluded: str = ""
    license_declared: str = ""
    
    # Checksum
    checksum: str = ""  # SHA256
    
    # Relationship
    relationship: str = "BUILD_DEPENDS_ON"
    
    def to_spdx(self) -> str:
        """Convert to SPDX tag-value format."""
        lines = [
            f"PackageName: {self.name}",
            f"SPDXID: SPDXRef-{self.spdx_id}",
            f"PackageVersion: {self.version}",
            f"PackageSupplier: {self.supplier}",
            f"PackageDownloadLocation: {self.download_location}",
            f"FilesAnalyzed: false",
            f"PackageVerificationCode: {self.checksum}",
            f"PackageLicenseConcluded: {self.license_concluded}",
            f"PackageLicenseDeclared: {self.license_declared}",
        ]
        return "\n".join(lines)


@dataclass
class CycloneDXComponent:
    """CycloneDX component."""
    
    type: str = "library"
    name: str = ""
    version: str = ""
    
    # Licensing
    licenses: list[dict[str, str]] = field(default_factory=list)
    
    # PURL
    purl: str = ""
    
    # Hashes
    hashes: list[dict[str, str]] = field(default_factory=list)
    
    # Evidence
    evidence: dict[str, Any] = field(default_factory=dict)
    
    def to_cyclonedx(self) -> dict[str, Any]:
        """Convert to CycloneDX JSON format."""
        return {
            "type": self.type,
            "name": self.name,
            "version": self.version,
            "licenses": self.licenses,
            "purl": self.purl,
            "hashes": self.hashes,
            "evidence": self.evidence,
        }


@dataclass
class VulnerabilityReference:
    """CVE/Vulnerability reference."""
    
    cve_id: str = ""
    cwe_id: str = ""
    severity: str = ""  # CRITICAL, HIGH, MEDIUM, LOW
    cvss_score: float = 0.0
    
    description: str = ""
    affected_versions: str = ""
    fixed_versions: str = ""


@dataclass
class FirmwareArtifact:
    """Complete firmware artifact manifest.
    
    This is the authoritative record of what was built and deployed.
    Essential for:
    - Audit trails
    - Security compliance
    - Reproducibility verification
    - CVE mapping
    """
    
    # Identity
    artifact_id: str = ""
    name: str = ""
    
    # Version
    semantic_version: str = ""  # MAJOR.MINOR.PATCH
    build_number: str = ""
    
    # Content
    firmware_hash: str = ""  # SHA256 of firmware binary
    firmware_size: int = 0
    
    # Build
    build: BuildInfo = field(default_factory=BuildInfo)
    git: GitInfo = field(default_factory=GitInfo)
    
    # Dependencies
    dependencies: list[DependencyInfo] = field(default_factory=list)
    
    # SBOM
    sbom_spdx: str = ""
    sbom_cyclonedx: list[dict[str, Any]] = field(default_factory=list)
    
    # Vulnerabilities
    vulnerabilities: list[VulnerabilityReference] = field(default_factory=list)
    
    # Target info
    target_name: str = ""
    target_chip: str = ""
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    exported_at: datetime | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "artifact_id": self.artifact_id,
            "name": self.name,
            "semantic_version": self.semantic_version,
            "build_number": self.build_number,
            "firmware_hash": self.firmware_hash,
            "firmware_size": self.firmware_size,
            "build": {
                "build_timestamp": self.build.build_timestamp,
                "compiler": self.build.compiler,
                "compiler_version": self.build.compiler_version,
                "compiler_flags": self.build.compiler_flags,
                "optimization_level": self.build.optimization_level,
                "reproducible": self.build.reproducible,
            },
            "git": self.git.to_dict(),
            "dependencies": [
                {
                    "name": d.name,
                    "version": d.version,
                    "license": d.license,
                }
                for d in self.dependencies
            ],
            "target": {
                "name": self.target_name,
                "chip": self.target_chip,
            },
            "created_at": self.created_at.isoformat(),
        }
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)
    
    def to_spdx(self) -> str:
        """Export as SPDX tag-value document."""
        lines = [
            "SPDXVersion: SPDX-2.3",
            f"DataLicense: CC0-1.0",
            f"SPDXID: SPDXRef-DOCUMENT",
            f"DocumentName: {self.name}",
            f"DocumentNamespace: https://ai-support.local/artifacts/{self.artifact_id}",
            "",
            "# Creation Info",
            "Creator: Tool: AI-Support-Firmware-Analyzer",
            f"Created: {self.created_at.isoformat()}",
            "",
            "# Package",
            f"PackageName: {self.name}",
            f"SPDXID: SPDXRef-Package-{self.name}",
            f"PackageVersion: {self.semantic_version}",
            f"PackageDownloadLocation: NOASSERTION",
            f"FilesAnalyzed: true",
            f"PackageVerificationCode: {self.firmware_hash} (excludes does not match)",
            f"PackageLicenseConcluded: NOASSERTION",
            f"PackageLicenseDeclared: NOASSERTION",
            "",
            "# Build Information",
            f"BuildCompiler: {self.build.compiler}",
            f"BuildCompilerVersion: {self.build.compiler_version}",
            f"BuildFlags: {' '.join(self.build.compiler_flags)}",
            f"BuildTimestamp: {self.build.build_timestamp}",
            "",
            "# Git Information",
            f"GitCommit: {self.git.commit_hash}",
            f"GitBranch: {self.git.branch}",
            f"GitDirty: {str(self.git.dirty).upper()}",
        ]
        
        # Add dependencies
        if self.dependencies:
            lines.append("")
            lines.append("# Dependencies")
            for dep in self.dependencies:
                lines.append(f"PackageName: {dep.name}")
                lines.append(f"SPDXID: SPDXRef-Package-{dep.name}")
                lines.append(f"PackageVersion: {dep.version}")
                lines.append(f"PackageLicenseConcluded: {dep.license}")
                lines.append(f"Relationship: SPDXRef-Package-{self.name} BUILD_DEPENDS_ON SPDXRef-Package-{dep.name}")
                lines.append("")
        
        return "\n".join(lines)
    
    def to_cyclonedx(self) -> dict[str, Any]:
        """Export as CycloneDX JSON."""
        components = [
            {
                "type": "firmware",
                "name": self.name,
                "version": self.semantic_version,
                "hashes": [
                    {"alg": "SHA-256", "content": self.firmware_hash},
                ],
                "properties": [
                    {"name": "build:compiler", "value": self.build.compiler},
                    {"name": "build:compiler_version", "value": self.build.compiler_version},
                    {"name": "build:timestamp", "value": self.build.build_timestamp},
                    {"name": "git:commit", "value": self.git.commit_hash},
                    {"name": "git:branch", "value": self.git.branch},
                ],
            }
        ]
        
        # Add dependencies as components
        for dep in self.dependencies:
            components.append({
                "type": "library",
                "name": dep.name,
                "version": dep.version,
                "licenses": [{"license": {"name": dep.license}}] if dep.license else [],
                "purl": dep.url,
            })
        
        return {
            "bomFormat": "CycloneDX",
            "specVersion": "1.5",
            "version": 1,
            "metadata": {
                "timestamp": self.created_at.isoformat(),
                "tools": [{"name": "AI-Support-Firmware-Analyzer", "version": "1.0"}],
            },
            "components": components,
        }


@dataclass
class ArtifactManifestBuilder:
    """Builds artifact manifest from firmware.
    
    Extracts metadata from:
    - ELF file
    - Build system
    - Git repository
    - Dependency files
    """
    
    @staticmethod
    async def from_firmware(
        firmware_path: str,
        name: str = "",
        version: str = "",
        target_name: str = "",
        target_chip: str = "",
    ) -> FirmwareArtifact:
        """Build manifest from firmware binary.
        
        Args:
            firmware_path: Path to firmware binary
            name: Artifact name
            version: Semantic version
            target_name: Target name
            target_chip: Target chip model
        
        Returns:
            FirmwareArtifact
        """
        artifact = FirmwareArtifact(
            artifact_id=hashlib.sha256(str(datetime.now().timestamp()).encode()).hexdigest()[:16],
            name=name or os.path.basename(firmware_path),
            semantic_version=version,
            target_name=target_name,
            target_chip=target_chip,
        )
        
        # Calculate firmware hash
        if os.path.exists(firmware_path):
            with open(firmware_path, "rb") as f:
                data = f.read()
                artifact.firmware_hash = hashlib.sha256(data).hexdigest()
                artifact.firmware_size = len(data)
        
        # Get build info
        artifact.build = await ArtifactManifestBuilder._get_build_info(firmware_path)
        
        # Get git info
        artifact.git = ArtifactManifestBuilder._get_git_info()
        
        return artifact
    
    @staticmethod
    async def from_elf(
        elf_path: str,
        name: str = "",
        version: str = "",
        target_name: str = "",
        target_chip: str = "",
    ) -> FirmwareArtifact:
        """Build manifest from ELF file.
        
        Extracts additional metadata from ELF.
        """
        artifact = FirmwareArtifact(
            artifact_id=hashlib.sha256(str(datetime.now().timestamp()).encode()).hexdigest()[:16],
            name=name or os.path.basename(elf_path),
            semantic_version=version,
            target_name=target_name,
            target_chip=target_chip,
        )
        
        # Parse ELF for metadata
        try:
            from elftools.elf.elffile import ELFFile
            
            with open(elf_path, "rb") as f:
                elf = ELFFile(f)
                
                # Get build info from ELF notes
                for section in elf.iter_sections():
                    if section.name == ".comment":
                        pass  # Parse build comments
        except ImportError:
            logger.warning("pyelftools_not_installed")
        
        # Calculate firmware hash (from binary output)
        bin_path = elf_path.replace(".elf", ".bin")
        if os.path.exists(bin_path):
            with open(bin_path, "rb") as f:
                data = f.read()
                artifact.firmware_hash = hashlib.sha256(data).hexdigest()
                artifact.firmware_size = len(data)
        
        # Get build info
        artifact.build = await ArtifactManifestBuilder._get_build_info(elf_path)
        
        # Get git info
        artifact.git = ArtifactManifestBuilder._get_git_info()
        
        return artifact
    
    @staticmethod
    async def _get_build_info(source_path: str) -> BuildInfo:
        """Get build information."""
        info = BuildInfo(
            build_timestamp=datetime.now().isoformat(),
            build_host=os.environ.get("HOSTNAME", "unknown"),
            build_user=os.environ.get("USER", "unknown"),
        )
        
        # Try to extract from build artifacts
        # Look for .d files or build logs
        build_info_file = source_path + ".build_info"
        if os.path.exists(build_info_file):
            try:
                with open(build_info_file, "r") as f:
                    data = json.load(f)
                    info.compiler = data.get("CC", "gcc")
                    info.compiler_flags = data.get("CFLAGS", "").split()
                    info.optimization_level = data.get("OPT", "-Os")
            except Exception:
                pass
        
        return info
    
    @staticmethod
    def _get_git_info() -> GitInfo:
        """Get git repository information."""
        info = GitInfo()
        
        try:
            # Get commit hash
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                info.commit_hash = result.stdout.strip()
            
            # Get branch
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                info.branch = result.stdout.strip()
            
            # Get commit message (first line)
            result = subprocess.run(
                ["git", "log", "-1", "--pretty=%B"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                info.commit_message = result.stdout.strip().split("\n")[0]
            
            # Get author
            result = subprocess.run(
                ["git", "log", "-1", "--pretty=%ae"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                info.commit_author = result.stdout.strip()
            
            # Check if dirty
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                info.dirty = len(result.stdout.strip()) > 0
            
            # Get tag if any
            result = subprocess.run(
                ["git", "describe", "--tags", "--exact-match"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                info.tag = result.stdout.strip()
            
        except Exception as e:
            logger.warning(f"Failed to get git info: {e}")
        
        return info
    
    @staticmethod
    def add_dependency(
        artifact: FirmwareArtifact,
        name: str,
        version: str,
        license: str = "",
        source: str = "internal",
    ) -> None:
        """Add dependency to artifact."""
        artifact.dependencies.append(DependencyInfo(
            name=name,
            version=version,
            license=license,
            source=source,
        ))
    
    @staticmethod
    def add_vulnerability(
        artifact: FirmwareArtifact,
        cve_id: str,
        severity: str = "",
        description: str = "",
    ) -> None:
        """Add vulnerability reference to artifact."""
        artifact.vulnerabilities.append(VulnerabilityReference(
            cve_id=cve_id,
            severity=severity,
            description=description,
        ))


@dataclass
class ReproducibleBuildVerifier:
    """Verifies reproducible builds.
    
    Compares build artifacts to ensure determinism.
    """
    
    @staticmethod
    async def verify_reproducibility(
        artifact1_path: str,
        artifact2_path: str,
    ) -> dict[str, Any]:
        """Verify two builds are reproducible.
        
        Args:
            artifact1_path: First firmware artifact
            artifact2_path: Second firmware artifact
        
        Returns:
            Verification result
        """
        result = {
            "reproducible": False,
            "artifact1_hash": "",
            "artifact2_hash": "",
            "differences": [],
        }
        
        # Calculate hashes
        for path, key in [(artifact1_path, "artifact1_hash"), (artifact2_path, "artifact2_hash")]:
            if os.path.exists(path):
                with open(path, "rb") as f:
                    result[key] = hashlib.sha256(f.read()).hexdigest()
        
        # Compare
        result["reproducible"] = result["artifact1_hash"] == result["artifact2_hash"]
        
        return result
    
    @staticmethod
    def generate_build_env_hash() -> str:
        """Generate hash of build environment.
        
        Includes compiler version, flags, timestamps, etc.
        """
        env_data = {
            "python_version": os.sys.version,
            "platform": os.sys.platform,
        }
        
        # Try to get gcc version
        try:
            result = subprocess.run(
                ["gcc", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                env_data["gcc_version"] = result.stdout.split("\n")[0]
        except Exception:
            pass
        
        # Try to get clang version
        try:
            result = subprocess.run(
                ["clang", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                env_data["clang_version"] = result.stdout.split("\n")[0]
        except Exception:
            pass
        
        env_str = json.dumps(env_data, sort_keys=True)
        return hashlib.sha256(env_str.encode()).hexdigest()


@dataclass
class ArtifactRegistry:
    """Registry of firmware artifacts.
    
    Maintains catalog of all built artifacts for:
    - Compliance auditing
    - CVE tracking
    - Rollback identification
    """
    
    registry_path: str
    
    _artifacts: dict[str, FirmwareArtifact] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Load existing registry."""
        self._load()
    
    def _load(self) -> None:
        """Load registry from disk."""
        if os.path.exists(self.registry_path):
            try:
                with open(self.registry_path, "r") as f:
                    data = json.load(f)
                    for item in data.get("artifacts", []):
                        artifact = FirmwareArtifact(
                            artifact_id=item["artifact_id"],
                            name=item["name"],
                            semantic_version=item["semantic_version"],
                            firmware_hash=item["firmware_hash"],
                        )
                        self._artifacts[artifact.artifact_id] = artifact
            except Exception as e:
                logger.error("registry_load_error", error=str(e))
    
    def _save(self) -> None:
        """Save registry to disk."""
        data = {
            "version": "1.0",
            "updated_at": datetime.now().isoformat(),
            "artifacts": [a.to_dict() for a in self._artifacts.values()],
        }
        
        with open(self.registry_path, "w") as f:
            json.dump(data, f, indent=2)
    
    def register(self, artifact: FirmwareArtifact) -> None:
        """Register new artifact."""
        self._artifacts[artifact.artifact_id] = artifact
        self._save()
    
    def get(self, artifact_id: str) -> FirmwareArtifact | None:
        """Get artifact by ID."""
        return self._artifacts.get(artifact_id)
    
    def get_by_hash(self, firmware_hash: str) -> FirmwareArtifact | None:
        """Get artifact by firmware hash."""
        for artifact in self._artifacts.values():
            if artifact.firmware_hash == firmware_hash:
                return artifact
        return None
    
    def list_by_version(self, version: str) -> list[FirmwareArtifact]:
        """List artifacts by version."""
        return [
            a for a in self._artifacts.values()
            if a.semantic_version == version
        ]
    
    def find_vulnerable(self) -> list[tuple[FirmwareArtifact, VulnerabilityReference]]:
        """Find artifacts with known vulnerabilities."""
        vulnerable = []
        
        for artifact in self._artifacts.values():
            for vuln in artifact.vulnerabilities:
                vulnerable.append((artifact, vuln))
        
        return vulnerable

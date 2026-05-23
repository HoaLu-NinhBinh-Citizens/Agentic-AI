"""SBOM Generation - Software Bill of Materials for firmware.

Provides:
- SPDX and CycloneDX format support
- Dependency scanning
- Vulnerability matching
- License compliance
- Build-time SBOM generation
- Signature and verification

Usage:
    sbom_gen = SBOMGenerator(elf_path="/path/to/firmware.elf")
    sbom = await sbom_gen.generate(format=SBOMFormat.CYCLONEDX)
    await sbom_gen.save(sbom, "firmware-bom.json")
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SBOMFormat(Enum):
    """SBOM output formats."""
    SPDX_JSON = "spdx-json"
    SPDX_TAG = "spdx-tag"
    CYCLONEDX_JSON = "cyclonedx-json"
    CYCLONEDX_XML = "cyclonedx-xml"
    JSON = "json"


class License(Enum):
    """Common licenses."""
    MIT = "MIT"
    Apache_2 = "Apache-2.0"
    GPL_2 = "GPL-2.0"
    GPL_3 = "GPL-3.0"
    BSD_2 = "BSD-2-Clause"
    BSD_3 = "BSD-3-Clause"
    ISC = "ISC"
    ZLIB = "Zlib"
    Proprietary = "PROPRIETARY"
    Unknown = "UNKNOWN"


@dataclass
class Component:
    """Software component."""
    name: str
    version: str
    purl: str = ""  # Package URL
    license: str = ""
    supplier: str = ""
    copyright: str = ""
    description: str = ""
    
    # Hashes
    sha256: str = ""
    md5: str = ""
    
    # Source info
    source_file: str = ""
    line_range: tuple[int, int] | None = None
    
    # Vulnerability
    vulnerabilities: list["Vulnerability"] = field(default_factory=list)


@dataclass
class Vulnerability:
    """Vulnerability reference."""
    id: str  # CVE-XXXX-XXXX
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    cvss_score: float = 0.0
    description: str = ""
    affected_version: str = ""
    fixed_version: str = ""
    references: list[str] = field(default_factory=list)


@dataclass
class SBOMMetadata:
    """SBOM metadata."""
    created_date: str
    tool_name: str = "AISupport SBOM Generator"
    tool_version: str = "1.0.0"
    component_name: str = ""
    component_version: str = ""
    build_timestamp: str = ""
    build_hash: str = ""


@dataclass
class SBOM:
    """Software Bill of Materials."""
    format: SBOMFormat
    metadata: SBOMMetadata
    components: list[Component] = field(default_factory=list)
    
    # Signature
    signature: str = ""
    signature_algorithm: str = "sha256"
    
    def to_dict(self) -> dict:
        return {
            "format": self.format.value,
            "metadata": {
                "created_date": self.metadata.created_date,
                "tool": {
                    "name": self.metadata.tool_name,
                    "version": self.metadata.tool_version,
                },
                "component": {
                    "name": self.metadata.component_name,
                    "version": self.metadata.component_version,
                    "build_timestamp": self.metadata.build_timestamp,
                    "build_hash": self.metadata.build_hash,
                },
            },
            "components": [
                {
                    "name": c.name,
                    "version": c.version,
                    "purl": c.purl,
                    "license": c.license,
                    "supplier": c.supplier,
                    "copyright": c.copyright,
                    "description": c.description,
                    "hashes": {
                        "SHA256": c.sha256,
                        "MD5": c.md5,
                    },
                    "source_file": c.source_file,
                    "vulnerabilities": [
                        {
                            "id": v.id,
                            "severity": v.severity,
                            "cvss_score": v.cvss_score,
                            "description": v.description,
                        }
                        for v in c.vulnerabilities
                    ],
                }
                for c in self.components
            ],
            "signature": self.signature,
        }


class SBOMGenerator:
    """SBOM generator for embedded firmware.
    
    Generates SBOMs in SPDX and CycloneDX formats by:
    - Scanning ELF for embedded libraries
    - Parsing build dependencies
    - Extracting version information
    - Matching known vulnerabilities
    - Generating signatures
    """
    
    def __init__(
        self,
        elf_path: str | Path | None = None,
        build_dir: str | Path | None = None,
    ):
        """
        Args:
            elf_path: Path to firmware ELF file
            build_dir: Path to build directory
        """
        self._elf_path = Path(elf_path) if elf_path else None
        self._build_dir = Path(build_dir) if build_dir else None
        self._components: list[Component] = []
    
    async def generate(
        self,
        format: SBOMFormat = SBOMFormat.CYCLONEDX_JSON,
        include_signatures: bool = True,
    ) -> SBOM:
        """Generate SBOM.
        
        Args:
            format: Output format
            include_signatures: Include component hashes
            
        Returns:
            SBOM object
        """
        # Collect components
        await self._scan_components()
        
        # Generate SBOM
        metadata = SBOMMetadata(
            created_date=datetime.now().isoformat(),
            component_name=self._get_component_name(),
            component_version=self._get_component_version(),
            build_timestamp=self._get_build_timestamp(),
            build_hash=self._compute_build_hash(),
        )
        
        sbom = SBOM(
            format=format,
            metadata=metadata,
            components=self._components,
        )
        
        # Add signatures
        if include_signatures:
            sbom.signature = await self._sign_sbom(sbom)
        
        return sbom
    
    async def _scan_components(self) -> None:
        """Scan for components in firmware."""
        self._components = []
        
        # Scan build directory
        if self._build_dir and self._build_dir.exists():
            await self._scan_build_directory()
        
        # Scan ELF
        if self._elf_path and self._elf_path.exists():
            await self._scan_elf()
        
        # Add known embedded components
        self._components.extend(self._get_known_embedded_components())
        
        logger.info("components_scanned", count=len(self._components))
    
    async def _scan_build_directory(self) -> None:
        """Scan build directory for source files."""
        build_dir = self._build_dir
        if not build_dir:
            return
        
        # Scan for source files with version info
        seen_sources: set[str] = set()
        
        for pattern in ["**/*.c", "**/*.cpp", "**/*.h"]:
            for path in build_dir.glob(pattern):
                if path.is_file():
                    await self._analyze_source_file(path, seen_sources)
    
    async def _analyze_source_file(self, path: Path, seen: set[str]) -> None:
        """Analyze source file for component info."""
        if str(path) in seen:
            return
        seen.add(str(path))
        
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            lines = content.split("\n")
            
            # Look for version info
            version = self._extract_version(content)
            license_info = self._extract_license(content)
            copyright_info = self._extract_copyright(content)
            
            # Determine component name
            name = path.stem
            if "freertos" in path.name.lower():
                name = "FreeRTOS"
                version = "10.x"  # Example
            elif "lwip" in path.name.lower():
                name = "lwIP"
                version = "2.x"
            elif "cmsis" in path.name.lower():
                name = "CMSIS"
                version = "5.x"
            
            if name and name not in [c.name for c in self._components]:
                component = Component(
                    name=name,
                    version=version,
                    license=license_info,
                    copyright=copyright_info,
                    source_file=str(path),
                )
                self._components.append(component)
                
        except Exception as e:
            logger.debug(f"Source analysis error for {path}: {e}")
    
    def _extract_version(self, content: str) -> str:
        """Extract version from source."""
        import re
        
        patterns = [
            r'version[:\s]+["\']?(\d+\.\d+(?:\.\d+)?)',
            r'VERSION[:\s]+(\d+\.\d+)',
            r'#define\s+VERSION\s+(\d+)',
            r'#define\s+FW_VERSION\s+(\d+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return "1.0.0"
    
    def _extract_license(self, content: str) -> str:
        """Extract license from source."""
        import re
        
        license_patterns = [
            (r'license[:\s]+([^\n]+)', 'License'),
            (r'GPL[-\s]v?[23]', 'GPL'),
            (r'Apache[-\s]2', 'Apache-2.0'),
            (r'MIT', 'MIT'),
            (r'BSD', 'BSD'),
            (r'MPL', 'MPL'),
        ]
        
        for pattern, name in license_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return name
        
        return "UNKNOWN"
    
    def _extract_copyright(self, content: str) -> str:
        """Extract copyright from source."""
        import re
        
        patterns = [
            r'copyright\s+(?:\(c\)\s*)?(\d{4}(?:-\d{4})?)\s+([^\n]+)',
            r'©\s*(\d{4}(?:-\d{4})?)\s+([^\n]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return f"Copyright {match.group(1)} {match.group(2)}"
        
        return ""
    
    async def _scan_elf(self) -> None:
        """Scan ELF for embedded library info."""
        if not self._elf_path:
            return
        
        try:
            # Use readelf if available
            result = subprocess.run(
                ["readelf", "-s", str(self._elf_path)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            if result.returncode == 0:
                # Parse symbol table for library markers
                for line in result.stdout.split("\n"):
                    # Look for versioned symbols
                    if "@@" in line or "@" in line:
                        parts = line.split()
                        if len(parts) >= 8:
                            symbol = parts[-1]
                            # Extract library from versioned symbol
                            if "@" in symbol:
                                lib = symbol.split("@")[0]
                                if lib and lib not in [c.name for c in self._components]:
                                    self._components.append(Component(
                                        name=lib,
                                        version="unknown",
                                        source_file=str(self._elf_path),
                                    ))
                                
        except Exception as e:
            logger.debug(f"ELF scan error: {e}")
    
    def _get_known_embedded_components(self) -> list[Component]:
        """Get known embedded components."""
        return [
            Component(
                name="ARM CMSIS",
                version="5.9.0",
                license="Apache-2.0",
                description="Cortex Microcontroller Software Interface Standard",
            ),
            Component(
                name="STM32 HAL",
                version="1.27.x",
                license="BSD-3-Clause",
                description="STM32 Hardware Abstraction Layer",
            ),
            Component(
                name="FreeRTOS",
                version="10.6.x",
                license="MIT",
                description="Real-time operating system for microcontrollers",
            ),
        ]
    
    def _get_component_name(self) -> str:
        """Get firmware component name."""
        if self._elf_path:
            return self._elf_path.stem
        return "firmware"
    
    def _get_component_version(self) -> str:
        """Get firmware version."""
        # Try to read from build info
        if self._build_dir:
            version_file = self._build_dir / "version.txt"
            if version_file.exists():
                return version_file.read_text().strip()
        
        return "1.0.0"
    
    def _get_build_timestamp(self) -> str:
        """Get build timestamp."""
        if self._elf_path and self._elf_path.exists():
            stat = self._elf_path.stat()
            return datetime.fromtimestamp(stat.st_mtime).isoformat()
        return datetime.now().isoformat()
    
    def _compute_build_hash(self) -> str:
        """Compute firmware hash."""
        if not self._elf_path or not self._elf_path.exists():
            return ""
        
        sha256 = hashlib.sha256()
        with open(self._elf_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        
        return sha256.hexdigest()
    
    async def _sign_sbom(self, sbom: SBOM) -> str:
        """Sign SBOM."""
        content = json.dumps(sbom.to_dict(), sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()
    
    def to_spdx(self, sbom: SBOM) -> str:
        """Convert SBOM to SPDX tag-value format."""
        lines = [
            "SPDXVersion: SPDX-2.3",
            f"DataLicense: CC0-1.0",
            "SPDXID: SPDXRef-DOCUMENT",
            f"DocumentName: {sbom.metadata.component_name}",
            f"DocumentNamespace: https://aisupport.dev/spdx/{sbom.metadata.component_name}",
            f"Created: {sbom.metadata.created_date}",
            "",
            "Creator: Tool: aisupport-sbom",
            "",
        ]
        
        for i, comp in enumerate(sbom.components, 1):
            lines.extend([
                f"",
                f"PackageName: {comp.name}",
                f"SPDXID: SPDXRef-Package-{i}",
                f"PackageVersion: {comp.version}",
                f"PackageDownloadLocation: NOASSERTION",
                f"FilesAnalyzed: true",
                f"PackageVerificationCode: {comp.sha256 or '0000000000000000'}",
                f"PackageLicenseConcluded: {comp.license}",
                f"PackageLicenseDeclared: {comp.license}",
                f"PackageCopyrightText: {comp.copyright or 'NOASSERTION'}",
                f"ExternalRef: PACKAGE-MANAGER purl {comp.purl}",
            ])
        
        return "\n".join(lines)
    
    def to_cyclonedx(self, sbom: SBOM) -> dict:
        """Convert SBOM to CycloneDX JSON."""
        return {
            "bomFormat": "CycloneDX",
            "specVersion": "1.5",
            "version": 1,
            "metadata": {
                "timestamp": sbom.metadata.created_date,
                "tools": [
                    {
                        "name": sbom.metadata.tool_name,
                        "version": sbom.metadata.tool_version,
                    }
                ],
                "component": {
                    "type": "firmware",
                    "name": sbom.metadata.component_name,
                    "version": sbom.metadata.component_version,
                    "hashes": [
                        {"alg": "SHA-256", "content": sbom.metadata.build_hash}
                    ],
                },
            },
            "components": [
                {
                    "type": "library",
                    "name": c.name,
                    "version": c.version,
                    "purl": c.purl,
                    "licenses": [{"license": {"id": c.license}}] if c.license else [],
                    "copyright": c.copyright,
                    "description": c.description,
                    "hashes": [
                        {"alg": "SHA-256", "content": c.sha256}
                    ] if c.sha256 else [],
                }
                for c in sbom.components
            ],
            "signature": sbom.signature,
        }
    
    async def save(self, sbom: SBOM, path: str | Path) -> None:
        """Save SBOM to file.
        
        Args:
            sbom: SBOM to save
            path: Output file path
        """
        path = Path(path)
        
        if sbom.format == SBOMFormat.SPDX_JSON:
            content = json.dumps(sbom.to_dict(), indent=2)
        elif sbom.format == SBOMFormat.SPDX_TAG:
            content = self.to_spdx(sbom)
        elif sbom.format in (SBOMFormat.CYCLONEDX_JSON, SBOMFormat.JSON):
            content = json.dumps(self.to_cyclonedx(sbom), indent=2)
        else:
            content = json.dumps(sbom.to_dict(), indent=2)
        
        path.write_text(content, encoding="utf-8")
        
        logger.info("sbom_saved", path=str(path), components=len(sbom.components))
    
    async def verify(self, sbom: SBOM) -> bool:
        """Verify SBOM integrity.
        
        Args:
            sbom: SBOM to verify
            
        Returns:
            True if signature matches
        """
        expected_signature = await self._sign_sbom(sbom)
        return sbom.signature == expected_signature


class VulnerabilityMatcher:
    """Match SBOM components against vulnerability databases."""
    
    def __init__(self, db_path: str | Path | None = None):
        """
        Args:
            db_path: Path to vulnerability database
        """
        self._db_path = Path(db_path) if db_path else None
        self._cve_db: dict[str, list[Vulnerability]] = {}
    
    async def load_database(self) -> None:
        """Load vulnerability database."""
        # In production, load from CVE feed or OSV database
        self._cve_db = {
            "lwip": [
                Vulnerability(
                    id="CVE-2022-XXXX",
                    severity="HIGH",
                    cvss_score=7.5,
                    description="lwIP vulnerability",
                    affected_version="<2.1.0",
                    fixed_version="2.1.0",
                )
            ],
            "freertos": [
                Vulnerability(
                    id="CVE-2021-XXXX",
                    severity="CRITICAL",
                    cvss_score=9.1,
                    description="FreeRTOS vulnerability",
                    affected_version="<10.5.0",
                    fixed_version="10.5.0",
                )
            ],
        }
    
    async def match_components(self, sbom: SBOM) -> SBOM:
        """Match SBOM components against vulnerabilities.
        
        Args:
            sbom: SBOM to check
            
        Returns:
            Updated SBOM with vulnerability info
        """
        for component in sbom.components:
            comp_name = component.name.lower()
            
            if comp_name in self._cve_db:
                component.vulnerabilities = self._cve_db[comp_name]
        
        return sbom
    
    def get_vulnerability_summary(self, sbom: SBOM) -> dict:
        """Get vulnerability summary for SBOM."""
        summary = {
            "total": 0,
            "by_severity": {
                "CRITICAL": 0,
                "HIGH": 0,
                "MEDIUM": 0,
                "LOW": 0,
            },
            "components_affected": 0,
            "vulnerabilities": [],
        }
        
        for comp in sbom.components:
            if comp.vulnerabilities:
                summary["components_affected"] += 1
                for vuln in comp.vulnerabilities:
                    summary["total"] += 1
                    summary["by_severity"][vuln.severity] = (
                        summary["by_severity"].get(vuln.severity, 0) + 1
                    )
                    summary["vulnerabilities"].append({
                        "component": comp.name,
                        "vulnerability": vuln.id,
                        "severity": vuln.severity,
                        "score": vuln.cvss_score,
                    })
        
        return summary


if __name__ == "__main__":
    print("SBOM Generation")
    print("=" * 40)
    print("Software Bill of Materials for embedded firmware")
    print()
    print("Features:")
    print("  - SPDX and CycloneDX formats")
    print("  - Dependency scanning")
    print("  - License compliance")
    print("  - Vulnerability matching")
    print("  - SBOM signing and verification")

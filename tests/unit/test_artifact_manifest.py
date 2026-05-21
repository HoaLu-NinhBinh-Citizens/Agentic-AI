"""Tests for Artifact Manifest - SBOM and metadata."""

import pytest
from datetime import datetime

from src.domain.hardware.flash.artifact_manifest import (
    BuildInfo,
    GitInfo,
    DependencyInfo,
    FirmwareArtifact,
    ArtifactManifestBuilder,
    ReproducibleBuildVerifier,
    ArtifactRegistry,
)


class TestBuildInfo:
    """Test BuildInfo dataclass."""
    
    def test_create_build_info(self):
        """Test creating build info."""
        info = BuildInfo(
            build_timestamp="2026-01-01T00:00:00",
            compiler="gcc",
            compiler_version="12.2.0",
            compiler_flags=["-Os", "-flto"],
        )
        
        assert info.compiler == "gcc"
        assert "-Os" in info.compiler_flags


class TestGitInfo:
    """Test GitInfo dataclass."""
    
    def test_create_git_info(self):
        """Test creating git info."""
        info = GitInfo(
            commit_hash="abc123def456",
            branch="main",
            tag="v1.0.0",
            dirty=False,
        )
        
        assert info.commit_hash == "abc123def456"
        assert info.branch == "main"
    
    def test_to_dict(self):
        """Test serialization to dict."""
        info = GitInfo(
            commit_hash="abc123",
            commit_message="feat: add feature",
            branch="develop",
        )
        
        data = info.to_dict()
        
        assert data["commit_hash"] == "abc123"
        assert data["branch"] == "develop"


class TestFirmwareArtifact:
    """Test FirmwareArtifact class."""
    
    def test_create_artifact(self):
        """Test creating firmware artifact."""
        artifact = FirmwareArtifact(
            artifact_id="test_001",
            name="test_firmware",
            semantic_version="1.0.0",
            firmware_hash="abc123",
            firmware_size=1024,
        )
        
        assert artifact.name == "test_firmware"
        assert artifact.semantic_version == "1.0.0"
    
    def test_to_dict(self):
        """Test serialization to dict."""
        artifact = FirmwareArtifact(
            artifact_id="test_001",
            name="firmware",
            semantic_version="2.0.0",
            firmware_hash="hash123",
        )
        
        data = artifact.to_dict()
        
        assert data["artifact_id"] == "test_001"
        assert data["name"] == "firmware"
        assert "build" in data
        assert "git" in data
    
    def test_to_spdx(self):
        """Test SPDX export."""
        artifact = FirmwareArtifact(
            artifact_id="test_001",
            name="test_fw",
            semantic_version="1.0.0",
            firmware_hash="abc123",
        )
        
        spdx = artifact.to_spdx()
        
        assert "SPDXVersion" in spdx
        assert "PackageName" in spdx
        assert "test_fw" in spdx
    
    def test_to_cyclonedx(self):
        """Test CycloneDX export."""
        artifact = FirmwareArtifact(
            artifact_id="test_001",
            name="test_fw",
            semantic_version="1.0.0",
            firmware_hash="abc123",
        )
        
        cbom = artifact.to_cyclonedx()
        
        assert "bomFormat" in cbom
        assert cbom["bomFormat"] == "CycloneDX"
        assert "components" in cbom


class TestArtifactManifestBuilder:
    """Test ArtifactManifestBuilder class."""
    
    def test_add_dependency(self):
        """Test adding dependency to artifact."""
        artifact = FirmwareArtifact(
            artifact_id="test",
            name="test",
        )
        
        ArtifactManifestBuilder.add_dependency(
            artifact,
            name="cmsis",
            version="5.9.0",
            license="Apache-2.0",
        )
        
        assert len(artifact.dependencies) == 1
        assert artifact.dependencies[0].name == "cmsis"
    
    def test_get_git_info(self):
        """Test getting git info."""
        info = ArtifactManifestBuilder._get_git_info()
        
        # Should return GitInfo even without git repo
        assert isinstance(info, GitInfo)


class TestReproducibleBuildVerifier:
    """Test ReproducibleBuildVerifier class."""
    
    def test_generate_build_env_hash(self):
        """Test generating build env hash."""
        hash1 = ReproducibleBuildVerifier.generate_build_env_hash()
        hash2 = ReproducibleBuildVerifier.generate_build_env_hash()
        
        # Same environment should produce same hash
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex


class TestArtifactRegistry:
    """Test ArtifactRegistry class."""
    
    @pytest.fixture
    def registry(self, tmp_path):
        """Create registry with temp path."""
        return ArtifactRegistry(
            registry_path=str(tmp_path / "registry.json")
        )
    
    def test_register_artifact(self, registry):
        """Test registering artifact."""
        artifact = FirmwareArtifact(
            artifact_id="test_001",
            name="firmware",
            semantic_version="1.0.0",
            firmware_hash="abc123",
        )
        
        registry.register(artifact)
        
        retrieved = registry.get("test_001")
        
        assert retrieved is not None
        assert retrieved.name == "firmware"
    
    def test_get_by_hash(self, registry):
        """Test getting artifact by hash."""
        artifact = FirmwareArtifact(
            artifact_id="test_002",
            name="firmware",
            firmware_hash="unique_hash_xyz",
        )
        
        registry.register(artifact)
        
        retrieved = registry.get_by_hash("unique_hash_xyz")
        
        assert retrieved is not None
        assert retrieved.artifact_id == "test_002"
    
    def test_list_by_version(self, registry):
        """Test listing artifacts by version."""
        registry.register(FirmwareArtifact(
            artifact_id="a",
            name="fw",
            semantic_version="1.0.0",
        ))
        registry.register(FirmwareArtifact(
            artifact_id="b",
            name="fw",
            semantic_version="2.0.0",
        ))
        registry.register(FirmwareArtifact(
            artifact_id="c",
            name="fw",
            semantic_version="1.0.0",
        ))
        
        v1_artifacts = registry.list_by_version("1.0.0")
        
        assert len(v1_artifacts) == 2

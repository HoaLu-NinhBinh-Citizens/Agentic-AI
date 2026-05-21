"""Tests for CRC Tree / Merkle Verification."""

import pytest
from src.domain.hardware.flash.crc_tree import (
    ChunkInfo,
    MerkleNode,
    VerificationTree,
    IncrementalVerifier,
    FirmwareManifest,
    DeltaVerifier,
)


class TestVerificationTree:
    """Test Merkle verification tree."""
    
    def test_build_tree_simple(self):
        """Test building tree with simple data."""
        tree = VerificationTree(chunk_size=16)
        data = b"A" * 64  # 4 chunks of 16 bytes
        
        root = tree.build(data)
        
        assert root is not None
        assert len(tree._chunks) == 4
        assert tree.root_hash != ""
    
    def test_build_tree_single_chunk(self):
        """Test building tree with single chunk."""
        tree = VerificationTree(chunk_size=16)
        data = b"X" * 16
        
        root = tree.build(data)
        
        assert len(tree._chunks) == 1
        assert tree.root_hash == tree._chunks[0].content_hash
    
    def test_chunk_content_hash(self):
        """Test chunk content hashing."""
        tree = VerificationTree(chunk_size=10)
        data = b"0123456789" * 3  # 30 bytes = 3 chunks
        
        tree.build(data)
        
        assert len(tree._chunks) == 3
        for chunk in tree._chunks:
            assert chunk.content_hash != ""
    
    def test_verify_chunk_success(self):
        """Test successful chunk verification."""
        tree = VerificationTree(chunk_size=16)
        data = b"F" * 64
        tree.build(data)
        
        # Verify with correct data
        result = tree.verify_chunk(0, b"F" * 16)
        assert result is True
        assert tree._chunks[0].verified is True
    
    def test_verify_chunk_failure(self):
        """Test failed chunk verification."""
        tree = VerificationTree(chunk_size=16)
        data = b"F" * 64
        tree.build(data)
        
        # Verify with wrong data
        result = tree.verify_chunk(0, b"X" * 16)
        assert result is False
    
    def test_get_proof(self):
        """Test getting Merkle proof."""
        tree = VerificationTree(chunk_size=16)
        data = b"A" * 64
        tree.build(data)
        
        proof = tree.get_proof(0)
        
        # Should have log2(n) proofs
        assert len(proof) == 2  # 4 chunks -> 2 levels
    
    def test_verify_proof(self):
        """Test verifying with proof."""
        tree = VerificationTree(chunk_size=16)
        data = b"T" * 64
        tree.build(data)
        
        proof = tree.get_proof(0)
        result = tree.verify_proof(0, proof)
        
        assert result is True
    
    def test_verify_proof_wrong_data(self):
        """Test proof verification with wrong data."""
        tree = VerificationTree(chunk_size=16)
        data = b"T" * 64
        tree.build(data)
        
        proof = tree.get_proof(0)
        
        # Verify with wrong chunk data
        tree._chunks[0].content_hash = "wrong_hash"
        result = tree.verify_proof(0, proof)
        
        assert result is False
    
    def test_tree_structure(self):
        """Test tree structure has correct levels."""
        tree = VerificationTree(chunk_size=16)
        data = b"A" * 64  # 4 chunks
        tree.build(data)
        
        # Level 0: 4 chunks
        assert len(tree._nodes[0]) == 4
        # Level 1: 2 parent nodes
        assert len(tree._nodes[1]) == 2
        # Level 2: 1 root node
        assert len(tree._nodes[2]) == 1


class TestIncrementalVerifier:
    """Test IncrementalVerifier class."""
    
    def test_build_from_firmware(self):
        """Test building verifier from firmware."""
        verifier = IncrementalVerifier()
        firmware = b"F" * 1024
        
        root = verifier.build_from_firmware(firmware, chunk_size=256)
        
        assert root != ""
        assert verifier.tree.root_hash == root
    
    def test_mark_verified(self):
        """Test marking chunk as verified."""
        verifier = IncrementalVerifier()
        firmware = b"X" * 512
        verifier.build_from_firmware(firmware, chunk_size=128)
        
        verifier.mark_verified(0)
        
        assert verifier.tree._chunks[0].verified is True
    
    def test_get_unverified_ranges(self):
        """Test getting unverified ranges."""
        verifier = IncrementalVerifier()
        firmware = b"X" * 512
        verifier.build_from_firmware(firmware, chunk_size=128)
        
        # Mark first chunk as verified
        verifier.mark_verified(0)
        
        ranges = verifier.get_unverified_ranges()
        
        # Should have 3 remaining chunks
        assert len(ranges) == 3
    
    def test_needs_verification(self):
        """Test needs_verification check."""
        verifier = IncrementalVerifier()
        firmware = b"X" * 256
        verifier.build_from_firmware(firmware, chunk_size=128)
        
        assert verifier.needs_verification() is True
        
        # Mark all verified
        for i in range(len(verifier.tree._chunks)):
            verifier.mark_verified(i)
        
        assert verifier.needs_verification() is False


class TestFirmwareManifest:
    """Test FirmwareManifest class."""
    
    def test_create_manifest(self):
        """Test creating manifest from firmware."""
        firmware = b"F" * 1024
        
        manifest = FirmwareManifest.from_firmware(
            firmware,
            chunk_size=256,
            version="1.0.0",
        )
        
        assert manifest.firmware_hash != ""
        assert manifest.root_hash != ""
        assert manifest.chunk_size == 256
        assert manifest.total_size == 1024
        assert manifest.version == "1.0.0"
        assert len(manifest.chunk_hashes) == 4
    
    def test_manifest_to_dict(self):
        """Test manifest serialization."""
        firmware = b"X" * 256
        
        manifest = FirmwareManifest.from_firmware(
            firmware,
            chunk_size=128,
        )
        
        data = manifest.to_dict()
        
        assert "firmware_hash" in data
        assert "root_hash" in data
        assert "chunk_hashes" in data
        assert len(data["chunk_hashes"]) == 2
    
    def test_manifest_export(self):
        """Test manifest export."""
        firmware = b"F" * 512
        
        manifest = FirmwareManifest.from_firmware(
            firmware,
            chunk_size=256,
        )
        
        exported = manifest.export_proofs()
        
        assert "firmware_hash" in exported
        assert "proofs" in exported


class TestDeltaVerifier:
    """Test DeltaVerifier class."""
    
    def test_add_base_firmware(self):
        """Test adding base firmware."""
        verifier = DeltaVerifier()
        base_firmware = b"A" * 512
        
        root = verifier.add_base_firmware(base_firmware, chunk_size=128)
        
        assert root != ""
        assert verifier.base_manifest is not None
    
    def test_verify_delta(self):
        """Test verifying delta chunks."""
        verifier = DeltaVerifier()
        base_firmware = b"A" * 512
        
        verifier.add_base_firmware(base_firmware, chunk_size=128)
        
        # Create delta with same data as base (to verify structure)
        delta = {
            0: b"A" * 128,
            1: b"A" * 128,
        }
        
        result = verifier.verify_delta(delta)
        
        assert "verified_chunks" in result
        assert result["verified_chunks"] == 2

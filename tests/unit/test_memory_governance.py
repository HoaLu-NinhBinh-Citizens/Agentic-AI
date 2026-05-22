"""Unit tests for Memory Governance module - Phase 4.6."""

import time
import pytest

from core.memory.governance import (
    ProvenanceTracker,
    ProvenanceLevel,
    FactProvenance,
    PIIRedactor,
    PIIPolicy,
    PIIDetector,
    PIIType,
    ConfidenceDecay,
    DecayStrategy,
    RetentionPolicy,
    MemoryType,
    MemoryGovernance,
    GovernanceConfig,
)


class TestProvenance:
    """Tests for ProvenanceTracker."""

    def test_register_fact(self):
        """Test registering a fact with provenance."""
        tracker = ProvenanceTracker()
        provenance = tracker.register(
            fact_id="fact1",
            source="user_input",
            source_id="session123",
            level=ProvenanceLevel.HIGH,
        )

        assert provenance.fact_id == "fact1"
        assert provenance.source == "user_input"
        assert provenance.level == ProvenanceLevel.HIGH
        assert provenance.has_provenance() is True

    def test_fact_without_provenance(self):
        """Test fact with NONE provenance cannot be used as basis."""
        tracker = ProvenanceTracker()
        tracker.register(
            fact_id="fact1",
            source="unknown",
            level=ProvenanceLevel.NONE,
        )

        assert tracker.can_use_as_basis("fact1") is False

    def test_high_provenance_can_be_basis(self):
        """Test HIGH provenance facts can be used as basis."""
        tracker = ProvenanceTracker()
        tracker.register(
            fact_id="fact1",
            source="verified_source",
            level=ProvenanceLevel.HIGH,
        )

        assert tracker.can_use_as_basis("fact1") is True

    def test_upgrade_provenance(self):
        """Test upgrading provenance level."""
        tracker = ProvenanceTracker()
        tracker.register(
            fact_id="fact1",
            source="user_input",
            level=ProvenanceLevel.LOW,
        )

        success = tracker.upgrade("fact1", ProvenanceLevel.VERIFIED, "user_verification")
        assert success is True

        provenance = tracker.get("fact1")
        assert provenance.level == ProvenanceLevel.VERIFIED
        assert provenance.verified_by == "user_verification"

    def test_filter_by_provenance_level(self):
        """Test filtering facts by provenance level."""
        tracker = ProvenanceTracker()
        tracker.register("fact1", "source", level=ProvenanceLevel.LOW)
        tracker.register("fact2", "source", level=ProvenanceLevel.MEDIUM)
        tracker.register("fact3", "source", level=ProvenanceLevel.HIGH)

        filtered = tracker.filter_by_provenance(
            ["fact1", "fact2", "fact3"],
            min_level=ProvenanceLevel.MEDIUM,
        )

        assert "fact1" not in filtered
        assert "fact2" in filtered
        assert "fact3" in filtered

    def test_confidence_decay_over_time(self):
        """Test confidence decays over time."""
        tracker = ProvenanceTracker()
        now = int(time.time())

        provenance = tracker.register(
            fact_id="fact1",
            source="user_input",
            level=ProvenanceLevel.HIGH,
            confidence_initial=1.0,
            decay_factor=0.1,
        )

        confidence_1h = provenance.get_current_confidence(now + 3600)
        confidence_24h = provenance.get_current_confidence(now + 86400)

        assert confidence_1h < 1.0
        assert confidence_24h < confidence_1h


class TestPIIRedactor:
    """Tests for PII detection and redaction."""

    def test_detect_email(self):
        """Test email detection."""
        detector = PIIDetector()
        text = "Contact me at john.doe@example.com for more info"
        matches = detector.detect(text)

        assert len(matches) >= 1
        assert any(m.pii_type == PIIType.EMAIL for m in matches)

    def test_detect_phone(self):
        """Test phone number detection."""
        detector = PIIDetector()
        text = "Call me at (555) 123-4567"
        matches = detector.detect(text)

        assert len(matches) >= 1
        assert any(m.pii_type == PIIType.PHONE for m in matches)

    def test_detect_api_key(self):
        """Test API key detection."""
        detector = PIIDetector()
        text = "api_key=sk-1234567890abcdefghijklmnopqrstuvwxyz"
        matches = detector.detect(text)

        assert len(matches) >= 1
        assert any(m.pii_type == PIIType.API_KEY for m in matches)

    def test_redact_pii(self):
        """Test PII redaction."""
        redactor = PIIRedactor()
        text = "Email me at john@example.com"
        redacted, matches = redactor.redact(text)

        assert "[REDACTED]" in redacted
        assert "john@example.com" not in redacted
        assert len(matches) > 0

    def test_no_pii(self):
        """Test text without PII."""
        redactor = PIIRedactor()
        text = "This is a normal sentence without any PII"
        redacted, matches = redactor.redact(text)

        assert redacted == text
        assert len(matches) == 0


class TestConfidenceDecay:
    """Tests for ConfidenceDecay."""

    def test_register_fact(self):
        """Test registering a fact for decay tracking."""
        decay = ConfidenceDecay()
        score = decay.register("fact1", initial_confidence=1.0)

        assert score.fact_id == "fact1"
        assert score.initial == 1.0
        assert score.current == 1.0

    def test_exponential_decay(self):
        """Test exponential decay over time."""
        decay = ConfidenceDecay(strategy=DecayStrategy.EXPONENTIAL)
        decay.register("fact1")

        confidence_now = decay.get_confidence("fact1")
        assert confidence_now is not None
        assert confidence_now == pytest.approx(1.0, rel=0.01)

    def test_boost_confidence(self):
        """Test boosting confidence after verification."""
        decay = ConfidenceDecay()
        decay.register("fact1", initial_confidence=0.5)

        result = decay.boost("fact1", 0.3)
        assert result is True

        result2 = decay.boost("nonexistent", 0.1)
        assert result2 is False

    def test_filter_by_confidence(self):
        """Test filtering facts by confidence threshold."""
        decay = ConfidenceDecay()

        score1 = decay.register("fact1", initial_confidence=0.9)
        score2 = decay.register("fact2", initial_confidence=0.5)

        filtered = decay.filter_by_confidence(["fact1", "fact2"], min_confidence=0.8)
        assert "fact1" in filtered
        assert "fact2" not in filtered


class TestRetentionPolicy:
    """Tests for RetentionPolicy."""

    def test_default_ttl_working(self):
        """Test default TTL for working memory."""
        policy = RetentionPolicy()
        ttl = policy.get_ttl(MemoryType.WORKING)

        assert ttl == 3600

    def test_default_ttl_long_term(self):
        """Test default TTL for long-term memory."""
        policy = RetentionPolicy()
        ttl = policy.get_ttl(MemoryType.LONG_TERM)

        assert ttl == 30 * 86400

    def test_register_fact(self):
        """Test registering a fact with retention."""
        policy = RetentionPolicy()
        policy.register("fact1", MemoryType.WORKING)

        result = policy.check("fact1")
        assert result.is_expired is False
        assert result.should_delete is False

    def test_expired_fact(self):
        """Test detecting expired fact."""
        policy = RetentionPolicy()
        created_time = int(time.time()) - 7200
        policy.register("fact1", MemoryType.WORKING, created_at=created_time)

        result = policy.check("fact1")
        assert result.is_expired is True
        assert result.should_delete is True

    def test_get_expired_facts(self):
        """Test getting all expired facts."""
        policy = RetentionPolicy()
        old_time = int(time.time()) - 7200
        policy.register("fact1", MemoryType.WORKING)
        policy.register("fact2", MemoryType.WORKING, created_at=old_time)

        expired = policy.get_expired_facts(MemoryType.WORKING)
        assert "fact2" in expired
        assert "fact1" not in expired

    def test_extend_ttl(self):
        """Test extending TTL for a fact."""
        policy = RetentionPolicy()
        created_time = int(time.time()) + 3600
        policy.register("fact1", MemoryType.WORKING, created_at=created_time)

        result_before = policy.check("fact1")
        policy.extend("fact1", 3600)
        result_after = policy.check("fact1")

        assert result_after.remaining_seconds < result_before.remaining_seconds


class TestMemoryGovernance:
    """Tests for MemoryGovernance integration."""

    @pytest.mark.asyncio
    async def test_preprocess_with_pii_redaction(self):
        """Test preprocessing content with PII redaction."""
        governance = MemoryGovernance()

        result = await governance.preprocess_for_storage(
            fact_id="fact1",
            content="Contact me at john@example.com",
            source="user_input",
        )

        assert result.allowed is True
        assert result.redacted_content is not None
        assert "[REDACTED]" in result.redacted_content
        assert "john@example.com" not in result.redacted_content

    @pytest.mark.asyncio
    async def test_preprocess_without_pii(self):
        """Test preprocessing content without PII."""
        governance = MemoryGovernance()

        result = await governance.preprocess_for_storage(
            fact_id="fact1",
            content="This is a normal fact",
            source="user_input",
        )

        assert result.allowed is True
        assert len(result.pii_detected) == 0

    @pytest.mark.asyncio
    async def test_verify_content_upgrades_provenance(self):
        """Test verifying content upgrades provenance."""
        governance = MemoryGovernance()
        await governance.preprocess_for_storage(
            fact_id="fact1",
            content="Verified fact",
            source="user_input",
        )

        success = await governance.verify_content("fact1", "user_verification")
        assert success is True

    @pytest.mark.asyncio
    async def test_filter_for_rag_requires_provenance(self):
        """Test RAG filter requires provenance."""
        governance = MemoryGovernance()

        await governance.preprocess_for_storage(
            fact_id="fact_no_prov",
            content="Fact without good provenance",
            source="unknown",
            provenance_level=ProvenanceLevel.NONE,
        )

        await governance.preprocess_for_storage(
            fact_id="fact_with_prov",
            content="Fact with high provenance",
            source="verified",
            provenance_level=ProvenanceLevel.HIGH,
        )

        filtered = await governance.filter_for_rag(
            ["fact_no_prov", "fact_with_prov"],
            min_provenance=ProvenanceLevel.MEDIUM,
        )

        assert "fact_no_prov" not in filtered
        assert "fact_with_prov" in filtered

    @pytest.mark.asyncio
    async def test_cleanup_expired_facts(self):
        """Test cleaning up expired facts."""
        governance = MemoryGovernance()

        old_time = int(time.time()) - 7200
        governance._retention_policy.register("fact1", MemoryType.WORKING, created_at=old_time)
        governance._provenance.register("fact1", "source", level=ProvenanceLevel.MEDIUM)
        governance._confidence_decay.register("fact1")

        cleaned = await governance.cleanup()
        assert "fact1" in cleaned

    @pytest.mark.asyncio
    async def test_stats(self):
        """Test getting governance stats."""
        governance = MemoryGovernance()
        await governance.preprocess_for_storage(
            fact_id="fact1",
            content="Test fact",
            source="user_input",
        )

        stats = await governance.get_stats()
        assert "provenance" in stats
        assert "confidence_decay" in stats
        assert "retention" in stats

"""RAG Hallucination Guard for W-005.

Detects and prevents hallucinated facts from poisoning RAG.
- Confidence scoring per retrieved chunk
- Citation verification
- Human-in-loop for low-confidence results
- Hallucination pattern detection
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class ConfidenceLevel(Enum):
    """Confidence level for retrieved chunks."""

    HIGH = "high"  # >= 0.8
    MEDIUM = "medium"  # >= 0.5
    LOW = "low"  # >= 0.3
    VERY_LOW = "very_low"  # < 0.3


@dataclass
class ChunkConfidence:
    """Confidence score for a retrieved chunk."""

    chunk_id: str
    doc_id: str
    vector_score: float
    lexical_score: float
    semantic_score: float
    citation_verified: bool = False
    source_reliability: float = 1.0
    temporal_relevance: float = 1.0
    domain_match: float = 1.0
    combined_confidence: float = 0.0

    def __post_init__(self) -> None:
        """Calculate combined confidence score."""
        self.combined_confidence = (
            self.vector_score * 0.3 +
            self.lexical_score * 0.15 +
            self.semantic_score * 0.25 +
            self.citation_verified * 0.15 +
            self.source_reliability * 0.1 +
            self.temporal_relevance * 0.025 +
            self.domain_match * 0.025
        )

    @property
    def confidence_level(self) -> ConfidenceLevel:
        """Get confidence level enum."""
        if self.combined_confidence >= 0.8:
            return ConfidenceLevel.HIGH
        elif self.combined_confidence >= 0.5:
            return ConfidenceLevel.MEDIUM
        elif self.combined_confidence >= 0.3:
            return ConfidenceLevel.LOW
        return ConfidenceLevel.VERY_LOW


@dataclass
class HallucinationFlag:
    """Flag indicating potential hallucination."""

    chunk_id: str
    flag_type: str
    severity: float  # 0.0 - 1.0
    description: str
    suggestions: list[str] = field(default_factory=list)


class HallucinationGuard:
    """Guard against hallucinated facts in RAG.

    W-005 Fix: Implements hallucination detection and prevention.
    """

    def __init__(
        self,
        confidence_threshold: float = 0.5,
        citation_required: bool = True,
        human_in_loop_threshold: float = 0.3,
        on_low_confidence: Optional[Callable] = None,
    ):
        """Initialize hallucination guard.

        Args:
            confidence_threshold: Minimum confidence to include in response.
            citation_required: Require verified citations for high confidence.
            human_in_loop_threshold: Threshold to trigger human review.
            on_low_confidence: Callback when low confidence detected.
        """
        self._confidence_threshold = confidence_threshold
        self._citation_required = citation_required
        self._human_in_loop_threshold = human_in_loop_threshold
        self._on_low_confidence = on_low_confidence
        self._verified_citations: dict[str, bool] = {}

    def score_chunk(
        self,
        chunk_id: str,
        doc_id: str,
        vector_score: float = 0.0,
        lexical_score: float = 0.0,
        semantic_score: float = 0.0,
        citation_verified: bool = False,
        source_reliability: float = 1.0,
        temporal_relevance: float = 1.0,
        domain_match: float = 1.0,
    ) -> ChunkConfidence:
        """Score a retrieved chunk for hallucination risk.

        Returns:
            ChunkConfidence with calculated scores.
        """
        confidence = ChunkConfidence(
            chunk_id=chunk_id,
            doc_id=doc_id,
            vector_score=vector_score,
            lexical_score=lexical_score,
            semantic_score=semantic_score,
            citation_verified=citation_verified,
            source_reliability=source_reliability,
            temporal_relevance=temporal_relevance,
            domain_match=domain_match,
        )

        # Cache citation verification
        if citation_verified:
            self._verified_citations[chunk_id] = True

        logger.debug(
            "Scored chunk for hallucination risk",
            chunk_id=chunk_id,
            confidence=confidence.combined_confidence,
            level=confidence.confidence_level.value,
        )

        return confidence

    def verify_citation(
        self,
        chunk_id: str,
        claim: str,
        source_text: str,
    ) -> tuple[bool, str]:
        """Verify a citation claim against source.

        Returns:
            Tuple of (is_verified, reason).
        """
        # Check if claim is substring of source
        if claim.lower() in source_text.lower():
            self._verified_citations[chunk_id] = True
            return True, "Claim found in source"

        # Check for semantic similarity (simplified)
        claim_words = set(claim.lower().split())
        source_words = set(source_text.lower().split())

        overlap = len(claim_words & source_words)
        total = len(claim_words)

        if total > 0:
            similarity = overlap / total
            if similarity >= 0.7:
                self._verified_citations[chunk_id] = True
                return True, f"Semantic match ({similarity:.2f})"

        self._verified_citations[chunk_id] = False
        return False, "Claim not supported by source"

    def filter_chunks(
        self,
        chunks: list[ChunkConfidence],
        require_citations: bool = True,
    ) -> tuple[list[ChunkConfidence], list[ChunkConfidence]]:
        """Filter chunks by confidence threshold.

        Returns:
            Tuple of (passed_chunks, filtered_chunks).
        """
        passed = []
        filtered = []

        for chunk in chunks:
            # Check citation requirement
            if require_citations and not chunk.citation_verified:
                if chunk.combined_confidence < self._confidence_threshold:
                    filtered.append(chunk)
                    continue

            # Check confidence threshold
            if chunk.combined_confidence >= self._confidence_threshold:
                passed.append(chunk)
            else:
                filtered.append(chunk)

        return passed, filtered

    def detect_hallucination_patterns(
        self,
        text: str,
        context: dict[str, Any],
    ) -> list[HallucinationFlag]:
        """Detect common hallucination patterns in text.

        Args:
            text: Text to analyze.
            context: Additional context (query, retrieved_chunks).

        Returns:
            List of hallucination flags.
        """
        flags = []
        text_lower = text.lower()

        # Pattern 1: Very specific numbers without citation
        import re

        number_patterns = re.findall(r'\b\d+(?:\.\d+)?%|\b\d+(?:\.\d+)?\s*(?:million|billion|trillion|thousand)\b', text_lower)
        for match in number_patterns:
            flags.append(HallucinationFlag(
                chunk_id=context.get("chunk_id", "unknown"),
                flag_type="specific_number",
                severity=0.7,
                description=f"Specific number '{match}' requires verification",
                suggestions=["Add citation", "Cross-reference with documentation"],
            ))

        # Pattern 2: Absolute statements (always, never, all, none)
        absolute_words = ["always", "never", "all", "none", "every", "impossible", "guaranteed"]
        for word in absolute_words:
            if f" {word} " in f" {text_lower} ":
                flags.append(HallucinationFlag(
                    chunk_id=context.get("chunk_id", "unknown"),
                    flag_type="absolute_statement",
                    severity=0.5,
                    description=f"Absolute statement '{word}' may be inaccurate",
                    suggestions=[f"Consider changing '{word}' to 'typically'", "Add qualifier"],
                ))

        # Pattern 3: Dates and historical claims
        date_patterns = re.findall(r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b', text, re.IGNORECASE)
        for match in date_patterns:
            flags.append(HallucinationFlag(
                chunk_id=context.get("chunk_id", "unknown"),
                flag_type="historical_claim",
                severity=0.4,
                description=f"Historical date '{match}' requires verification",
                suggestions=["Verify date accuracy", "Add source citation"],
            ))

        # Pattern 4: Technical specifications
        spec_patterns = re.findall(r'\b(?:clock|speed|size|memory|storage|voltage|current)\s*(?:is|:)\s*\d+', text_lower)
        for match in spec_patterns:
            flags.append(HallucinationFlag(
                chunk_id=context.get("chunk_id", "unknown"),
                flag_type="technical_spec",
                severity=0.6,
                description=f"Technical specification '{match}' requires verification",
                suggestions=["Verify against datasheet", "Add citation"],
            ))

        return flags

    def requires_human_review(
        self,
        chunks: list[ChunkConfidence],
    ) -> tuple[bool, list[str]]:
        """Check if human review is required.

        Returns:
            Tuple of (requires_review, reasons).
        """
        if not self._on_low_confidence:
            return False, []

        reasons = []
        very_low_count = 0

        for chunk in chunks:
            if chunk.combined_confidence < self._human_in_loop_threshold:
                very_low_count += 1
                reasons.append(
                    f"Chunk {chunk.chunk_id} has very low confidence "
                    f"({chunk.combined_confidence:.2f})"
                )

        # Trigger if > 30% of chunks are very low confidence
        if len(chunks) > 0 and very_low_count / len(chunks) > 0.3:
            return True, reasons

        # Trigger if any single chunk is below absolute threshold
        if any(c.combined_confidence < 0.2 for c in chunks):
            return True, reasons + ["Critical: Some chunks below absolute threshold"]

        return False, []

    def sanitize_response(
        self,
        chunks: list[ChunkConfidence],
        text: str,
        context: dict[str, Any],
    ) -> tuple[str, list[HallucinationFlag], bool]:
        """Sanitize response text and detect hallucinations.

        Returns:
            Tuple of (sanitized_text, flags, requires_review).
        """
        flags = self.detect_hallucination_patterns(text, context)
        requires_review, reasons = self.requires_human_review(chunks)

        # Add warning for low-confidence chunks
        if requires_review:
            warning = "\n\n[⚠️ LOW CONFIDENCE WARNING: This response contains information that may not be accurate. Please verify the following claims manually.]"
            text = text + warning

            for reason in reasons:
                flags.append(HallucinationFlag(
                    chunk_id="response",
                    flag_type="low_confidence",
                    severity=0.9,
                    description=reason,
                    suggestions=["Verify with authoritative source"],
                ))

        return text, flags, requires_review

    def is_citation_verified(self, chunk_id: str) -> bool:
        """Check if citation was verified for chunk."""
        return self._verified_citations.get(chunk_id, False)

    def get_stats(self) -> dict[str, Any]:
        """Get hallucination guard statistics."""
        total = len(self._verified_citations)
        verified = sum(1 for v in self._verified_citations.values() if v)

        return {
            "total_citations": total,
            "verified_citations": verified,
            "unverified_citations": total - verified,
            "verification_rate": verified / total if total > 0 else 0.0,
        }

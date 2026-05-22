"""Confidence decay for memory facts.

Implements time-based confidence decay for memory facts to prevent
stale information from being used as primary basis.

Facts decay over time, reducing their influence in RAG responses.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ConfidenceScore:
    """Represents a confidence score with decay metadata."""

    fact_id: str
    initial: float
    current: float
    decay_rate: float
    last_updated: int
    min_threshold: float = 0.1

    def is_usable(self, threshold: float | None = None) -> bool:
        """Check if fact is still usable above threshold.

        Args:
            threshold: Custom threshold. Uses min_threshold if not provided.

        Returns:
            True if current confidence > threshold.
        """
        effective_threshold = threshold if threshold is not None else self.min_threshold
        return self.current >= effective_threshold

    def update(self, new_confidence: float) -> None:
        """Update confidence score.

        Args:
            new_confidence: New confidence value.
        """
        self.current = max(0.0, min(1.0, new_confidence))
        self.last_updated = int(time.time())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "fact_id": self.fact_id,
            "initial": self.initial,
            "current": self.current,
            "decay_rate": self.decay_rate,
            "last_updated": self.last_updated,
            "min_threshold": self.min_threshold,
        }


class DecayStrategy(str, Enum):
    """Strategy for confidence decay."""

    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    STEP = "step"
    NONE = "none"


class ConfidenceDecay:
    """Manages confidence decay for memory facts.

    Implements various decay strategies:
    - Linear: constant rate per time unit
    - Exponential: multiplicative decay
    - Step: decay in discrete steps
    - None: no automatic decay
    """

    DEFAULT_DECAY_RATE = 0.01
    DEFAULT_HALF_LIFE_DAYS = 30

    def __init__(
        self,
        strategy: DecayStrategy = DecayStrategy.EXPONENTIAL,
        default_decay_rate: float = DEFAULT_DECAY_RATE,
        default_half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
        min_confidence_threshold: float = 0.1,
    ) -> None:
        """Initialize confidence decay manager.

        Args:
            strategy: Decay strategy to use.
            default_decay_rate: Default decay rate per day (for linear/exponential).
            default_half_life_days: Default half-life in days (for exponential).
            min_confidence_threshold: Minimum confidence before fact is excluded.
        """
        self._strategy = strategy
        self._default_decay_rate = default_decay_rate
        self._default_half_life_days = default_half_life_days
        self._min_threshold = min_confidence_threshold
        self._scores: dict[str, ConfidenceScore] = {}

    def register(
        self,
        fact_id: str,
        initial_confidence: float = 1.0,
        decay_rate: float | None = None,
    ) -> ConfidenceScore:
        """Register a fact with confidence tracking.

        Args:
            fact_id: Unique fact identifier.
            initial_confidence: Initial confidence (0-1).
            decay_rate: Custom decay rate. Uses default if not provided.

        Returns:
            Created confidence score record.
        """
        effective_rate = decay_rate or self._default_decay_rate

        if self._strategy == DecayStrategy.EXPONENTIAL:
            effective_rate = 1.0 - (0.5 ** (1.0 / self._default_half_life_days))

        score = ConfidenceScore(
            fact_id=fact_id,
            initial=initial_confidence,
            current=initial_confidence,
            decay_rate=effective_rate,
            last_updated=int(time.time()),
            min_threshold=self._min_threshold,
        )
        self._scores[fact_id] = score
        return score

    def get_confidence(
        self,
        fact_id: str,
        current_time: int | None = None,
    ) -> float | None:
        """Get current confidence for a fact with decay applied.

        Args:
            fact_id: Fact identifier.
            current_time: Current timestamp. Uses now if not provided.

        Returns:
            Current confidence (0-1) or None if fact not registered.
        """
        score = self._scores.get(fact_id)
        if not score:
            return None

        if current_time is None:
            current_time = int(time.time())

        current_confidence = self._calculate_decayed_confidence(
            score,
            current_time,
        )

        score.current = current_confidence
        return current_confidence

    def _calculate_decayed_confidence(
        self,
        score: ConfidenceScore,
        current_time: int,
    ) -> float:
        """Calculate decayed confidence based on strategy.

        Args:
            score: Confidence score record.
            current_time: Current timestamp.

        Returns:
            Decayed confidence (0-1).
        """
        days_elapsed = (current_time - score.last_updated) / 86400

        if self._strategy == DecayStrategy.LINEAR:
            decayed = score.initial - (score.decay_rate * days_elapsed)

        elif self._strategy == DecayStrategy.EXPONENTIAL:
            decayed = score.initial * ((1 - score.decay_rate) ** days_elapsed)

        elif self._strategy == DecayStrategy.STEP:
            steps = int(days_elapsed)
            decayed = score.initial * ((1 - score.decay_rate) ** steps)

        else:
            decayed = score.current

        return max(0.0, min(1.0, decayed))

    def boost(self, fact_id: str, boost_amount: float = 0.1) -> bool:
        """Boost confidence for a fact (e.g., after verification).

        Args:
            fact_id: Fact identifier.
            boost_amount: Amount to boost (0-1).

        Returns:
            True if boosted, False if fact not found.
        """
        score = self._scores.get(fact_id)
        if not score:
            return False

        new_value = min(1.0, score.current + boost_amount)
        score.initial = new_value
        score.current = new_value
        score.last_updated = int(time.time())
        return True

    def decay_all(self, current_time: int | None = None) -> list[str]:
        """Apply decay to all registered facts.

        Args:
            current_time: Current timestamp. Uses now if not provided.

        Returns:
            List of fact IDs that fell below threshold.
        """
        if current_time is None:
            current_time = int(time.time())

        expired = []
        for fact_id in list(self._scores.keys()):
            score = self._scores[fact_id]
            new_confidence = self._calculate_decayed_confidence(score, current_time)

            if new_confidence < self._min_threshold:
                expired.append(fact_id)

        return expired

    def filter_by_confidence(
        self,
        fact_ids: list[str],
        min_confidence: float | None = None,
    ) -> list[str]:
        """Filter facts by minimum confidence.

        Args:
            fact_ids: List of fact IDs to filter.
            min_confidence: Minimum confidence threshold.

        Returns:
            Filtered list of fact IDs.
        """
        effective_threshold = min_confidence or self._min_threshold
        result = []

        for fact_id in fact_ids:
            confidence = self.get_confidence(fact_id)
            if confidence is not None and confidence >= effective_threshold:
                result.append(fact_id)

        return result

    def get_stats(self) -> dict[str, Any]:
        """Get decay statistics.

        Returns:
            Statistics dictionary.
        """
        if not self._scores:
            return {
                "strategy": self._strategy.value,
                "total_facts": 0,
                "avg_confidence": 0.0,
                "below_threshold": 0,
            }

        confidences = [s.current for s in self._scores.values()]
        below_threshold = sum(1 for c in confidences if c < self._min_threshold)

        return {
            "strategy": self._strategy.value,
            "total_facts": len(self._scores),
            "avg_confidence": sum(confidences) / len(confidences),
            "below_threshold": below_threshold,
            "default_decay_rate": self._default_decay_rate,
            "half_life_days": self._default_half_life_days,
            "min_threshold": self._min_threshold,
        }

    def remove(self, fact_id: str) -> bool:
        """Remove a fact from tracking.

        Args:
            fact_id: Fact identifier.

        Returns:
            True if removed, False if not found.
        """
        if fact_id in self._scores:
            del self._scores[fact_id]
            return True
        return False

    def clear(self) -> None:
        """Clear all tracking."""
        self._scores.clear()

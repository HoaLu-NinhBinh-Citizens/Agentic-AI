"""Provenance metadata system for tracking data origin and confidence.

This module implements provenance tracking for all hardware domain data,
including detection results, snapshots, capabilities, and ontology nodes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ProvenanceSource(Enum):
    """Source of provenance data."""

    AUTO_DETECT = "auto_detect"
    USER_CONFIG = "user_config"
    AI_INFERENCE = "ai_inference"
    PLUGIN_QUERY = "plugin_query"
    SVD_PARSING = "svd_parsing"
    ELFMETADATA = "elf_metadata"
    CACHE = "cache"
    FALLBACK = "fallback"
    MANUAL = "manual"


class ConfidenceLevel(Enum):
    """Confidence levels for provenance data."""

    HIGH = "high"      # >= 0.9
    MEDIUM = "medium"  # >= 0.7
    LOW = "low"        # >= 0.5
    UNKNOWN = "unknown"  # < 0.5


@dataclass
class Provenance:
    """Provenance metadata for any domain object.

    Tracks the origin and reliability of data throughout the system.

    Attributes:
        source: Where the data came from
        confidence: Confidence score (0.0 to 1.0)
        timestamp: When the data was generated
        method: Specific method/algorithm used
        inputs: Inputs used to derive this data
        parent_id: ID of parent object (for derived data)
        lineage: Chain of provenance IDs
        metadata: Additional source-specific metadata
    """

    source: ProvenanceSource
    confidence: float = 1.0
    timestamp: datetime = field(default_factory=datetime.now)
    method: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)
    parent_id: str | None = None
    lineage: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate and normalize confidence score."""
        self.confidence = max(0.0, min(1.0, self.confidence))

    @property
    def confidence_level(self) -> ConfidenceLevel:
        """Get confidence as categorical level."""
        if self.confidence >= 0.9:
            return ConfidenceLevel.HIGH
        elif self.confidence >= 0.7:
            return ConfidenceLevel.MEDIUM
        elif self.confidence >= 0.5:
            return ConfidenceLevel.LOW
        return ConfidenceLevel.UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "source": self.source.value,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level.value,
            "timestamp": self.timestamp.isoformat(),
            "method": self.method,
            "inputs": self.inputs,
            "parent_id": self.parent_id,
            "lineage": self.lineage,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Provenance":
        """Create from dictionary."""
        source = data.get("source", "manual")
        if isinstance(source, str):
            source = ProvenanceSource(source)

        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        elif timestamp is None:
            timestamp = datetime.now()

        return cls(
            source=source,
            confidence=data.get("confidence", 1.0),
            timestamp=timestamp,
            method=data.get("method", ""),
            inputs=data.get("inputs", {}),
            parent_id=data.get("parent_id"),
            lineage=data.get("lineage", []),
            metadata=data.get("metadata", {}),
        )

    def merge(self, other: "Provenance") -> "Provenance":
        """Merge with another provenance, taking the lower confidence.

        Args:
            other: Another provenance to merge with

        Returns:
            New Provenance with combined lineage
        """
        return Provenance(
            source=self.source,
            confidence=min(self.confidence, other.confidence),
            timestamp=min(self.timestamp, other.timestamp),
            method=f"{self.method};{other.method}",
            inputs={**self.inputs, **other.inputs},
            parent_id=self.parent_id,
            lineage=self.lineage + [other.parent_id or ""],
            metadata={**self.metadata, **other.metadata},
        )


class ProvenanceTracker:
    """Tracker for managing provenance metadata.

    Provides utilities for creating and managing provenance
    across the hardware domain.
    """

    def __init__(self):
        """Initialize tracker."""
        self._objects: dict[str, Provenance] = {}

    def track(
        self,
        object_id: str,
        source: ProvenanceSource,
        confidence: float = 1.0,
        method: str = "",
        inputs: dict[str, Any] | None = None,
        parent_id: str | None = None,
        **metadata,
    ) -> Provenance:
        """Track an object with provenance.

        Args:
            object_id: Unique ID of the object
            source: Source of the data
            confidence: Confidence score
            method: Method used to derive
            inputs: Inputs used
            parent_id: Parent object ID
            **metadata: Additional metadata

        Returns:
            Created Provenance
        """
        provenance = Provenance(
            source=source,
            confidence=confidence,
            method=method,
            inputs=inputs or {},
            parent_id=parent_id,
            metadata=metadata,
        )

        self._objects[object_id] = provenance
        return provenance

    def get(self, object_id: str) -> Provenance | None:
        """Get provenance for an object.

        Args:
            object_id: Object ID

        Returns:
            Provenance or None
        """
        return self._objects.get(object_id)

    def update(
        self,
        object_id: str,
        confidence: float | None = None,
        **metadata,
    ) -> bool:
        """Update provenance metadata.

        Args:
            object_id: Object ID
            confidence: New confidence score
            **metadata: Metadata to update

        Returns:
            True if updated
        """
        if object_id not in self._objects:
            return False

        provenance = self._objects[object_id]

        if confidence is not None:
            provenance.confidence = max(0.0, min(1.0, confidence))

        provenance.metadata.update(metadata)
        return True

    def link(
        self,
        child_id: str,
        parent_id: str,
    ) -> bool:
        """Link child to parent provenance.

        Args:
            child_id: Child object ID
            parent_id: Parent object ID

        Returns:
            True if linked
        """
        if child_id not in self._objects or parent_id not in self._objects:
            return False

        child = self._objects[child_id]
        parent = self._objects[parent_id]

        child.parent_id = parent_id
        child.lineage = parent.lineage + [parent_id]

        # Reduce confidence when derived
        child.confidence = min(child.confidence, parent.confidence)

        return True

    def get_lineage(self, object_id: str) -> list[str]:
        """Get full lineage of an object.

        Args:
            object_id: Object ID

        Returns:
            List of ancestor IDs
        """
        if object_id not in self._objects:
            return []

        lineage = []
        current_id = object_id

        while current_id:
            lineage.append(current_id)
            provenance = self._objects.get(current_id)
            if provenance:
                current_id = provenance.parent_id
            else:
                break

        return lineage

    def filter_by_confidence(
        self,
        min_confidence: float,
    ) -> dict[str, Provenance]:
        """Filter objects by minimum confidence.

        Args:
            min_confidence: Minimum confidence threshold

        Returns:
            Dictionary of filtered objects
        """
        return {
            obj_id: prov
            for obj_id, prov in self._objects.items()
            if prov.confidence >= min_confidence
        }

    def filter_by_source(
        self,
        source: ProvenanceSource,
    ) -> dict[str, Provenance]:
        """Filter objects by source.

        Args:
            source: Source to filter by

        Returns:
            Dictionary of filtered objects
        """
        return {
            obj_id: prov
            for obj_id, prov in self._objects.items()
            if prov.source == source
        }

    def to_dict(self) -> dict[str, Any]:
        """Export all provenance data."""
        return {
            obj_id: prov.to_dict()
            for obj_id, prov in self._objects.items()
        }

    def summary(self) -> dict[str, Any]:
        """Get summary statistics."""
        if not self._objects:
            return {
                "total_objects": 0,
                "by_source": {},
                "by_confidence_level": {},
            }

        by_source: dict[str, int] = {}
        by_confidence: dict[str, int] = {}

        for prov in self._objects.values():
            source_key = prov.source.value
            by_source[source_key] = by_source.get(source_key, 0) + 1

            level = prov.confidence_level.value
            by_confidence[level] = by_confidence.get(level, 0) + 1

        return {
            "total_objects": len(self._objects),
            "by_source": by_source,
            "by_confidence_level": by_confidence,
        }


# Helper functions for common provenance patterns
def from_auto_detection(
    method: str,
    inputs: dict[str, Any],
    confidence: float = 0.9,
) -> Provenance:
    """Create provenance from auto-detection.

    Args:
        method: Detection method (e.g., "idcode", "vid_pid")
        inputs: Detection inputs
        confidence: Detection confidence

    Returns:
        Provenance for auto-detection
    """
    return Provenance(
        source=ProvenanceSource.AUTO_DETECT,
        confidence=confidence,
        method=method,
        inputs=inputs,
    )


def from_user_config(
    config_path: str,
    confidence: float = 1.0,
) -> Provenance:
    """Create provenance from user configuration.

    Args:
        config_path: Path to config file
        confidence: Config confidence (usually high)

    Returns:
        Provenance for user config
    """
    return Provenance(
        source=ProvenanceSource.USER_CONFIG,
        confidence=confidence,
        method="yaml_config",
        inputs={"config_path": config_path},
    )


def from_ai_inference(
    model: str,
    inputs: dict[str, Any],
    confidence: float = 0.7,
) -> Provenance:
    """Create provenance from AI inference.

    Args:
        model: AI model used
        inputs: Model inputs
        confidence: Inference confidence

    Returns:
        Provenance for AI inference
    """
    return Provenance(
        source=ProvenanceSource.AI_INFERENCE,
        confidence=confidence,
        method=f"model:{model}",
        inputs=inputs,
    )


def from_plugin(
    plugin_name: str,
    method: str,
    confidence: float = 0.95,
) -> Provenance:
    """Create provenance from plugin query.

    Args:
        plugin_name: Plugin name
        method: Plugin method called
        confidence: Plugin result confidence

    Returns:
        Provenance for plugin query
    """
    return Provenance(
        source=ProvenanceSource.PLUGIN_QUERY,
        confidence=confidence,
        method=f"{plugin_name}.{method}",
        inputs={"plugin": plugin_name},
        metadata={"plugin_name": plugin_name},
    )

"""Data labeling tool for bug classification (Phase 11.2).

Provides:
- CLI/Web interface for labeling bugs
- Bug type classification
- Patch correctness labeling
- Label export for ML training
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class BugLabel(Enum):
    """Bug classification labels."""
    # Correctness
    CORRECT_FIX = "correct_fix"
    INCORRECT_FIX = "incorrect_fix"
    PARTIAL_FIX = "partial_fix"
    
    # Type
    HARDWARE_BUG = "hardware_bug"
    SOFTWARE_BUG = "software_bug"
    CONFIG_BUG = "config_bug"
    RACE_CONDITION = "race_condition"
    MEMORY_LEAK = "memory_leak"
    TIMING_BUG = "timing_bug"
    
    # Quality
    GENUINE_BUG = "genuine_bug"
    FALSE_POSITIVE = "false_positive"
    DUPLICATE = "duplicate"
    
    # Severity
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class LabelConfidence(Enum):
    """Confidence in the label."""
    HIGH = "high"      # Very confident
    MEDIUM = "medium"  # Somewhat confident
    LOW = "low"        # Not very confident


@dataclass
class Label:
    """Single label assignment."""
    name: BugLabel
    confidence: LabelConfidence
    assigned_by: str
    assigned_at: datetime = field(default_factory=datetime.now)
    notes: str = ""


@dataclass
class LabeledBug:
    """Bug with labels."""
    bug_id: str
    title: str
    description: str
    labels: list[Label] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_modified: datetime = field(default_factory=datetime.now)
    
    # Original data preserved
    original_data: dict[str, Any] = field(default_factory=dict)
    
    @property
    def primary_label(self) -> BugLabel | None:
        """Get the primary (correctness) label."""
        for label in self.labels:
            if label.name in [BugLabel.CORRECT_FIX, BugLabel.INCORRECT_FIX, BugLabel.PARTIAL_FIX]:
                return label.name
        return None
    
    @property
    def is_verified(self) -> bool:
        """Check if bug is verified (has correctness label)."""
        return self.primary_label is not None


class LabelingSession:
    """Labeling session management."""
    
    def __init__(self, session_id: str, labeler: str) -> None:
        self.id = session_id
        self.labeler = labeler
        self.started_at = datetime.now()
        self.completed_at: datetime | None = None
        self.bugs_labeled: list[str] = []
    
    @property
    def is_complete(self) -> bool:
        return self.completed_at is not None
    
    def mark_complete(self) -> None:
        self.completed_at = datetime.now()


class DataLabeler:
    """Main labeling system.
    
    Phase 11.2: Data labeling tool
    """
    
    def __init__(self, storage_path: str = "data/labels.json") -> None:
        self._storage_path = storage_path
        self._labeled_bugs: dict[str, LabeledBug] = {}
        self._sessions: dict[str, LabelingSession] = {}
    
    def start_session(self, labeler: str) -> LabelingSession:
        """Start a new labeling session."""
        import uuid
        session = LabelingSession(
            session_id=str(uuid.uuid4())[:8],
            labeler=labeler,
        )
        self._sessions[session.id] = session
        return session
    
    def add_bug(self, bug: LabeledBug) -> None:
        """Add or update a labeled bug."""
        self._labeled_bugs[bug.bug_id] = bug
        logger.info("Added labeled bug", bug_id=bug.bug_id)
    
    def label_bug(
        self,
        bug_id: str,
        label: BugLabel,
        labeler: str,
        confidence: LabelConfidence = LabelConfidence.MEDIUM,
        notes: str = "",
    ) -> bool:
        """Apply a label to a bug."""
        if bug_id not in self._labeled_bugs:
            logger.warning("Bug not found", bug_id=bug_id)
            return False
        
        bug = self._labeled_bugs[bug_id]
        
        # Check if label already exists
        for existing in bug.labels:
            if existing.name == label:
                # Update existing
                existing.confidence = confidence
                existing.notes = notes
                bug.last_modified = datetime.now()
                return True
        
        # Add new label
        bug.labels.append(Label(
            name=label,
            confidence=confidence,
            assigned_by=labeler,
            notes=notes,
        ))
        bug.last_modified = datetime.now()
        
        logger.info("Applied label", bug_id=bug_id, label=label.value)
        return True
    
    def get_labeled_bug(self, bug_id: str) -> LabeledBug | None:
        """Get a labeled bug."""
        return self._labeled_bugs.get(bug_id)
    
    def get_unlabeled_bugs(self) -> list[LabeledBug]:
        """Get bugs without correctness labels."""
        return [
            bug for bug in self._labeled_bugs.values()
            if not bug.is_verified
        ]
    
    def get_verified_bugs(self) -> list[LabeledBug]:
        """Get bugs with correctness labels."""
        return [
            bug for bug in self._labeled_bugs.values()
            if bug.is_verified
        ]
    
    def get_statistics(self) -> dict[str, Any]:
        """Get labeling statistics."""
        verified = self.get_verified_bugs()
        correct = sum(1 for b in verified if b.primary_label == BugLabel.CORRECT_FIX)
        incorrect = sum(1 for b in verified if b.primary_label == BugLabel.INCORRECT_FIX)
        
        return {
            "total_labeled": len(self._labeled_bugs),
            "verified": len(verified),
            "unverified": len(self._labeled_bugs) - len(verified),
            "correct_fixes": correct,
            "incorrect_fixes": incorrect,
            "accuracy": correct / len(verified) if verified else 0.0,
            "sessions": len(self._sessions),
        }
    
    def export_training_data(
        self,
        output_path: str,
        include_unverified: bool = False,
    ) -> int:
        """Export labeled data for ML training.
        
        Returns:
            Number of samples exported
        """
        bugs = self._labeled_bugs.values()
        if not include_unverified:
            bugs = [b for b in bugs if b.is_verified]
        
        training_data = []
        for bug in bugs:
            sample = {
                "bug_id": bug.bug_id,
                "title": bug.title,
                "description": bug.description,
                "labels": [l.name.value for l in bug.labels],
                "primary_label": bug.primary_label.value if bug.primary_label else None,
                "created_at": bug.created_at.isoformat(),
            }
            # Include original data (already anonymized)
            if bug.original_data:
                sample["features"] = self._extract_features(bug)
            training_data.append(sample)
        
        with open(output_path, "w") as f:
            json.dump(training_data, f, indent=2)
        
        logger.info("Exported training data", count=len(training_data), path=output_path)
        return len(training_data)
    
    def _extract_features(self, bug: LabeledBug) -> dict[str, Any]:
        """Extract features for ML from bug data."""
        features = {}
        if bug.original_data:
            features["bug_type"] = bug.original_data.get("bug_type", "")
            features["severity"] = bug.original_data.get("severity", "")
            features["file_patterns"] = bug.original_data.get("file_patterns", [])
            features["has_stack_trace"] = "stack_trace" in bug.original_data
            features["root_cause_count"] = len(bug.original_data.get("root_causes", []))
        return features
    
    def save(self) -> None:
        """Save labeled data to storage."""
        data = {
            "bugs": {
                bid: {
                    **vars(bug),
                    "labels": [
                        {
                            **vars(l),
                            "name": l.name.value,
                            "confidence": l.confidence.value,
                            "assigned_at": l.assigned_at.isoformat(),
                        }
                        for l in bug.labels
                    ],
                    "primary_label": bug.primary_label.value if bug.primary_label else None,
                    "created_at": bug.created_at.isoformat(),
                    "last_modified": bug.last_modified.isoformat(),
                }
                for bid, bug in self._labeled_bugs.items()
            },
            "sessions": [
                {
                    "id": s.id,
                    "labeler": s.labeler,
                    "started_at": s.started_at.isoformat(),
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                    "bugs_labeled": s.bugs_labeled,
                }
                for s in self._sessions.values()
            ],
        }
        
        Path(self._storage_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self._storage_path, "w") as f:
            json.dump(data, f, indent=2)
        
        logger.info("Saved labeled data", count=len(self._labeled_bugs))
    
    def load(self) -> None:
        """Load labeled data from storage."""
        try:
            with open(self._storage_path) as f:
                data = json.load(f)
            
            for bid, bug_data in data.get("bugs", {}).items():
                bug_data["labels"] = [
                    Label(
                        name=BugLabel(l["name"]),
                        confidence=LabelConfidence(l["confidence"]),
                        assigned_by=l["assigned_by"],
                        assigned_at=datetime.fromisoformat(l["assigned_at"]),
                        notes=l.get("notes", ""),
                    )
                    for l in bug_data.get("labels", [])
                ]
                bug_data["created_at"] = datetime.fromisoformat(bug_data["created_at"])
                bug_data["last_modified"] = datetime.fromisoformat(bug_data["last_modified"])
                self._labeled_bugs[bid] = LabeledBug(**bug_data)
            
            for session_data in data.get("sessions", []):
                session = LabelingSession(
                    session_id=session_data["id"],
                    labeler=session_data["labeler"],
                )
                session.started_at = datetime.fromisoformat(session_data["started_at"])
                if session_data.get("completed_at"):
                    session.completed_at = datetime.fromisoformat(session_data["completed_at"])
                session.bugs_labeled = session_data.get("bugs_labeled", [])
                self._sessions[session.id] = session
            
            logger.info("Loaded labeled data", count=len(self._labeled_bugs))
        except FileNotFoundError:
            logger.info("No labels file found")
        except Exception as e:
            logger.error("Failed to load labels", error=str(e))


# Global singleton
_labeler: DataLabeler | None = None


def get_data_labeler() -> DataLabeler:
    """Get global data labeler instance."""
    global _labeler
    if _labeler is None:
        _labeler = DataLabeler()
        _labeler.load()
    return _labeler


# CLI for labeling
if __name__ == "__main__":
    labeler = get_data_labeler()
    
    # Create sample labeled bug
    bug = LabeledBug(
        bug_id="bug_001",
        title="HardFault fix",
        description="Fix for hardfault caused by NULL pointer",
        original_data={
            "bug_type": "hard_fault",
            "severity": "critical",
            "root_causes": ["NULL pointer dereference"],
        },
    )
    labeler.add_bug(bug)
    
    # Apply labels
    labeler.label_bug(
        "bug_001",
        BugLabel.CORRECT_FIX,
        labeler="engineer1",
        confidence=LabelConfidence.HIGH,
        notes="Patch correctly handles NULL check",
    )
    
    labeler.label_bug(
        "bug_001",
        BugLabel.HARDWARE_BUG,
        labeler="engineer1",
        confidence=LabelConfidence.MEDIUM,
    )
    
    print("Labeling Statistics:")
    stats = labeler.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # Export training data
    count = labeler.export_training_data("data/training_data.json")
    print(f"\nExported {count} training samples")

"""Crash clustering for fleet-wide error analysis (Phase 8.5).

Groups similar crashes across fleet:
- Signature-based clustering
- Pattern matching across error types
- Multi-board correlation
- Cluster analysis and reporting

Tier 1 value component.
"""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CrashSignature:
    """Unique signature for a crash type."""
    signature: str
    pattern_type: str
    error_category: str
    file_patterns: list[str] = field(default_factory=list)
    function_patterns: list[str] = field(default_factory=list)
    hash_components: list[str] = field(default_factory=list)
    
    @classmethod
    def from_error(cls, error_type: str, message: str, file: str = "", function: str = "") -> CrashSignature:
        """Create signature from error details."""
        # Extract stable components
        file_base = file.split("/")[-1].split("\\")[-1] if file else ""
        
        # Create hash from stable components
        components = [
            error_type.lower(),
            file_base.lower(),
            function.lower() if function else "",
        ]
        # Normalize message - remove variable parts
        normalized = message.lower()
        for part in ["0x[0-9a-f]+", r"\d+", r"\d+\.\d+"]:
            import re
            normalized = re.sub(part, "{VAR}", normalized)
        
        components.append(normalized[:100])
        
        signature = hashlib.sha256("|".join(components).encode()).hexdigest()[:16]
        
        return cls(
            signature=signature,
            pattern_type=error_type,
            error_category=cls._categorize_error(error_type),
            file_patterns=[file_base] if file_base else [],
            function_patterns=[function] if function else [],
            hash_components=components,
        )
    
    @staticmethod
    def _categorize_error(error_type: str) -> str:
        """Categorize error type."""
        error_lower = error_type.lower()
        if "fault" in error_lower:
            return "fault"
        elif "timeout" in error_lower:
            return "timeout"
        elif "overflow" in error_lower:
            return "overflow"
        elif "deadlock" in error_lower:
            return "deadlock"
        elif "assert" in error_lower:
            return "assertion"
        return "general"


@dataclass
class CrashCluster:
    """Cluster of similar crashes."""
    cluster_id: str
    signature: CrashSignature
    
    # Statistics
    total_occurrences: int = 0
    unique_boards: list[str] = field(default_factory=list)
    unique_firmware_versions: list[str] = field(default_factory=list)
    
    # Timing
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    
    # Sample data
    sample_error: str = ""
    sample_board: str = ""
    sample_firmware: str = ""
    
    # Analysis
    affected_boards_count: int = 0
    firmware_versions_count: int = 0
    is_regression: bool = False  # Appeared in recent firmware only
    
    @property
    def impact_score(self) -> float:
        """Calculate impact score based on affected boards and recency."""
        board_score = min(1.0, self.affected_boards_count / 10)  # Max at 10 boards
        recency_days = (datetime.now() - self.last_seen).days
        recency_score = max(0, 1.0 - recency_days / 30)  # Decay over 30 days
        
        return board_score * 0.6 + recency_score * 0.4
    
    @property
    def severity(self) -> str:
        """Determine severity based on impact."""
        if self.impact_score > 0.8:
            return "CRITICAL"
        elif self.impact_score > 0.5:
            return "HIGH"
        elif self.impact_score > 0.2:
            return "MEDIUM"
        return "LOW"


@dataclass
class CrashReport:
    """Individual crash report."""
    crash_id: str
    signature: CrashSignature
    
    # Error details
    error_type: str
    error_message: str
    stack_trace: list[str] = field(default_factory=list)
    
    # Location
    file: str = ""
    function: str = ""
    line: int = 0
    
    # Context
    board_id: str = ""
    firmware_version: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Metadata
    source: str = "unknown"  # "gdb", "openocd", "segger", "generic"


class CrashClusteringEngine:
    """Engine for clustering crashes across fleet.
    
    Phase 8.5: Crash clustering
    
    Groups errors across fleet for:
    - Identifying widespread issues
    - Detecting regressions
    - Prioritizing fixes
    """
    
    def __init__(self) -> None:
        self._crashes: list[CrashReport] = []
        self._clusters: dict[str, CrashCluster] = {}
        self._board_crashes: dict[str, list[str]] = defaultdict(list)  # board_id -> crash_ids
    
    def add_crash(self, crash: CrashReport) -> CrashCluster | None:
        """Add a crash report and update clusters."""
        self._crashes.append(crash)
        
        # Find or create cluster
        cluster = self._find_or_create_cluster(crash)
        return cluster
    
    def add_crash_from_error(
        self,
        error_type: str,
        error_message: str,
        board_id: str = "",
        firmware_version: str = "",
        file: str = "",
        function: str = "",
        source: str = "unknown",
    ) -> CrashCluster:
        """Convenience method to add crash from error details."""
        signature = CrashSignature.from_error(error_type, error_message, file, function)
        
        crash = CrashReport(
            crash_id=hashlib.sha256(f"{datetime.now().isoformat()}{error_type}".encode()).hexdigest()[:16],
            signature=signature,
            error_type=error_type,
            error_message=error_message,
            board_id=board_id,
            firmware_version=firmware_version,
            file=file,
            function=function,
            source=source,
        )
        
        return self.add_crash(crash)
    
    def _find_or_create_cluster(self, crash: CrashReport) -> CrashCluster:
        """Find existing cluster or create new one."""
        sig = crash.signature
        
        # Search for matching cluster
        for cluster_id, cluster in self._clusters.items():
            if self._signatures_match(sig, cluster.signature):
                # Update existing cluster
                cluster.total_occurrences += 1
                cluster.last_seen = max(cluster.last_seen, crash.timestamp)
                
                if crash.board_id and crash.board_id not in cluster.unique_boards:
                    cluster.unique_boards.append(crash.board_id)
                    cluster.affected_boards_count = len(cluster.unique_boards)
                
                if crash.firmware_version and crash.firmware_version not in cluster.unique_firmware_versions:
                    cluster.unique_firmware_versions.append(crash.firmware_version)
                    cluster.firmware_versions_count = len(cluster.unique_firmware_versions)
                
                # Update sample if newer
                if crash.timestamp > datetime.fromisoformat(cluster.last_seen.isoformat()):
                    cluster.sample_error = crash.error_message
                    cluster.sample_board = crash.board_id
                    cluster.sample_firmware = crash.firmware_version
                
                # Track board crashes
                if crash.board_id:
                    self._board_crashes[crash.board_id].append(cluster_id)
                
                return cluster
        
        # Create new cluster
        cluster = CrashCluster(
            cluster_id=sig.signature,
            signature=sig,
            total_occurrences=1,
            unique_boards=[crash.board_id] if crash.board_id else [],
            unique_firmware_versions=[crash.firmware_version] if crash.firmware_version else [],
            first_seen=crash.timestamp,
            last_seen=crash.timestamp,
            sample_error=crash.error_message,
            sample_board=crash.board_id,
            sample_firmware=crash.firmware_version,
            affected_boards_count=1 if crash.board_id else 0,
            firmware_versions_count=1 if crash.firmware_version else 0,
        )
        
        self._clusters[cluster.cluster_id] = cluster
        
        if crash.board_id:
            self._board_crashes[crash.board_id].append(cluster.cluster_id)
        
        logger.info("Created new crash cluster", cluster_id=cluster.cluster_id, error_type=crash.error_type)
        
        return cluster
    
    def _signatures_match(self, sig1: CrashSignature, sig2: CrashSignature) -> bool:
        """Check if two signatures match (fuzzy matching)."""
        # Exact match on signature
        if sig1.signature == sig2.signature:
            return True
        
        # Category match + similar patterns
        if sig1.error_category == sig2.error_category:
            # Check file patterns
            if sig1.file_patterns and sig2.file_patterns:
                if sig1.file_patterns[0] == sig2.file_patterns[0]:
                    return True
            
            # Check function patterns
            if sig1.function_patterns and sig2.function_patterns:
                if sig1.function_patterns[0] == sig2.function_patterns[0]:
                    return True
        
        return False
    
    def get_clusters(self) -> list[CrashCluster]:
        """Get all clusters sorted by impact."""
        clusters = list(self._clusters.values())
        clusters.sort(key=lambda c: c.impact_score, reverse=True)
        return clusters
    
    def get_cluster(self, cluster_id: str) -> CrashCluster | None:
        """Get specific cluster."""
        return self._clusters.get(cluster_id)
    
    def get_top_clusters(self, limit: int = 10) -> list[CrashCluster]:
        """Get top N clusters by impact score."""
        return self.get_clusters()[:limit]
    
    def get_clusters_by_board(self, board_id: str) -> list[CrashCluster]:
        """Get all clusters affecting a specific board."""
        cluster_ids = self._board_crashes.get(board_id, [])
        return [self._clusters[cid] for cid in cluster_ids if cid in self._clusters]
    
    def detect_regressions(self) -> list[CrashCluster]:
        """Detect crashes that only affect recent firmware versions."""
        regressions = []
        
        for cluster in self._clusters.values():
            if len(cluster.unique_firmware_versions) == 1:
                # Only one firmware version affected - check if it's recent
                if cluster.is_regression:
                    regressions.append(cluster)
        
        return regressions
    
    def get_fleet_wide_crashes(self) -> list[CrashCluster]:
        """Get crashes affecting multiple boards."""
        return [c for c in self._clusters.values() if c.affected_boards_count > 1]
    
    def analyze_patterns(self) -> dict[str, Any]:
        """Analyze crash patterns across fleet."""
        clusters = self.get_clusters()
        
        if not clusters:
            return {
                "total_crashes": 0,
                "total_clusters": 0,
                "fleet_wide_count": 0,
                "top_patterns": [],
            }
        
        # Group by error category
        by_category: dict[str, int] = defaultdict(int)
        for cluster in clusters:
            by_category[cluster.signature.error_category] += cluster.total_occurrences
        
        return {
            "total_crashes": sum(c.total_occurrences for c in clusters),
            "total_clusters": len(clusters),
            "fleet_wide_count": len(self.get_fleet_wide_crashes()),
            "affected_boards": len(self._board_crashes),
            "by_category": dict(by_category),
            "top_patterns": [
                {
                    "cluster_id": c.cluster_id,
                    "error_type": c.signature.pattern_type,
                    "occurrences": c.total_occurrences,
                    "affected_boards": c.affected_boards_count,
                    "impact_score": c.impact_score,
                    "severity": c.severity,
                }
                for c in clusters[:10]
            ],
        }
    
    def export_cluster_report(self) -> dict[str, Any]:
        """Export full cluster report."""
        clusters = self.get_clusters()
        
        return {
            "generated_at": datetime.now().isoformat(),
            "summary": self.analyze_patterns(),
            "critical_clusters": [
                self._cluster_summary(c) for c in clusters if c.severity == "CRITICAL"
            ],
            "high_impact_clusters": [
                self._cluster_summary(c) for c in clusters if c.severity == "HIGH"
            ],
            "fleet_wide_issues": [
                self._cluster_summary(c) for c in self.get_fleet_wide_crashes()
            ],
        }
    
    def _cluster_summary(self, cluster: CrashCluster) -> dict[str, Any]:
        """Create summary of a cluster."""
        return {
            "cluster_id": cluster.cluster_id,
            "error_type": cluster.signature.pattern_type,
            "occurrences": cluster.total_occurrences,
            "affected_boards": cluster.affected_boards_count,
            "board_list": cluster.unique_boards[:5],  # First 5
            "firmware_versions": cluster.unique_firmware_versions,
            "first_seen": cluster.first_seen.isoformat(),
            "last_seen": cluster.last_seen.isoformat(),
            "impact_score": cluster.impact_score,
            "severity": cluster.severity,
            "sample_error": cluster.sample_error[:200],
        }


# Global singleton
_clustering_engine: CrashClusteringEngine | None = None


def get_crash_clustering_engine() -> CrashClusteringEngine:
    """Get global crash clustering engine."""
    global _clustering_engine
    if _clustering_engine is None:
        _clustering_engine = CrashClusteringEngine()
    return _clustering_engine


# CLI for testing
if __name__ == "__main__":
    engine = get_crash_clustering_engine()
    
    print("Testing crash clustering:")
    print("-" * 50)
    
    # Simulate crashes from multiple boards
    crashes = [
        ("hard_fault", "HardFault at 0x20001000", "board_001", "v1.0.0", "stm32f4xx_it.c", "HardFault_Handler"),
        ("hard_fault", "HardFault at 0x20002000", "board_002", "v1.0.0", "stm32f4xx_it.c", "HardFault_Handler"),
        ("hard_fault", "HardFault at 0x20003000", "board_003", "v1.1.0", "stm32f4xx_it.c", "HardFault_Handler"),
        ("timeout", "I2C timeout on bus 1", "board_001", "v1.0.0", "i2c.c", "I2C_Transmit"),
        ("stack_overflow", "Stack overflow in task main", "board_002", "v1.1.0", "main.c", "task_main"),
    ]
    
    for error_type, msg, board, fw, file, func in crashes:
        engine.add_crash_from_error(
            error_type=error_type,
            error_message=msg,
            board_id=board,
            firmware_version=fw,
            file=file,
            function=func,
        )
    
    # Analyze
    print("\nCluster Analysis:")
    analysis = engine.analyze_patterns()
    print(f"  Total crashes: {analysis['total_crashes']}")
    print(f"  Total clusters: {analysis['total_clusters']}")
    print(f"  Fleet-wide issues: {analysis['fleet_wide_count']}")
    print(f"  By category: {analysis['by_category']}")
    
    print("\nTop Clusters:")
    for cluster in engine.get_top_clusters(3):
        print(f"  [{cluster.severity}] {cluster.signature.pattern_type}")
        print(f"    Occurrences: {cluster.total_occurrences}")
        print(f"    Boards: {cluster.affected_boards_count}")
        print(f"    Impact: {cluster.impact_score:.2f}")

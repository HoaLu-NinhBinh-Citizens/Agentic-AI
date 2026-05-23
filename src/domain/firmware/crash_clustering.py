"""Fleet Crash Clustering - Grouping similar crash reports from fleet devices.

Provides:
- Crash report ingestion from multiple devices
- Similarity-based crash grouping
- Root cause clustering
- Stack trace normalization
- Device fingerprinting
- Anomaly detection for new crash types

Usage:
    clusterer = CrashClusterer()
    await clusterer.add_crash_report(report)
    clusters = await clusterer.get_clusters()
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class CrashSeverity(Enum):
    """Crash severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    FATAL = "fatal"


class CrashSource(Enum):
    """Crash report source."""
    HARD_FAULT = "hard_fault"
    MEM_FAULT = "mem_fault"
    ASSERT_FAIL = "assert_fail"
    WATCHDOG = "watchdog"
    UNEXPECTED = "unexpected"


@dataclass
class CrashReport:
    """Individual crash report from a device."""
    report_id: str
    device_id: str
    firmware_version: str
    
    # Crash info
    source: CrashSource
    severity: CrashSeverity
    message: str
    timestamp: datetime
    
    # Stack trace
    stack_trace: list[str] = field(default_factory=list)
    registers: dict[str, int] = field(default_factory=dict)
    
    # Memory state
    fault_address: int = 0
    memory_dump: bytes | None = None
    
    # Metadata
    build_hash: str = ""
    build_timestamp: str = ""
    device_type: str = ""
    device_variant: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    
    # Fingerprint (computed)
    fingerprint: str = ""
    
    @property
    def normalized_trace(self) -> str:
        """Get normalized stack trace for clustering."""
        return self._normalize_trace(self.stack_trace)
    
    @staticmethod
    def _normalize_trace(trace: list[str]) -> str:
        """Normalize stack trace by removing addresses and variable parts."""
        normalized = []
        
        for line in trace:
            # Remove hex addresses
            line = re.sub(r'0x[0-9a-fA-F]+', '<ADDR>', line)
            # Remove decimal values
            line = re.sub(r'\b\d+\b', '<NUM>', line)
            # Remove specific file paths, keep just filename
            line = re.sub(r'.*[/\\]([^/\\]+:\d+)', r'\1', line)
            # Normalize whitespace
            line = re.sub(r'\s+', ' ', line).strip()
            
            if line:
                normalized.append(line)
        
        return "\n".join(normalized)
    
    def compute_fingerprint(self) -> str:
        """Compute crash fingerprint for clustering."""
        # Combine normalized trace with exception type
        components = [
            self.source.value,
            self._normalize_trace(self.stack_trace),
            self._extract_exception_type(),
        ]
        
        fingerprint = "|".join(components)
        self.fingerprint = hashlib.sha256(fingerprint.encode()).hexdigest()[:16]
        return self.fingerprint
    
    def _extract_exception_type(self) -> str:
        """Extract exception/crash type from message."""
        # Common patterns
        patterns = [
            r'(HardFault|MemoryManagement|BusFault|UsageFault)',
            r'assert.*failed',
            r'Watchdog.*reset',
            r'Stack overflow',
            r'NULL pointer',
            r'Division by zero',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, self.message, re.IGNORECASE)
            if match:
                return match.group(0)
        
        return "unknown_exception"


@dataclass
class CrashCluster:
    """Group of similar crash reports."""
    cluster_id: str
    fingerprint: str
    
    # Statistics
    count: int = 0
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    
    # Severity tracking
    max_severity: CrashSeverity = CrashSeverity.INFO
    severity_counts: dict[CrashSeverity, int] = field(default_factory=dict)
    
    # Device distribution
    affected_devices: set[str] = field(default_factory=set)
    firmware_versions: set[str] = field(default_factory=set)
    
    # Cluster data
    representative: CrashReport | None = None
    reports: list[CrashReport] = field(default_factory=list)
    
    # Analysis
    root_cause: str = ""
    is_new: bool = True  # Never seen before in fleet
    is_anomaly: bool = False  # Outlier compared to known clusters
    
    def add_report(self, report: CrashReport) -> None:
        """Add a crash report to this cluster."""
        self.reports.append(report)
        self.count += 1
        
        # Update timestamps
        if self.first_seen is None or report.timestamp < self.first_seen:
            self.first_seen = report.timestamp
        if self.last_seen is None or report.timestamp > self.last_seen:
            self.last_seen = report.timestamp
        
        # Update severity
        if report.severity.value > self.max_severity.value:
            self.max_severity = report.severity
        
        self.severity_counts[report.severity] = self.severity_counts.get(report.severity, 0) + 1
        
        # Update device/firmware sets
        self.affected_devices.add(report.device_id)
        self.firmware_versions.add(report.firmware_version)
        
        # Set representative (first one or most complete)
        if self.representative is None or len(report.stack_trace) > len(self.representative.stack_trace):
            self.representative = report
    
    def compute_fingerprint(self) -> str:
        """Compute cluster fingerprint."""
        if self.representative:
            return self.representative.compute_fingerprint()
        return self.fingerprint
    
    def to_dict(self) -> dict:
        return {
            "cluster_id": self.cluster_id,
            "fingerprint": self.fingerprint,
            "count": self.count,
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "max_severity": self.max_severity.value,
            "affected_devices": len(self.affected_devices),
            "firmware_versions": list(self.firmware_versions),
            "root_cause": self.root_cause,
            "is_new": self.is_new,
            "is_anomaly": self.is_anomaly,
            "severity_distribution": {
                s.value: self.severity_counts.get(s, 0) 
                for s in CrashSeverity
            },
        }


class CrashClusterer:
    """Crash report clustering for fleet-wide analysis.
    
    Features:
    - Automatic crash grouping by similarity
    - Stack trace normalization
    - Root cause analysis
    - Anomaly detection for new crash types
    - Device and firmware version tracking
    """
    
    def __init__(
        self,
        similarity_threshold: float = 0.8,
        min_cluster_size: int = 1,
    ):
        """
        Args:
            similarity_threshold: Minimum similarity to join a cluster (0-1)
            min_cluster_size: Minimum reports before cluster is analyzed
        """
        self._similarity_threshold = similarity_threshold
        self._min_cluster_size = min_cluster_size
        
        self._clusters: dict[str, CrashCluster] = {}
        self._device_index: dict[str, str] = {}  # device_id -> cluster_id
        self._report_index: dict[str, CrashReport] = {}  # report_id -> report
        
        # Statistics
        self._total_reports = 0
        self._known_fingerprints: set[str] = set()
    
    async def add_crash_report(self, report: CrashReport) -> str:
        """Add a crash report and return cluster ID.
        
        Args:
            report: Crash report to add
            
        Returns:
            Cluster ID where report was placed
        """
        self._total_reports += 1
        
        # Compute fingerprint
        fingerprint = report.compute_fingerprint()
        
        # Check for exact fingerprint match
        for cluster_id, cluster in self._clusters.items():
            if cluster.fingerprint == fingerprint:
                cluster.add_report(report)
                self._report_index[report.report_id] = report
                self._device_index[report.device_id] = cluster_id
                logger.info(
                    "crash_added_to_existing_cluster",
                    report_id=report.report_id,
                    cluster_id=cluster_id,
                    cluster_count=cluster.count,
                )
                return cluster_id
        
        # Try to find similar cluster
        best_match = None
        best_similarity = 0.0
        
        for cluster_id, cluster in self._clusters.items():
            if cluster.representative:
                similarity = self._compute_similarity(
                    report.normalized_trace,
                    cluster.representative.normalized_trace,
                )
                if similarity >= self._similarity_threshold and similarity > best_similarity:
                    best_match = cluster_id
                    best_similarity = similarity
        
        if best_match:
            self._clusters[best_match].add_report(report)
            self._report_index[report.report_id] = report
            self._device_index[report.device_id] = best_match
            logger.info(
                "crash_added_to_similar_cluster",
                report_id=report.report_id,
                cluster_id=best_match,
                similarity=best_similarity,
            )
            return best_match
        
        # Create new cluster
        cluster_id = f"CRASH-{len(self._clusters) + 1:04d}"
        cluster = CrashCluster(
            cluster_id=cluster_id,
            fingerprint=fingerprint,
            is_new=True,
        )
        cluster.add_report(report)
        
        self._clusters[cluster_id] = cluster
        self._report_index[report.report_id] = report
        self._device_index[report.device_id] = cluster_id
        
        # Check if this is an anomaly
        cluster.is_anomaly = fingerprint not in self._known_fingerprints
        
        logger.info(
            "crash_new_cluster_created",
            report_id=report.report_id,
            cluster_id=cluster_id,
            is_anomaly=cluster.is_anomaly,
        )
        
        return cluster_id
    
    def _compute_similarity(self, trace1: str, trace2: str) -> float:
        """Compute similarity between two normalized traces."""
        if not trace1 or not trace2:
            return 0.0
        
        # Use line-by-line comparison
        lines1 = trace1.split("\n")
        lines2 = trace2.split("\n")
        
        # Jaccard similarity
        set1 = set(lines1)
        set2 = set(lines2)
        
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        
        if union == 0:
            return 0.0
        
        # Also consider order similarity
        jaccard = intersection / union
        
        # Calculate longest common subsequence ratio for order
        lcs_len = self._lcs_length(lines1, lines2)
        order_sim = lcs_len / max(len(lines1), len(lines2), 1)
        
        # Combine
        return (jaccard + order_sim) / 2
    
    def _lcs_length(self, seq1: list[str], seq2: list[str]) -> int:
        """Compute length of longest common subsequence."""
        m, n = len(seq1), len(seq2)
        
        if m == 0 or n == 0:
            return 0
        
        # Optimized for memory
        prev = [0] * (n + 1)
        curr = [0] * (n + 1)
        
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if seq1[i - 1] == seq2[j - 1]:
                    curr[j] = prev[j - 1] + 1
                else:
                    curr[j] = max(prev[j], curr[j - 1])
            prev, curr = curr, prev
        
        return prev[n]
    
    async def get_clusters(
        self,
        min_count: int = 1,
        sort_by: str = "count",
        severity_filter: CrashSeverity | None = None,
    ) -> list[CrashCluster]:
        """Get crash clusters.
        
        Args:
            min_count: Minimum crash count
            sort_by: Sort field (count, last_seen, severity)
            severity_filter: Filter by minimum severity
            
        Returns:
            List of matching clusters
        """
        clusters = []
        
        for cluster in self._clusters.values():
            # Apply filters
            if cluster.count < min_count:
                continue
            
            if severity_filter:
                if cluster.max_severity.value < severity_filter.value:
                    continue
            
            clusters.append(cluster)
        
        # Sort
        if sort_by == "count":
            clusters.sort(key=lambda c: c.count, reverse=True)
        elif sort_by == "last_seen":
            clusters.sort(key=lambda c: c.last_seen or datetime.min, reverse=True)
        elif sort_by == "severity":
            clusters.sort(key=lambda c: c.max_severity.value, reverse=True)
        
        return clusters
    
    async def get_cluster(self, cluster_id: str) -> CrashCluster | None:
        """Get a specific cluster."""
        return self._clusters.get(cluster_id)
    
    async def get_report(self, report_id: str) -> CrashReport | None:
        """Get a specific crash report."""
        return self._report_index.get(report_id)
    
    async def get_device_crashes(self, device_id: str) -> list[CrashReport]:
        """Get all crash reports from a device."""
        cluster_id = self._device_index.get(device_id)
        if not cluster_id:
            return []
        
        cluster = self._clusters.get(cluster_id)
        if not cluster:
            return []
        
        return [r for r in cluster.reports if r.device_id == device_id]
    
    async def analyze_new_crashes(self) -> dict[str, Any]:
        """Analyze newly discovered crash types.
        
        Returns:
            Analysis report for new crash clusters
        """
        new_clusters = [c for c in self._clusters.values() if c.is_new and c.count >= 3]
        
        analysis = {
            "new_crash_types": [],
            "anomaly_clusters": [],
            "critical_count": 0,
            "new_device_count": len(set(r.device_id for c in new_clusters for r in c.reports)),
        }
        
        for cluster in new_clusters:
            if cluster.max_severity == CrashSeverity.CRITICAL:
                analysis["critical_count"] += 1
            
            cluster.is_new = False  # Mark as analyzed
            self._known_fingerprints.add(cluster.fingerprint)
            
            analysis["new_crash_types"].append({
                "cluster_id": cluster.cluster_id,
                "count": cluster.count,
                "severity": cluster.max_severity.value,
                "sample_message": cluster.representative.message if cluster.representative else "",
                "affected_firmware": list(cluster.firmware_versions),
            })
        
        # Find anomalies (outliers)
        for cluster in self._clusters.values():
            if cluster.is_anomaly:
                analysis["anomaly_clusters"].append(cluster.cluster_id)
        
        logger.info(
            "new_crashes_analyzed",
            new_types=len(analysis["new_crash_types"]),
            anomalies=len(analysis["anomaly_clusters"]),
        )
        
        return analysis
    
    async def get_statistics(self) -> dict[str, Any]:
        """Get fleet-wide crash statistics."""
        total_clusters = len(self._clusters)
        total_reports = self._total_reports
        
        severity_dist = {}
        for severity in CrashSeverity:
            severity_dist[severity.value] = sum(
                c.severity_counts.get(severity, 0)
                for c in self._clusters.values()
            )
        
        return {
            "total_reports": total_reports,
            "total_clusters": total_clusters,
            "unique_devices": len(self._device_index),
            "severity_distribution": severity_dist,
            "new_clusters": sum(1 for c in self._clusters.values() if c.is_new),
            "anomaly_clusters": sum(1 for c in self._clusters.values() if c.is_anomaly),
            "top_clusters": [
                {
                    "cluster_id": c.cluster_id,
                    "count": c.count,
                    "severity": c.max_severity.value,
                }
                for c in sorted(
                    self._clusters.values(),
                    key=lambda x: x.count,
                    reverse=True
                )[:5]
            ],
        }
    
    async def find_root_cause(self, cluster_id: str) -> str:
        """Attempt to determine root cause for a cluster."""
        cluster = self._clusters.get(cluster_id)
        if not cluster or not cluster.representative:
            return "Unknown"
        
        report = cluster.representative
        
        # Analyze based on source
        if report.source == CrashSource.HARD_FAULT:
            # Analyze fault type
            if "NMI" in report.message:
                return "NMI interrupt triggered (hardware/watchdog)"
            elif "MemManage" in report.message:
                return "Memory management fault (invalid memory access)"
            elif "BusFault" in report.message:
                return "Bus fault (prefetch/data abort)"
            elif "UsageFault" in report.message:
                return "Usage fault (illegal instruction/division)"
        
        elif report.source == CrashSource.ASSERT_FAIL:
            # Extract assertion that failed
            match = re.search(r'assert.*\((.*?)\)', report.message, re.IGNORECASE)
            if match:
                return f"Assertion failed: {match.group(1)}"
            return "Assertion failure"
        
        elif report.source == CrashSource.WATCHDOG:
            return "Watchdog timeout (task starvation/deadlock)"
        
        elif report.source == CrashSource.MEM_FAULT:
            if report.fault_address == 0:
                return "NULL pointer dereference"
            elif report.fault_address < 0x20000000:
                return f"Invalid memory access to 0x{report.fault_address:08X} (stack/heap)"
            else:
                return f"Invalid peripheral access to 0x{report.fault_address:08X}"
        
        # Look at first few stack frames
        if report.stack_trace:
            frames = report.stack_trace[:3]
            return f"Likely caused by: {' -> '.join(frames)}"
        
        return "Unable to determine root cause"


# Utility functions

def create_crash_report(
    device_id: str,
    firmware_version: str,
    source: CrashSource,
    message: str,
    stack_trace: list[str],
    **kwargs,
) -> CrashReport:
    """Create a crash report with common defaults."""
    import uuid
    
    return CrashReport(
        report_id=str(uuid.uuid4()),
        device_id=device_id,
        firmware_version=firmware_version,
        source=source,
        severity=CrashSeverity.ERROR,
        message=message,
        stack_trace=stack_trace,
        timestamp=datetime.now(),
        **kwargs,
    )


if __name__ == "__main__":
    print("Fleet Crash Clustering")
    print("=" * 40)
    print("Grouping similar crash reports from multiple devices")
    print()
    print("Features:")
    print("  - Stack trace normalization")
    print("  - Similarity-based grouping")
    print("  - Root cause analysis")
    print("  - Anomaly detection")
    print("  - Fleet-wide statistics")

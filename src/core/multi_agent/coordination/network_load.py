"""
Network Load Reporter.

Provides network I/O reporting for workers:
- RTT (round-trip time)
- Bandwidth estimation
- Packet loss rate
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class NetworkMetrics:
    """Network metrics for a worker."""
    worker_id: str
    timestamp: datetime
    rtt_ms: float
    bandwidth_mbps: float
    packet_loss_rate: float
    upload_bytes: int = 0
    download_bytes: int = 0
    active_connections: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkerLoadProfile:
    """Aggregated load profile for a worker."""
    worker_id: str
    avg_rtt_ms: float
    p50_rtt_ms: float
    p99_rtt_ms: float
    avg_bandwidth_mbps: float
    avg_packet_loss_rate: float
    score: float  # Lower is better
    last_updated: datetime


class NetworkLoadReporter:
    """
    Reports and manages network load from workers.
    
    Features:
    - RTT measurement via echo requests
    - Bandwidth estimation
    - Packet loss rate tracking
    - Worker scoring for load balancing
    
    Usage:
    - Workers report metrics periodically
    - Coordinator uses metrics for task routing
    - Backpressure adjusts based on load
    """
    
    def __init__(
        self,
        rtt_weight: float = 0.5,
        bandwidth_weight: float = 0.3,
        packet_loss_weight: float = 0.2,
        history_window_seconds: int = 60,
        healthy_rtt_threshold_ms: float = 100.0,
        degraded_rtt_threshold_ms: float = 500.0,
    ):
        self.rtt_weight = rtt_weight
        self.bandwidth_weight = bandwidth_weight
        self.packet_loss_weight = packet_loss_weight
        self.history_window = history_window_seconds
        self.healthy_rtt = healthy_rtt_threshold_ms
        self.degraded_rtt = degraded_rtt_threshold_ms
        
        # Metrics storage
        self._metrics: Dict[str, List[NetworkMetrics]] = defaultdict(list)
        self._worker_scores: Dict[str, float] = {}
        self._lock = asyncio.Lock()
    
    async def report_metrics(
        self,
        worker_id: str,
        rtt_ms: float,
        bandwidth_mbps: float,
        packet_loss_rate: float,
        upload_bytes: int = 0,
        download_bytes: int = 0,
        active_connections: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> WorkerLoadProfile:
        """Report network metrics from a worker."""
        metrics = NetworkMetrics(
            worker_id=worker_id,
            timestamp=datetime.now(),
            rtt_ms=rtt_ms,
            bandwidth_mbps=bandwidth_mbps,
            packet_loss_rate=packet_loss_rate,
            upload_bytes=upload_bytes,
            download_bytes=download_bytes,
            active_connections=active_connections,
            metadata=metadata or {},
        )
        
        async with self._lock:
            self._metrics[worker_id].append(metrics)
            
            # Trim old metrics
            cutoff = datetime.now().timestamp() - self.history_window
            self._metrics[worker_id] = [
                m for m in self._metrics[worker_id]
                if m.timestamp.timestamp() > cutoff
            ]
            
            # Calculate score
            profile = await self._calculate_profile(worker_id)
            self._worker_scores[worker_id] = profile.score
            
            return profile
    
    async def _calculate_profile(self, worker_id: str) -> WorkerLoadProfile:
        """Calculate aggregated load profile for worker."""
        metrics = self._metrics.get(worker_id, [])
        
        if not metrics:
            return WorkerLoadProfile(
                worker_id=worker_id,
                avg_rtt_ms=0,
                p50_rtt_ms=0,
                p99_rtt_ms=0,
                avg_bandwidth_mbps=0,
                avg_packet_loss_rate=0,
                score=float('inf'),
                last_updated=datetime.now(),
            )
        
        rtt_values = [m.rtt_ms for m in metrics]
        bandwidth_values = [m.bandwidth_mbps for m in metrics]
        loss_values = [m.packet_loss_rate for m in metrics]
        
        rtt_values.sort()
        
        # Calculate percentiles
        p50_idx = len(rtt_values) // 2
        p99_idx = int(len(rtt_values) * 0.99)
        
        avg_rtt = sum(rtt_values) / len(rtt_values)
        avg_bandwidth = sum(bandwidth_values) / len(bandwidth_values)
        avg_loss = sum(loss_values) / len(loss_values)
        
        # Calculate score (lower is better)
        # Normalize metrics to 0-1 range
        rtt_score = min(1.0, avg_rtt / self.degraded_rtt)
        bandwidth_score = max(0, 1.0 - avg_bandwidth / 1000)  # Assume 1 Gbps max
        loss_score = min(1.0, avg_loss * 10)  # 10% loss = 1.0
        
        score = (
            rtt_score * self.rtt_weight +
            bandwidth_score * self.bandwidth_weight +
            loss_score * self.packet_loss_weight
        )
        
        return WorkerLoadProfile(
            worker_id=worker_id,
            avg_rtt_ms=avg_rtt,
            p50_rtt_ms=rtt_values[p50_idx] if rtt_values else 0,
            p99_rtt_ms=rtt_values[p99_idx] if len(rtt_values) > p99_idx else rtt_values[-1],
            avg_bandwidth_mbps=avg_bandwidth,
            avg_packet_loss_rate=avg_loss,
            score=score,
            last_updated=datetime.now(),
        )
    
    async def get_worker_score(self, worker_id: str) -> float:
        """Get load score for a worker."""
        async with self._lock:
            return self._worker_scores.get(worker_id, float('inf'))
    
    async def get_best_worker(
        self,
        worker_ids: List[str],
        exclude_degraded: bool = True,
    ) -> Optional[str]:
        """
        Get the best worker based on load scores.
        
        Returns worker with lowest score (best network conditions).
        """
        async with self._lock:
            candidates = []
            
            for worker_id in worker_ids:
                score = self._worker_scores.get(worker_id, float('inf'))
                if exclude_degraded:
                    profile = await self._calculate_profile(worker_id)
                    if profile.avg_rtt_ms > self.degraded_rtt:
                        continue
                candidates.append((score, worker_id))
            
            if not candidates:
                return None
            
            candidates.sort()
            return candidates[0][1]
    
    async def get_worker_profiles(
        self,
        worker_ids: Optional[List[str]] = None,
    ) -> Dict[str, WorkerLoadProfile]:
        """Get load profiles for workers."""
        profiles = {}
        
        async with self._lock:
            workers = worker_ids or list(self._metrics.keys())
            
            for worker_id in workers:
                profiles[worker_id] = await self._calculate_profile(worker_id)
        
        return profiles
    
    async def get_sorted_workers(
        self,
        worker_ids: List[str],
    ) -> List[str]:
        """Get workers sorted by load score (best first)."""
        scores = []
        
        for worker_id in worker_ids:
            score = await self.get_worker_score(worker_id)
            scores.append((score, worker_id))
        
        scores.sort()
        return [w for _, w in scores]
    
    async def get_aggregate_metrics(self) -> Dict[str, Any]:
        """Get aggregate metrics across all workers."""
        async with self._lock:
            all_rtt = []
            all_bandwidth = []
            all_loss = []
            
            for metrics in self._metrics.values():
                for m in metrics:
                    all_rtt.append(m.rtt_ms)
                    all_bandwidth.append(m.bandwidth_mbps)
                    all_loss.append(m.packet_loss_rate)
            
            return {
                "total_workers": len(self._metrics),
                "avg_rtt_ms": sum(all_rtt) / len(all_rtt) if all_rtt else 0,
                "max_rtt_ms": max(all_rtt) if all_rtt else 0,
                "avg_bandwidth_mbps": sum(all_bandwidth) / len(all_bandwidth) if all_bandwidth else 0,
                "avg_packet_loss": sum(all_loss) / len(all_loss) if all_loss else 0,
                "healthy_workers": sum(
                    1 for s in self._worker_scores.values()
                    if s < 0.5  # Arbitrary threshold
                ),
            }

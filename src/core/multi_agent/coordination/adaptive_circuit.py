"""
Adaptive Circuit Breaker Error Classification.

Features:
- Adaptive error classification based on historical learning
- Error cardinality analysis
- ML-based severity prediction
- Configurable per-error-type behavior
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class AdaptiveErrorType(str, Enum):
    """Adaptive error types with context awareness."""
    # Temporary errors
    TEMP_TRANSIENT = "temp_transient"       # Likely to recover
    TEMP_RATE_LIMIT = "temp_rate_limit"    # Retry with backoff
    TEMP_TIMEOUT_SHORT = "temp_timeout_short"  # Network hiccup
    
    # Serious errors
    SERIOUS_5XX = "serious_5xx"           # Server error
    SERIOUS_CONNECTION = "serious_connection"  # Network failure
    SERIOUS_RESOURCE = "serious_resource"   # Out of resources
    SERIOUS_TIMEOUT_LONG = "serious_timeout_long"  # Service hung
    
    # Critical errors
    CRITICAL_PANIC = "critical_panic"      # Service panic
    CRITICAL_CORRUPTION = "critical_corruption"  # Data corruption
    CRITICAL_SECURITY = "critical_security"  # Security incident
    CRITICAL_DEADLOCK = "critical_deadlock"  # Deadlock detected


@dataclass
class ErrorSignature:
    """Signature of an error for pattern matching."""
    error_type: str
    error_message: str
    service: str
    endpoint: Optional[str] = None
    status_code: Optional[int] = None
    error_category: str = "unknown"


@dataclass
class ErrorClassification:
    """Result of adaptive error classification."""
    error_type: AdaptiveErrorType
    severity_score: float  # 0-1, how serious
    retry_recommended: bool
    breaker_action: str  # trip, count, ignore
    confidence: float  # 0-1
    factors: List[str]  # Why this classification
    historical_similarity: float  # How similar to past errors


@dataclass
class ErrorCardinalityMetrics:
    """Metrics for error cardinality analysis."""
    total_errors: int
    unique_error_signatures: int
    error_entropy: float  # Measure of error diversity
    dominant_error_type: Optional[str]
    error_distribution: Dict[str, int]
    burst_detected: bool
    anomaly_score: float


class AdaptiveCircuitErrorClassifier:
    """
    Adaptive circuit breaker error classification.
    
    Features:
    - Historical failure learning
    - Error cardinality analysis
    - Context-aware severity scoring
    - Configurable per-error-type behavior
    """
    
    # Error patterns with context awareness
    PATTERNS = {
        # Transient errors (retry recommended)
        AdaptiveErrorType.TEMP_TRANSIENT: {
            "patterns": ["timeout", "temporary", "unavailable"],
            "status_codes": [408, 502, 503, 504],
            "retry": True,
            "severity": 0.2,
        },
        AdaptiveErrorType.TEMP_RATE_LIMIT: {
            "patterns": ["rate limit", "too many requests", "429", "backoff"],
            "status_codes": [429],
            "retry": True,
            "severity": 0.3,
        },
        AdaptiveErrorType.TEMP_TIMEOUT_SHORT: {
            "patterns": ["timeout", "timed out", "connection reset"],
            "status_codes": [],
            "retry": True,
            "severity": 0.25,
            "max_duration_ms": 5000,  # Short timeout
        },
        
        # Serious errors (may trip breaker)
        AdaptiveErrorType.SERIOUS_5XX: {
            "patterns": ["500", "internal error", "server error"],
            "status_codes": [500, 501, 502, 503, 504],
            "retry": False,
            "severity": 0.6,
        },
        AdaptiveErrorType.SERIOUS_CONNECTION: {
            "patterns": ["connection refused", "network", "unreachable"],
            "status_codes": [],
            "retry": False,
            "severity": 0.7,
        },
        AdaptiveErrorType.SERIOUS_RESOURCE: {
            "patterns": ["out of memory", "oom", "disk full", "too many connections"],
            "status_codes": [],
            "retry": False,
            "severity": 0.8,
        },
        AdaptiveErrorType.SERIOUS_TIMEOUT_LONG: {
            "patterns": ["timeout", "timed out"],
            "status_codes": [],
            "retry": False,
            "severity": 0.65,
            "min_duration_ms": 30000,  # Long timeout
        },
        
        # Critical errors (always trip)
        AdaptiveErrorType.CRITICAL_PANIC: {
            "patterns": ["panic", "crash", "assertion failed", "segfault"],
            "status_codes": [],
            "retry": False,
            "severity": 1.0,
        },
        AdaptiveErrorType.CRITICAL_CORRUPTION: {
            "patterns": ["corruption", "checksum", "invalid data", "parse error"],
            "status_codes": [],
            "retry": False,
            "severity": 1.0,
        },
        AdaptiveErrorType.CRITICAL_SECURITY: {
            "patterns": ["unauthorized", "forbidden", "authentication", "ssl"],
            "status_codes": [401, 403],
            "retry": False,
            "severity": 1.0,
        },
        AdaptiveErrorType.CRITICAL_DEADLOCK: {
            "patterns": ["deadlock", "circular", "cyclic dependency"],
            "status_codes": [],
            "retry": False,
            "severity": 1.0,
        },
    }
    
    def __init__(
        self,
        historical_window_seconds: float = 3600.0,
        cardinality_threshold: int = 50,
        burst_detection_window: float = 60.0,
    ):
        self.historical_window = timedelta(seconds=historical_window_seconds)
        self.cardinality_threshold = cardinality_threshold
        self.burst_window = timedelta(seconds=burst_detection_window)
        
        # Historical error tracking
        self._error_history: List[Tuple[datetime, ErrorSignature, AdaptiveErrorType]] = []
        
        # Cardinality tracking
        self._error_signatures: Dict[str, int] = defaultdict(int)
        self._error_counts_by_type: Dict[AdaptiveErrorType, int] = defaultdict(int)
        
        # ML-like model weights (simplified)
        self._type_weights: Dict[AdaptiveErrorType, float] = {
            et: 1.0 for et in AdaptiveErrorType
        }
        
        # Learning from past behavior
        self._learned_patterns: Dict[str, AdaptiveErrorType] = {}
        
        self._lock = asyncio.Lock()
    
    async def classify(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
    ) -> ErrorClassification:
        """
        Classify error with adaptive learning.
        
        Args:
            error: The exception to classify
            context: Additional context (duration, status_code, service, etc.)
        """
        context = context or {}
        
        # Build error signature
        signature = self._build_signature(error, context)
        
        # Check if we've seen similar errors
        historical_type = await self._check_historical(signature)
        
        # Determine error type
        error_type, factors = await self._determine_type(error, signature, context)
        
        # Calculate severity
        severity = await self._calculate_severity(error_type, signature, context)
        
        # Determine retry recommendation
        pattern_info = self.PATTERNS.get(error_type, {})
        retry_recommended = pattern_info.get("retry", False)
        
        # Calculate confidence
        confidence = await self._calculate_confidence(
            error_type, historical_type, signature
        )
        
        # Determine breaker action
        breaker_action = self._determine_breaker_action(error_type, severity)
        
        # Update history
        await self._record_classification(signature, error_type)
        
        return ErrorClassification(
            error_type=error_type,
            severity_score=severity,
            retry_recommended=retry_recommended,
            breaker_action=breaker_action,
            confidence=confidence,
            factors=factors,
            historical_similarity=await self._get_historical_similarity(signature),
        )
    
    def _build_signature(
        self,
        error: Exception,
        context: Dict[str, Any],
    ) -> ErrorSignature:
        """Build error signature for matching."""
        error_str = str(error)
        error_type = type(error).__name__
        
        # Create hash for cardinality tracking
        sig_hash = hashlib.md5(
            f"{error_type}:{error_str}:{context.get('service', 'unknown')}".encode()
        ).hexdigest()[:16]
        
        return ErrorSignature(
            error_type=error_type,
            error_message=error_str[:200],  # Truncate
            service=context.get("service", "unknown"),
            endpoint=context.get("endpoint"),
            status_code=context.get("status_code"),
        )
    
    async def _check_historical(
        self,
        signature: ErrorSignature,
    ) -> Optional[AdaptiveErrorType]:
        """Check historical patterns for similar errors."""
        async with self._lock:
            cutoff = datetime.now() - self.historical_window
            
            for dt, sig, err_type in reversed(self._error_history):
                if dt < cutoff:
                    break
                
                # Similarity check
                if (sig.service == signature.service and
                    sig.error_type == signature.error_type):
                    return err_type
        
        return None
    
    async def _determine_type(
        self,
        error: Exception,
        signature: ErrorSignature,
        context: Dict[str, Any],
    ) -> Tuple[AdaptiveErrorType, List[str]]:
        """Determine error type from patterns and context."""
        error_str = str(error).lower()
        error_type = type(error).__name__.lower()
        factors = []
        
        # Check status code first
        status_code = context.get("status_code")
        if status_code:
            for err_type, info in self.PATTERNS.items():
                if status_code in info.get("status_codes", []):
                    factors.append(f"status_code_{status_code}")
                    return err_type, factors
        
        # Check duration for timeout classification
        duration_ms = context.get("duration_ms", 0)
        
        # Check patterns
        for err_type, info in self.PATTERNS.items():
            for pattern in info.get("patterns", []):
                if pattern.lower() in error_str or pattern.lower() in error_type:
                    factors.append(f"pattern_{pattern}")
                    
                    # Adjust for duration if timeout
                    if "timeout" in err_type.value:
                        max_dur = info.get("max_duration_ms", 0)
                        min_dur = info.get("min_duration_ms", 0)
                        
                        if max_dur and duration_ms < max_dur:
                            return AdaptiveErrorType.TEMP_TIMEOUT_SHORT, factors
                        if min_dur and duration_ms >= min_dur:
                            return AdaptiveErrorType.SERIOUS_TIMEOUT_LONG, factors
                    
                    return err_type, factors
        
        # Default based on exception type
        if "timeout" in error_type:
            return AdaptiveErrorType.TEMP_TRANSIENT, ["exception_type_timeout"]
        if "connection" in error_type.lower():
            return AdaptiveErrorType.SERIOUS_CONNECTION, ["exception_type_connection"]
        
        # Default to transient (optimistic)
        return AdaptiveErrorType.TEMP_TRANSIENT, ["default_classification"]
    
    async def _calculate_severity(
        self,
        error_type: AdaptiveErrorType,
        signature: ErrorSignature,
        context: Dict[str, Any],
    ) -> float:
        """Calculate severity score with context awareness."""
        base_severity = self.PATTERNS.get(error_type, {}).get("severity", 0.5)
        
        # Adjust based on context
        severity = base_severity
        
        # Adjust for error frequency (recency weighted)
        frequency_factor = await self._get_frequency_factor(signature)
        severity = min(1.0, severity + frequency_factor * 0.2)
        
        # Adjust for business impact
        if context.get("business_critical"):
            severity = min(1.0, severity + 0.2)
        
        # Adjust for user impact
        if context.get("user_facing"):
            severity = min(1.0, severity + 0.1)
        
        return severity
    
    async def _get_frequency_factor(self, signature: ErrorSignature) -> float:
        """Get frequency factor based on recent error rate."""
        async with self._lock:
            cutoff = datetime.now() - self.historical_window
            recent_count = sum(
                1 for dt, sig, _ in self._error_history
                if dt >= cutoff and sig.service == signature.service
            )
            
            # Normalize to 0-1
            return min(1.0, recent_count / 100)
    
    async def _calculate_confidence(
        self,
        error_type: AdaptiveErrorType,
        historical_type: Optional[AdaptiveErrorType],
        signature: ErrorSignature,
    ) -> float:
        """Calculate classification confidence."""
        confidence = 0.5  # Base confidence
        
        # Boost if historical matches
        if historical_type == error_type:
            confidence += 0.3
        
        # Boost if pattern matched strongly
        pattern_info = self.PATTERNS.get(error_type, {})
        if pattern_info:
            confidence += 0.1
        
        # Boost if we've seen this signature before
        sig_key = f"{signature.service}:{signature.error_type}"
        if sig_key in self._learned_patterns:
            confidence += 0.1
        
        return min(1.0, confidence)
    
    def _determine_breaker_action(
        self,
        error_type: AdaptiveErrorType,
        severity: float,
    ) -> str:
        """Determine circuit breaker action."""
        # Critical errors always trip
        if error_type in [
            AdaptiveErrorType.CRITICAL_PANIC,
            AdaptiveErrorType.CRITICAL_CORRUPTION,
            AdaptiveErrorType.CRITICAL_SECURITY,
            AdaptiveErrorType.CRITICAL_DEADLOCK,
        ]:
            return "trip"
        
        # Serious errors trip based on severity
        if severity >= 0.7:
            return "trip"
        
        # Medium severity counts but doesn't trip
        if severity >= 0.4:
            return "count"
        
        # Low severity ignored
        return "ignore"
    
    async def _record_classification(
        self,
        signature: ErrorSignature,
        error_type: AdaptiveErrorType,
    ) -> None:
        """Record classification for historical learning."""
        async with self._lock:
            self._error_history.append((datetime.now(), signature, error_type))
            
            # Track cardinality
            sig_key = f"{signature.service}:{signature.error_type}"
            self._error_signatures[sig_key] += 1
            self._error_counts_by_type[error_type] += 1
            
            # Update learned patterns
            if self._error_counts_by_type[error_type] >= 5:
                self._learned_patterns[sig_key] = error_type
            
            # Cleanup old history
            cutoff = datetime.now() - self.historical_window * 2
            self._error_history = [
                (dt, sig, et) for dt, sig, et in self._error_history
                if dt >= cutoff
            ]
    
    async def _get_historical_similarity(self, signature: ErrorSignature) -> float:
        """Get similarity score with historical errors."""
        async with self._lock:
            similar_count = sum(
                1 for _, sig, _ in self._error_history
                if sig.service == signature.service and
                   sig.error_type == signature.error_type
            )
            
            return min(1.0, similar_count / 10)
    
    async def get_cardinality_metrics(self) -> ErrorCardinalityMetrics:
        """Get error cardinality metrics."""
        async with self._lock:
            cutoff = datetime.now() - self.historical_window
            
            # Count recent errors
            recent_errors = [
                (sig, et) for dt, sig, et in self._error_history
                if dt >= cutoff
            ]
            
            # Unique signatures - use error_type string as key
            unique_sigs = set(sig.error_type for sig, _ in recent_errors)
            
            # Error distribution
            distribution = defaultdict(int)
            for _, et in recent_errors:
                distribution[et.value] += 1
            
            # Dominant error type
            dominant = max(distribution.items(), key=lambda x: x[1]) if distribution else (None, 0)
            
            # Burst detection (errors in short window)
            burst_cutoff = datetime.now() - self.burst_window
            burst_count = sum(1 for dt, _, _ in self._error_history if dt >= burst_cutoff)
            
            # Calculate entropy
            total = len(recent_errors) or 1
            entropy = 0.0
            for count in distribution.values():
                p = count / total
                if p > 0:
                    entropy -= p * (p ** 0.5)  # Simplified entropy
            
            # Anomaly score based on cardinality
            anomaly_score = len(unique_sigs) / max(1, self.cardinality_threshold)
            
            return ErrorCardinalityMetrics(
                total_errors=len(recent_errors),
                unique_error_signatures=len(unique_sigs),
                error_entropy=entropy,
                dominant_error_type=dominant[0],
                error_distribution=dict(distribution),
                burst_detected=burst_count > 100,
                anomaly_score=anomaly_score,
            )
    
    async def get_error_summary(self) -> Dict[str, Any]:
        """Get error classification summary."""
        metrics = await self.get_cardinality_metrics()
        
        return {
            "total_classifications": len(self._error_history),
            "unique_patterns_learned": len(self._learned_patterns),
            "cardinality": metrics.unique_error_signatures,
            "dominant_error": metrics.dominant_error_type,
            "burst_detected": metrics.burst_detected,
            "distribution": metrics.error_distribution,
        }

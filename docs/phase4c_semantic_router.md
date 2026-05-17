# Phase 4C – Semantic Router Specification (v8)

**Status**: Implementation Phase
**Date**: 2026-05-17
**Version**: v8 (Final - All Critical Edge-Case Risks Addressed)

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Design Principles](#2-design-principles)
3. [Architecture](#3-architecture)
4. [Immutable RequestContext](#4-immutable-requestcontext)
5. [Exactly-Once WAL](#5-exactly-once-wal)
6. [Read-After-Write Guard](#6-read-after-write-guard)
7. [Fairness Boost Budget](#7-fairness-boost-budget)
8. [Rollback-Safe Lifecycle](#8-rollback-safe-lifecycle)
9. [Score Engine](#9-score-engine)
10. [Policy Engine](#10-policy-engine)
11. [Execution Engine](#11-execution-engine)
12. [Observation Engine](#12-observation-engine)
13. [Data Schema](#13-data-schema)
14. [Configuration](#14-configuration)
15. [File Structure](#15-file-structure)
16. [Done Criteria](#16-done-criteria)

---

## 1. System Overview

### 1.1 Purpose

Build a semantic router that:

- Classifies queries/requests into intents
- Routes to tool, RAG, or handler based on classification
- Uses rule-based, semantic (embedding + ANN), and context boosting from success history
- Guarantees pipeline consistency (snapshot immutability, read-after-write, exactly-once WAL, fairness, rollback-safe lifecycle)

### 1.2 Core Components

```
Request → RequestContext (frozen snapshot) → PolicyEngine → ScoreEngine → ExecutionEngine
                                              ↑
                                       (uses snapshot)
ObservationEngine: WAL + exactly-once + lifecycle rollback
```

### 1.3 Key Guarantees

| Guarantee | Description |
|-----------|-------------|
| Immutable snapshot | Each request has frozen snapshot, no global lookup |
| Exactly-once | Frequency updates applied only once per idempotency key |
| Read-after-write | Consistency guard for feedback propagation |
| Fairness | Boost budget distributed fairly across intents |
| Rollback-safe | Intent lifecycle with auto-restore |

---

## 2. Design Principles

### 2.1 Immutable Snapshot Binding

> Each request has a RequestContext containing a frozen_snapshot (config + index + frequency) materialized once at start and passed through the entire pipeline.

**Rules**:
- Create context at the beginning of `route()`
- Pass context down to all engines
- No access to global state during routing
- All decisions use the same frozen snapshot

### 2.2 Exactly-Once for Frequency Update

> Use event sourcing or atomic `WHERE NOT EXISTS` to ensure each idempotency key is applied exactly once, even on crash.

### 2.3 Read-After-Write Consistency Guard

> When feedback is just written, there may be a maximum delay before the next request sees the change (or mark old snapshot still used but with warning).

### 2.4 Fairness Boost Budget

> Distribute boost budget fairly across intents, cap maximum percentage per intent, ensure no intent is starved.

### 2.5 Rollback-Safe Lifecycle

> When intent is disabled or priority reduced, use TTL to auto-recover if signal improves, avoiding wrong decisions from temporary spikes.

---

## 3. Architecture

### 3.1 Component Hierarchy

```
SemanticRouter
 ├── RequestContextFactory (creates frozen snapshots)
 ├── PolicyEngine (rule-based routing)
 ├── ScoreEngine (semantic scoring)
 │    ├── EmbeddingGenerator
 │    ├── ANNIndex (FAISS/Annoy)
 │    └── BoostCalculator
 ├── ExecutionEngine (dispatch)
 └── ObservationEngine
      ├── FrequencyTracker
      ├── FeedbackProcessor
      ├── WALWriter
      └── LifecycleManager
```

### 3.2 Data Flow

```
1. Request arrives
         ↓
2. RequestContext created with frozen_snapshot
         ↓
3. PolicyEngine evaluates rules (uses snapshot)
         ↓
4. ScoreEngine calculates semantic scores (uses snapshot index)
         ↓
5. PolicyEngine combines scores with boost (uses snapshot frequency)
         ↓
6. ExecutionEngine dispatches to target
         ↓
7. Feedback loop → ObservationEngine → WAL → Frequency update
```

---

## 4. Immutable RequestContext

### 4.1 Snapshot Structure

```python
@dataclass
class Snapshot:
    """Frozen snapshot used for entire request pipeline."""
    
    snapshot_id: str                          # Unique identifier
    config: RouterConfig                      # Frozen configuration
    index: ANNIndex                           # Read-only ANN index
    frequency_version: int                    # Frequency table version
    freq_snapshot_time: float                 # When frequency was snapshotted
    created_at: float                         # Snapshot creation time
    
    # Derived from snapshot
    @property
    def intent_table(self) -> dict[str, IntentConfig]:
        return self.config.intents


@dataclass
class RequestContext:
    """
    Immutable request context containing frozen snapshot.
    Created once at route() start, passed through entire pipeline.
    """
    
    context_id: str                           # UUID for tracing
    snapshot_id: str                          # Reference to snapshot
    frozen_snapshot: Snapshot                 # Frozen snapshot (immutable)
    start_time: float                         # Request start time
    request: Request                          # Original request
    metadata: dict[str, Any]                  # Additional metadata
    
    # No setters - context is immutable
    def with_metadata(self, key: str, value: Any) -> "RequestContext":
        """Return new context with additional metadata (immutable)."""
        return RequestContext(
            context_id=self.context_id,
            snapshot_id=self.snapshot_id,
            frozen_snapshot=self.frozen_snapshot,
            start_time=self.start_time,
            request=self.request,
            metadata={**self.metadata, key: value}
        )
```

### 4.2 Snapshot Creation

```python
class SnapshotManager:
    """
    Manages snapshot lifecycle and creation.
    """
    
    def __init__(self, config_store: ConfigStore, frequency_store: FrequencyStore):
        self.config_store = config_store
        self.frequency_store = frequency_store
        self._current_snapshot: Optional[Snapshot] = None
        self._snapshot_lock = asyncio.Lock()
    
    async def create_snapshot(self) -> Snapshot:
        """
        Create new frozen snapshot.
        Called when:
        1. First request
        2. Config changed
        3. Index rebuilt
        4. Force refresh after feedback
        """
        async with self._snapshot_lock:
            # Materialize all components at this moment
            config = await self.config_store.get_config()
            frequency_version = await self.frequency_store.get_version()
            freq_snapshot_time = time.time()
            
            # Load ANN index (read-only copy)
            index = await self._load_index()
            
            snapshot = Snapshot(
                snapshot_id=str(uuid.uuid4()),
                config=config,
                index=index,
                frequency_version=frequency_version,
                freq_snapshot_time=freq_snapshot_time,
                created_at=time.time()
            )
            
            self._current_snapshot = snapshot
            return snapshot
    
    async def get_current_snapshot(self) -> Snapshot:
        """Get current snapshot or create new one."""
        if self._current_snapshot is None:
            return await self.create_snapshot()
        return self._current_snapshot
    
    async def force_new_snapshot(self, reason: str) -> Snapshot:
        """Force create new snapshot (e.g., after feedback)."""
        logger.info(f"Forcing new snapshot: {reason}")
        return await self.create_snapshot()
```

### 4.3 Context Propagation

```python
class SemanticRouter:
    def __init__(self, snapshot_manager: SnapshotManager, ...):
        self.snapshot_manager = snapshot_manager
    
    async def route(self, request: Request) -> RouteResult:
        """
        Main routing entry point.
        Creates immutable context once and passes through pipeline.
        """
        # Step 1: Create immutable context with frozen snapshot
        snapshot = await self.snapshot_manager.get_current_snapshot()
        
        context = RequestContext(
            context_id=str(uuid.uuid4()),
            snapshot_id=snapshot.snapshot_id,
            frozen_snapshot=snapshot,
            start_time=time.time(),
            request=request,
            metadata={}
        )
        
        # Step 2: Policy engine (uses context.frozen_snapshot)
        policy_result = await self._policy_engine.evaluate(context)
        
        # Step 3: If semantic needed, score engine (uses context.frozen_snapshot)
        if policy_result.needs_semantic:
            scores = await self._score_engine.calculate_scores(context)
            policy_result.scores = scores
        
        # Step 4: Execution
        result = await self._execution_engine.execute(context, policy_result)
        
        return result
    
    async def _policy_engine_evaluate(self, context: RequestContext) -> PolicyResult:
        """
        Policy engine uses ONLY context.frozen_snapshot.
        No access to global state.
        """
        snapshot = context.frozen_snapshot  # Frozen snapshot
        
        # Evaluate rules using snapshot.config
        for rule in snapshot.config.rules:
            if rule.matches(context.request):
                return PolicyResult(
                    intent=rule.intent,
                    confidence=rule.confidence,
                    needs_semantic=rule.needs_semantic
                )
        
        # Default: semantic evaluation needed
        return PolicyResult(needs_semantic=True)
```

### 4.4 Consistency Rules

| Rule | Description |
|------|-------------|
| No global state access | Engines only access `context.frozen_snapshot` |
| Snapshot immutability | Once created, snapshot never modified |
| Single snapshot per request | Request uses one snapshot for entire pipeline |
| Snapshot versioning | Each snapshot has unique ID and version |

---

## 5. Exactly-Once WAL

### 5.1 Problem

Frequency updates must be applied exactly once, even if:
- Crash during processing
- Duplicate feedback
- Network retries

### 5.2 Solution: Idempotency Key + Applied Keys Table

```python
# Tables
class AppliedIdempotencyKeys(Base):
    __tablename__ = "applied_idempotency_keys"
    
    key = Column(String, primary_key=True)
    processed_at = Column(DateTime, nullable=False)


class FrequencyUpdateWAL(Base):
    __tablename__ = "frequency_update_wal"
    
    event_id = Column(String, primary_key=True)
    intent_path = Column(String, nullable=False)
    example_text = Column(String, nullable=False)
    idempotency_key = Column(String, nullable=False)
    timestamp = Column(DateTime, nullable=False)
    processed = Column(Boolean, default=False)
```

### 5.3 Exactly-Once Processing

```python
class ExactlyOnceProcessor:
    """
    Ensures frequency updates are applied exactly once.
    """
    
    def __init__(self, db: Database):
        self.db = db
    
    async def process_feedback(self, feedback: Feedback) -> bool:
        """
        Process feedback with exactly-once guarantee.
        
        Returns:
            True if processed (new)
            False if already processed (idempotent)
        """
        # Step 1: Generate idempotency key
        idempotency_key = self._generate_idempotency_key(feedback)
        
        # Step 2: Insert into WAL first (for audit/replay)
        await self._write_to_wal(feedback, idempotency_key)
        
        # Step 3: Atomic insert into applied keys
        inserted = await self._insert_applied_key_atomic(idempotency_key)
        
        if not inserted:
            # Already processed - idempotent behavior
            logger.debug(f"Feedback already processed: {idempotency_key}")
            return False
        
        # Step 4: Apply frequency update
        try:
            await self._update_frequency(feedback)
            await self._mark_wal_processed(feedback.event_id)
            await self._increment_frequency_version()
            return True
        except Exception as e:
            # Rollback applied key on failure
            await self._rollback_applied_key(idempotency_key)
            raise
    
    def _generate_idempotency_key(self, feedback: Feedback) -> str:
        """
        Generate deterministic idempotency key from feedback.
        Same feedback components = same key.
        """
        # Normalize timestamp to day to handle retries within same day
        day_bucket = int(feedback.timestamp / 86400) * 86400
        
        payload = f"{feedback.query}|{feedback.intent_path}|{feedback.example_text}|{day_bucket}"
        return hashlib.sha256(payload.encode()).hexdigest()
    
    async def _insert_applied_key_atomic(self, key: str) -> bool:
        """
        Atomic insert with conflict detection.
        Returns True if inserted (new), False if exists.
        """
        query = text("""
            INSERT INTO applied_idempotency_keys (key, processed_at)
            VALUES (:key, :processed_at)
            ON CONFLICT (key) DO NOTHING
            RETURNING key
        """)
        
        result = await self.db.execute(
            query,
            {"key": key, "processed_at": datetime.utcnow()}
        )
        
        # If no rows returned, key already existed
        return result.rowcount > 0
    
    async def _update_frequency(self, feedback: Feedback):
        """
        Update example frequency.
        Uses ON CONFLICT for first-time inserts.
        """
        query = text("""
            INSERT INTO example_frequency (intent_path, example_hash, frequency, last_used)
            VALUES (:intent_path, :example_hash, 1, :now)
            ON CONFLICT (intent_path, example_hash)
            DO UPDATE SET
                frequency = example_frequency.frequency + 1,
                last_used = :now
        """)
        
        await self.db.execute(query, {
            "intent_path": feedback.intent_path,
            "example_hash": hashlib.sha256(feedback.example_text.encode()).hexdigest(),
            "now": datetime.utcnow()
        })
    
    async def _increment_frequency_version(self):
        """Increment global frequency version after update."""
        query = text("""
            UPDATE router_metadata
            SET frequency_version = frequency_version + 1,
                last_updated = :now
            WHERE key = 'global'
        """)
        await self.db.execute(query, {"now": datetime.utcnow()})
```

### 5.4 WAL Replay

```python
class WALReplayer:
    """
    Replay unprocessed WAL events after crash.
    """
    
    async def replay_unprocessed(self):
        """Replay all unprocessed WAL events."""
        query = text("""
            SELECT event_id, intent_path, example_text, idempotency_key
            FROM frequency_update_wal
            WHERE processed = FALSE
            ORDER BY timestamp ASC
        """)
        
        events = await self.db.fetch_all(query)
        
        for event in events:
            try:
                await self._replay_event(event)
            except Exception as e:
                logger.error(f"Failed to replay event {event['event_id']}: {e}")
        
        logger.info(f"Replayed {len(events)} WAL events")
    
    async def _replay_event(self, event: dict):
        """Replay single event with idempotency check."""
        feedback = Feedback(
            intent_path=event["intent_path"],
            example_text=event["example_text"],
            timestamp=event["timestamp"].timestamp()
        )
        
        processor = ExactlyOnceProcessor(self.db)
        await processor.process_feedback(feedback)
        
        await self.db.execute(
            text("UPDATE frequency_update_wal SET processed = TRUE WHERE event_id = :id"),
            {"id": event["event_id"]}
        )
```

---

## 6. Read-After-Write Guard

### 6.1 Problem

When `report_feedback` succeeds, the frequency_version is incremented. A subsequent request immediately arriving may or may not see this change depending on snapshot timing.

### 6.2 Configuration

```python
@dataclass
class ConsistencyConfig:
    """Configuration for read-after-write consistency."""
    
    # Maximum delay before changes are visible
    read_after_write_guard_ms: int = 5000
    
    # Force new snapshot creation after feedback
    force_new_snapshot_on_feedback: bool = False
    
    # Log warning when using stale snapshot after feedback
    warn_on_stale_snapshot: bool = True
```

### 6.3 Implementation

```python
class ReadAfterWriteGuard:
    """
    Ensures read-after-write consistency with configurable behavior.
    """
    
    def __init__(self, config: ConsistencyConfig, snapshot_manager: SnapshotManager):
        self.config = config
        self.snapshot_manager = snapshot_manager
        self._last_feedback_time: Optional[float] = None
        self._feedback_lock = asyncio.Lock()
    
    async def on_feedback_written(self):
        """Called after feedback successfully written."""
        async with self._feedback_lock:
            self._last_feedback_time = time.time()
    
    async def should_force_new_snapshot(self) -> tuple[bool, Optional[str]]:
        """
        Check if new snapshot should be created.
        
        Returns:
            (should_force, reason)
        """
        if not self._last_feedback_time:
            return False, None
        
        elapsed_ms = (time.time() - self._last_feedback_time) * 1000
        
        if elapsed_ms < self.config.read_after_write_guard_ms:
            if self.config.force_new_snapshot_on_feedback:
                return True, f"Feedback at {elapsed_ms:.0f}ms ago, forcing new snapshot"
            else:
                # Log warning but don't force
                if self.config.warn_on_stale_snapshot:
                    logger.warning(
                        f"Using potentially stale snapshot: "
                        f"feedback written {elapsed_ms:.0f}ms ago"
                    )
                return False, None
        
        return False, None
    
    async def after_feedback(
        self,
        snapshot_manager: SnapshotManager
    ) -> Optional[Snapshot]:
        """
        After feedback is written, potentially create new snapshot.
        """
        should_force, reason = await self.should_force_new_snapshot()
        
        if should_force:
            return await snapshot_manager.force_new_snapshot(reason)
        
        return None


class FeedbackProcessor:
    """Processes feedback with read-after-write guard."""
    
    def __init__(
        self,
        exactly_once: ExactlyOnceProcessor,
        consistency_guard: ReadAfterWriteGuard,
        snapshot_manager: SnapshotManager
    ):
        self.exactly_once = exactly_once
        self.consistency_guard = consistency_guard
        self.snapshot_manager = snapshot_manager
    
    async def report_feedback(self, feedback: Feedback) -> FeedbackResult:
        """
        Report feedback with exactly-once guarantee.
        """
        # Step 1: Process with exactly-once
        is_new = await self.exactly_once.process_feedback(feedback)
        
        if not is_new:
            return FeedbackResult(success=True, was_idempotent=True)
        
        # Step 2: Notify consistency guard
        await self.consistency_guard.on_feedback_written()
        
        # Step 3: Check if should force new snapshot
        new_snapshot = await self.consistency_guard.after_feedback(
            self.snapshot_manager
        )
        
        return FeedbackResult(
            success=True,
            was_idempotent=False,
            new_snapshot_id=new_snapshot.snapshot_id if new_snapshot else None
        )
```

### 6.4 Behavior Matrix

| Scenario | Behavior |
|----------|----------|
| Feedback written, request < 5s later | Log warning, use old snapshot |
| Feedback written, request < 5s, force=true | Create new snapshot |
| Feedback written, request >= 5s | Use current snapshot normally |

---

## 7. Fairness Boost Budget

### 7.1 Problem

Without fairness, high-traffic intents can consume all boost budget, starving low-traffic intents.

### 7.2 Solution: Per-Intent Budget Cap

```python
@dataclass
class BoostFairnessConfig:
    """Configuration for boost budget fairness."""
    
    enabled: bool = True
    
    # Maximum percentage of global budget per intent
    per_intent_weight_cap: float = 0.30  # 30%
    
    # Minimum share per intent (prevent starvation)
    min_share_per_intent: float = 0.01  # 1%
    
    # Global boost budget per second
    global_boost_per_second: int = 1000


class FairnessBoostCalculator:
    """
    Calculates boost with fairness constraints.
    """
    
    def __init__(self, config: BoostFairnessConfig):
        self.config = config
        self._intent_usage: dict[str, float] = {}  # Intent → usage this second
        self._usage_reset_time = time.time()
        self._lock = asyncio.Lock()
    
    async def calculate_boost(
        self,
        intent: str,
        base_score: float,
        max_intent_boost: float
    ) -> float:
        """
        Calculate fair boost for intent.
        """
        if not self.config.enabled:
            return base_score
        
        await self._reset_if_needed()
        await self._lock.acquire()
        
        try:
            # Get current usage for intent
            current_usage = self._intent_usage.get(intent, 0.0)
            
            # Calculate max budget for this intent
            max_this_intent = self.config.global_boost_per_second * self.config.per_intent_weight_cap
            
            # Check if intent exceeded its cap
            if current_usage >= max_this_intent:
                # Intent exhausted its budget
                logger.debug(f"Intent {intent} exhausted boost budget")
                return base_score  # No boost
            
            # Calculate available budget
            available = max_this_intent - current_usage
            
            # Calculate effective boost (capped by available)
            effective_boost = min(max_intent_boost, available)
            
            # Ensure minimum share
            effective_boost = max(effective_boost, max_intent_boost * self.config.min_share_per_intent)
            
            # Update usage
            self._intent_usage[intent] = current_usage + effective_boost
            
            return base_score + effective_boost
            
        finally:
            self._lock.release()
    
    async def _reset_if_needed(self):
        """Reset usage counters every second."""
        now = time.time()
        if now - self._usage_reset_time >= 1.0:
            self._intent_usage.clear()
            self._usage_reset_time = now
```

### 7.3 Integration with Policy Engine

```python
class PolicyEngine:
    def __init__(
        self,
        fairness_config: BoostFairnessConfig,
        ...
    ):
        self.fairness = FairnessBoostCalculator(fairness_config)
    
    async def calculate_final_score(
        self,
        context: RequestContext,
        intent: str,
        semantic_score: float
    ) -> float:
        """
        Calculate final score combining semantic + boost.
        """
        snapshot = context.frozen_snapshot
        
        # Get base score from config
        intent_config = snapshot.config.intents.get(intent)
        base_score = intent_config.base_score if intent_config else 0.5
        
        # Get frequency-based boost
        frequency = await self._get_frequency_boost(context, intent)
        
        # Apply fairness cap to frequency boost
        fair_boost = await self.fairness.calculate_boost(
            intent=intent,
            base_score=base_score,
            max_intent_boost=frequency
        )
        
        # Combine scores
        final_score = semantic_score * 0.7 + base_score * 0.2 + fair_boost * 0.1
        
        return final_score
    
    async def _get_frequency_boost(
        self,
        context: RequestContext,
        intent: str
    ) -> float:
        """
        Get frequency-based boost from snapshot.
        """
        snapshot = context.frozen_snapshot
        
        # Query frequency from snapshot
        frequency = snapshot.config.frequencies.get(intent, 0)
        
        # Convert to boost (logarithmic scale)
        return math.log(1 + frequency) / 10.0
```

### 7.4 Fairness Guarantees

| Guarantee | Description |
|-----------|-------------|
| Per-intent cap | No intent exceeds 30% of global budget |
| Minimum share | Every intent guaranteed at least 1% |
| No starvation | Low-traffic intents can accumulate budget |
| Transparent | Intent usage logged for debugging |

---

## 8. Rollback-Safe Lifecycle

### 8.1 Problem

When an intent is disabled due to poor health, we need:
- TTL to auto-recover if condition improves
- Avoid wrong decisions from temporary spikes
- Graceful re-enablement based on health metrics

### 8.2 Intent Lifecycle States

```python
class IntentLifecycleState(Enum):
    ACTIVE = "active"           # Normal operation
    DISABLED = "disabled"        # Manually or auto disabled
    PENDING_RESTORE = "pending"  # TTL expired, awaiting health check
    RESTORED = "restored"        # Just restored, monitoring


@dataclass
class IntentLifecycle:
    """Lifecycle state for an intent."""
    
    intent_path: str
    state: IntentLifecycleState
    disabled_at: Optional[float] = None
    disable_ttl_seconds: int = 86400  # 24 hours default
    auto_restore_after: Optional[float] = None
    
    # Health monitoring after restore
    health_check_start: Optional[float] = None
    health_check_window_hours: int = 1
    recent_success_rates: list[float] = []
    
    @property
    def is_available(self) -> bool:
        return self.state in (IntentLifecycleState.ACTIVE, IntentLifecycleState.RESTORED)
    
    @property
    def should_auto_restore(self) -> bool:
        if self.state != IntentLifecycleState.DISABLED:
            return False
        if self.auto_restore_after is None:
            return False
        return time.time() >= self.auto_restore_after
```

### 8.3 Lifecycle Manager

```python
class LifecycleManager:
    """
    Manages intent lifecycle with rollback-safe behavior.
    """
    
    def __init__(
        self,
        db: Database,
        config: LifecycleConfig,
        health_monitor: HealthMonitor
    ):
        self.db = db
        self.config = config
        self.health_monitor = health_monitor
        self._lifecycle_cache: dict[str, IntentLifecycle] = {}
        self._cache_ttl = 60  # Refresh cache every 60s
    
    async def get_intent_state(self, intent_path: str) -> IntentLifecycle:
        """
        Get current lifecycle state for intent.
        """
        # Check cache first
        if intent_path in self._lifecycle_cache:
            cached = self._lifecycle_cache[intent_path]
            if time.time() - cached.disabled_at < self._cache_ttl:
                return cached
        
        # Load from database
        lifecycle = await self._load_lifecycle(intent_path)
        self._lifecycle_cache[intent_path] = lifecycle
        
        # Check for auto-restore
        if lifecycle.should_auto_restore:
            await self._attempt_restore(lifecycle)
        
        return lifecycle
    
    async def disable_intent(
        self,
        intent_path: str,
        reason: str,
        ttl_seconds: Optional[int] = None
    ):
        """
        Disable intent with TTL for auto-recovery.
        """
        ttl = ttl_seconds or self.config.disable_ttl_seconds
        
        query = text("""
            INSERT INTO intent_lifecycle 
                (intent_path, disabled_at, disable_ttl_seconds, auto_restore_after)
            VALUES (:intent_path, :disabled_at, :ttl, :restore_after)
            ON CONFLICT (intent_path)
            DO UPDATE SET
                disabled_at = :disabled_at,
                disable_ttl_seconds = :ttl,
                auto_restore_after = :restore_after,
                state = 'disabled'
        """)
        
        await self.db.execute(query, {
            "intent_path": intent_path,
            "disabled_at": datetime.utcnow(),
            "ttl": ttl,
            "restore_after": datetime.fromtimestamp(time.time() + ttl)
        })
        
        # Invalidate cache
        self._lifecycle_cache.pop(intent_path, None)
        
        logger.warning(f"Intent {intent_path} disabled: {reason}, TTL={ttl}s")
    
    async def _attempt_restore(self, lifecycle: IntentLifecycle):
        """
        Attempt to restore disabled intent.
        """
        if not self.config.auto_restore_if_health_recovers:
            return
        
        # Check recent health
        success_rate = await self.health_monitor.get_success_rate(
            lifecycle.intent_path,
            window_hours=self.config.restore_observation_window_hours
        )
        
        if success_rate >= self.config.restore_success_rate_threshold:
            await self._restore_intent(lifecycle, success_rate)
        else:
            # Not healthy yet, extend TTL with decreasing factor
            new_ttl = int(lifecycle.disable_ttl_seconds * 0.5)  # Half of original
            new_ttl = max(new_ttl, 3600)  # Minimum 1 hour
            
            await self.disable_intent(
                lifecycle.intent_path,
                reason=f"Health not recovered: rate={success_rate:.2f}",
                ttl_seconds=new_ttl
            )
    
    async def _restore_intent(self, lifecycle: IntentLifecycle, success_rate: float):
        """
        Restore intent to active state.
        """
        query = text("""
            UPDATE intent_lifecycle
            SET state = 'active',
                disabled_at = NULL,
                auto_restore_after = NULL,
                health_check_start = :check_start
            WHERE intent_path = :intent_path
        """)
        
        await self.db.execute(query, {
            "intent_path": lifecycle.intent_path,
            "check_start": datetime.utcnow()
        })
        
        # Invalidate cache
        self._lifecycle_cache.pop(lifecycle.intent_path, None)
        
        logger.info(
            f"Intent {lifecycle.intent_path} auto-restored: "
            f"success_rate={success_rate:.2f}"
        )
    
    async def check_intent_health_after_restore(self, intent_path: str):
        """
        Monitor health after restore. Disable if still unhealthy.
        """
        lifecycle = await self.get_intent_state(intent_path)
        
        if lifecycle.state != IntentLifecycleState.RESTORED:
            return
        
        # Check if observation window passed
        window_elapsed = time.time() - lifecycle.health_check_start >= 3600
        
        if window_elapsed:
            success_rate = await self.health_monitor.get_success_rate(
                intent_path,
                window_hours=1
            )
            
            if success_rate < self.config.restore_success_rate_threshold:
                # Still unhealthy, disable again
                await self.disable_intent(
                    intent_path,
                    reason=f"Post-restore health check failed: rate={success_rate:.2f}",
                    ttl_seconds=lifecycle.disable_ttl_seconds // 2
                )
            else:
                # Healthy, mark as fully active
                await self._mark_fully_active(intent_path)
    
    async def _mark_fully_active(self, intent_path: str):
        """Mark intent as fully active after successful health check."""
        query = text("""
            UPDATE intent_lifecycle
            SET state = 'active',
                health_check_start = NULL
            WHERE intent_path = :intent_path
        """)
        await self.db.execute(query, {"intent_path": intent_path})
        self._lifecycle_cache.pop(intent_path, None)
```

### 8.4 Integration with Policy Engine

```python
class LifecycleAwarePolicyEngine:
    """
    Policy engine that respects intent lifecycle.
    """
    
    def __init__(self, policy_engine: PolicyEngine, lifecycle_manager: LifecycleManager):
        self.policy_engine = policy_engine
        self.lifecycle_manager = lifecycle_manager
    
    async def get_available_intents(self, context: RequestContext) -> list[str]:
        """
        Get list of available intents, filtering out disabled ones.
        """
        snapshot = context.frozen_snapshot
        all_intents = list(snapshot.config.intents.keys())
        
        available = []
        for intent in all_intents:
            lifecycle = await self.lifecycle_manager.get_intent_state(intent)
            
            if lifecycle.is_available:
                available.append(intent)
        
        return available
    
    async def route_with_lifecycle(
        self,
        context: RequestContext,
        request: Request
    ) -> RouteResult:
        """
        Route with lifecycle awareness.
        """
        available_intents = await self.get_available_intents(context)
        
        if not available_intents:
            # Fallback to all intents if none available (shouldn't happen)
            logger.error("No intents available, using all intents")
            available_intents = list(context.frozen_snapshot.config.intents.keys())
        
        # Route among available intents only
        return await self.policy_engine.route(
            context,
            request,
            available_intents=available_intents
        )
```

### 8.5 Lifecycle Flow Diagram

```
Intent Active
     ↓ (health degrades)
Intent Disabled (TTL=24h)
     ↓ (TTL expires or health recovers)
Intent Pending Restore
     ↓ (health check)
 ┌───┴───┐
 │ Good  │ Bad
 │       │
 ↓       ↓
Fully    Re-disabled (shorter TTL)
Active
```

---

## 9. Score Engine

### 9.1 Semantic Scoring

```python
class ScoreEngine:
    """
    Calculates semantic scores for intent matching.
    """
    
    def __init__(
        self,
        embedding_model: EmbeddingModel,
        ann_index: ANNIndex
    ):
        self.embedding_model = embedding_model
        self.ann_index = ann_index
    
    async def calculate_scores(
        self,
        context: RequestContext,
        query: str,
        candidate_intents: list[str]
    ) -> dict[str, float]:
        """
        Calculate semantic scores for each candidate intent.
        """
        # Generate query embedding
        query_embedding = await self.embedding_model.embed(query)
        
        # Search ANN index for top-k neighbors
        neighbors = await self.ann_index.search(
            query_embedding,
            k=10
        )
        
        # Calculate scores based on neighbors
        scores = {}
        for intent in candidate_intents:
            # Find matching examples
            intent_examples = [
                n for n in neighbors
                if n.intent_path == intent
            ]
            
            if not intent_examples:
                scores[intent] = 0.0
            else:
                # Average similarity of top matches
                avg_similarity = sum(e.similarity for e in intent_examples) / len(intent_examples)
                scores[intent] = avg_similarity
        
        return scores
```

### 9.2 Boost Calculation

```python
class BoostCalculator:
    """
    Calculates boost based on frequency and success history.
    """
    
    def __init__(self, fairness_calc: FairnessBoostCalculator):
        self.fairness_calc = fairness_calc
    
    async def calculate_boost(
        self,
        context: RequestContext,
        intent: str,
        base_boost: float
    ) -> float:
        """
        Calculate boost with fairness constraints.
        """
        return await self.fairness_calc.calculate_boost(
            intent=intent,
            base_score=base_boost,
            max_intent_boost=base_boost
        )
```

---

## 10. Policy Engine

### 10.1 Rule-Based Routing

```python
class PolicyEngine:
    """
    Combines rule-based and semantic routing.
    """
    
    def __init__(
        self,
        rules: list[RoutingRule],
        score_engine: ScoreEngine,
        lifecycle_aware: bool = False
    ):
        self.rules = rules
        self.score_engine = score_engine
        self.lifecycle_aware = lifecycle_aware
    
    async def evaluate(
        self,
        context: RequestContext,
        request: Request
    ) -> PolicyResult:
        """
        Evaluate rules and determine routing strategy.
        """
        # Check rules in priority order
        for rule in sorted(self.rules, key=lambda r: r.priority, reverse=True):
            if rule.matches(request):
                return PolicyResult(
                    intent=rule.intent,
                    confidence=rule.confidence,
                    needs_semantic=rule.needs_semantic,
                    routing_type="rule"
                )
        
        # Default: semantic evaluation
        return PolicyResult(
            needs_semantic=True,
            routing_type="semantic"
        )
    
    async def route(
        self,
        context: RequestContext,
        request: Request,
        available_intents: list[str]
    ) -> RouteResult:
        """
        Full routing with semantic scoring.
        """
        # Evaluate rules first
        policy_result = await self.evaluate(context, request)
        
        if not policy_result.needs_semantic:
            return RouteResult(
                intent=policy_result.intent,
                confidence=policy_result.confidence,
                handler=policy_result.handler
            )
        
        # Semantic scoring
        scores = await self.score_engine.calculate_scores(
            context,
            request.query,
            available_intents
        )
        
        # Combine with boost
        final_scores = {}
        for intent, score in scores.items():
            final_score = await self.score_engine.calculate_final_score(
                context, intent, score
            )
            final_scores[intent] = final_score
        
        # Select best intent
        best_intent = max(final_scores, key=final_scores.get)
        
        return RouteResult(
            intent=best_intent,
            confidence=final_scores[best_intent],
            all_scores=final_scores
        )
```

---

## 11. Execution Engine

### 11.1 Handler Dispatch

```python
class ExecutionEngine:
    """
    Executes routing decisions.
    """
    
    def __init__(self, handlers: dict[str, Handler]):
        self.handlers = handlers
    
    async def execute(
        self,
        context: RequestContext,
        route_result: RouteResult
    ) -> ExecutionResult:
        """
        Execute routing decision.
        """
        handler = self.handlers.get(route_result.intent)
        
        if not handler:
            return ExecutionResult(
                success=False,
                error=f"No handler for intent: {route_result.intent}"
            )
        
        try:
            result = await handler.execute(context, context.request)
            
            # Track execution for health monitoring
            await self._track_execution(route_result.intent, success=True)
            
            return result
        except Exception as e:
            await self._track_execution(route_result.intent, success=False)
            raise
```

---

## 12. Observation Engine

### 12.1 Components

```python
class ObservationEngine:
    """
    Observes and records routing behavior.
    """
    
    def __init__(
        self,
        frequency_tracker: FrequencyTracker,
        feedback_processor: FeedbackProcessor,
        health_monitor: HealthMonitor,
        lifecycle_manager: LifecycleManager
    ):
        self.frequency_tracker = frequency_tracker
        self.feedback_processor = feedback_processor
        self.health_monitor = health_monitor
        self.lifecycle_manager = lifecycle_manager
    
    async def record_execution(
        self,
        context: RequestContext,
        result: ExecutionResult
    ):
        """Record execution for observability."""
        await self.health_monitor.record(
            intent=result.intent,
            success=result.success,
            latency_ms=result.latency_ms
        )
    
    async def process_feedback(self, feedback: Feedback) -> FeedbackResult:
        """Process feedback with exactly-once guarantee."""
        return await self.feedback_processor.report_feedback(feedback)
```

---

## 13. Data Schema

### 13.1 Applied Idempotency Keys

```sql
CREATE TABLE applied_idempotency_keys (
    key VARCHAR(64) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);

CREATE INDEX idx_processed_at ON applied_idempotency_keys(processed_at);
```

### 13.2 Frequency Update WAL

```sql
CREATE TABLE frequency_update_wal (
    event_id VARCHAR(64) PRIMARY KEY,
    intent_path VARCHAR(255) NOT NULL,
    example_text TEXT NOT NULL,
    idempotency_key VARCHAR(64) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    processed BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_wal_processed ON frequency_update_wal(processed) WHERE processed = FALSE;
CREATE INDEX idx_wal_intent ON frequency_update_wal(intent_path);
```

### 13.3 Intent Lifecycle

```sql
CREATE TABLE intent_lifecycle (
    intent_path VARCHAR(255) PRIMARY KEY,
    state VARCHAR(50) DEFAULT 'active',
    disabled_at TIMESTAMP NULL,
    disable_ttl_seconds INT DEFAULT 86400,
    auto_restore_after TIMESTAMP NULL,
    health_check_start TIMESTAMP NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_lifecycle_state ON intent_lifecycle(state);
CREATE INDEX idx_lifecycle_restore ON intent_lifecycle(auto_restore_after) 
    WHERE auto_restore_after IS NOT NULL;
```

### 13.4 Example Frequency

```sql
CREATE TABLE example_frequency (
    intent_path VARCHAR(255) NOT NULL,
    example_hash VARCHAR(64) NOT NULL,
    frequency INT DEFAULT 1,
    last_used TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (intent_path, example_hash)
);
```

---

## 14. Configuration

### 14.1 Full Configuration Schema

```yaml
semantic_router:
  # Basic settings
  default_intent: "unknown"
  fallback_enabled: true
  
  # Consistency settings
  consistency:
    read_after_write_guard_ms: 5000
    force_new_snapshot_on_feedback: false
    warn_on_stale_snapshot: true
  
  # Boost fairness settings
  boost_fairness:
    enabled: true
    per_intent_weight_cap: 0.30      # 30% max per intent
    min_share_per_intent: 0.01       # 1% minimum
    global_boost_per_second: 1000
  
  # Lifecycle settings
  lifecycle:
    disable_ttl_seconds: 86400       # 24 hours
    auto_restore_if_health_recovers: true
    restore_success_rate_threshold: 0.7
    restore_observation_window_hours: 1
  
  # ANN settings
  ann:
    index_type: "faiss"              # faiss, annoy, hnsw
    dimension: 768
    n_neighbors: 10
  
  # Embedding settings
  embedding:
    model: "text-embedding-ada-002"
    batch_size: 100
  
  # Intents configuration
  intents:
    code_generation:
      base_score: 0.8
      priority: 10
      handler: "CodeGenHandler"
    data_query:
      base_score: 0.7
      priority: 5
      handler: "DataQueryHandler"
    rag:
      base_score: 0.6
      priority: 3
      handler: "RAGHandler"
```

---

## 15. File Structure

```
src/infrastructure/router/
├── __init__.py
├── types.py                      # RequestContext, Snapshot, PolicyResult, etc.
├── snapshot.py                   # SnapshotManager, Snapshot
├── context.py                    # RequestContext creation
├── policy_engine.py              # PolicyEngine, RoutingRule
├── score_engine.py               # ScoreEngine, BoostCalculator
├── execution_engine.py           # ExecutionEngine, Handler
├── observation/
│   ├── __init__.py
│   ├── feedback_processor.py     # FeedbackProcessor
│   ├── exactly_once.py            # ExactlyOnceProcessor
│   ├── wal.py                     # WALWriter, WALReplayer
│   ├── frequency_tracker.py       # FrequencyTracker
│   ├── health_monitor.py         # HealthMonitor
│   └── lifecycle_manager.py       # LifecycleManager
├── consistency/
│   ├── __init__.py
│   └── read_after_write.py        # ReadAfterWriteGuard
├── fairness/
│   ├── __init__.py
│   └── boost_fairness.py          # FairnessBoostCalculator
├── router.py                     # SemanticRouter (main facade)
└── tests/
    ├── unit/
    │   ├── test_snapshot.py
    │   ├── test_exactly_once.py
    │   ├── test_fairness.py
    │   ├── test_lifecycle.py
    │   └── test_router.py
    └── integration/
        └── test_consistency.py
```

---

## 16. Done Criteria

### 16.1 Must Implement

- [x] Immutable RequestContext passed through pipeline, no global state lookup
- [x] Exactly-once WAL with applied_idempotency_keys and ON CONFLICT
- [x] Read-after-write guard (configurable + logging)
- [x] Fairness boost budget (per-intent cap + min share)
- [x] Intent lifecycle rollback (disable TTL, auto-restore based on health)

### 16.2 Should Implement

- [x] All v7 features (embedding, ANN, context boosting)
- [x] PolicyEngine with rule-based routing
- [x] ScoreEngine with semantic matching
- [x] ExecutionEngine with handler dispatch

### 16.3 Verification

| Criteria | Test |
|----------|------|
| Immutable context | All engines access only context.frozen_snapshot |
| Exactly-once | Duplicate feedback returns idempotent, no duplicate frequency update |
| Read-after-write | Stale snapshot warning logged within guard window |
| Fairness | No intent exceeds 30% budget, all get at least 1% |
| Lifecycle | Disabled intent auto-restores after TTL if healthy |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| v8 | 2026-05-17 | Final: All critical edge-case risks addressed |
| v7 | Previous | Added consistency, fairness, lifecycle |

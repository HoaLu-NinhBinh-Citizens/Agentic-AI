"""Deterministic time, random, and UUID generation - Phase 5B v10.

Provides deterministic values for workflow replay:
- ctx.now(): Returns recorded timestamp or records new one
- ctx.random(): Deterministic pseudo-random number
- ctx.uuid(): Deterministic UUID v5
"""

from __future__ import annotations

import hashlib
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DeterministicValueStore:
    """Store for recorded deterministic values."""
    
    timestamps: dict[str, float] = field(default_factory=dict)
    randoms: dict[str, float] = field(default_factory=dict)
    uuids: dict[str, str] = field(default_factory=dict)
    
    def record_timestamp(self, key: str, value: float) -> None:
        """Record a timestamp value."""
        self.timestamps[key] = value
    
    def get_timestamp(self, key: str) -> Optional[float]:
        """Get recorded timestamp."""
        return self.timestamps.get(key)
    
    def record_random(self, key: str, value: float) -> None:
        """Record a random value."""
        self.randoms[key] = value
    
    def get_random(self, key: str) -> Optional[float]:
        """Get recorded random value."""
        return self.randoms.get(key)
    
    def record_uuid(self, key: str, value: str) -> None:
        """Record a UUID value."""
        self.uuids[key] = value
    
    def get_uuid(self, key: str) -> Optional[str]:
        """Get recorded UUID value."""
        return self.uuids.get(key)


class DeterministicValueGenerator:
    """Generates deterministic values for workflow execution.
    
    Values are generated from workflow_id + sequence to ensure
    reproducibility during replay.
    """
    
    def __init__(
        self,
        workflow_id: str,
        base_seed: Optional[int] = None,
        store: Optional[DeterministicValueStore] = None,
    ):
        self._workflow_id = workflow_id
        self._store = store or DeterministicValueStore()
        
        seed_input = base_seed if base_seed is not None else self._workflow_id
        self._base_random = random.Random(self._hash_seed(seed_input))
        self._sequence = 0
    
    def _hash_seed(self, value: str) -> int:
        """Generate a numeric seed from string."""
        return int(hashlib.sha256(value.encode()).hexdigest()[:16], 16)
    
    def now(self, record_key: Optional[str] = None) -> float:
        """Get deterministic current timestamp.
        
        On first call, generates a new timestamp.
        On replay, returns the recorded value.
        
        Args:
            record_key: Optional key for recording (defaults to sequence)
            
        Returns:
            Deterministic timestamp
        """
        key = record_key or f"now_{self._sequence}"
        
        recorded = self._store.get_timestamp(key)
        if recorded is not None:
            return recorded
        
        timestamp = time.time()
        self._store.record_timestamp(key, timestamp)
        self._sequence += 1
        return timestamp
    
    def random(self, record_key: Optional[str] = None) -> float:
        """Get deterministic random number between 0 and 1.
        
        Uses seeded random from workflow_id + sequence.
        
        Args:
            record_key: Optional key for recording
            
        Returns:
            Deterministic random float in [0, 1)
        """
        key = record_key or f"random_{self._sequence}"
        
        recorded = self._store.get_random(key)
        if recorded is not None:
            return recorded
        
        value = self._base_random.random()
        self._store.record_random(key, value)
        self._sequence += 1
        return value
    
    def uuid(self, namespace: Optional[str] = None, record_key: Optional[str] = None) -> str:
        """Get deterministic UUID v5.
        
        UUID v5 is generated from namespace + workflow_id + sequence
        to ensure deterministic but unique IDs.
        
        Args:
            namespace: Optional namespace for UUID
            record_key: Optional key for recording
            
        Returns:
            Deterministic UUID string
        """
        key = record_key or f"uuid_{self._sequence}"
        
        recorded = self._store.get_uuid(key)
        if recorded is not None:
            return recorded
        
        ns = uuid.UUID(namespace) if namespace else uuid.NAMESPACE_OID
        unique_string = f"{self._workflow_id}:{self._sequence}"
        
        new_uuid = str(uuid.uuid5(ns, unique_string))
        self._store.record_uuid(key, new_uuid)
        self._sequence += 1
        return new_uuid
    
    def choice(self, options: list, record_key: Optional[str] = None) -> any:
        """Get deterministic choice from options.
        
        Args:
            options: List of options to choose from
            record_key: Optional key for recording
            
        Returns:
            Deterministic choice
        """
        idx = int(self.random(record_key) * len(options))
        return options[idx]
    
    def shuffle(self, items: list, record_key: Optional[str] = None) -> list:
        """Get deterministic shuffled copy of items.
        
        Args:
            items: List to shuffle
            record_key: Optional key for recording
            
        Returns:
            Deterministic shuffled list
        """
        key = record_key or f"shuffle_{self._sequence}"
        
        result = items.copy()
        seed = int(self.random(key) * 1000000)
        rng = random.Random(seed)
        rng.shuffle(result)
        return result
    
    def randint(self, a: int, b: int, record_key: Optional[str] = None) -> int:
        """Get deterministic integer in range [a, b].
        
        Args:
            a: Lower bound
            b: Upper bound
            record_key: Optional key for recording
            
        Returns:
            Deterministic integer
        """
        return a + int(self.random(record_key) * (b - a + 1))


class WorkflowValueRecorder:
    """Records deterministic values for a workflow.
    
    Used by the runtime to serialize values for replay.
    """
    
    def __init__(self, workflow_id: str):
        self._workflow_id = workflow_id
        self._values: dict[str, any] = {}
    
    def record(self, key: str, value: any) -> None:
        """Record a value."""
        self._values[key] = value
    
    def get_recorded_values(self) -> dict:
        """Get all recorded values for serialization."""
        return self._values.copy()
    
    def load_recorded_values(self, values: dict) -> None:
        """Load recorded values from serialization."""
        self._values = values.copy()


class DeterministicContextProvider:
    """Provides deterministic values to workflow context.
    
    Integrates with WorkflowContext to provide:
    - ctx.now()
    - ctx.random()
    - ctx.uuid()
    - ctx.choice()
    - ctx.randint()
    """
    
    def __init__(
        self,
        workflow_id: str,
        store: Optional[DeterministicValueStore] = None,
    ):
        self._generator = DeterministicValueGenerator(workflow_id, store=store)
        self._recorder = WorkflowValueRecorder(workflow_id)
    
    @property
    def now(self) -> float:
        """Get current timestamp."""
        return self._generator.now()
    
    @property
    def random(self) -> float:
        """Get random float."""
        return self._generator.random()
    
    def uuid(self, namespace: Optional[str] = None) -> str:
        """Get deterministic UUID."""
        return self._generator.uuid(namespace)
    
    def choice(self, options: list) -> any:
        """Get deterministic choice."""
        return self._generator.choice(options)
    
    def randint(self, a: int, b: int) -> int:
        """Get deterministic integer."""
        return self._generator.randint(a, b)
    
    def get_store(self) -> DeterministicValueStore:
        """Get the underlying store."""
        return self._generator._store
    
    def load_from_recorded(self, recorded: dict) -> None:
        """Load recorded values for replay."""
        store = DeterministicValueStore()
        
        for key, value in recorded.items():
            if key.startswith("now_"):
                store.record_timestamp(key, value)
            elif key.startswith("random_"):
                store.record_random(key, value)
            elif key.startswith("uuid_"):
                store.record_uuid(key, value)
        
        self._generator = DeterministicValueGenerator(
            self._generator._workflow_id,
            store=store,
        )

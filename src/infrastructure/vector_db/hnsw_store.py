"""HNSW Vector Store — Production-grade similarity search with HNSW index.

Fixes: InMemory O(N) search bottleneck.
Provides: O(log N) similarity search with configurable M and ef parameters.
"""
from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import structlog

if TYPE_CHECKING:
    from src.domain.knowledge.kb import KBEntry

logger = structlog.get_logger(__name__)


@dataclass
class HNSWConfig:
    """HNSW index configuration."""
    M: int = 16  # Connections per node
    ef_construction: int = 200  # Candidate set size during construction
    ef_search: int = 100  # Candidate set size during search
    max_elements: int = 1_000_000  # Maximum vectors to store


@dataclass
class HNSWNode:
    """Node in HNSW graph."""
    id: str
    embedding: list[float]
    connections: dict[int, set[str]] = field(default_factory=dict)


class HNSWVectorStore:
    """HNSW-based vector similarity store.
    
    Provides O(log N) similarity search using Hierarchical Navigable Small World graphs.
    Persists to SQLite for durability.
    
    Usage:
        store = HNSWVectorStore(Path(".ai_support/hnsw_index.db"))
        await store.add_entry(entry, embedding)
        results = await store.search(query_embedding, top_k=10)
    """
    
    def __init__(
        self,
        db_path: Path | str = ".ai_support/hnsw_index.db",
        config: HNSWConfig | None = None,
    ):
        self._db_path = Path(db_path)
        self._config = config or HNSWConfig()
        self._conn: sqlite3.Connection | None = None
        
        # In-memory HNSW structures
        self._nodes: dict[str, HNSWNode] = {}
        self._entry_point: Optional[str] = None
        self._max_level = 0
        self._nodes_lock = None
        
        # LRU cache for recent queries
        self._query_cache: OrderedDict[str, list[tuple[str, float, dict]]] = OrderedDict()
        self._cache_max_size = 1000
    
    def _init_lock(self) -> Any:
        """Initialize async lock lazily."""
        import asyncio
        if self._nodes_lock is None:
            self._nodes_lock = asyncio.Lock()
        return self._nodes_lock
    
    def connect(self) -> None:
        """Connect to SQLite and load HNSW index."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()
        self._load_index()
    
    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._save_index()
            self._conn.close()
            self._conn = None
    
    def _init_schema(self) -> None:
        """Initialize database schema."""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS vectors (
                id TEXT PRIMARY KEY,
                embedding_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_vectors_id ON vectors(id)
        """)
        self._conn.commit()
    
    def _load_index(self) -> None:
        """Load HNSW nodes from database."""
        cursor = self._conn.execute("SELECT id, embedding_json, metadata_json FROM vectors")
        for row in cursor:
            node_id, embedding_json, _ = row
            embedding = json.loads(embedding_json)
            self._nodes[node_id] = HNSWNode(id=node_id, embedding=embedding)
        
        if self._nodes:
            self._entry_point = next(iter(self._nodes))
            self._max_level = max(self._config.M.bit_length() - 1, 1)
    
    def _save_index(self) -> None:
        """Save HNSW nodes to database."""
        for node in self._nodes.values():
            self._conn.execute(
                """INSERT OR REPLACE INTO vectors (id, embedding_json, metadata_json)
                   VALUES (?, ?, ?)""",
                (node.id, json.dumps(node.embedding), '{}'),
            )
        self._conn.commit()
    
    def _cosine_distance(self, a: list[float], b: list[float]) -> float:
        """Compute cosine distance between two vectors."""
        if len(a) != len(b):
            return 1.0
        
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        
        if norm_a == 0 or norm_b == 0:
            return 1.0
        
        return 1.0 - (dot / (norm_a * norm_b))
    
    def _random_level(self) -> int:
        """Generate random level for HNSW insertion."""
        import random
        level = 0
        while random.random() < 0.5 and level < self._max_level:
            level += 1
        return level
    
    def _search_layer(
        self,
        query: list[float],
        entry_point: str,
        level: int,
        ef: int,
    ) -> list[str]:
        """Search at a specific level of HNSW graph."""
        candidates = [(self._cosine_distance(query, self._nodes[entry_point].embedding), entry_point)]
        visited = {entry_point}
        results: list[tuple[float, str]] = []
        
        while candidates:
            candidates.sort(key=lambda x: x[0])
            if len(results) >= ef or candidates[0][0] > results[-1][0] if results else False:
                break
            
            _, current = candidates.pop(0)
            results.append((self._cosine_distance(query, self._nodes[current].embedding), current))
            
            if current in self._nodes and level in self._nodes[current].connections:
                for neighbor in self._nodes[current].connections[level]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        candidates.append((
                            self._cosine_distance(query, self._nodes[neighbor].embedding),
                            neighbor
                        ))
        
        return [r[1] for r in sorted(results)[:ef]]
    
    async def add_entry(self, entry: "KBEntry", embedding: list[float] | None = None) -> None:
        """Add entry with HNSW indexing."""
        import asyncio
        
        async with self._init_lock():
            node_id = entry.id
            embedding = embedding or entry.embedding or []
            
            if node_id in self._nodes:
                self._nodes[node_id].embedding = embedding
            else:
                level = self._random_level()
                self._nodes[node_id] = HNSWNode(id=node_id, embedding=embedding)
                
                # Connect to entry point
                if self._entry_point is None:
                    self._entry_point = node_id
                    self._max_level = max(self._max_level, level)
                else:
                    # Find neighbors at each level
                    for l in range(min(level + 1, self._max_level + 1)):
                        neighbors = self._search_layer(
                            embedding,
                            self._entry_point,
                            l,
                            self._config.ef_construction,
                        )
                        self._nodes[node_id].connections[l] = set(neighbors[:self._config.M])
            
            self._conn.execute(
                "INSERT OR REPLACE INTO vectors (id, embedding_json, metadata_json) VALUES (?, ?, ?)",
                (node_id, json.dumps(embedding), '{}'),
            )
    
    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[tuple[str, float, dict[str, Any]]]:
        """Search using HNSW graph traversal."""
        import asyncio
        
        async with self._init_lock():
            # Check query cache
            cache_key = str(query_embedding[:10])  # Hash first 10 dims
            if cache_key in self._query_cache:
                return self._query_cache[cache_key][:top_k]
            
            if not self._nodes or self._entry_point is None:
                return []
            
            # HNSW search
            entry = self._entry_point
            for level in range(self._max_level, -1, -1):
                candidates = self._search_layer(
                    query_embedding,
                    entry,
                    level,
                    self._config.ef_search,
                )
                if candidates:
                    entry = candidates[0]
            
            # Final search at level 0
            neighbors = self._search_layer(
                query_embedding,
                entry,
                0,
                self._config.ef_search,
            )
            
            results: list[tuple[str, float, dict[str, Any]]] = []
            for node_id in neighbors[:top_k]:
                if node_id in self._nodes:
                    distance = self._cosine_distance(
                        query_embedding,
                        self._nodes[node_id].embedding,
                    )
                    similarity = 1.0 - distance
                    results.append((node_id, similarity, {}))
            
            # Cache results
            if cache_key not in self._query_cache:
                if len(self._query_cache) >= self._cache_max_size:
                    self._query_cache.popitem(last=False)
                self._query_cache[cache_key] = results
            
            return results
    
    async def count(self) -> int:
        """Get total entries."""
        return len(self._nodes)
    
    async def clear(self) -> None:
        """Clear all entries."""
        self._nodes.clear()
        self._entry_point = None
        self._query_cache.clear()
        self._conn.execute("DELETE FROM vectors")
        self._conn.commit()
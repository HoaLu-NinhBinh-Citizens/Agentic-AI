"""
Advanced Memory System (DEPRECATED)

This module is DEPRECATED. Use memory/store.py instead.

The store.py implementation (AgentMemory) is the canonical memory system.
This file exists for backward compatibility only.

Migration:
    # OLD (deprecated)
    from src.core.memory.advanced_memory import AdvancedMemorySystem

    # NEW
    from src.core.memory.store import AgentMemory
"""

import warnings

# Emit deprecation warning
warnings.warn(
    "memory.advanced_memory is deprecated. Use memory.store.AgentMemory instead.",
    DeprecationWarning,
    stacklevel=2
)

# Continue with original implementation
import asyncio
import hashlib
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class MemoryRecord:
    """Base class for memory records"""
    id: str = field(default_factory=lambda: str(uuid4()))
    type: str = ""
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None
    created_at: datetime = field(default_factory=datetime.now)
    accessed_at: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    importance_score: float = 0.5
    tags: List[str] = field(default_factory=list)


@dataclass
class EpisodicMemoryRecord(MemoryRecord):
    """Stores specific experiences and events"""
    type: str = "episodic"
    context: Dict[str, Any] = field(default_factory=dict)
    outcome: str = ""
    lessons_learned: List[str] = field(default_factory=list)
    related_task: str = ""


@dataclass
class SemanticMemoryRecord(MemoryRecord):
    """Stores general knowledge and facts"""
    type: str = "semantic"
    concept: str = ""
    facts: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    confidence: float = 1.0
    validity_expiry: Optional[datetime] = None


@dataclass
class ProceduralMemoryRecord(MemoryRecord):
    """Stores skills, workflows, and procedures"""
    type: str = "procedural"
    skill_name: str = ""
    steps: List[str] = field(default_factory=list)
    prerequisites: List[str] = field(default_factory=list)
    success_rate: float = 0.0
    usage_count: int = 0


class BaseMemoryStore(ABC):
    """Abstract base for memory stores"""

    @abstractmethod
    async def store(self, record: MemoryRecord) -> str:
        """Store a memory record"""
        pass

    @abstractmethod
    async def retrieve(self, query: str, limit: int = 10) -> List[MemoryRecord]:
        """Retrieve relevant memories"""
        pass

    @abstractmethod
    async def get(self, memory_id: str) -> Optional[MemoryRecord]:
        """Get specific memory by ID"""
        pass

    @abstractmethod
    async def delete(self, memory_id: str) -> bool:
        """Delete a memory"""
        pass


class ChromaDBMemoryStore(BaseMemoryStore):
    """ChromaDB-backed vector memory store"""

    def __init__(self, persist_directory: str = "AI_support/memory/chroma_db"):
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self._client = None
        self._collection = None

    async def _get_collection(self):
        """Lazy initialization of ChromaDB client"""
        if self._collection is None:
            try:
                import chromadb
                from chromadb.config import Settings

                self._client = chromadb.PersistentClient(
                    path=str(self.persist_directory),
                    settings=Settings(anonymized_telemetry=False)
                )
                self._collection = self._client.get_or_create_collection(
                    name="agent_memory",
                    metadata={"hnsw:space": "cosine"}
                )
            except ImportError:
                logger.warning("ChromaDB not installed, using fallback memory")
                self._collection = None

    async def store(self, record: MemoryRecord) -> str:
        """Store a memory record with embedding"""
        await self._get_collection()

        if self._collection and record.embedding:
            self._collection.add(
                embeddings=[record.embedding],
                documents=[record.content],
                metadatas=[{
                    "id": record.id,
                    "type": record.type,
                    "tags": ",".join(record.tags),
                    "created_at": record.created_at.isoformat(),
                }],
                ids=[record.id]
            )

        self._store_json_backup(record)
        return record.id

    async def retrieve(self, query: str, limit: int = 10) -> List[MemoryRecord]:
        """Retrieve relevant memories using vector search"""
        await self._get_collection()

        results = []

        if self._collection:
            try:
                from src.infrastructure.embeddings.embedding_service import EmbeddingService
                svc = EmbeddingService()
                query_embedding = asyncio.run(svc.embed(query))
                if query_embedding:
                    query_results = self._collection.query(
                        query_embeddings=[query_embedding],
                        n_results=limit
                    )

                    docs = query_results.get("documents", [[]])[0]
                    metadatas = query_results.get("metadatas", [[]])
                    for i, doc in enumerate(docs):
                        if i < len(metadatas[0]):
                            metadata = metadatas[0][i]
                        else:
                            metadata = {}
                        results.append(MemoryRecord(
                            id=metadata.get("id", str(uuid4())),
                            type=metadata.get("type", "unknown"),
                            content=doc,
                            tags=metadata.get("tags", "").split(",") if metadata.get("tags") else [],
                            created_at=datetime.fromisoformat(metadata.get("created_at", datetime.now().isoformat()))
                        ))
            except Exception as exc:
                logger.warning(f"Vector search failed: {exc}")

        if not results:
            results = self._fallback_search(query, limit)

        return results

    async def get(self, memory_id: str) -> Optional[MemoryRecord]:
        """Get specific memory by ID"""
        backup_path = self.persist_directory / f"{memory_id}.json"
        if backup_path.exists():
            return self._load_from_json(backup_path)
        return None

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory"""
        if self._collection:
            try:
                self._collection.delete(ids=[memory_id])
            except Exception:
                pass

        backup_path = self.persist_directory / f"{memory_id}.json"
        if backup_path.exists():
            backup_path.unlink()
            return True
        return False

    def _store_json_backup(self, record: MemoryRecord):
        """Backup record as JSON"""
        backup_path = self.persist_directory / f"{record.id}.json"
        data = {
            "id": record.id,
            "type": record.type,
            "content": record.content,
            "metadata": record.metadata,
            "created_at": record.created_at.isoformat(),
            "accessed_at": record.accessed_at.isoformat(),
            "access_count": record.access_count,
            "importance_score": record.importance_score,
            "tags": record.tags,
        }
        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

    def _load_from_json(self, path: Path) -> MemoryRecord:
        """Load record from JSON"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return MemoryRecord(
            id=data["id"],
            type=data["type"],
            content=data["content"],
            metadata=data.get("metadata", {}),
            tags=data.get("tags", []),
            created_at=datetime.fromisoformat(data["created_at"]),
            accessed_at=datetime.fromisoformat(data["accessed_at"]),
            access_count=data.get("access_count", 0),
            importance_score=data.get("importance_score", 0.5),
        )

    def _fallback_search(self, query: str, limit: int) -> List[MemoryRecord]:
        """Fallback text search when vector DB is unavailable"""
        query_lower = query.lower()
        results = []

        for json_file in self.persist_directory.glob("*.json"):
            try:
                record = self._load_from_json(json_file)
                if query_lower in record.content.lower():
                    record.access_count += 1
                    results.append(record)
            except Exception:
                continue

        results.sort(key=lambda r: (r.access_count, r.importance_score), reverse=True)
        return results[:limit]


class InMemoryStore(BaseMemoryStore):
    """Simple in-memory fallback store"""

    def __init__(self):
        self._store: Dict[str, MemoryRecord] = {}
        self._index: Dict[str, List[str]] = {}

    async def store(self, record: MemoryRecord) -> str:
        self._store[record.id] = record

        for tag in record.tags:
            if tag not in self._index:
                self._index[tag] = []
            self._index[tag].append(record.id)

        return record.id

    async def retrieve(self, query: str, limit: int = 10) -> List[MemoryRecord]:
        query_lower = query.lower()
        results = [
            r for r in self._store.values()
            if query_lower in r.content.lower()
        ]
        results.sort(key=lambda r: (r.access_count, r.importance_score), reverse=True)
        return results[:limit]

    async def get(self, memory_id: str) -> Optional[MemoryRecord]:
        record = self._store.get(memory_id)
        if record:
            record.access_count += 1
            record.accessed_at = datetime.now()
        return record

    async def delete(self, memory_id: str) -> bool:
        if memory_id in self._store:
            del self._store[memory_id]
            return True
        return False


class AdvancedMemorySystem:
    """
    Multi-layered memory system with episodic, semantic, procedural memory.
    Provides intelligent memory retrieval and learning.
    """

    def __init__(
        self,
        vector_store: Optional[BaseMemoryStore] = None,
        use_chroma: bool = True,
    ):
        if vector_store:
            self.vector_store = vector_store
        elif use_chroma:
            try:
                self.vector_store = ChromaDBMemoryStore()
            except Exception:
                self.vector_store = InMemoryStore()
        else:
            self.vector_store = InMemoryStore()

        self.episodic_store: Dict[str, List[EpisodicMemoryRecord]] = {}
        self.semantic_store: Dict[str, SemanticMemoryRecord] = {}
        self.procedural_store: Dict[str, ProceduralMemoryRecord] = {}
        self.working_memory: Dict[str, Any] = {}

    async def remember_episode(
        self,
        task: str,
        context: Dict[str, Any],
        outcome: str,
        success: bool,
        lessons: List[str] | None = None,
    ) -> str:
        """Store an episodic memory from a task execution"""
        record = EpisodicMemoryRecord(
            type="episodic",
            content=f"Task: {task}\nOutcome: {outcome}\nContext: {json.dumps(context)}",
            context=context,
            outcome=outcome,
            lessons_learned=lessons or [],
            related_task=task,
            importance_score=1.0 if success else 0.8,
            tags=["task", "execution", "success" if success else "failure"],
        )

        task_hash = hashlib.sha256(task.encode()).hexdigest()[:16]
        if task_hash not in self.episodic_store:
            self.episodic_store[task_hash] = []
        self.episodic_store[task_hash].append(record)

        await self.vector_store.store(record)
        return record.id

    async def learn_concept(
        self,
        concept: str,
        facts: List[str],
        sources: List[str] | None = None,
        confidence: float = 1.0,
    ) -> str:
        """Store semantic knowledge"""
        record = SemanticMemoryRecord(
            type="semantic",
            concept=concept,
            content=f"Concept: {concept}\nFacts: {'; '.join(facts)}",
            facts=facts,
            sources=sources or [],
            confidence=confidence,
            importance_score=confidence,
            tags=["concept", "knowledge"],
        )

        self.semantic_store[concept] = record
        await self.vector_store.store(record)
        return record.id

    async def learn_procedure(
        self,
        skill_name: str,
        steps: List[str],
        prerequisites: List[str] | None = None,
        success_rate: float = 0.0,
    ) -> str:
        """Store procedural knowledge (skills/workflows)"""
        record = ProceduralMemoryRecord(
            type="procedural",
            skill_name=skill_name,
            content=f"Skill: {skill_name}\nSteps: {' -> '.join(steps)}",
            steps=steps,
            prerequisites=prerequisites or [],
            success_rate=success_rate,
            usage_count=0,
            importance_score=success_rate,
            tags=["skill", "procedure", "workflow"],
        )

        self.procedural_store[skill_name] = record
        await self.vector_store.store(record)
        return record.id

    async def recall(
        self,
        query: str,
        memory_types: List[str] = None,
        limit: int = 10,
    ) -> Dict[str, List[MemoryRecord]]:
        """Recall memories across all layers"""
        if memory_types is None:
            memory_types = ["episodic", "semantic", "procedural"]

        results = await self.vector_store.retrieve(query, limit=limit)

        filtered_results = {
            "episodic": [],
            "semantic": [],
            "procedural": [],
        }

        for record in results:
            if record.type in filtered_results:
                filtered_results[record.type].append(record)

        return filtered_results

    async def recall_similar_task(self, task: str, limit: int = 5) -> List[EpisodicMemoryRecord]:
        """Recall similar past tasks for learning"""
        results = await self.vector_store.retrieve(task, limit=limit)
        return [
            r for r in results
            if isinstance(r, EpisodicMemoryRecord) or r.type == "episodic"
        ]

    async def get_skill(self, skill_name: str) -> Optional[ProceduralMemoryRecord]:
        """Get a specific procedural skill"""
        skill = self.procedural_store.get(skill_name)
        if skill:
            skill.usage_count += 1
        return skill

    async def update_working_memory(self, key: str, value: Any):
        """Update working memory (short-term context)"""
        self.working_memory[key] = value

    async def get_working_memory(self, key: str) -> Optional[Any]:
        """Get from working memory"""
        return self.working_memory.get(key)

    async def clear_working_memory(self):
        """Clear working memory"""
        self.working_memory.clear()

    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory system statistics"""
        return {
            "episodic_count": sum(len(v) for v in self.episodic_store.values()),
            "semantic_count": len(self.semantic_store),
            "procedural_count": len(self.procedural_store),
            "working_memory_size": len(self.working_memory),
            "top_skills": sorted(
                [(s.skill_name, s.usage_count, s.success_rate)
                 for s in self.procedural_store.values()],
                key=lambda x: x[1],
                reverse=True
            )[:5],
        }

    async def consolidate_learning(self) -> Dict[str, int]:
        """Consolidate episodic memories into semantic/procedural knowledge"""
        consolidated = {"lessons": 0, "skills": 0, "concepts": 0}

        for task_hash, episodes in self.episodic_store.items():
            if len(episodes) < 3:
                continue

            successful = [e for e in episodes if e.outcome == "success"]
            if len(successful) / len(episodes) > 0.8:
                all_lessons = set()
                for ep in successful:
                    all_lessons.update(ep.lessons_learned)

                if all_lessons:
                    await self.learn_concept(
                        concept=f"Learned from: {episodes[0].related_task}",
                        facts=list(all_lessons),
                        confidence=len(successful) / len(episodes),
                    )
                    consolidated["concepts"] += 1

        return consolidated


class AgentMemory(AdvancedMemorySystem):
    """
    Extended memory system with agent-specific capabilities.
    Integrates with the existing AgentMemory interface.
    """

    def __init__(self, config: Dict[str, Any] = None):
        config = config or {}
        super().__init__(
            use_chroma=config.get("use_chroma", True)
        )
        self.max_episodes_per_task = config.get("max_episodes_per_task", 10)
        self.auto_consolidate = config.get("auto_consolidate", True)

    async def record_task_execution(
        self,
        task: str,
        actions: List[str],
        result: str,
        success: bool,
        duration_ms: float,
    ) -> str:
        """Record a complete task execution"""
        lessons = self._extract_lessons(actions, result, success)

        record_id = await self.remember_episode(
            task=task,
            context={
                "actions": actions,
                "result": result,
                "duration_ms": duration_ms,
            },
            outcome="success" if success else "failure",
            success=success,
            lessons=lessons,
        )

        if self.auto_consolidate and success:
            await self.consolidate_learning()

        return record_id

    def _extract_lessons(self, actions: List[str], result: str, success: bool) -> List[str]:
        """Extract lessons from task execution"""
        lessons = []

        if not success:
            lessons.append(f"Failed task - avoid repeating: {result[:100]}")
        else:
            lessons.append(f"Successfully completed task with actions: {' -> '.join(actions[:3])}")

        return lessons

    async def get_relevant_context(self, query: str, limit: int = 5) -> str:
        """Get relevant memory context for prompts"""
        memories = await self.recall(query, limit=limit)

        context_parts = []

        for memory in memories.get("episodic", [])[:2]:
            context_parts.append(f"Past experience: {memory.content[:200]}")

        for memory in memories.get("semantic", [])[:2]:
            context_parts.append(f"Known fact: {memory.content[:200]}")

        for memory in memories.get("procedural", [])[:2]:
            context_parts.append(f"Procedure: {memory.content[:200]}")

        return "\n\n".join(context_parts) if context_parts else ""

    def export_memory(self) -> Dict[str, Any]:
        """Export all memory for backup"""
        return {
            "episodic": {
                k: [
                    {
                        "content": e.content,
                        "outcome": e.outcome,
                        "lessons": e.lessons_learned,
                        "created_at": e.created_at.isoformat(),
                    }
                    for e in episodes
                ]
                for k, episodes in self.episodic_store.items()
            },
            "semantic": {
                k: {
                    "concept": v.concept,
                    "facts": v.facts,
                    "confidence": v.confidence,
                }
                for k, v in self.semantic_store.items()
            },
            "procedural": {
                k: {
                    "skill_name": v.skill_name,
                    "steps": v.steps,
                    "success_rate": v.success_rate,
                    "usage_count": v.usage_count,
                }
                for k, v in self.procedural_store.items()
            },
            "exported_at": datetime.now().isoformat(),
        }

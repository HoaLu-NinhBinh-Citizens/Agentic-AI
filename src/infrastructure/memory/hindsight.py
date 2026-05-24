"""Hindsight memory system for Agentic-AI CLI.

Inspired by oh-my-pi's Hindsight memory:
- retain: Queue durable facts into memory bank
- recall: Search memory bank for relevant facts
- reflect: Synthesize answer over memory bank
- Project-scoped by default
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class MemoryEntry:
    """A fact stored in the memory bank."""
    
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""
    context: str = ""  # How this fact was learned
    project_id: str = ""  # Project scope
    project_path: str = ""
    
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    
    # Usage tracking
    access_count: int = 0
    usefulness_score: float = 0.0
    
    # Metadata
    tags: list[str] = field(default_factory=list)
    source: str = ""  # How it was retained (manual, auto, extraction)
    embedding: list[float] | None = None  # For semantic search
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "context": self.context,
            "project_id": self.project_id,
            "project_path": self.project_path,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "access_count": self.access_count,
            "usefulness_score": self.usefulness_score,
            "tags": self.tags,
            "source": self.source,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryEntry:
        return cls(
            id=data["id"],
            content=data["content"],
            context=data.get("context", ""),
            project_id=data.get("project_id", ""),
            project_path=data.get("project_path", ""),
            created_at=datetime.fromisoformat(data["created_at"]),
            last_accessed=datetime.fromisoformat(data.get("last_accessed", data["created_at"])),
            access_count=data.get("access_count", 0),
            usefulness_score=data.get("usefulness_score", 0.0),
            tags=data.get("tags", []),
            source=data.get("source", ""),
        )


@dataclass
class MemorySearchResult:
    """Result from memory search."""
    entry: MemoryEntry
    relevance_score: float
    matched_terms: list[str] = field(default_factory=list)


class HindsightMemoryBank:
    """Project-scoped memory bank.
    
    Like omp's Hindsight system:
    - retain() queues durable facts
    - recall() searches the bank
    - reflect() synthesizes answers
    - Project-scoped by default
    """
    
    def __init__(self, project_id: str, project_path: Path | None = None):
        self.project_id = project_id
        self.project_path = project_path or Path.cwd()
        self.storage_path = self._get_storage_path()
        self.entries: dict[str, MemoryEntry] = {}
        self._load()
    
    def _get_storage_path(self) -> Path:
        """Get path for memory storage."""
        config_home = Path.home() / ".config" / "ai-support"
        project_dir = config_home / "memory" / self.project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        return project_dir / "bank.json"
    
    def _load(self):
        """Load memory bank from disk."""
        if not self.storage_path.exists():
            return
        
        try:
            data = json.loads(self.storage_path.read_text())
            self.entries = {
                e["id"]: MemoryEntry.from_dict(e)
                for e in data.get("entries", [])
            }
        except Exception:
            pass
    
    def _save(self):
        """Save memory bank to disk."""
        data = {
            "project_id": self.project_id,
            "project_path": str(self.project_path),
            "updated_at": datetime.now().isoformat(),
            "entries": [e.to_dict() for e in self.entries.values()],
        }
        self.storage_path.write_text(json.dumps(data, indent=2))
    
    async def retain(
        self,
        content: str,
        context: str = "",
        tags: list[str] | None = None,
        source: str = "manual",
    ) -> str:
        """Queue a durable fact into the memory bank.
        
        Args:
            content: The fact to retain
            context: How this fact was learned
            tags: Optional tags for organization
            source: How it was retained (manual, auto, extraction)
            
        Returns:
            Entry ID for later reference
        """
        entry = MemoryEntry(
            content=content,
            context=context,
            project_id=self.project_id,
            project_path=str(self.project_path),
            tags=tags or [],
            source=source,
        )
        
        self.entries[entry.id] = entry
        self._save()
        
        return entry.id
    
    async def recall(
        self,
        query: str,
        limit: int = 5,
        tags: list[str] | None = None,
    ) -> list[MemorySearchResult]:
        """Search the memory bank for relevant facts.
        
        Args:
            query: Search query
            limit: Maximum results to return
            tags: Optional tag filter
            
        Returns:
            List of relevant memory entries with relevance scores
        """
        query_lower = query.lower()
        query_terms = set(query_lower.split())
        
        results: list[MemorySearchResult] = []
        
        for entry in self.entries.values():
            # Filter by tags if specified
            if tags and not any(t in entry.tags for t in tags):
                continue
            
            # Calculate relevance score
            score = 0.0
            matched_terms = []
            
            content_lower = entry.content.lower()
            
            # Exact query in content
            if query_lower in content_lower:
                score += 10.0
                matched_terms.append(query_lower)
            
            # Any query term in content
            for term in query_terms:
                if term in content_lower:
                    score += 1.0
                    matched_terms.append(term)
            
            # Query in context
            if query_lower in entry.context.lower():
                score += 2.0
            
            # Recency bonus
            days_old = (datetime.now() - entry.last_accessed).days
            if days_old < 7:
                score += 2.0
            elif days_old < 30:
                score += 1.0
            
            # Access frequency bonus
            score += min(entry.access_count * 0.1, 2.0)
            
            # Usefulness score
            score += entry.usefulness_score * 0.5
            
            if score > 0:
                results.append(MemorySearchResult(
                    entry=entry,
                    relevance_score=score,
                    matched_terms=list(set(matched_terms)),
                ))
        
        # Sort by relevance
        results.sort(key=lambda r: r.relevance_score, reverse=True)
        
        # Limit results
        return results[:limit]
    
    async def reflect(self, question: str, limit: int = 10) -> str:
        """Synthesize an answer from the memory bank.
        
        Uses the LLM to synthesize an answer based on relevant facts.
        
        Args:
            question: The question to answer
            limit: Number of facts to consider
            
        Returns:
            Synthesized answer string
        """
        facts = await self.recall(question, limit=limit)
        
        if not facts:
            return "I don't have any relevant memories for this."
        
        # Build context from facts
        context_parts = []
        for i, result in enumerate(facts, 1):
            entry = result.entry
            context_parts.append(f"[{i}] {entry.content}")
            if entry.context:
                context_parts.append(f"    Context: {entry.context}")
        
        context = "\n".join(context_parts)
        
        # Build reflection prompt
        prompt = f"""Based on the following memories, answer the question.

Question: {question}

Memories:
{context}

Answer the question based on the memories above. If the memories don't contain enough information to fully answer, say what you can based on available information."""
        
        # TODO: Integrate with LLM
        # For now, return formatted context
        return f"Based on my memory bank:\n\n{context}"
    
    async def update_usefulness(
        self,
        entry_id: str,
        helpful: bool,
    ) -> None:
        """Update usefulness score after recall.
        
        Args:
            entry_id: The memory entry ID
            helpful: Whether the recalled fact was helpful
        """
        if entry_id not in self.entries:
            return
        
        entry = self.entries[entry_id]
        entry.access_count += 1
        entry.last_accessed = datetime.now()
        
        # Update usefulness score (simple exponential moving average)
        delta = 1.0 if helpful else -0.5
        entry.usefulness_score = max(0, min(10, entry.usefulness_score + delta * 0.2))
        
        self._save()
    
    async def forget(self, entry_id: str) -> bool:
        """Remove a fact from memory.
        
        Args:
            entry_id: The memory entry ID to remove
            
        Returns:
            True if removed, False if not found
        """
        if entry_id in self.entries:
            del self.entries[entry_id]
            self._save()
            return True
        return False
    
    def list_all(self, tags: list[str] | None = None) -> list[MemoryEntry]:
        """List all memory entries.
        
        Args:
            tags: Optional tag filter
            
        Returns:
            List of all memory entries
        """
        entries = list(self.entries.values())
        
        if tags:
            entries = [e for e in entries if any(t in e.tags for t in tags)]
        
        return sorted(entries, key=lambda e: e.created_at, reverse=True)
    
    def get_stats(self) -> dict[str, Any]:
        """Get memory bank statistics."""
        entries = list(self.entries.values())
        
        return {
            "total_entries": len(entries),
            "project_id": self.project_id,
            "project_path": str(self.project_path),
            "storage_path": str(self.storage_path),
            "total_accesses": sum(e.access_count for e in entries),
            "avg_usefulness": sum(e.usefulness_score for e in entries) / len(entries) if entries else 0,
            "entries_by_source": {
                source: sum(1 for e in entries if e.source == source)
                for source in set(e.source for e in entries)
            },
            "entries_by_tag": {
                tag: sum(1 for e in entries if tag in e.tags)
                for tag in set(t for e in entries for t in e.tags)
            },
        }


class SessionCompactor:
    """Compress session into mental model for next session.
    
    Like omp's session compaction:
    - Compresses conversation into key learnings
    - Stored in Hindsight bank
    - Loaded at next session start
    """
    
    def __init__(self, memory_bank: HindsightMemoryBank):
        self.bank = memory_bank
    
    async def compress(
        self,
        session_messages: list[dict[str, Any]],
        session_summary: str = "",
    ) -> list[str]:
        """Compress session into mental model.
        
        Args:
            session_messages: List of session messages
            session_summary: Optional human summary
            
        Returns:
            List of retained fact IDs
        """
        retained_ids = []
        
        # Extract key facts from conversation
        facts = self._extract_facts(session_messages)
        
        for fact in facts:
            entry_id = await self.bank.retain(
                content=fact["content"],
                context=fact.get("context", ""),
                tags=fact.get("tags", []),
                source="session_compaction",
            )
            retained_ids.append(entry_id)
        
        # Also retain human summary if provided
        if session_summary:
            entry_id = await self.bank.retain(
                content=session_summary,
                context="Session summary",
                tags=["session-summary"],
                source="session_compaction",
            )
            retained_ids.append(entry_id)
        
        return retained_ids
    
    def _extract_facts(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Extract key facts from session messages."""
        facts = []
        
        # Simple extraction - look for patterns
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            if role == "assistant" and content:
                # Look for important statements
                if "important:" in content.lower():
                    facts.append({
                        "content": content,
                        "context": f"From {role} message",
                        "tags": ["important", "session-info"],
                    })
                
                # Look for code that was written
                if "```" in content:
                    facts.append({
                        "content": f"Code was written: {content[:200]}...",
                        "context": "Code generation during session",
                        "tags": ["code", "session-info"],
                    })
        
        return facts


# Global memory bank instance
_memory_bank: HindsightMemoryBank | None = None


def get_memory_bank(project_id: str = "default") -> HindsightMemoryBank:
    """Get or create global memory bank."""
    global _memory_bank
    if _memory_bank is None or _memory_bank.project_id != project_id:
        _memory_bank = HindsightMemoryBank(project_id)
    return _memory_bank

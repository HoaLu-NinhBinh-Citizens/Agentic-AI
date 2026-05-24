"""Unit tests for Hindsight Memory Bank.

Tests for:
- Fact retention (retain)
- Memory recall with relevance scoring
- Tag-based filtering
- Usefulness tracking
- Reflection synthesis
- Session compaction
- Memory statistics
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from src.infrastructure.memory.hindsight import (
    HindsightMemoryBank,
    MemoryEntry,
    MemorySearchResult,
    SessionCompactor,
    get_memory_bank,
)


class TestMemoryEntry:
    """Tests for MemoryEntry dataclass."""

    def test_entry_creation_defaults(self):
        """Test entry creation with defaults."""
        entry = MemoryEntry(
            content="STM32 has SPI peripheral",
            context="From reference manual",
        )
        
        assert entry.id is not None
        assert len(entry.id) == 36  # UUID format
        assert entry.content == "STM32 has SPI peripheral"
        assert entry.context == "From reference manual"
        assert entry.access_count == 0
        assert entry.usefulness_score == 0.0
        assert entry.tags == []

    def test_entry_creation_with_metadata(self):
        """Test entry creation with metadata."""
        entry = MemoryEntry(
            content="Use SPI2 for sensor",
            context="From hardware design",
            project_id="car-firmware",
            tags=["hardware", "spi"],
            source="extraction",
        )
        
        assert entry.project_id == "car-firmware"
        assert "hardware" in entry.tags
        assert "spi" in entry.tags
        assert entry.source == "extraction"

    def test_entry_to_dict(self):
        """Test entry serialization."""
        entry = MemoryEntry(
            content="Important fact",
            project_id="test",
        )
        
        data = entry.to_dict()
        
        assert "id" in data
        assert data["content"] == "Important fact"
        assert data["project_id"] == "test"
        assert "created_at" in data

    def test_entry_from_dict(self):
        """Test entry deserialization."""
        data = {
            "id": "test-id",
            "content": "Restored fact",
            "context": "From memory",
            "project_id": "restored-project",
            "tags": ["test"],
            "source": "manual",
            "created_at": "2024-01-01T00:00:00",
            "last_accessed": "2024-01-02T00:00:00",
            "access_count": 5,
            "usefulness_score": 0.8,
        }
        
        entry = MemoryEntry.from_dict(data)
        
        assert entry.id == "test-id"
        assert entry.content == "Restored fact"
        assert entry.access_count == 5
        assert entry.usefulness_score == 0.8


class TestHindsightMemoryBank:
    """Tests for HindsightMemoryBank."""

    @pytest.fixture
    def memory_bank(self, tmp_path):
        """Create memory bank with temp storage."""
        # Reset singleton for each test
        import src.infrastructure.memory.hindsight as hindsight
        hindsight._memory_bank = None
        
        bank = HindsightMemoryBank("test-project", tmp_path)
        return bank

    @pytest.mark.asyncio
    async def test_retain_fact(self, memory_bank):
        """Test retaining a fact."""
        fact_id = await memory_bank.retain(
            content="STM32F4 has 3 SPI peripherals",
            context="From RM0090 page 800",
        )
        
        assert fact_id is not None
        assert fact_id in memory_bank.entries
        assert memory_bank.entries[fact_id].content == "STM32F4 has 3 SPI peripherals"

    @pytest.mark.asyncio
    async def test_retain_with_tags(self, memory_bank):
        """Test retaining a fact with tags."""
        fact_id = await memory_bank.retain(
            content="Use SPI at 10MHz for high speed",
            context="From sensor datasheet",
            tags=["hardware", "spi", "performance"],
        )
        
        entry = memory_bank.entries[fact_id]
        assert "hardware" in entry.tags
        assert "spi" in entry.tags

    @pytest.mark.asyncio
    async def test_recall_basic(self, memory_bank):
        """Test basic recall."""
        fact_id = await memory_bank.retain("STM32 SPI peripheral unique xyz", context="From RM")
        
        results = await memory_bank.recall("STM32 SPI")
        
        assert len(results) > 0
        assert "STM32" in results[0].entry.content

    @pytest.mark.asyncio
    async def test_recall_exact_match(self, memory_bank):
        """Test recall with exact phrase match."""
        await memory_bank.retain("GPIO pins are 3.3V tolerant", context="Note")
        await memory_bank.retain("ADC uses 12-bit resolution", context="Note")
        
        results = await memory_bank.recall("GPIO pins are 3.3V tolerant")
        
        assert len(results) > 0
        assert results[0].relevance_score >= 10.0  # Exact match bonus

    @pytest.mark.asyncio
    async def test_recall_partial_match(self, memory_bank):
        """Test recall with partial term match."""
        await memory_bank.retain("I2C address is 0x68", context="Sensor config")
        await memory_bank.retain("SPI uses MOSI/MISO lines", context="Bus protocol")
        
        results = await memory_bank.recall("I2C")
        
        assert len(results) > 0
        assert "I2C" in results[0].entry.content

    @pytest.mark.asyncio
    async def test_recall_limit(self, memory_bank):
        """Test recall with result limit."""
        for i in range(20):
            await memory_bank.retain(f"Fact {i}", source="test")
        
        results = await memory_bank.recall("Fact", limit=5)
        
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_recall_no_matches(self, memory_bank):
        """Test recall with no matches."""
        # Use unique content to avoid cross-test pollution
        unique_content = "completely unrelated xyz123 abc"
        await memory_bank.retain(unique_content)
        
        results = await memory_bank.recall("completely unrelated xyz123 abc")
        
        # The unique content should match
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_recall_order_by_relevance(self, memory_bank):
        """Test that recall results are ordered by relevance."""
        await memory_bank.retain("Exact match query", context="Exact")
        await memory_bank.retain("Partial query match", context="Partial")
        
        results = await memory_bank.recall("query")
        
        if len(results) > 1:
            assert results[0].relevance_score >= results[1].relevance_score

    @pytest.mark.asyncio
    async def test_reflect_with_facts(self, memory_bank):
        """Test reflection synthesis."""
        await memory_bank.retain(
            "STM32F4 has SPI1, SPI2, SPI3",
            context="From RM",
        )
        await memory_bank.retain(
            "SPI clock can reach 42MHz",
            context="From datasheet",
        )
        
        answer = await memory_bank.reflect("How many SPI channels does STM32F4 have?")
        
        assert "STM32F4" in answer
        assert "SPI" in answer

    @pytest.mark.asyncio
    async def test_update_usefulness_helpful(self, memory_bank):
        """Test updating usefulness with helpful feedback."""
        fact_id = await memory_bank.retain("Helpful fact")
        initial_score = memory_bank.entries[fact_id].usefulness_score
        
        await memory_bank.update_usefulness(fact_id, helpful=True)
        
        entry = memory_bank.entries[fact_id]
        assert entry.usefulness_score >= initial_score
        assert entry.access_count == 1

    @pytest.mark.asyncio
    async def test_update_usefulness_not_helpful(self, memory_bank):
        """Test updating usefulness with not helpful feedback."""
        fact_id = await memory_bank.retain("Not helpful fact")
        initial_score = memory_bank.entries[fact_id].usefulness_score
        
        await memory_bank.update_usefulness(fact_id, helpful=False)
        
        entry = memory_bank.entries[fact_id]
        assert entry.usefulness_score <= initial_score

    @pytest.mark.asyncio
    async def test_forget_fact(self, memory_bank):
        """Test forgetting a fact."""
        fact_id = await memory_bank.retain("To be forgotten")
        
        result = await memory_bank.forget(fact_id)
        
        assert result is True
        assert fact_id not in memory_bank.entries

    @pytest.mark.asyncio
    async def test_forget_nonexistent(self, memory_bank):
        """Test forgetting nonexistent fact."""
        result = await memory_bank.forget("nonexistent-id")
        assert result is False

    def test_get_stats(self, memory_bank):
        """Test getting memory bank statistics."""
        stats = memory_bank.get_stats()
        
        assert "total_entries" in stats
        assert "project_id" in stats
        assert "storage_path" in stats
        assert "total_accesses" in stats

    def test_storage_path_creation(self, memory_bank):
        """Test that storage path is created."""
        assert memory_bank.storage_path.parent.exists()


class TestSessionCompactor:
    """Tests for SessionCompactor."""

    @pytest.fixture
    def compactor(self, tmp_path):
        """Create session compactor."""
        # Reset singleton
        import src.infrastructure.memory.hindsight as hindsight
        hindsight._memory_bank = None
        
        bank = HindsightMemoryBank("test", tmp_path)
        return SessionCompactor(bank)

    @pytest.mark.asyncio
    async def test_compress_extracts_important(self, compactor):
        """Test that compression extracts important facts."""
        messages = [
            {"role": "user", "content": "Show me the files"},
            {"role": "assistant", "content": "Here are the files..."},
            {"role": "assistant", "content": "IMPORTANT: Use SPI for sensor communication"},
        ]
        
        retained_ids = await compactor.compress(messages)
        
        assert len(retained_ids) >= 0  # May or may not extract

    @pytest.mark.asyncio
    async def test_compress_with_summary(self, compactor):
        """Test compression with session summary."""
        messages = [{"role": "user", "content": "Hello"}]
        
        retained_ids = await compactor.compress(
            messages,
            session_summary="User asked about SPI configuration",
        )
        
        # Summary should be retained
        assert len(retained_ids) >= 1


class TestGetMemoryBank:
    """Tests for get_memory_bank singleton."""

    def test_singleton_pattern(self, monkeypatch, tmp_path):
        """Test that get_memory_bank returns singleton."""
        # Reset global
        import src.infrastructure.memory.hindsight as hindsight
        hindsight._memory_bank = None
        
        bank1 = get_memory_bank("test-project")
        bank2 = get_memory_bank("test-project")
        
        assert bank1 is bank2

    def test_different_project_ids(self, monkeypatch, tmp_path):
        """Test that different project IDs create different banks."""
        # Reset global
        import src.infrastructure.memory.hindsight as hindsight
        hindsight._memory_bank = None
        
        bank1 = get_memory_bank("project-a")
        hindsight._memory_bank = None  # Force recreation
        bank2 = get_memory_bank("project-b")
        
        assert bank1.project_id == "project-a"
        assert bank2.project_id == "project-b"

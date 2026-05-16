"""Tests for SemanticMemory error handling contract.

These tests verify the agent-facing error handling API:
- last_operation state tracking
- health_check() structured response
- Error code mapping
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.core.memory.semantic_memory import (
    SemanticMemory,
    MemoryOperation,
    OperationStatus,
    ErrorCode,
    HealthStatus,
    TRANSIENT_ERRORS,
)
from src.infrastructure.embeddings.embedding_service import (
    EmbeddingService,
    EmbeddingErrorCode,
)


class TestMemoryOperation:
    """Tests for MemoryOperation dataclass."""

    def test_default_state(self):
        """Default operation should be success with no error."""
        op = MemoryOperation()
        assert op.status == OperationStatus.SUCCESS
        assert op.error_code is None
        assert op.reason == ""
        assert op.retryable is False
        assert op.dedup_parent_id is None

    def test_to_dict(self):
        """to_dict should return agent-consumable format."""
        op = MemoryOperation(
            status=OperationStatus.FAILED,
            error_code=ErrorCode.LIMIT_REACHED,
            reason="Storage full",
            retryable=False,
            dedup_parent_id=None,
        )
        d = op.to_dict()
        assert d["status"] == "failed"
        assert d["error_code"] == "LIMIT_REACHED"
        assert d["reason"] == "Storage full"
        assert d["retryable"] is False
        assert d["dedup_parent_id"] is None

    def test_dedup_operation(self):
        """Dedup operation should have dedup_parent_id."""
        op = MemoryOperation(
            status=OperationStatus.DEDUPED,
            error_code=ErrorCode.DUPLICATE_CONTENT,
            reason="Duplicate detected",
            retryable=False,
            dedup_parent_id="parent-123",
        )
        assert op.status == OperationStatus.DEDUPED
        assert op.dedup_parent_id == "parent-123"


class TestErrorCode:
    """Tests for ErrorCode enum."""

    def test_transient_errors_defined(self):
        """TRANSIENT_ERRORS should contain expected codes."""
        assert ErrorCode.EMBEDDING_TIMEOUT in TRANSIENT_ERRORS
        assert ErrorCode.EMBEDDING_NETWORK_ERROR in TRANSIENT_ERRORS
        assert ErrorCode.OLLAMA_UNAVAILABLE in TRANSIENT_ERRORS
        assert ErrorCode.DB_CONNECTION_LOST in TRANSIENT_ERRORS

    def test_non_retryable_not_in_transient(self):
        """Permanent errors should not be retryable."""
        assert ErrorCode.LIMIT_REACHED not in TRANSIENT_ERRORS
        assert ErrorCode.DIMENSION_MISMATCH not in TRANSIENT_ERRORS
        assert ErrorCode.NO_MEMORY_MODE not in TRANSIENT_ERRORS
        assert ErrorCode.DUPLICATE_CONTENT not in TRANSIENT_ERRORS

    def test_error_code_values(self):
        """Error codes should have expected string values."""
        assert ErrorCode.LIMIT_REACHED.value == "LIMIT_REACHED"
        assert ErrorCode.DIMENSION_MISMATCH.value == "DIMENSION_MISMATCH"


class TestHealthStatus:
    """Tests for HealthStatus dataclass."""

    def test_healthy_status(self):
        """Healthy status should have all true."""
        hs = HealthStatus(status="healthy", db=True, embedding=True)
        assert hs.status == "healthy"
        assert hs.db is True
        assert hs.embedding is True

    def test_no_memory_status(self):
        """No-memory status should have all false."""
        hs = HealthStatus(status="no_memory", db=False, embedding=False)
        assert hs.status == "no_memory"
        assert hs.db is False
        assert hs.embedding is False

    def test_to_dict(self):
        """to_dict should return agent-consumable format."""
        hs = HealthStatus(status="degraded", db=True, embedding=False)
        d = hs.to_dict()
        assert d["status"] == "degraded"
        assert d["db"] is True
        assert d["embedding"] is False


class TestEmbeddingErrorCode:
    """Tests for EmbeddingErrorCode enum."""

    def test_error_code_values(self):
        """Error codes should have expected string values."""
        assert EmbeddingErrorCode.TIMEOUT.value == "TIMEOUT"
        assert EmbeddingErrorCode.NETWORK_ERROR.value == "NETWORK_ERROR"
        assert EmbeddingErrorCode.SERVICE_UNAVAILABLE.value == "SERVICE_UNAVAILABLE"

    def test_none_is_default(self):
        """NONE should be the default."""
        assert EmbeddingErrorCode.NONE.value == "NONE"


class TestSemanticMemoryErrorContract:
    """Tests for SemanticMemory error handling contract."""

    @pytest.fixture
    def memory(self):
        """Create memory instance with mocked embedding service."""
        mock_embed_service = MagicMock(spec=EmbeddingService)
        mock_embed_service.embed = AsyncMock(return_value=[])
        mock_embed_service.health_check = AsyncMock(return_value=False)
        mock_embed_service.last_error_code = EmbeddingErrorCode.SERVICE_UNAVAILABLE
        mock_embed_service.close = AsyncMock()
        mock_embed_service.get_stats = AsyncMock(return_value={})

        mem = SemanticMemory(embedding_service=mock_embed_service)
        mem._no_memory_mode = True  # Force no-memory mode
        return mem

    def test_last_operation_initial_none(self, memory):
        """last_operation should be None initially."""
        assert memory.last_operation is None

    @pytest.mark.asyncio
    async def test_no_memory_sets_operation(self, memory):
        """Storing in no-memory mode should set last_operation."""
        result = await memory.store_conversation("s1", "user", "hello")
        assert result is False
        op = memory.last_operation
        assert op is not None
        assert op.status == OperationStatus.NO_MEMORY
        assert op.error_code == ErrorCode.NO_MEMORY_MODE
        assert op.retryable is False

    @pytest.mark.asyncio
    async def test_empty_content_sets_operation(self, memory):
        """Empty content should set skipped status."""
        memory._no_memory_mode = False
        memory._embedding_service.embed = AsyncMock(return_value=[0.1] * 768)

        result = await memory.store_conversation("s1", "user", "")
        assert result is False
        op = memory.last_operation
        assert op.status == OperationStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_limit_reached_sets_operation(self, memory):
        """Limit reached should set FAILED with LIMIT_REACHED."""
        memory._no_memory_mode = False
        memory._max_vectors = 1
        memory._table = MagicMock()
        memory._table.count_rows = MagicMock(return_value=1)

        result = await memory.store_conversation("s1", "user", "hello world test")
        assert result is False
        op = memory.last_operation
        assert op.status == OperationStatus.FAILED
        assert op.error_code == ErrorCode.LIMIT_REACHED
        assert op.retryable is False


class TestEmbeddingServiceErrorTracking:
    """Tests for EmbeddingService error tracking."""

    @pytest.fixture
    def service(self):
        """Create embedding service."""
        return EmbeddingService()

    def test_default_error_code_none(self, service):
        """Default error code should be NONE."""
        assert service.last_error_code == EmbeddingErrorCode.NONE

    @pytest.mark.asyncio
    async def test_stats_includes_error_code(self, service):
        """get_stats should include last_error_code."""
        stats = await service.get_stats()
        assert "last_error_code" in stats
        assert stats["last_error_code"] == "NONE"

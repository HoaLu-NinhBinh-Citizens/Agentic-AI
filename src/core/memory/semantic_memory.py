"""SemanticMemory core implementation with LanceDB vector store.

Features:
|- Persistent semantic storage and retrieval
|- Async-safe operations
|- Atomic batch inserts
|- Session-based retrieval
|- RAG context building
|- Agent error handling contract (no-log-based state tracking)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

from infrastructure.embeddings.embedding_service import EmbeddingService, EmbeddingErrorCode
from .chunker import Chunker
from .deduplication import DeduplicationEngine

logger = logging.getLogger(__name__)

LANCE_DB_AVAILABLE = False
try:
    import lancedb
    LANCE_DB_AVAILABLE = True
except ImportError:
    logger.warning("LanceDB not installed. Install with: pip install lancedb")


class OperationStatus(str, Enum):
    """Status of a memory operation."""
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    DEDUPED = "deduped"
    NO_MEMORY = "no_memory"


class ErrorCode(str, Enum):
    """Error codes for memory operations.
    
    Retryable (transient): EMBEDDING_TIMEOUT, EMBEDDING_NETWORK_ERROR,
        OLLAMA_UNAVAILABLE, DB_CONNECTION_LOST
    Non-retryable (permanent): DIMENSION_MISMATCH, LIMIT_REACHED, INVALID_INPUT,
        BLOOM_ERROR
    Dedup: DUPLICATE_CONTENT
    System degraded: NO_MEMORY_MODE
    """
    # Retryable (transient)
    EMBEDDING_TIMEOUT = "EMBEDDING_TIMEOUT"
    EMBEDDING_NETWORK_ERROR = "EMBEDDING_NETWORK_ERROR"
    OLLAMA_UNAVAILABLE = "OLLAMA_UNAVAILABLE"
    DB_CONNECTION_LOST = "DB_CONNECTION_LOST"
    # Non-retryable (permanent)
    DIMENSION_MISMATCH = "DIMENSION_MISMATCH"
    LIMIT_REACHED = "LIMIT_REACHED"
    INVALID_INPUT = "INVALID_INPUT"
    BLOOM_ERROR = "BLOOM_ERROR"
    # Dedup
    DUPLICATE_CONTENT = "DUPLICATE_CONTENT"
    # System degraded
    NO_MEMORY_MODE = "NO_MEMORY_MODE"


TRANSIENT_ERRORS = frozenset({
    ErrorCode.EMBEDDING_TIMEOUT,
    ErrorCode.EMBEDDING_NETWORK_ERROR,
    ErrorCode.OLLAMA_UNAVAILABLE,
    ErrorCode.DB_CONNECTION_LOST,
})


@dataclass
class MemoryOperation:
    """Represents the state of the last memory operation.
    
    This is the PRIMARY source of truth for agents - NOT logs.
    
    Agent usage:
        success = await memory.store_conversation(...)
        if not success:
            state = memory.last_operation  # Use this, NOT logs
            # Decision: retry, dedup_success, or fail
    """
    status: OperationStatus = field(default=OperationStatus.SUCCESS)
    error_code: ErrorCode | None = None
    reason: str = ""
    retryable: bool = False
    dedup_parent_id: str | None = None
    timestamp: int = field(default_factory=lambda: int(time.time()))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for agent consumption."""
        return {
            "status": self.status.value,
            "error_code": self.error_code.value if self.error_code else None,
            "reason": self.reason,
            "retryable": self.retryable,
            "dedup_parent_id": self.dedup_parent_id,
            "timestamp": self.timestamp,
        }


@dataclass
class MemoryRecord:
    """A memory record for storage."""

    id: str
    type: str
    content: str
    embedding: list[float]
    session_id: str
    metadata: dict
    created_at: int
    chunk_index: int
    chunk_total: int
    parent_id: str


@dataclass
class MemoryResult:
    """A retrieved memory result."""

    content: str
    type: str
    metadata: dict
    score: float


@dataclass
class HealthStatus:
    """Health status response for agent contract.
    
    Usage:
        health = await memory.health_check()
        if health["status"] == "no_memory":
            use_local_context_only()
    """
    status: str  # "healthy", "degraded", "no_memory"
    db: bool
    embedding: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "db": self.db,
            "embedding": self.embedding,
        }


class SemanticMemory:
    """Semantic memory system with vector storage and retrieval.
    
    Agent Error Handling Contract:
    - NEVER read logs for decision making
    - Use ONLY: return value, last_operation, health_check()
    - last_operation is the PRIMARY source of truth for failures
    
    Example Agent Usage:
        ok = await memory.store_conversation(sid, role, content)
        if not ok:
            state = memory.last_operation
            if state.status == "deduped":
                pass  # Safe success
            elif state.error_code == "LIMIT_REACHED":
                stop_writes()
            elif state.retryable:
                await retry()
    """

    TABLE_NAME = "memory"
    TRIVIAL_PATTERNS = [
        re.compile(r"^(ok|got it|sure|yes|no|thanks|i see|yep|nope|uh huh)$"),
        re.compile(r"^.{0,9}$"),
    ]

    def __init__(
        self,
        db_path: str = "./data/lancedb",
        enable_bloom_dedup: bool = True,
        dedup_window: int = 20,
        max_chunk_size: int = 500,
        embedding_service: EmbeddingService | None = None,
        max_vectors: int = 0,
        warn_at_percent: int = 80,
        embedding_dimension: int = 1024,
    ) -> None:
        """Initialize semantic memory.

        Args:
            db_path: Path for LanceDB storage.
            enable_bloom_dedup: Enable Bloom filter for exact dedup.
            dedup_window: Window size for semantic dedup.
            max_chunk_size: Maximum chunk size in characters.
            embedding_service: Optional pre-configured embedding service.
            max_vectors: Maximum number of vectors (0 = unlimited).
            warn_at_percent: Warn when storage reaches this percentage of max_vectors.
            embedding_dimension: Expected embedding vector dimension (default 1024 for bge-m3).
        """
        self._db_path = db_path
        self._db = None
        self._table = None
        self._embedding_service = embedding_service or EmbeddingService()
        self._chunker = Chunker(max_chunk_size=max_chunk_size)
        self._dedup = DeduplicationEngine(
            window_size=dedup_window,
            enable_bloom=enable_bloom_dedup,
        )
        self._initialized = False
        self._no_memory_mode = False
        self._max_vectors = max_vectors
        self._warn_at_percent = warn_at_percent
        self._expected_embedding_dim: int | None = None
        self._embedding_dimension = embedding_dimension
        self._last_operation: MemoryOperation | None = None

    def _set_operation(
        self,
        status: OperationStatus,
        error_code: ErrorCode | None = None,
        reason: str = "",
        retryable: bool = False,
        dedup_parent_id: str | None = None,
    ) -> None:
        """Set last_operation state for agent consumption."""
        self._last_operation = MemoryOperation(
            status=status,
            error_code=error_code,
            reason=reason,
            retryable=retryable,
            dedup_parent_id=dedup_parent_id,
            timestamp=int(time.time()),
        )

    def _map_embedding_error(self, code: EmbeddingErrorCode) -> ErrorCode:
        """Map EmbeddingErrorCode to SemanticMemory ErrorCode.
        
        Args:
            code: Embedding error code.
            
        Returns:
            Corresponding SemanticMemory ErrorCode.
        """
        mapping = {
            EmbeddingErrorCode.TIMEOUT: ErrorCode.EMBEDDING_TIMEOUT,
            EmbeddingErrorCode.NETWORK_ERROR: ErrorCode.EMBEDDING_NETWORK_ERROR,
            EmbeddingErrorCode.HTTP_ERROR: ErrorCode.OLLAMA_UNAVAILABLE,
            EmbeddingErrorCode.EMPTY_RESULT: ErrorCode.OLLAMA_UNAVAILABLE,
            EmbeddingErrorCode.SERVICE_UNAVAILABLE: ErrorCode.OLLAMA_UNAVAILABLE,
            EmbeddingErrorCode.NONE: ErrorCode.OLLAMA_UNAVAILABLE,
        }
        return mapping.get(code, ErrorCode.OLLAMA_UNAVAILABLE)

    @property
    def last_operation(self) -> MemoryOperation | None:
        """Get the last operation state.
        
        PRIMARY source of truth for agents - NEVER use logs.
        
        Returns:
            MemoryOperation or None if no operation has been performed.
        """
        return self._last_operation

    async def init_db(self) -> None:
        """Initialize the database connection."""
        if not LANCE_DB_AVAILABLE:
            logger.warning("LanceDB not available. Running in no-memory mode.")
            self._no_memory_mode = True
            self._set_operation(
                OperationStatus.NO_MEMORY,
                ErrorCode.NO_MEMORY_MODE,
                "LanceDB not installed",
                retryable=False,
            )
            return

        try:
            os.makedirs(self._db_path, exist_ok=True)

            def _init_sync():
                return lancedb.connect(self._db_path)

            self._db = await asyncio.to_thread(_init_sync)

            table_names = await asyncio.to_thread(lambda: self._db.table_names())
            if self.TABLE_NAME not in table_names:
                schema = self._create_schema()
                await asyncio.to_thread(
                    lambda: self._db.create_table(self.TABLE_NAME, schema=schema)
                )
                logger.info("Created memory table: %s", self.TABLE_NAME)
            else:
                self._table = self._db.open_table(self.TABLE_NAME)
                await self._maybe_create_index()

            self._initialized = True
            logger.info("SemanticMemory initialized at: %s", self._db_path)

        except Exception as e:
            logger.error("Failed to initialize SemanticMemory: %s", str(e))
            self._no_memory_mode = True
            self._set_operation(
                OperationStatus.NO_MEMORY,
                ErrorCode.DB_CONNECTION_LOST,
                f"Initialization failed: {str(e)}",
                retryable=True,
            )

    async def _maybe_create_index(self) -> None:
        """Create index if beneficial and not already exists."""
        if self._table is None:
            return

        try:
            count = await asyncio.to_thread(lambda: self._table.count_rows())

            existing_indices = await asyncio.to_thread(
                lambda: self._table.list_indices()
            )

            if any(idx.get("column") == "embedding" for idx in existing_indices):
                logger.debug("memory_index_already_exists: embedding column index exists, skipping creation")
                return

            if count < 10000:
                logger.debug(
                    "Table has %d rows (< 10000), skipping index creation",
                    count,
                )
                return

            logger.info("Creating IVF_FLAT index for %d rows", count)

            def _create_index():
                self._table.create_index(
                    metric="cosine",
                    index_type="IVF_FLAT",
                    num_partitions=256,
                )

            await asyncio.to_thread(_create_index)
            logger.info("Index creation complete")

            if count > 500000:
                logger.warning(
                    "memory_index_recommendation: Table has > 500k rows. "
                    "Consider index tuning in Phase 4B."
                )

        except Exception as e:
            logger.error("Failed to create index: %s", str(e))

    async def _check_backpressure(self) -> tuple[bool, ErrorCode | None, str]:
        """Check if storage is within limits (backpressure check).

        Returns:
            Tuple of (allowed, error_code, reason).
        """
        if self._max_vectors == 0:
            return True, None, ""

        if self._table is None:
            return True, None, ""

        try:
            count = await asyncio.to_thread(lambda: self._table.count_rows())
            usage_percent = (count / self._max_vectors) * 100

            if usage_percent >= self._warn_at_percent:
                logger.warning(
                    "memory_store_warning_limit: storage at %.1f%% capacity (%d/%d vectors)",
                    usage_percent,
                    count,
                    self._max_vectors,
                )

            if count >= self._max_vectors:
                logger.error(
                    "memory_store_rejected_limit: storage limit reached (%d/%d vectors)",
                    count,
                    self._max_vectors,
                )
                return False, ErrorCode.LIMIT_REACHED, f"Storage limit reached ({count}/{self._max_vectors})"

            return True, None, ""

        except Exception as e:
            logger.warning("Failed to check backpressure: %s", str(e))
            return True, None, ""

    def _validate_embedding_dimension(self, embedding: list[float]) -> tuple[bool, str]:
        """Validate embedding dimension matches expected dimension.

        Args:
            embedding: The embedding to validate.

        Returns:
            Tuple of (valid, error_reason).
        """
        actual_dim = len(embedding)

        if self._expected_embedding_dim is None:
            self._expected_embedding_dim = actual_dim
            logger.info(
                "memory_embedding_dimension: initialized with dimension %d",
                actual_dim,
            )
            return True, ""

        if actual_dim != self._expected_embedding_dim:
            msg = f"expected {self._expected_embedding_dim}, got {actual_dim}"
            logger.error(
                "memory_embedding_dimension_mismatch: %s",
                msg,
            )
            return False, msg

        return True, ""

    def _create_schema(self):
        """Create LanceDB schema for memory table."""
        if not LANCE_DB_AVAILABLE:
            return None

        import lancedb

        dimension = self._expected_embedding_dim or self._embedding_dimension
        schema = lancedb.schema(
            [
                lancedb.field("id", lancedb.string()),
                lancedb.field("type", lancedb.string()),
                lancedb.field("content", lancedb.string()),
                lancedb.field("embedding", lancedb.vector(dimension)),
                lancedb.field("session_id", lancedb.string()),
                lancedb.field("metadata", lancedb.json()),
                lancedb.field("created_at", lancedb.int64()),
                lancedb.field("chunk_index", lancedb.int32()),
                lancedb.field("chunk_total", lancedb.int32()),
                lancedb.field("parent_id", lancedb.string()),
            ]
        )
        return schema

    def _is_trivial_content(self, content: str) -> bool:
        """Check if content is trivial and should be skipped."""
        content = content.strip().lower()
        if len(content) < 10:
            return True
        for pattern in self.TRIVIAL_PATTERNS:
            if pattern.match(content):
                return True
        return False

    async def store_conversation(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> bool:
        """Store a conversation turn.

        Args:
            session_id: Session identifier.
            role: Role (user or assistant).
            content: Message content.

        Returns:
            True if stored successfully. False indicates failure.
            Check last_operation for error details.

        Agent Contract:
            ok = await memory.store_conversation(sid, role, content)
            if not ok:
                state = memory.last_operation
                # Use state.status, state.error_code, state.retryable
        """
        if self._no_memory_mode:
            self._set_operation(
                OperationStatus.NO_MEMORY,
                ErrorCode.NO_MEMORY_MODE,
                "System in no-memory mode",
                retryable=False,
            )
            return False

        allowed, err_code, reason = await self._check_backpressure()
        if not allowed:
            self._set_operation(
                OperationStatus.FAILED,
                err_code,
                reason,
                retryable=False,
            )
            return False

        content = content.strip()
        if not content:
            self._set_operation(
                OperationStatus.SKIPPED,
                None,
                "Empty content",
                retryable=False,
            )
            return False

        if role == "assistant" and self._is_trivial_content(content):
            self._set_operation(
                OperationStatus.SKIPPED,
                None,
                "Trivial content skipped",
                retryable=False,
            )
            return False

        start_time = time.monotonic()
        parent_id = str(uuid.uuid4())
        chunks = self._chunker.chunk(content, parent_id)

        if not chunks:
            self._set_operation(
                OperationStatus.SKIPPED,
                None,
                "No chunks generated",
                retryable=False,
            )
            return False

        logger.info(
            "memory_chunked_event: role=%s, original_len=%d, num_chunks=%d",
            role,
            len(content),
            len(chunks),
        )

        records: list[MemoryRecord] = []
        for chunk in chunks:
            is_dup, dup_reason = await self._dedup.check_and_add(chunk.text, [])
            if is_dup:
                logger.info(
                    "memory_store_dedup_skipped: parent_id=%s, reason=%s",
                    parent_id,
                    dup_reason,
                )
                self._set_operation(
                    OperationStatus.DEDUPED,
                    ErrorCode.DUPLICATE_CONTENT,
                    f"Dedup: {dup_reason}",
                    retryable=False,
                    dedup_parent_id=parent_id,
                )
                return False

            embed_result = await self._embedding_service.embed(chunk.text)
            if not embed_result:
                err_code = self._embedding_service.last_error_code
                mapped_code = self._map_embedding_error(err_code)
                self._set_operation(
                    OperationStatus.FAILED,
                    mapped_code,
                    "Embedding failed",
                    retryable=mapped_code in TRANSIENT_ERRORS,
                )
                return False

            valid, dim_error = self._validate_embedding_dimension(embed_result)
            if not valid:
                self._set_operation(
                    OperationStatus.FAILED,
                    ErrorCode.DIMENSION_MISMATCH,
                    dim_error,
                    retryable=False,
                )
                return False

            is_dup, dup_reason = await self._dedup.check_and_add(chunk.text, embed_result)
            if is_dup:
                logger.info(
                    "memory_store_dedup_skipped (after embed): parent_id=%s, reason=%s",
                    parent_id,
                    dup_reason,
                )
                self._set_operation(
                    OperationStatus.DEDUPED,
                    ErrorCode.DUPLICATE_CONTENT,
                    f"Dedup after embed: {dup_reason}",
                    retryable=False,
                    dedup_parent_id=parent_id,
                )
                return False

            records.append(
                MemoryRecord(
                    id=str(uuid.uuid4()),
                    type="conversation",
                    content=chunk.text,
                    embedding=embed_result,
                    session_id=session_id,
                    metadata={"role": role},
                    created_at=int(time.time()),
                    chunk_index=chunk.chunk_index,
                    chunk_total=chunk.chunk_total,
                    parent_id=parent_id,
                )
            )

        if not records:
            self._set_operation(
                OperationStatus.SKIPPED,
                None,
                "No records to store",
                retryable=False,
            )
            return False

        try:
            await self._write_records(records)
            latency_ms = (time.monotonic() - start_time) * 1000
            logger.info(
                "memory_store_success: type=conversation, session_id=%s, "
                "num_chunks=%d, parent_id=%s, latency_ms=%.2f",
                session_id,
                len(records),
                parent_id,
                latency_ms,
            )
            self._set_operation(
                OperationStatus.SUCCESS,
                None,
                f"Stored {len(records)} chunks",
                retryable=False,
            )
            return True

        except Exception as e:
            logger.error("Failed to store conversation: %s", str(e))
            self._set_operation(
                OperationStatus.FAILED,
                ErrorCode.DB_CONNECTION_LOST,
                f"DB write failed: {str(e)}",
                retryable=True,
            )
            return False

    async def store_tool_result(
        self,
        session_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        result: str,
    ) -> bool:
        """Store a tool execution result.

        Args:
            session_id: Session identifier.
            tool_name: Tool name.
            arguments: Tool arguments.
            result: Tool result.

        Returns:
            True if stored successfully. False indicates failure.
            Check last_operation for error details.

        Agent Contract:
            ok = await memory.store_tool_result(sid, tool, args, result)
            if not ok:
                state = memory.last_operation
                # Use state.status, state.error_code, state.retryable
        """
        if self._no_memory_mode:
            self._set_operation(
                OperationStatus.NO_MEMORY,
                ErrorCode.NO_MEMORY_MODE,
                "System in no-memory mode",
                retryable=False,
            )
            return False

        allowed, err_code, reason = await self._check_backpressure()
        if not allowed:
            self._set_operation(
                OperationStatus.FAILED,
                err_code,
                reason,
                retryable=False,
            )
            return False

        if not result or not result.strip():
            self._set_operation(
                OperationStatus.SKIPPED,
                None,
                "Empty result",
                retryable=False,
            )
            return False

        start_time = time.monotonic()
        parent_id = str(uuid.uuid4())

        normalized_args = json.dumps(arguments, sort_keys=True)
        combined_text = f"Tool: {tool_name}\nArguments: {normalized_args}\nResult: {result}"

        chunks = self._chunker.chunk(combined_text, parent_id)

        if not chunks:
            self._set_operation(
                OperationStatus.SKIPPED,
                None,
                "No chunks generated",
                retryable=False,
            )
            return False

        tool_signature = f"{tool_name}:{normalized_args}"
        metadata = {
            "tool_name": tool_name,
            "tool_signature": tool_signature,
        }

        records: list[MemoryRecord] = []
        for chunk in chunks:
            is_dup, dup_reason = await self._dedup.check_and_add(chunk.text, [])
            if is_dup:
                logger.info(
                    "memory_store_dedup_skipped: parent_id=%s, reason=%s",
                    parent_id,
                    dup_reason,
                )
                self._set_operation(
                    OperationStatus.DEDUPED,
                    ErrorCode.DUPLICATE_CONTENT,
                    f"Dedup: {dup_reason}",
                    retryable=False,
                    dedup_parent_id=parent_id,
                )
                return False

            embed_result = await self._embedding_service.embed(chunk.text)
            if not embed_result:
                err_code = self._embedding_service.last_error_code
                mapped_code = self._map_embedding_error(err_code)
                self._set_operation(
                    OperationStatus.FAILED,
                    mapped_code,
                    "Embedding failed",
                    retryable=mapped_code in TRANSIENT_ERRORS,
                )
                return False

            valid, dim_error = self._validate_embedding_dimension(embed_result)
            if not valid:
                self._set_operation(
                    OperationStatus.FAILED,
                    ErrorCode.DIMENSION_MISMATCH,
                    dim_error,
                    retryable=False,
                )
                return False

            is_dup, dup_reason = await self._dedup.check_and_add(chunk.text, embed_result)
            if is_dup:
                logger.info(
                    "memory_store_dedup_skipped (after embed): parent_id=%s, reason=%s",
                    parent_id,
                    dup_reason,
                )
                self._set_operation(
                    OperationStatus.DEDUPED,
                    ErrorCode.DUPLICATE_CONTENT,
                    f"Dedup after embed: {dup_reason}",
                    retryable=False,
                    dedup_parent_id=parent_id,
                )
                return False

            records.append(
                MemoryRecord(
                    id=str(uuid.uuid4()),
                    type="tool_result",
                    content=chunk.text,
                    embedding=embed_result,
                    session_id=session_id,
                    metadata=metadata,
                    created_at=int(time.time()),
                    chunk_index=chunk.chunk_index,
                    chunk_total=chunk.chunk_total,
                    parent_id=parent_id,
                )
            )

        if not records:
            self._set_operation(
                OperationStatus.SKIPPED,
                None,
                "No records to store",
                retryable=False,
            )
            return False

        try:
            await self._write_records(records)
            latency_ms = (time.monotonic() - start_time) * 1000
            logger.info(
                "memory_store_success: type=tool_result, session_id=%s, "
                "num_chunks=%d, parent_id=%s, latency_ms=%.2f",
                session_id,
                len(records),
                parent_id,
                latency_ms,
            )
            self._set_operation(
                OperationStatus.SUCCESS,
                None,
                f"Stored {len(records)} chunks",
                retryable=False,
            )
            return True

        except Exception as e:
            logger.error("Failed to store tool result: %s", str(e))
            self._set_operation(
                OperationStatus.FAILED,
                ErrorCode.DB_CONNECTION_LOST,
                f"DB write failed: {str(e)}",
                retryable=True,
            )
            return False

    async def _write_records(self, records: list[MemoryRecord]) -> None:
        """Write records to database."""
        if self._no_memory_mode or self._db is None:
            return

        if self._table is None:
            self._table = self._db.open_table(self.TABLE_NAME)

        data = [
            {
                "id": r.id,
                "type": r.type,
                "content": r.content,
                "embedding": np.array(r.embedding, dtype=np.float32),
                "session_id": r.session_id,
                "metadata": json.dumps(r.metadata),
                "created_at": r.created_at,
                "chunk_index": r.chunk_index,
                "chunk_total": r.chunk_total,
                "parent_id": r.parent_id,
            }
            for r in records
        ]

        def _add():
            self._table.add(data)

        await asyncio.to_thread(_add)

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        session_id: str | None = None,
        min_score: float = 0.0,
    ) -> list[MemoryResult]:
        """Retrieve relevant memories.

        Args:
            query: Search query.
            top_k: Number of results to return.
            session_id: Optional session filter.
            min_score: Minimum similarity score (0-1).

        Returns:
            List of memory results. Empty list is NOT an error.

        Agent Contract:
            - Empty results = valid state (no relevant memory found)
            - Check health_check() only if you need to know why
        """
        if self._no_memory_mode or self._db is None:
            return []

        start_time = time.monotonic()
        query_embedding = await self._embedding_service.embed(query)

        if not query_embedding:
            logger.error("Failed to embed query for retrieval")
            return []

        if self._table is None:
            self._table = self._db.open_table(self.TABLE_NAME)

        oversample = max(top_k * 4, 20)

        try:
            table = self._table

            def _search():
                return (
                    table.search(query_embedding)
                    .limit(oversample)
                    .to_list()
                )

            results = await asyncio.to_thread(_search)

        except Exception as e:
            logger.error("Retrieval search failed: %s", str(e))
            return []

        filtered_results: list[MemoryResult] = []
        for row in results:
            row_session_id = row.get("session_id", "")
            distance = row.get("_distance", 1.0)
            score = 1.0 - distance

            if session_id and row_session_id != session_id:
                continue

            if score < min_score:
                continue

            metadata_str = row.get("metadata", "{}")
            try:
                metadata = json.loads(metadata_str) if isinstance(metadata_str, str) else metadata_str
            except json.JSONDecodeError:
                metadata = {}

            filtered_results.append(
                MemoryResult(
                    content=row.get("content", ""),
                    type=row.get("type", "conversation"),
                    metadata=metadata,
                    score=score,
                )
            )

        filtered_results.sort(key=lambda x: x.score, reverse=True)
        filtered_results = filtered_results[:top_k]

        if len(results) >= oversample and len(filtered_results) < top_k:
            logger.warning(
                "memory_retrieve_low_recall: requested %d, got %d after post-filter. "
                "Consider increasing oversample factor or check session size.",
                top_k,
                len(filtered_results),
            )

        latency_ms = (time.monotonic() - start_time) * 1000
        logger.info(
            "memory_retrieve_results: query=%s, top_k=%d, returned=%d, latency_ms=%.2f",
            query[:50],
            top_k,
            len(filtered_results),
            latency_ms,
        )

        return filtered_results

    async def build_rag_context(
        self,
        query: str,
        min_score: float = 0.5,
        max_results: int = 5,
    ) -> str:
        """Build RAG context from retrieved memories.

        Args:
            query: Search query.
            min_score: Minimum similarity score.
            max_results: Maximum number of results.

        Returns:
            Formatted RAG context string. Empty string is NOT an error.

        Agent Contract:
            context = await memory.build_rag_context(query)
            if not context:
                # NOT an error - just means no relevant context
                use_base_knowledge()
        """
        if min_score < 0.3:
            logger.warning("memory_rag_low_threshold_warning: min_score=%.2f", min_score)

        results = await self.retrieve(
            query=query,
            top_k=max_results,
            min_score=min_score,
        )

        if not results:
            return ""

        lines = ["[Memory Context]\n", "Use ONLY if relevant. Ignore if not helpful.\n"]

        for i, result in enumerate(results, 1):
            type_prefix = result.type
            if result.type == "conversation":
                role = result.metadata.get("role", "")
                type_prefix = f"conversation:{role}"

            content = result.content.replace("\n", " ").strip()
            if len(content) > 200:
                content = content[:200] + "..."

            lines.append(f"{i}. (score: {result.score:.2f} | {type_prefix}) {content}")

        return "\n".join(lines)

    async def close(self) -> None:
        """Close the database connection."""
        if self._embedding_service:
            await self._embedding_service.close()
        if self._db:
            self._db = None
            self._table = None

    async def health_check(self) -> HealthStatus:
        """Check if memory system is healthy.

        Returns:
            HealthStatus with status, db, and embedding flags.

        Agent Contract:
            Call BEFORE important writes (user input, tool results,
            structured JSON, multi-paragraph content).

            health = await memory.health_check()
            if health["status"] == "no_memory":
                use_local_context_only()
            elif health["status"] == "degraded":
                proceed_with_caution()
        """
        if self._no_memory_mode:
            return HealthStatus(
                status="no_memory",
                db=False,
                embedding=False,
            )

        embedding_ok = await self._embedding_service.health_check()
        db_ok = self._db is not None and self._table is not None

        if embedding_ok and db_ok:
            status = "healthy"
        elif embedding_ok or db_ok:
            status = "degraded"
        else:
            status = "no_memory"

        return HealthStatus(
            status=status,
            db=db_ok,
            embedding=embedding_ok,
        )

    async def get_stats(self) -> dict[str, Any]:
        """Get memory statistics.

        Returns:
            Statistics dictionary.
        """
        stats = {
            "initialized": self._initialized,
            "no_memory_mode": self._no_memory_mode,
            "db_path": self._db_path,
            "embedding_service": await self._embedding_service.get_stats(),
            "dedup_stats": await self._dedup.get_stats(),
        }

        if not self._no_memory_mode and self._table is not None:
            try:
                count = await asyncio.to_thread(lambda: self._table.count_rows())
                stats["vector_count"] = count
            except Exception:
                pass

        return stats

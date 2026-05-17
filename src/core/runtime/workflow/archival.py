"""Archival Retrieval - Phase 5A (v6).

Workflow history archival retrieval semantics.
Supports lazy restore, selective restore, and archive verification.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional, List

logger = logging.getLogger(__name__)


@dataclass
class ArchiveMetadata:
    """Metadata for archived workflow."""
    workflow_id: str
    archived_at: float
    event_count: int
    total_size_bytes: int
    
    # Archive location
    archive_path: str
    archive_format: str = "json"  # json, parquet, etc.
    
    # Integrity
    checksum: str = ""  # SHA-256 of archive content
    
    # Index
    first_sequence: int = 0
    last_sequence: int = 0
    
    # Compression
    compressed: bool = False
    compression_type: str = ""  # gzip, zstd, etc.


class ArchiveIndex:
    """Index for archived workflow retrieval.
    
    Maintains metadata for efficient archive lookup.
    """
    
    def __init__(self, index_store: Any = None):
        self._index_store = index_store
        self._cache: dict[str, ArchiveMetadata] = {}
    
    async def register_archive(
        self,
        workflow_id: str,
        metadata: ArchiveMetadata,
    ) -> None:
        """Register archived workflow in index."""
        self._cache[workflow_id] = metadata
        
        if self._index_store:
            await self._index_store.save(metadata)
    
    async def get_archive_metadata(
        self,
        workflow_id: str,
    ) -> Optional[ArchiveMetadata]:
        """Get archive metadata for workflow."""
        if workflow_id in self._cache:
            return self._cache[workflow_id]
        
        if self._index_store:
            metadata = await self._index_store.load(workflow_id)
            if metadata:
                self._cache[workflow_id] = metadata
            return metadata
        
        return None
    
    async def list_archived_workflows(
        self,
        prefix: str = "",
        limit: int = 100,
    ) -> List[ArchiveMetadata]:
        """List archived workflows."""
        if self._index_store:
            return await self._index_store.list(prefix, limit)
        
        return list(self._cache.values())[:limit]
    
    async def delete_archive(
        self,
        workflow_id: str,
    ) -> bool:
        """Remove archive from index."""
        if workflow_id in self._cache:
            del self._cache[workflow_id]
        
        if self._index_store:
            await self._index_store.delete(workflow_id)
        
        return True


class ArchiveRetriever:
    """Retrieves archived workflow history.
    
    RESTORE SEMANTICS
    ==================
    
    1. LAZY RESTORE:
       - Only restore when workflow needs to be replayed
       - Don't load entire archive into memory
       - Stream events as needed
    
    2. SELECTIVE RESTORE:
       - Can restore specific event ranges
       - Supports partial replay after restore
    
    3. VERIFICATION:
       - Verify checksum before restore
       - Reject corrupted archives
    
    4. INDEX LOOKUP:
       - Use archive index to find workflow
       - Fetch metadata before restore
    """
    
    def __init__(
        self,
        archive_store: Any = None,
        index: Optional[ArchiveIndex] = None,
        verify_checksum: bool = True,
    ):
        self._archive_store = archive_store
        self._index = index or ArchiveIndex()
        self._verify_checksum = verify_checksum
    
    async def restore_workflow(
        self,
        workflow_id: str,
        from_sequence: int = 0,
        to_sequence: int = 0,
    ) -> List[Any]:
        """Restore archived workflow events.
        
        Args:
            workflow_id: Workflow to restore.
            from_sequence: Start sequence (0 = beginning).
            to_sequence: End sequence (0 = end).
            
        Returns:
            List of archived events.
            
        Raises:
            ArchiveNotFoundError: If workflow not archived.
            ArchiveCorruptedError: If checksum verification fails.
        """
        # Step 1: Index lookup
        metadata = await self._index.get_archive_metadata(workflow_id)
        if not metadata:
            raise ArchiveNotFoundError(workflow_id)
        
        # Step 2: Verify integrity
        if self._verify_checksum:
            await self._verify_archive(workflow_id, metadata)
        
        # Step 3: Determine sequence range
        start_seq = max(from_sequence, metadata.first_sequence)
        end_seq = to_sequence or metadata.last_sequence
        
        # Step 4: Restore from archive
        events = await self._restore_events(
            metadata.archive_path,
            start_seq,
            end_seq,
            metadata.compressed,
            metadata.compression_type,
        )
        
        logger.info(
            f"Restored {len(events)} events for workflow {workflow_id[:8]}... "
            f"(sequences {start_seq}-{end_seq})"
        )
        
        return events
    
    async def restore_event_stream(
        self,
        workflow_id: str,
        from_sequence: int = 0,
    ):
        """Async generator for streaming event restore.
        
        Use for large archives to avoid loading all events into memory.
        
        Args:
            workflow_id: Workflow to restore.
            from_sequence: Start sequence.
            
        Yields:
            Events one at a time.
        """
        metadata = await self._index.get_archive_metadata(workflow_id)
        if not metadata:
            raise ArchiveNotFoundError(workflow_id)
        
        if self._verify_checksum:
            await self._verify_archive(workflow_id, metadata)
        
        start_seq = max(from_sequence, metadata.first_sequence)
        
        async for event in self._stream_events(
            metadata.archive_path,
            start_seq,
            metadata.compressed,
            metadata.compression_type,
        ):
            yield event
    
    async def _restore_events(
        self,
        archive_path: str,
        from_seq: int,
        to_seq: int,
        compressed: bool = False,
        compression: str = "",
    ) -> List[Any]:
        """Restore events from archive."""
        if self._archive_store:
            return await self._archive_store.fetch_range(
                archive_path,
                from_seq,
                to_seq,
            )
        
        # Local file fallback
        import os
        if os.path.exists(archive_path):
            data = self._read_archive_file(archive_path, compressed, compression)
            events = data.get("events", [])
            return [
                e for e in events
                if from_seq <= e.get("sequence", 0) <= to_seq
            ]
        
        return []
    
    async def _stream_events(
        self,
        archive_path: str,
        from_seq: int,
        compressed: bool,
        compression: str,
    ):
        """Stream events from archive."""
        if self._archive_store:
            async for event in self._archive_store.stream_range(
                archive_path,
                from_seq,
            ):
                yield event
            return
        
        # Local file fallback
        import os
        if os.path.exists(archive_path):
            data = self._read_archive_file(archive_path, compressed, compression)
            events = data.get("events", [])
            for event in events:
                if event.get("sequence", 0) >= from_seq:
                    yield event
    
    def _read_archive_file(
        self,
        path: str,
        compressed: bool,
        compression: str,
    ) -> dict:
        """Read and decompress archive file."""
        import gzip
        import zlib
        
        mode = "rb"
        if compression == "gzip" or (compressed and not compression):
            opener = lambda f: gzip.open(f, "rt", encoding="utf-8")
        else:
            opener = lambda f: open(f, "r", encoding="utf-8")
        
        with opener(path) as f:
            return json.load(f)
    
    async def _verify_archive(
        self,
        workflow_id: str,
        metadata: ArchiveMetadata,
    ) -> None:
        """Verify archive integrity via checksum."""
        if not metadata.checksum:
            logger.warning(f"No checksum for archive {workflow_id[:8]}...")
            return
        
        computed = await self._compute_checksum(metadata.archive_path)
        
        if computed != metadata.checksum:
            raise ArchiveCorruptedError(workflow_id, metadata.checksum, computed)
    
    async def _compute_checksum(self, path: str) -> str:
        """Compute SHA-256 checksum of archive."""
        import os
        
        if path.startswith("s3://"):
            # S3 checksum computation would go here
            # Use boto3 to get object metadata
            logger.debug(f"Would compute S3 checksum for {path}")
            return ""
        
        # Local file
        sha = hashlib.sha256()
        if os.path.exists(path):
            with open(path, "rb") as f:
                while chunk := f.read(8192):
                    sha.update(chunk)
        return sha.hexdigest()
    
    async def is_workflow_archived(self, workflow_id: str) -> bool:
        """Check if workflow is in archive."""
        metadata = await self._index.get_archive_metadata(workflow_id)
        return metadata is not None
    
    async def get_archive_info(self, workflow_id: str) -> Optional[ArchiveMetadata]:
        """Get archive metadata without restoring events."""
        return await self._index.get_archive_metadata(workflow_id)
    
    async def estimate_restore_size(
        self,
        workflow_id: str,
        from_sequence: int = 0,
        to_sequence: int = 0,
    ) -> int:
        """Estimate size of restored events in bytes."""
        metadata = await self._index.get_archive_metadata(workflow_id)
        if not metadata:
            return 0
        
        start_seq = max(from_sequence, metadata.first_sequence)
        end_seq = to_sequence or metadata.last_sequence
        total_seqs = end_seq - start_seq + 1
        
        if metadata.event_count > 0:
            avg_event_size = metadata.total_size_bytes / metadata.event_count
            return int(total_seqs * avg_event_size)
        
        return metadata.total_size_bytes


class ArchiveNotFoundError(Exception):
    """Raised when archived workflow is not found."""
    
    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        super().__init__(f"Archived workflow not found: {workflow_id}")


class ArchiveCorruptedError(Exception):
    """Raised when archive checksum verification fails."""
    
    def __init__(self, workflow_id: str, expected: str, actual: str):
        self.workflow_id = workflow_id
        self.expected_checksum = expected
        self.actual_checksum = actual
        super().__init__(
            f"Archive corrupted: {workflow_id} "
            f"(expected {expected[:8]}..., got {actual[:8]}...)"
        )

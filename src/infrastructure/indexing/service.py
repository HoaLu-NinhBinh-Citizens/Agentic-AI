"""IndexingService — wires KnowledgeBase + EmbeddingService + IncrementalIndexer
+ FileWatcher into one lifecycle-managed unit for the API server.

Before this module existed, every component was implemented but nothing
instantiated them in the serving path: the indexer was never constructed,
the watcher never started, and re-index never ran. This service is the
single integration point. Enable via AI_SUPPORT_ENABLE_INDEXING=1.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from src.domain.knowledge.kb import KnowledgeBase
from src.infrastructure.indexing.file_watcher import FileChange, FileWatcher
from src.infrastructure.indexing.incremental import IncrementalIndexer, is_indexable

logger = logging.getLogger(__name__)

DEFAULT_STATE_DB = ".ai_support/index_state.db"
DEFAULT_KB_DIR = ".ai_support/kb_chroma"


class IndexingService:
    """Owns the live indexing pipeline: initial sync + watcher-driven deltas.

    Watchdog callbacks arrive on a watchdog thread; they are marshalled onto
    the asyncio loop with call_soon_threadsafe because IncrementalIndexer
    schedules re-index work with asyncio.create_task (loop-thread only).
    """

    def __init__(
        self,
        workspace: Path,
        kb: KnowledgeBase | None = None,
        embed_service=None,
        state_db: Path | str = DEFAULT_STATE_DB,
    ) -> None:
        self._workspace = Path(workspace)

        if kb is None:
            from src.infrastructure.vector_db.chromadb.knowledge_store import (
                ChromaDBKnowledgeStore,
            )

            kb = KnowledgeBase(store=ChromaDBKnowledgeStore(DEFAULT_KB_DIR))
        self._kb = kb

        if embed_service is None:
            from src.infrastructure.embeddings.embedding_service import (
                EmbeddingService,
            )

            embed_service = EmbeddingService()
        self._kb.set_embed_service(embed_service)

        self._indexer = IncrementalIndexer(
            kb=self._kb, embed_svc=embed_service, state_db=state_db
        )
        self._watcher = FileWatcher(
            self._workspace, on_change=self._on_watcher_change
        )
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._sync_task: Optional[asyncio.Task] = None
        self._started = False

    @property
    def kb(self) -> KnowledgeBase:
        return self._kb

    async def start(self) -> None:
        """Connect state DB, start the watcher, kick off initial sync."""
        if self._started:
            return
        self._loop = asyncio.get_running_loop()
        self._indexer.connect()
        self._watcher.start()
        # Initial sync in the background so server startup is not blocked
        self._sync_task = asyncio.create_task(self._initial_sync())
        self._started = True
        logger.info("IndexingService started for %s", self._workspace)

    async def _initial_sync(self) -> None:
        try:
            stats = await self._indexer.sync(self._workspace)
            logger.info(
                "Initial index sync done: %d/%d files indexed, %d skipped, "
                "%d failed in %.1fs",
                stats.indexed_files,
                stats.total_files,
                stats.skipped_files,
                stats.failed_files,
                stats.elapsed_seconds,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Initial index sync failed")

    def _on_watcher_change(self, change: FileChange) -> None:
        """Watchdog-thread callback: marshal onto the asyncio loop."""
        if self._loop is None or self._loop.is_closed():
            return
        if not is_indexable(change.path):
            return
        # mark_dirty handles both modified and deleted paths: its reindex
        # batch deletes DB/KB entries for paths that no longer exist on disk.
        self._loop.call_soon_threadsafe(self._indexer.mark_dirty, change.path)

    async def stop(self) -> None:
        """Stop watcher, cancel in-flight sync, close the indexer."""
        if not self._started:
            return
        self._watcher.stop()
        if self._sync_task is not None and not self._sync_task.done():
            self._sync_task.cancel()
            try:
                await self._sync_task
            except (asyncio.CancelledError, Exception):
                pass
            self._sync_task = None
        self._indexer.close()
        self._started = False
        logger.info("IndexingService stopped")

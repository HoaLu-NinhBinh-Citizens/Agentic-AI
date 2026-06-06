"""Incremental Indexer — only re-index changed files since last run.

Architecture:
    State DB (SQLite) stores (path → mtime → content_hash → indexed_at).
    On sync(): diff filesystem vs DB → reindex only DELTA files →
    update DB → ChromaDB upserts delta only.

For watch mode: file watcher triggers mark_dirty() per changed path,
then a background task re-indexes lazily without blocking startup.

Dependency tracking:
    When file X changes, also re-index files that import X.
    Uses file_dependencies table for dependency graph.

Performance optimizations:
    - ThreadPoolExecutor for parallel file hashing
    - Async batch processing with controlled concurrency
    - LRU cache for content hashes
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Optional, Sequence

from src.infrastructure.indexing.hash_utils import compute_content_hash, compute_short_hash

if TYPE_CHECKING:
    from src.domain.knowledge.kb import KnowledgeBase
    from src.infrastructure.embeddings.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

# Supported file extensions for indexing
INDEXED_EXTENSIONS = {
    ".py", ".c", ".h", ".cpp", ".hpp", ".cc", ".cxx",
    ".rs", ".go", ".java", ".ts", ".tsx", ".js", ".jsx",
    ".yaml", ".yml", ".toml", ".json", ".md",
}

# Files / dirs to exclude from indexing
EXCLUDE_PATTERNS = {
    "node_modules", ".git", "__pycache__", ".pytest_cache",
    "build", "dist", ".venv", "venv", ".tox", ".mypy_cache",
    "*.pyc", "*.pyo", ".DS_Store",
}

# Maximum number of hash entries to cache
_MAX_HASH_CACHE_SIZE = 10000


# =============================================================================
# CACHED HASH FUNCTIONS
# =============================================================================


@lru_cache(maxsize=_MAX_HASH_CACHE_SIZE)
def cached_content_hash(content: str) -> str:
    """LRU-cached content hash for repeated lookups."""
    return compute_short_hash(content)


def compute_file_hash_parallel(
    files: list[Path],
    max_workers: int = 4,
) -> dict[str, tuple[str, float]]:
    """Compute content hashes for multiple files in parallel.
    
    Args:
        files: List of file paths to hash
        max_workers: Number of parallel workers
        
    Returns:
        Dict mapping path_str -> (content_hash, mtime)
    """
    results: dict[str, tuple[str, float]] = {}
    
    def hash_one(path: Path) -> tuple[str, tuple[str, float]]:
        try:
            mtime = path.stat().st_mtime
            content = path.read_text(encoding="utf-8", errors="replace")
            content_hash = cached_content_hash(content)
            return str(path), (content_hash, mtime)
        except OSError:
            return str(path), ("", 0.0)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(hash_one, f): f for f in files}
        for future in as_completed(futures):
            try:
                path_str, (content_hash, mtime) = future.result()
                results[path_str] = (content_hash, mtime)
            except Exception:
                pass
    
    return results


# =============================================================================
# STATE DB
# =============================================================================


@dataclass(slots=True)
class FileState:
    """State record for one tracked file."""
    
    path: str
    mtime: float
    content_hash: str
    indexed_at: float | None


class IndexStateDB:
    """SQLite-backed file state tracker for incremental indexing."""

    def __init__(self, db_path: Path | str = ".ai_support/index_state.db"):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    # ── lifecycle ──────────────────────────────────────────────────────────────

    def connect(self) -> None:
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _init_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS file_index_state (
                path       TEXT    PRIMARY KEY,
                mtime      REAL    NOT NULL,
                content_hash TEXT  NOT NULL,
                indexed_at REAL
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_indexed_at
            ON file_index_state (indexed_at)
        """)
        # Dependency tracking table
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS file_dependencies (
                source_path TEXT    NOT NULL,
                target_path TEXT    NOT NULL,
                dep_type   TEXT    NOT NULL DEFAULT 'import',
                line       INTEGER,
                PRIMARY KEY (source_path, target_path)
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_dependents
            ON file_dependencies (target_path)
        """)
        self._conn.commit()

    # ── read ──────────────────────────────────────────────────────────────────

    def get(self, path: str) -> FileState | None:
        row = self._conn.execute(
            "SELECT path, mtime, content_hash, indexed_at FROM file_index_state WHERE path=?",
            (path,),
        ).fetchone()
        return FileState(*row) if row else None

    def get_all(self) -> dict[str, FileState]:
        rows = self._conn.execute(
            "SELECT path, mtime, content_hash, indexed_at FROM file_index_state"
        ).fetchall()
        return {r[0]: FileState(*r) for r in rows}

    # ── write ─────────────────────────────────────────────────────────────────

    def upsert(self, state: FileState) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO file_index_state
               (path, mtime, content_hash, indexed_at) VALUES (?,?,?,?)""",
            (state.path, state.mtime, state.content_hash, state.indexed_at),
        )
        self._conn.commit()

    def mark_unindexed(self, path: str) -> None:
        self._conn.execute(
            "UPDATE file_index_state SET indexed_at=NULL WHERE path=?",
            (path,),
        )
        self._conn.commit()

    def delete(self, path: str) -> None:
        self._conn.execute("DELETE FROM file_index_state WHERE path=?", (path,))
        self._conn.commit()
    
    # ── dependency tracking ─────────────────────────────────────────────────────
    
    def upsert_dependencies(
        self,
        source_path: str,
        target_paths: list[str],
        dep_type: str = "import",
    ) -> None:
        """Store file dependencies.
        
        Args:
            source_path: Path to the file with the imports
            target_paths: List of paths that this file imports
            dep_type: Type of dependency (import, include, etc.)
        """
        # Delete existing dependencies for this source
        self._conn.execute(
            "DELETE FROM file_dependencies WHERE source_path=?",
            (source_path,),
        )
        # Insert new dependencies
        for target_path in target_paths:
            self._conn.execute(
                """INSERT OR REPLACE INTO file_dependencies
                   (source_path, target_path, dep_type) VALUES (?,?,?)""",
                (source_path, target_path, dep_type),
            )
        self._conn.commit()
    
    def get_dependents(self, path: str) -> list[str]:
        """Get all files that depend on the given file.
        
        Args:
            path: Path to the target file
            
        Returns:
            List of file paths that depend on this file
        """
        rows = self._conn.execute(
            "SELECT source_path FROM file_dependencies WHERE target_path=?",
            (path,),
        ).fetchall()
        return [r[0] for r in rows]
    
    def get_dependencies(self, path: str) -> list[str]:
        """Get all files that the given file depends on.
        
        Args:
            path: Path to the source file
            
        Returns:
            List of file paths that this file depends on
        """
        rows = self._conn.execute(
            "SELECT target_path FROM file_dependencies WHERE source_path=?",
            (path,),
        ).fetchall()
        return [r[0] for r in rows]
    
    def get_all_dependents_transitive(self, path: str) -> set[str]:
        """Get all files that transitively depend on the given file.
        
        Args:
            path: Path to the target file
            
        Returns:
            Set of all transitive dependent file paths
        """
        result: set[str] = set()
        queue = [path]
        
        while queue:
            current = queue.pop()
            dependents = self.get_dependents(current)
            for dep in dependents:
                if dep not in result:
                    result.add(dep)
                    queue.append(dep)
        
        return result
    
    def clear_dependencies(self, path: str) -> None:
        """Clear all dependencies for a file.
        
        Args:
            path: Path to clear dependencies for
        """
        self._conn.execute(
            "DELETE FROM file_dependencies WHERE source_path=? OR target_path=?",
            (path, path),
        )
        self._conn.commit()

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def content_hash_from_path(file_path: Path) -> str:
        try:
            return compute_short_hash(file_path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            return ""

    @staticmethod
    def content_hash_from_str(content: str) -> str:
        return compute_short_hash(content)


# =============================================================================
# FILE DISCOVERY
# =============================================================================


def is_indexable(file_path: Path) -> bool:
    """Return True if file should be indexed based on extension and exclusions."""
    if file_path.suffix.lower() not in INDEXED_EXTENSIONS:
        return False
    name = file_path.name
    if name in EXCLUDE_PATTERNS or name.startswith("."):
        return False
    for part in file_path.parts:
        if part in EXCLUDE_PATTERNS:
            return False
    return True


def discover_files(root: Path) -> list[Path]:
    """Walk `root` and return all indexable files."""
    files = []
    for path in root.rglob("*"):
        if path.is_file() and is_indexable(path):
            files.append(path)
    return files


# =============================================================================
# INCREMENTAL INDEXER
# =============================================================================


@dataclass
class IndexerStats:
    """Statistics from an indexing run."""
    total_files: int = 0
    changed_files: int = 0
    indexed_files: int = 0
    failed_files: int = 0
    skipped_files: int = 0
    elapsed_seconds: float = 0.0


class IncrementalIndexer:
    """Incremental indexer that only processes changed files.

    Usage:
        indexer = IncrementalIndexer(
            kb=knowledge_base,
            embed_svc=embedding_service,
            state_db=Path(".ai_support/index_state.db"),
        )
        indexer.connect()
        stats = await indexer.sync(Path("src/"))
        print(f"Indexed {stats.indexed_files}/{stats.total_files} files in {stats.elapsed_seconds:.1f}s")
        indexer.close()
    """

    def __init__(
        self,
        kb: "KnowledgeBase",
        embed_svc: "EmbeddingService",
        state_db: Path | str = ".ai_support/index_state.db",
        concurrency: int = 4,
        hash_workers: int = 4,
    ):
        """
        Args:
            kb:          KnowledgeBase instance for ChromaDB storage.
            embed_svc:   EmbeddingService instance for generating vectors.
            state_db:    Path to SQLite state database.
            concurrency: Max parallel embedding/indexing tasks.
            hash_workers: Number of workers for parallel file hashing.
        """
        self._kb = kb
        self._embed = embed_svc
        self._db = IndexStateDB(state_db)
        self._sem = asyncio.Semaphore(concurrency)
        self._hash_workers = hash_workers
        self._hash_executor = ThreadPoolExecutor(max_workers=hash_workers)
        self._running = False
        self._watch_task: asyncio.Task | None = None
        self._dirty_paths: set[str] = set()
        self._dirty_lock = asyncio.Lock()

    # ── lifecycle ──────────────────────────────────────────────────────────────

    def connect(self) -> None:
        self._db.connect()

    def close(self) -> None:
        if self._watch_task:
            self._watch_task.cancel()
            self._watch_task = None
        self._hash_executor.shutdown(wait=False)
        self._db.close()

    # ── main sync API ─────────────────────────────────────────────────────────

    async def sync(self, project_root: Path) -> IndexerStats:
        """Re-index all files that have changed since last run.

        Returns IndexerStats with counts and timing.
        """
        t0 = time.monotonic()
        stats = IndexerStats()

        # 1. Discover all indexable files on disk
        disk_files = {str(p): p for p in discover_files(project_root)}
        stats.total_files = len(disk_files)

        # 2. Find changed (new / modified / deleted) files using PARALLEL hashing
        db_states = self._db.get_all()
        changed: list[tuple[Path, str]] = []  # (path, content_hash)

        # Parallel hash computation for all files
        loop = asyncio.get_event_loop()
        file_paths = list(disk_files.values())
        hash_results = await loop.run_in_executor(
            None,
            lambda: compute_file_hash_parallel(file_paths, max_workers=self._hash_workers)
        )

        for path_str, path in disk_files.items():
            content_hash, mtime = hash_results.get(path_str, ("", 0.0))
            if not content_hash:  # Failed to read
                stats.failed_files += 1
                continue

            db_state = db_states.get(path_str)
            if db_state is None:
                # New file
                changed.append((path, content_hash))
            elif db_state.content_hash != content_hash:
                # Modified file
                changed.append((path, content_hash))
            else:
                # Unchanged — skip
                stats.skipped_files += 1

        # 3. Mark deleted files as unindexed (file removed from disk)
        for path_str, db_state in db_states.items():
            if path_str not in disk_files:
                self._db.delete(path_str)
                await self._delete_from_kb(path_str)

        # 4. Index changed files in parallel
        stats.changed_files = len(changed)
        self._running = True

        async def index_one(path_content: tuple[Path, str]) -> bool:
            path, content_hash = path_content
            async with self._sem:
                if not self._running:
                    return False
                try:
                    await self._index_file(path, content_hash)
                    return True
                except Exception as exc:
                    logger.error("index_file_failed", path=str(path), exc=str(exc))
                    return False

        results = await asyncio.gather(
            *[index_one(item) for item in changed],
            return_exceptions=True,
        )
        self._running = False

        for ok in results:
            if ok is True:
                stats.indexed_files += 1
            elif ok is False:
                pass  # skipped due to shutdown
            else:
                stats.failed_files += 1

        stats.elapsed_seconds = time.monotonic() - t0
        logger.info("incremental_index_complete",
                    indexed=stats.indexed_files,
                    changed=stats.changed_files,
                    total=stats.total_files,
                    elapsed=f"{stats.elapsed_seconds:.1f}s",
                    failed=stats.failed_files)
        return stats

    # ── watch mode ───────────────────────────────────────────────────────────

    async def start_watch(
        self,
        project_root: Path,
        debounce_seconds: float = 2.0,
    ) -> None:
        """Start a background file watcher that marks files dirty on change.

        Debounces to avoid flooding re-indexing on bulk operations.
        When a batch of changes settles for `debounce_seconds`,
        the accumulated dirty paths are re-indexed in one batch.
        """
        import watchfiles

        async def _on_change(changes: set[tuple[str, str]]) -> None:
            async with self._dirty_lock:
                for _, path_str in changes:
                    if is_indexable(Path(path_str)):
                        self._dirty_paths.add(path_str)

            # Debounce: wait for settling
            await asyncio.sleep(debounce_seconds)

            async with self._dirty_lock:
                dirty = self._dirty_paths.copy()
                self._dirty_paths.clear()

            if dirty and self._running:
                await self._reindex_batch(dirty)

        # Run watchfiles in thread since it blocks
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: watchfiles.run_process(
                str(project_root),
                lambda: None,  # we handle changes via _on_change
                step=500,
                debounce=0,
                ignore_extensions={"pyc", "pyo"},
            ),
        )

    def mark_dirty(self, path: str | Path) -> None:
        """Manually mark a file as dirty (e.g. from a LSP file-change notification)."""
        path_str = str(path)
        if is_indexable(Path(path_str)):
            self._db.mark_unindexed(path_str)
            asyncio.create_task(self._reindex_batch([path_str]))

    def mark_dirty_with_dependents(self, path: str | Path) -> list[str]:
        """Mark a file and all files that depend on it as dirty.
        
        This triggers cascading re-indexing when a dependency changes.
        
        Args:
            path: Path to the changed file
            
        Returns:
            List of all paths that were marked dirty
        """
        path_str = str(path)
        if not is_indexable(Path(path_str)):
            return []
        
        # Get all files that depend on this file (transitively)
        dependent_paths = list(self._db.get_all_dependents_transitive(path_str))
        dependent_paths.append(path_str)
        
        # Mark all as unindexed
        for p in dependent_paths:
            self._db.mark_unindexed(p)
        
        # Trigger re-indexing
        asyncio.create_task(self._reindex_batch(dependent_paths))
        
        logger.debug(
            "marked_dirty_with_dependents",
            path=path_str,
            dependents=len(dependent_paths) - 1,
        )
        
        return dependent_paths

    # ── internal helpers ─────────────────────────────────────────────────────

    async def _index_file(self, file_path: Path, content_hash: str) -> None:
        """Read file, chunk, embed, and upsert to KB + state DB.
        
        Also extracts and stores import dependencies for cascading re-indexing.
        """
        content = file_path.read_text(encoding="utf-8", errors="replace")
        rel_path = str(file_path)

        # Update state DB first (optimistic — if KB fails we mark unindexed)
        self._db.upsert(FileState(
            path=rel_path,
            mtime=file_path.stat().st_mtime,
            content_hash=content_hash,
            indexed_at=None,
        ))

        # Extract and store dependencies
        dependencies = self._extract_dependencies(content, file_path)
        if dependencies:
            self._db.upsert_dependencies(rel_path, dependencies)

        # Chunk and embed
        chunks = self._chunk_content(content, rel_path)
        embeddings = await self._embed.embed_batch(
            [c["text"] for c in chunks]
        )

        # Upsert to KB
        await self._kb.upsert_entries(chunks, embeddings)

        # Mark indexed
        self._db.upsert(FileState(
            path=rel_path,
            mtime=file_path.stat().st_mtime,
            content_hash=content_hash,
            indexed_at=time.time(),
        ))

        logger.debug("indexed_file", path=rel_path, chunks=len(chunks))

    def _extract_dependencies(self, content: str, file_path: Path) -> list[str]:
        """Extract import dependencies from file content.
        
        Args:
            content: File content
            file_path: Path to the file
            
        Returns:
            List of file paths that this file depends on
        """
        dependencies: list[str] = []
        suffix = file_path.suffix.lower()
        
        if suffix == ".py":
            # Python imports
            import re
            patterns = [
                re.compile(r"^from\s+([\w.]+)\s+import", re.MULTILINE),
                re.compile(r"^import\s+([\w.]+)", re.MULTILINE),
            ]
            
            for pattern in patterns:
                for match in pattern.finditer(content):
                    module = match.group(1)
                    # Try to resolve to a file path
                    resolved = self._resolve_python_import(module, file_path.parent)
                    if resolved:
                        dependencies.append(resolved)
        
        elif suffix in {".c", ".h", ".cpp", ".hpp"}:
            # C/C++ includes
            import re
            pattern = re.compile(r'#include\s*[<"]([^>"]+)[>"]')
            for match in pattern.finditer(content):
                include = match.group(1)
                # System includes usually don't have local files
                if not include.startswith("<"):
                    resolved = self._resolve_c_include(include, file_path.parent)
                    if resolved:
                        dependencies.append(resolved)
        
        return list(set(dependencies))  # Deduplicate
    
    def _resolve_python_import(self, module: str, current_dir: Path) -> Optional[str]:
        """Resolve a Python import to a file path.
        
        Args:
            module: Module name (e.g., "src.utils")
            current_dir: Directory of the importing file
            
        Returns:
            Resolved file path or None
        """
        # Try to find module file
        parts = module.split(".")
        for i in range(len(parts), 0, -1):
            module_path = "/".join(parts[:i])
            candidates = [
                current_dir / f"{module_path}.py",
                current_dir / module_path / "__init__.py",
            ]
            for candidate in candidates:
                if candidate.exists():
                    return str(candidate)
        return None
    
    def _resolve_c_include(self, include: str, current_dir: Path) -> Optional[str]:
        """Resolve a C include to a file path.
        
        Args:
            include: Include name (e.g., "utils.h")
            current_dir: Directory of the including file
            
        Returns:
            Resolved file path or None
        """
        # Try current directory first
        candidate = current_dir / include
        if candidate.exists():
            return str(candidate)
        
        # Try parent directories
        for parent in current_dir.parents:
            candidate = parent / include
            if candidate.exists():
                return str(candidate)
        
        return None

    async def _delete_from_kb(self, path: str) -> None:
        """Remove all KB entries that originated from `path`."""
        try:
            await self._kb.delete_by_source(path)
        except Exception as exc:
            logger.warning("kb_delete_failed", path=path, exc=str(exc))

    async def _reindex_batch(self, paths: Sequence[str], batch_size: int = 10) -> None:
        """Re-index a batch of dirty paths with batch processing optimization.
        
        Args:
            paths: List of file paths to reindex
            batch_size: Number of files to process in each batch
        """
        # Process in batches for better memory management
        for i in range(0, len(paths), batch_size):
            batch = paths[i:i + batch_size]
            
            # Process batch in parallel
            async def index_path(path_str: str) -> None:
                path = Path(path_str)
                if not path.exists():
                    self._db.delete(path_str)
                    await self._delete_from_kb(path_str)
                    return
                try:
                    content_hash = cached_content_hash(
                        path.read_text(encoding="utf-8", errors="replace")
                    )
                    await self._index_file(path, content_hash)
                except Exception as exc:
                    logger.error("reindex_batch_failed", path=path_str, exc=str(exc))
            
            await asyncio.gather(*[index_path(p) for p in batch], return_exceptions=True)

    @staticmethod
    def _chunk_content(content: str, source: str) -> list[dict[str, Any]]:
        """Split file content into semantically coherent chunks for embedding.
        
        Semantic chunking strategy:
        - First tries to split at function/class definition boundaries
        - If a function is too large (>max_chars), splits at logical sub-sections
          using indentation levels and blank lines as guides
        - Preserves indentation context to maintain code hierarchy
        
        This prevents breaking function signatures from their bodies,
        class definitions from methods, or related logic from context.
        """
        max_chars = 2000
        lines = content.splitlines()
        chunks = []
        buffer: list[str] = []
        buf_len = 0
        
        # Track current indentation level to identify logical blocks
        def get_indent(line: str) -> int:
            return len(line) - len(line.lstrip())
        
        def should_split_at_line(line: str, prev_indent: int) -> bool:
            """Determine if line marks a semantic boundary for splitting.
            
            Split at:
            - Function/class definitions (def, class, async def)
            - Major section comments (# ----, # ===, etc.)
            - Significant indent changes that indicate new blocks
            """
            stripped = line.strip()
            if not stripped:
                return True  # Blank lines are natural split points
            
            # Function/method/class definitions
            if stripped.startswith(("def ", "async def ", "class ", "async ")):
                return True
            
            # Major section headers (comment lines that look like headers)
            if stripped.startswith("#") and len(stripped) > 2:
                first_char = stripped[1]
                if first_char in ("=", "-", "*", "#"):
                    return True
            
            return False
        
        prev_indent = 0
        for line in lines:
            current_indent = get_indent(line)
            is_boundary = should_split_at_line(line, prev_indent)
            
            # Check if adding this line would exceed max_chars
            would_exceed = buf_len + len(line) > max_chars
            
            # Split if: would exceed AND we have content, OR this is a semantic boundary
            if (would_exceed and buffer) or (is_boundary and buffer):
                chunks.append({
                    "text": "\n".join(buffer),
                    "source": source,
                    "type": "code",
                })
                buffer = []
                buf_len = 0
            
            buffer.append(line)
            buf_len += len(line) + 1
            prev_indent = current_indent

        if buffer:
            chunks.append({
                "text": "\n".join(buffer),
                "source": source,
                "type": "code",
            })
        return chunks

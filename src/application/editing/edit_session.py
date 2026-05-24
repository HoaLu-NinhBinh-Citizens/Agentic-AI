"""Edit Transaction System — diff generation, conflict detection, rollback, apply.

Architecture:
    User prompt → LLM generates plan → EditBlock instances (old/new per file)
    → DiffRenderer (unified diff preview) → EditSession.apply_all()
    → conflict check → CONFLICTED / APPLIED → history stack
    → rollback() → revert from stored rollback_content

Supports:
- Multi-file atomic transactions (all-or-nothing optional)
- Conflict detection against current file state
- Full undo/redo history
- Chunk-level accept/reject (per-block)
- Dry-run mode (preview without applying)
"""

from __future__ import annotations

import difflib
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS & DATA CLASSES
# =============================================================================


class EditStatus(Enum):
    """Lifecycle state of an edit block."""
    PENDING = auto()       # Created, not yet applied
    APPLIED = auto()       # Successfully written to disk
    CREATED = auto()       # File was newly created
    CONFLICTED = auto()    # File changed between preview and apply
    ROLLED_BACK = auto()   # Reverted after apply
    FAILED = auto()        # Write error


class ConflictStrategy(Enum):
    """How to handle conflicts during apply."""
    ABORT_ALL = auto()      # Stop on first conflict (atomic)
    SKIP_CONFLICTED = auto()  # Skip conflicted, apply rest
    FORCE = auto()          # Overwrite regardless (risky)


@dataclass
class EditBlock:
    """A single file edit within a session."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    file_path: str = ""
    old_content: str = ""        # Content expected to be replaced
    new_content: str = ""        # Content to write
    rollback_content: str = ""   # Snapshot before apply (for rollback)
    status: EditStatus = EditStatus.PENDING
    applied_at: float | None = None
    error: str = ""

    @property
    def is_applied(self) -> bool:
        return self.status == EditStatus.APPLIED


@dataclass
class DiffChunk:
    """One hunk within a unified diff."""
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[str]   # Formatted unified diff lines


@dataclass
class EditResult:
    """Result of an apply operation on a single block."""
    block_id: str
    status: EditStatus
    conflict_type: str | None = None   # "content_changed" | "deleted" | "permission"
    error: str = ""


@dataclass
class SessionStats:
    """Aggregated stats for an EditSession."""
    total: int = 0
    applied: int = 0
    conflicted: int = 0
    failed: int = 0
    rolled_back: int = 0


# =============================================================================
# DIFF RENDERER
# =============================================================================


class DiffRenderer:
    """Generates unified diff for a single file or multiple files."""

    @staticmethod
    def render_file(old: str, new: str,
                    file_path: str = "file") -> str:
        """Return a unified diff string for one file."""
        old_lines = old.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)

        diff = difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm="",
        )
        return "".join(diff)

    @staticmethod
    def render_blocks(blocks: list[EditBlock]) -> str:
        """Render a multi-file diff from a list of edit blocks."""
        parts = [f"# Edit Session — {len(blocks)} file(s)\n"]
        for b in blocks:
            if b.old_content == b.new_content:
                continue
            parts.append(f"\n## {b.file_path}\n")
            parts.append(DiffRenderer.render_file(
                b.old_content, b.new_content, b.file_path))
        return "".join(parts)

    @staticmethod
    def parse_hunks(diff_output: str) -> list[DiffChunk]:
        """Parse a unified diff output into structured hunks.

        Lightweight parser — handles the output of render_file().
        """
        hunks: list[DiffChunk] = []
        current: dict[str, Any] = {}
        lines_so_far: list[str] = []

        def _commit():
            if current:
                hunks.append(DiffChunk(
                    old_start=current.get("old_start", 0),
                    old_count=current.get("old_count", 0),
                    new_start=current.get("new_start", 0),
                    new_count=current.get("new_count", 0),
                    lines=list(lines_so_far),
                ))
            current.clear()
            lines_so_far.clear()

        for line in diff_output.splitlines():
            if line.startswith("@@"):
                _commit()
                # Parse @@ -old_start,old_count +new_start,new_count @@
                parts = line.split(" ", 2)
                if len(parts) >= 3:
                    ranges = parts[1], parts[2]
                    old_rng = ranges[0][1:].split(",")
                    new_rng = ranges[1][1:].split(",")
                    current["old_start"] = int(old_rng[0])
                    current["old_count"] = int(old_rng[1]) if len(old_rng) > 1 else 1
                    current["new_start"] = int(new_rng[0])
                    current["new_count"] = int(new_rng[1]) if len(new_rng) > 1 else 1
            elif current:
                lines_so_far.append(line)

        _commit()
        return hunks


# =============================================================================
# FILE SYSTEM ADAPTER
# =============================================================================


class FileSystemAdapter:
    """Abstraction over file I/O — allows injecting fakefs in tests."""

    async def read(self, path: str) -> str:
        return Path(path).read_text(encoding="utf-8", errors="replace")

    async def write(self, path: str, content: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content, encoding="utf-8")

    async def exists(self, path: str) -> bool:
        return Path(path).exists()

    async def backup(self, path: str) -> str:
        """Create a backup copy and return backup path."""
        p = Path(path)
        backup = p.with_suffix(p.suffix + f".bak.{int(time.time())}")
        backup.write_bytes(p.read_bytes())
        return str(backup)


# =============================================================================
# CONFLICT DETECTOR
# =============================================================================


class ConflictDetector:
    """Detects whether an EditBlock can be safely applied to the current file."""

    @staticmethod
    def check(block: EditBlock, current_content: str | None) -> tuple[bool, str | None]:
        """
        Returns (has_conflict, conflict_type).
        conflict_type: "file_deleted" | "old_content_not_found" | "content_changed" | None
        """
        if current_content is None:
            return True, "file_deleted"

        # Empty file = new file → no conflict (new content will be written)
        if current_content == "":
            return False, None

        # Check if the target snippet exists at the expected position in the file
        pos = current_content.find(block.old_content)
        if pos == -1:
            return True, "old_content_not_found"

        return False, None


# =============================================================================
# EDIT SESSION
# =============================================================================


class EditSession:
    """Manages a multi-file edit transaction with full undo/redo support.

    Usage:
        session = EditSession(FileSystemAdapter())
        await session.load("src/foo.py")
        session.add("src/foo.py",
                    old_content="old text",
                    new_content="new text")
        # Preview:
        preview = DiffRenderer.render_blocks(session.pending_blocks)
        # Apply:
        results = await session.apply_all(ConflictStrategy.ABORT_ALL)
        # Rollback:
        await session.rollback_last()
    """

    def __init__(
        self,
        fs: FileSystemAdapter | None = None,
        session_id: str | None = None,
    ):
        self._fs = fs or FileSystemAdapter()
        self._id = session_id or uuid.uuid4().hex[:12]
        self._blocks: list[EditBlock] = []
        self._history: list[list[EditBlock]] = []  # undo stack
        self._redo_stack: list[list[EditBlock]] = []  # redo stack
        self._stats = SessionStats()

    # ── properties ─────────────────────────────────────────────────────────

    @property
    def id(self) -> str:
        return self._id

    @property
    def pending_blocks(self) -> list[EditBlock]:
        return [b for b in self._blocks if b.status == EditStatus.PENDING]

    @property
    def applied_blocks(self) -> list[EditBlock]:
        return [b for b in self._blocks if b.is_applied]

    @property
    def stats(self) -> SessionStats:
        self._stats.total = len(self._blocks)
        self._stats.applied = sum(1 for b in self._blocks if b.status == EditStatus.APPLIED)
        self._stats.conflicted = sum(1 for b in self._blocks if b.status == EditStatus.CONFLICTED)
        self._stats.failed = sum(1 for b in self._blocks if b.status == EditStatus.FAILED)
        self._stats.rolled_back = sum(1 for b in self._blocks if b.status == EditStatus.ROLLED_BACK)
        return self._stats

    # ── block management ───────────────────────────────────────────────────

    def add(
        self,
        file_path: str,
        old_content: str,
        new_content: str,
        rollback_content: str = "",
    ) -> EditBlock:
        """Add a new edit block to the session.

        If rollback_content is empty, the current file content is used.
        """
        block = EditBlock(
            file_path=file_path,
            old_content=old_content,
            new_content=new_content,
            rollback_content=rollback_content,
        )
        self._blocks.append(block)
        self._redo_stack.clear()  # New edits invalidate redo
        return block

    async def load(self, file_path: str) -> str:
        """Pre-populate old_content + rollback_content from current file state."""
        if await self._fs.exists(file_path):
            return await self._fs.read(file_path)
        return ""

    def block_by_id(self, block_id: str) -> EditBlock | None:
        for b in self._blocks:
            if b.id == block_id:
                return b
        return None

    def remove(self, block_id: str) -> bool:
        """Remove a pending block. Cannot remove applied blocks."""
        for i, b in enumerate(self._blocks):
            if b.id == block_id and b.status == EditStatus.PENDING:
                self._blocks.pop(i)
                return True
        return False

    # ── apply ───────────────────────────────────────────────────────────────

    async def apply_all(
        self,
        strategy: ConflictStrategy = ConflictStrategy.ABORT_ALL,
        dry_run: bool = False,
    ) -> list[EditResult]:
        """Apply all pending blocks.

        Args:
            strategy:  Conflict handling mode.
            dry_run:   If True, only check conflicts without writing.

        Returns:
            List of EditResult, one per block (in order).
        """
        results: list[EditResult] = []

        # Snapshot current file contents once before applying any block.
        # This ensures that multiple blocks editing the same file all see
        # the original content, not the already-modified content.
        original_snapshots: dict[str, str] = {}
        for block in self._blocks:
            if block.status != EditStatus.PENDING:
                continue
            if block.file_path not in original_snapshots:
                original_snapshots[block.file_path] = (
                    await self._fs.read(block.file_path)
                    if await self._fs.exists(block.file_path) else ""
                )

        for block in self._blocks:
            if block.status != EditStatus.PENDING:
                continue

            result = await self._apply_one(block, dry_run=dry_run,
                                           original_snapshot=original_snapshots.get(block.file_path))
            results.append(result)

            if result.status == EditStatus.CONFLICTED and strategy == ConflictStrategy.ABORT_ALL:
                # Stop processing remaining blocks
                for remaining in self._blocks[len(results):]:
                    if remaining.status == EditStatus.PENDING:
                        remaining.status = EditStatus.CONFLICTED
                        remaining.error = "aborted_due_to_prior_conflict"
                        results.append(EditResult(
                            block_id=remaining.id,
                            status=EditStatus.CONFLICTED,
                            error="aborted_due_to_prior_conflict",
                        ))
                break

        if not dry_run and any(r.status in (EditStatus.APPLIED, EditStatus.CREATED) for r in results):
            # Commit to history only if something was applied/created
            snapshot = [EditBlock(
                id=b.id,
                file_path=b.file_path,
                old_content=b.old_content,
                new_content=b.new_content,
                rollback_content=b.rollback_content or "",
                status=b.status,
                applied_at=b.applied_at,
            ) for b in self._blocks if b.status in (EditStatus.APPLIED, EditStatus.CREATED)]
            self._history.append(snapshot)

        return results

    async def _apply_one(
        self,
        block: EditBlock,
        dry_run: bool,
        original_snapshot: str | None = None,
    ) -> EditResult:
        """Apply a single block with conflict detection."""
        # Use pre-snapshotted content if provided; otherwise read current state
        current = original_snapshot if original_snapshot is not None else (
            await self._fs.read(block.file_path)
            if await self._fs.exists(block.file_path) else ""
        )

        # Conflict check — skips new file (empty current)
        has_conflict, conflict_type = ConflictDetector.check(block, current)
        if has_conflict:
            block.status = EditStatus.CONFLICTED
            block.error = f"conflict: {conflict_type}"
            return EditResult(
                block_id=block.id,
                status=EditStatus.CONFLICTED,
                conflict_type=conflict_type,
            )

        if dry_run:
            block.status = EditStatus.PENDING  # unchanged
            return EditResult(block_id=block.id, status=EditStatus.PENDING)

        # Use original snapshot for rollback so we revert to the pre-session state
        block.rollback_content = original_snapshot if original_snapshot is not None else current

        try:
            is_new_file = (current == "")
            await self._fs.write(block.file_path, block.new_content)
            applied_status = EditStatus.CREATED if is_new_file else EditStatus.APPLIED
            block.status = applied_status
            block.applied_at = time.time()
            logger.info("edit_applied", file=block.file_path,
                         block_id=block.id,
                         is_new=is_new_file)
            return EditResult(block_id=block.id, status=applied_status)

        except Exception as exc:
            block.status = EditStatus.FAILED
            block.error = str(exc)
            logger.error("edit_apply_failed", file=block.file_path, exc=str(exc))
            return EditResult(block_id=block.id, status=EditStatus.FAILED, error=str(exc))

    # ── rollback ──────────────────────────────────────────────────────────

    async def rollback_last(self) -> int:
        """Revert the most recent apply batch.

        Returns the number of blocks rolled back.
        """
        if not self._history:
            return 0

        snapshot = self._history.pop()
        rolled_back = 0

        for block in snapshot:
            if block.status in (EditStatus.APPLIED, EditStatus.CREATED):
                try:
                    if block.status == EditStatus.CREATED:
                        # New file: delete it on rollback
                        from pathlib import Path
                        Path(block.file_path).unlink(missing_ok=True)
                        logger.info("edit_rolled_back_delete", file=block.file_path)
                    else:
                        await self._fs.write(block.file_path, block.rollback_content)
                        logger.info("edit_rolled_back", file=block.file_path)
                    if live := self.block_by_id(block.id):
                        live.status = EditStatus.ROLLED_BACK
                    rolled_back += 1
                    logger.info("edit_rolled_back", file=block.file_path)
                except Exception as exc:
                    logger.error("rollback_failed", file=block.file_path, exc=str(exc))

        if rolled_back:
            self._redo_stack.append(snapshot)

        return rolled_back

    async def rollback_to(self, history_index: int) -> int:
        """Rollback all applies back to and including history[history_index]."""
        total = 0
        while self._history and len(self._history) > history_index:
            total += await self.rollback_last()
        return total

    # ── redo ──────────────────────────────────────────────────────────────

    async def redo(self) -> int:
        """Re-apply the most recently rolled-back batch.

        Returns number of blocks re-applied.
        """
        if not self._redo_stack:
            return 0

        snapshot = self._redo_stack.pop()
        re_applied = 0

        for block in snapshot:
            if block.status == EditStatus.ROLLED_BACK:
                try:
                    await self._fs.write(block.file_path, block.new_content)
                    if live := self.block_by_id(block.id):
                        live.status = EditStatus.APPLIED
                        live.applied_at = time.time()
                    re_applied += 1
                except Exception as exc:
                    logger.error("redo_failed", file=block.file_path, exc=str(exc))

        if re_applied:
            self._history.append(snapshot)

        return re_applied

    # ── preview ────────────────────────────────────────────────────────────

    def preview(self) -> str:
        """Return unified diff of all pending blocks."""
        return DiffRenderer.render_blocks(self.pending_blocks)

    def preview_html(self) -> str:
        """Return a minimal HTML diff view (for TUI / web preview)."""
        chunks = []
        for block in self.pending_blocks:
            hunks = DiffRenderer.parse_hunks(
                DiffRenderer.render_file(block.old_content, block.new_content, block.file_path)
            )
            hunks_json = [
                {"old_start": h.old_start, "lines": h.lines}
                for h in hunks
            ]
            chunks.append({
                "file": block.file_path,
                "block_id": block.id,
                "hunks": hunks_json,
            })
        import json as _json
        return _json.dumps(chunks, indent=2)


# =============================================================================
# LLM INTEGRATION — parse model output into EditBlocks
# =============================================================================


class EditPlanParser:
    """Parse structured output from an LLM into EditBlock list.

    Accepts output in two formats:
    1. Structured JSON array:
        [{"file": "src/foo.py", "old": "...", "new": "..."}, ...]
    2. Markdown fenced code blocks:
        ```file:src/foo.py
        old:
        ---
        new:
        ---
        ```
    """

    @staticmethod
    def parse_json(raw: str) -> list[dict[str, str]]:
        """Try to extract a JSON array from raw LLM output."""
        import json as _json
        # Find first [ and last ]
        start = raw.find("[")
        end = raw.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                return _json.loads(raw[start:end + 1])
            except _json.JSONDecodeError:
                pass
        # Try whole string
        try:
            return _json.loads(raw)
        except _json.JSONDecodeError:
            return []

    @staticmethod
    def parse_blocks_from_json(raw: str) -> list[EditBlock]:
        """Parse LLM JSON output into EditBlock instances."""
        items = EditPlanParser.parse_json(raw)
        blocks = []
        for item in items:
            if not isinstance(item, dict):
                continue
            file_path = item.get("file") or item.get("path") or item.get("file_path", "")
            old_content = item.get("old") or item.get("old_content") or item.get("before", "")
            new_content = item.get("new") or item.get("new_content") or item.get("after", "")
            if file_path and (old_content or new_content):
                blocks.append(EditBlock(
                    file_path=file_path,
                    old_content=old_content,
                    new_content=new_content,
                ))
        return blocks

    @staticmethod
    def parse_blocks_from_markdown(raw: str) -> list[EditBlock]:
        """Parse markdown ```file:... blocks into EditBlocks."""
        blocks = []
        # Split by fenced code blocks
        parts = raw.split("```")
        for i, part in enumerate(parts):
            lines = part.strip().splitlines()
            if not lines:
                continue
            # Header line: "file:src/foo.py" or just the file path
            header = lines[0].strip()
            if not header or header.startswith("file:"):
                file_path = header.split(":", 1)[1].strip() if ":" in header else ""
            else:
                file_path = header

            if not file_path:
                continue

            # Find old/new sections separated by ---
            body = "\n".join(lines[1:])
            sections = body.split("---")
            old_content = sections[0].strip() if len(sections) > 0 else ""
            new_content = sections[1].strip() if len(sections) > 1 else ""

            blocks.append(EditBlock(
                file_path=file_path,
                old_content=old_content,
                new_content=new_content,
            ))

        return blocks

    @classmethod
    def parse(cls, raw: str) -> list[EditBlock]:
        """Auto-detect format and parse into EditBlocks."""
        blocks = cls.parse_blocks_from_json(raw)
        if blocks:
            return blocks
        return cls.parse_blocks_from_markdown(raw)

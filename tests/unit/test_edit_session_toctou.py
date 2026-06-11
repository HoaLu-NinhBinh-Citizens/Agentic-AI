"""Tests for external-modification detection in EditSession.apply_all().

Covers the fix adding a re-check of on-disk content just before each write:
a file changed by another process between snapshot and write must surface a
CONFLICTED result instead of being silently overwritten.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.editing.edit_session import (
    ConflictStrategy,
    EditSession,
    EditStatus,
    FileSystemAdapter,
)


class RacingFS(FileSystemAdapter):
    """FS adapter that mutates a file after N reads, simulating an external
    writer racing the edit session between snapshot and write."""

    def __init__(self, race_path: str, external_content: str, after_reads: int):
        self.race_path = race_path
        self.external_content = external_content
        self.reads_remaining = after_reads
        self._raced = False

    async def read(self, path: str) -> str:
        if path == self.race_path and not self._raced:
            if self.reads_remaining <= 0:
                Path(path).write_text(self.external_content, encoding="utf-8")
                self._raced = True
            else:
                self.reads_remaining -= 1
        return await super().read(path)


class TestExternalModificationDetection:
    @pytest.mark.asyncio
    async def test_external_change_between_snapshot_and_write_conflicts(
        self, tmp_path: Path
    ):
        target = tmp_path / "f.py"
        target.write_text("original", encoding="utf-8")

        # First read = snapshot; the pre-write re-read then sees raced content
        fs = RacingFS(str(target), "externally changed", after_reads=1)
        session = EditSession(fs)
        session.add(str(target), old_content="original", new_content="edited")

        results = await session.apply_all(ConflictStrategy.ABORT_ALL)

        assert results[0].status == EditStatus.CONFLICTED
        assert results[0].conflict_type == "file_changed_externally"
        # The external edit was preserved, not overwritten
        assert target.read_text(encoding="utf-8") == "externally changed"

    @pytest.mark.asyncio
    async def test_unchanged_file_applies_normally(self, tmp_path: Path):
        target = tmp_path / "f.py"
        target.write_text("original", encoding="utf-8")

        session = EditSession(FileSystemAdapter())
        session.add(str(target), old_content="original", new_content="edited")

        results = await session.apply_all(ConflictStrategy.ABORT_ALL)

        assert results[0].status == EditStatus.APPLIED
        assert target.read_text(encoding="utf-8") == "edited"

    @pytest.mark.asyncio
    async def test_two_blocks_same_file_do_not_false_conflict(self, tmp_path: Path):
        # Block 1 writes the file; block 2's pre-write re-check must compare
        # against block 1's output, not the original snapshot.
        target = tmp_path / "f.py"
        target.write_text("v0", encoding="utf-8")

        session = EditSession(FileSystemAdapter())
        session.add(str(target), old_content="v0", new_content="v1")
        session.add(str(target), old_content="v0", new_content="v2")

        results = await session.apply_all(ConflictStrategy.ABORT_ALL)

        assert [r.status for r in results] == [EditStatus.APPLIED, EditStatus.APPLIED]
        assert target.read_text(encoding="utf-8") == "v2"

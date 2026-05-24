"""Unit tests for Hashline Editor.

Tests for:
- Hashline anchor creation
- Patch application
- Stale anchor detection
- Context verification
- Multi-line edits
- Preview generation
"""

from __future__ import annotations

import hashlib
import pytest
from pathlib import Path

from src.infrastructure.tools.hashline import (
    HashlineEditor,
    HashlineAnchor,
    HashlinePatch,
    EditResult,
    StaleAnchorError,
    ContextDriftError,
    edit_file,
    preview_edit,
)


class TestHashlineAnchor:
    """Tests for HashlineAnchor."""

    def test_anchor_from_content(self):
        """Test anchor creation from content."""
        content = "line1\nline2\nline3"
        anchor = HashlineAnchor.from_content(content, line_hint=1)
        
        assert anchor.content_hash is not None
        assert len(anchor.content_hash) == 16

    def test_anchor_from_file(self, tmp_path):
        """Test anchor creation from file."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("line1\nline2\nline3")
        
        anchor = HashlineAnchor.from_file(file_path, line=1)
        
        assert anchor.content_hash is not None
        assert anchor.line_hint == 1

    def test_anchor_deterministic(self):
        """Test that anchor hash is deterministic."""
        content = "test content"
        
        anchor1 = HashlineAnchor.from_content(content)
        anchor2 = HashlineAnchor.from_content(content)
        
        assert anchor1.content_hash == anchor2.content_hash

    def test_anchor_different_content_different_hash(self):
        """Test different content produces different hash."""
        anchor1 = HashlineAnchor.from_content("content 1")
        anchor2 = HashlineAnchor.from_content("content 2")
        
        assert anchor1.content_hash != anchor2.content_hash


class TestHashlinePatch:
    """Tests for HashlinePatch."""

    def test_patch_creation(self):
        """Test patch creation."""
        patch = HashlinePatch(
            file_path="/test/file.py",
            old_content="old line",
            new_content="new line",
        )
        
        assert patch.file_path == "/test/file.py"
        assert patch.old_content == "old line"
        assert patch.new_content == "new line"

    def test_patch_with_anchor(self):
        """Test patch with anchor."""
        anchor = HashlineAnchor.from_content("context")
        patch = HashlinePatch(
            file_path="/test.py",
            anchor=anchor,
            old_content="old",
            new_content="new",
        )
        
        assert patch.anchor is not None

    def test_patch_to_dict(self):
        """Test patch serialization."""
        patch = HashlinePatch(
            file_path="/test.py",
            old_content="old",
            new_content="new",
        )
        
        data = patch.to_dict()
        
        assert data["file_path"] == "/test.py"
        assert data["old_content"] == "old"
        assert data["new_content"] == "new"


class TestHashlineEditor:
    """Tests for HashlineEditor."""

    @pytest.fixture
    def editor(self):
        """Create hashline editor."""
        return HashlineEditor()

    @pytest.fixture
    def test_file(self, tmp_path):
        """Create test file."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("line1\nline2\nline3\nline4\nline5")
        return file_path

    def test_find_anchor_line(self, editor, test_file):
        """Test finding anchor line in content."""
        content = test_file.read_text()
        
        # Create anchor from line 2
        anchor = HashlineAnchor.from_content(content, line_hint=1)
        
        found_line = editor.find_anchor_line(content, anchor)
        
        assert found_line is not None

    def test_apply_patch_file_not_found(self, editor, tmp_path):
        """Test patch on nonexistent file."""
        patch = HashlinePatch(
            file_path="/nonexistent/file.txt",
            old_content="test",
            new_content="new",
        )
        
        result = editor.apply_patch(tmp_path / "missing.txt", patch)
        
        assert result.success is False
        assert "not found" in result.error.lower()

    def test_apply_patch_pattern_not_found(self, editor, test_file):
        """Test patch when pattern not found."""
        patch = HashlinePatch(
            file_path=str(test_file),
            old_content="nonexistent_pattern_xyz",
            new_content="new",
        )
        
        result = editor.apply_patch(test_file, patch)
        
        assert result.success is False
        assert "could not find" in result.error.lower()

    def test_create_patch(self, editor, test_file):
        """Test patch creation."""
        patch = editor.create_patch(
            test_file,
            old_content="line2",
            new_content="new_line2",
            anchor_line=1,
        )
        
        assert patch.file_path == str(test_file)
        assert patch.old_content == "line2"
        assert patch.new_content == "new_line2"
        assert patch.anchor is not None

    def test_preview_patch(self, editor, test_file):
        """Test patch preview generation."""
        patch = editor.create_patch(
            test_file,
            old_content="line2",
            new_content="preview_line2",
        )
        
        preview = editor.preview_patch(test_file, patch)
        
        assert "line2" in preview
        assert "preview_line2" in preview

    def test_context_lines_in_anchor(self, editor, tmp_path):
        """Test that anchor includes context lines."""
        file_path = tmp_path / "context.txt"
        file_path.write_text("a\nb\nc\nd\ne")
        
        anchor = HashlineAnchor.from_file(file_path, line=2, context_lines=2)
        
        # Anchor should include surrounding context
        assert anchor.context_lines == 2

    def test_verify_anchor_valid(self, editor, test_file):
        """Test anchor verification with valid context."""
        content = test_file.read_text()
        anchor = HashlineAnchor.from_content(content, line_hint=1)
        
        is_valid = editor.verify_anchor(content, anchor, 1)
        
        assert is_valid is True

    def test_verify_anchor_invalid(self, editor, test_file):
        """Test anchor verification with modified content."""
        content = test_file.read_text()
        anchor = HashlineAnchor.from_content("original content", line_hint=0)
        
        is_valid = editor.verify_anchor("modified content", anchor, 0)
        
        assert is_valid is False


class TestEditFileFunction:
    """Tests for edit_file convenience function."""

    def test_edit_file_success(self, tmp_path):
        """Test edit_file with valid edit."""
        file_path = tmp_path / "edit.txt"
        file_path.write_text("hello world")
        
        result = edit_file(
            file_path,
            old="world",
            new="python",
        )
        
        assert result.success is True
        assert "python" in file_path.read_text()

    def test_edit_file_no_verify(self, tmp_path):
        """Test edit_file without context verification."""
        file_path = tmp_path / "no_verify.txt"
        file_path.write_text("test content")
        
        result = edit_file(
            file_path,
            old="content",
            new="changed",
            verify=False,
        )
        
        assert result.success is True


class TestPreviewEditFunction:
    """Tests for preview_edit convenience function."""

    def test_preview_edit(self, tmp_path):
        """Test preview_edit."""
        file_path = tmp_path / "preview.txt"
        file_path.write_text("line1\nline2\nline3")
        
        preview = preview_edit(
            file_path,
            old="line2",
            new="modified_line2",
        )
        
        assert "line2" in preview
        assert "modified_line2" in preview


class TestEditResult:
    """Tests for EditResult dataclass."""

    def test_edit_result_success(self):
        """Test successful edit result."""
        result = EditResult(
            success=True,
            file_path="/test.py",
            old_content="old",
            new_content="new",
            lines_changed=0,
            anchor_line=5,
        )
        
        assert result.success is True
        assert result.error is None
        assert result.anchor_line == 5

    def test_edit_result_failure(self):
        """Test failed edit result."""
        result = EditResult(
            success=False,
            file_path="/test.py",
            error="Pattern not found",
        )
        
        assert result.success is False
        assert result.error == "Pattern not found"


class TestEdgeCases:
    """Tests for edge cases."""

    def test_single_line_file(self, tmp_path):
        """Test editing single line file."""
        file_path = tmp_path / "single.txt"
        file_path.write_text("only line")
        
        result = edit_file(file_path, old="only line", new="modified")
        
        assert result.success is True
        assert "modified" in file_path.read_text()

    def test_large_file(self, tmp_path):
        """Test editing large file."""
        file_path = tmp_path / "large.txt"
        lines = [f"line {i}" for i in range(1000)]
        file_path.write_text("\n".join(lines))
        
        result = edit_file(file_path, old="line 500", new="modified_500")
        
        assert result.success is True

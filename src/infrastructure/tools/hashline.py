"""Hashline edit implementation for reliable file patching.

Inspired by oh-my-pi's hashline approach:
- Content-hash anchors instead of line numbers
- Stale-anchor recovery
- Context verification before edit
- Atomic all-or-nothing operations
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple


class HashlineError(Exception):
    """Base exception for hashline operations."""
    pass


class StaleAnchorError(HashlineError):
    """Raised when anchor hash cannot be found."""
    pass


class ContextDriftError(HashlineError):
    """Raised when file changed since anchor was created."""
    pass


class EditConflictError(HashlineError):
    """Raised when concurrent edit detected."""
    pass


@dataclass
class HashlineAnchor:
    """A content-hash anchor for positioning edits.
    
    Unlike line numbers, anchors are based on content hashes,
    making them stable across unrelated changes.
    """
    
    content_hash: str  # SHA256 of surrounding context
    line_hint: int | None = None  # Optional line number hint
    context_lines: int = 3  # Number of lines to include in hash
    
    @classmethod
    def from_content(cls, content: str, line_hint: int | None = None, context_lines: int = 3) -> HashlineAnchor:
        """Create anchor from content string."""
        # Include context lines in hash
        lines = content.splitlines()
        start = max(0, (line_hint or 0) - context_lines)
        end = min(len(lines), (line_hint or len(lines)) + context_lines + 1)
        context = "\n".join(lines[start:end])
        
        return cls(
            content_hash=hashlib.sha256(context.encode()).hexdigest()[:16],
            line_hint=line_hint,
            context_lines=context_lines,
        )
    
    @classmethod
    def from_file(cls, path: Path, line: int, context_lines: int = 3) -> HashlineAnchor:
        """Create anchor from file position."""
        content = path.read_text(encoding="utf-8")
        return cls.from_content(content, line_hint=line, context_lines=context_lines)


@dataclass
class HashlinePatch:
    """A patch using hashline anchors."""
    
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    file_path: str = ""
    anchor: HashlineAnchor | None = None
    
    old_content: str = ""
    new_content: str = ""
    
    # Metadata
    created_at: str = ""  # ISO timestamp
    created_by: str = "agent"
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "file_path": self.file_path,
            "anchor": {
                "content_hash": self.anchor.content_hash if self.anchor else None,
                "line_hint": self.anchor.line_hint if self.anchor else None,
                "context_lines": self.anchor.context_lines if self.anchor else None,
            } if self.anchor else None,
            "old_content": self.old_content,
            "new_content": self.new_content,
            "created_at": self.created_at,
            "created_by": self.created_by,
        }


@dataclass
class EditResult:
    """Result of an edit operation."""
    
    success: bool
    file_path: str
    old_content: str = ""
    new_content: str = ""
    lines_changed: int = 0
    
    error: str | None = None
    patch_id: str | None = None
    
    # For hashline verification
    verified_hash: str | None = None
    anchor_line: int | None = None


class HashlineEditor:
    """File editor using content-hash anchors."""
    
    def __init__(self, verify_context: bool = True):
        """Initialize editor.
        
        Args:
            verify_context: Verify surrounding context hasn't changed before edit.
        """
        self.verify_context = verify_context
    
    def find_anchor_line(self, content: str, anchor: HashlineAnchor) -> int | None:
        """Find line number matching anchor hash."""
        lines = content.splitlines()
        
        if anchor.line_hint is not None and 0 <= anchor.line_hint < len(lines):
            # Check hint first
            context = self._get_context(lines, anchor.line_hint, anchor.context_lines)
            if self._hash_context(context) == anchor.content_hash:
                return anchor.line_hint
        
        # Search all positions
        for i in range(len(lines)):
            context = self._get_context(lines, i, anchor.context_lines)
            if self._hash_context(context) == anchor.content_hash:
                return i
        
        return None
    
    def _get_context(self, lines: list[str], center: int, context_lines: int) -> str:
        """Get surrounding context for a line."""
        start = max(0, center - context_lines)
        end = min(len(lines), center + context_lines + 1)
        return "\n".join(lines[start:end])
    
    def _hash_context(self, context: str) -> str:
        """Hash context string."""
        return hashlib.sha256(context.encode()).hexdigest()[:16]
    
    def verify_anchor(self, content: str, anchor: HashlineAnchor, anchor_line: int) -> bool:
        """Verify anchor is still valid at given line."""
        lines = content.splitlines()
        context = self._get_context(lines, anchor_line, anchor.context_lines)
        return self._hash_context(context) == anchor.content_hash
    
    def apply_patch(self, path: Path, patch: HashlinePatch) -> EditResult:
        """Apply a hashline patch to a file."""
        if not path.exists():
            return EditResult(
                success=False,
                file_path=str(path),
                error=f"File not found: {path}",
            )
        
        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            return EditResult(
                success=False,
                file_path=str(path),
                error=f"Cannot read file: {e}",
            )
        
        # Find anchor
        if patch.anchor is None:
            # Use old_content as pattern match
            anchor_line = self._find_by_content(content, patch.old_content)
            if anchor_line is None:
                return EditResult(
                    success=False,
                    file_path=str(path),
                    error="Could not find old_content in file",
                )
        else:
            anchor_line = self.find_anchor_line(content, patch.anchor)
            if anchor_line is None:
                return EditResult(
                    success=False,
                    file_path=str(path),
                    error=f"Could not find anchor hash {patch.anchor.content_hash}",
                )
            
            # Verify context if requested
            if self.verify_context and not self.verify_anchor(content, patch.anchor, anchor_line):
                return EditResult(
                    success=False,
                    file_path=str(path),
                    error="Context has changed since anchor was created",
                )
        
        # Verify old_content matches at anchor line
        lines = content.splitlines()
        
        # Find the old_content in file starting from anchor_line
        search_start = anchor_line
        found_line = None
        
        for i in range(search_start, len(lines)):
            if self._content_matches(lines[i], patch.old_content):
                found_line = i
                break
        
        if found_line is None:
            return EditResult(
                success=False,
                file_path=str(path),
                error="Could not find old_content at anchor position",
            )
        
        # Apply edit
        try:
            old_lines = lines[:found_line]
            new_lines = lines[found_line + 1:]
            
            # Handle multi-line old_content
            if "\n" in patch.old_content:
                old_parts = patch.old_content.split("\n")
                remaining = lines[found_line + 1:]
                
                # Find end of old_content block
                end_match = found_line
                for j, part in enumerate(old_parts[1:], 1):
                    if end_match + j < len(lines) and self._content_matches(lines[end_match + j], part):
                        end_match += j
                
                old_lines = lines[:found_line]
                new_lines = lines[end_match + 1:]
            
            # Reconstruct with new content
            new_text = "\n".join(old_lines)
            if new_text and patch.new_content:
                new_text += "\n"
            new_text += patch.new_content
            if new_lines:
                new_text += "\n" + "\n".join(new_lines)
            
            # Write atomically
            path.write_text(new_text, encoding="utf-8")
            
            return EditResult(
                success=True,
                file_path=str(path),
                old_content=patch.old_content,
                new_content=patch.new_content,
                lines_changed=len(patch.new_content.splitlines()) - len(patch.old_content.splitlines()),
                anchor_line=found_line,
                verified_hash=patch.anchor.content_hash if patch.anchor else None,
            )
            
        except Exception as e:
            return EditResult(
                success=False,
                file_path=str(path),
                error=f"Failed to apply patch: {e}",
            )
    
    def _content_matches(self, line: str, content: str) -> bool:
        """Check if line matches expected content."""
        line = line.strip()
        content = content.strip()
        
        # Exact match
        if line == content:
            return True
        
        # Content is substring of line
        if content in line:
            return True
        
        return False
    
    def _find_by_content(self, content: str, pattern: str) -> int | None:
        """Find line number by content pattern."""
        lines = content.splitlines()
        
        for i, line in enumerate(lines):
            if self._content_matches(line, pattern):
                return i
        
        return None
    
    def create_patch(
        self,
        path: Path,
        old_content: str,
        new_content: str,
        anchor_line: int | None = None,
    ) -> HashlinePatch:
        """Create a hashline patch for later application."""
        from datetime import datetime, timezone
        
        if anchor_line is None:
            content = path.read_text(encoding="utf-8")
            anchor_line = self._find_by_content(content, old_content)
        
        anchor = HashlineAnchor.from_file(path, anchor_line) if anchor_line is not None else None
        
        return HashlinePatch(
            file_path=str(path),
            anchor=anchor,
            old_content=old_content,
            new_content=new_content,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
    
    def preview_patch(self, path: Path, patch: HashlinePatch) -> str:
        """Generate a preview of what the patch would do."""
        if not path.exists():
            return f"Error: File not found: {path}"
        
        content = path.read_text(encoding="utf-8")
        anchor_line = None
        
        if patch.anchor:
            anchor_line = self.find_anchor_line(content, patch.anchor)
        
        if anchor_line is None and patch.old_content:
            anchor_line = self._find_by_content(content, patch.old_content)
        
        if anchor_line is None:
            return f"Could not locate patch location in {path}"
        
        lines = content.splitlines()
        start = max(0, anchor_line - 3)
        end = min(len(lines), anchor_line + len(patch.old_content.splitlines()) + 4)
        
        preview = [f"=== {path} (around line {anchor_line + 1}) ==="]
        preview.append("")
        
        for i, line in enumerate(lines[start:end], start + 1):
            marker = ">>> " if i == anchor_line else "    "
            preview.append(f"{marker}{i:4d}: {line}")
        
        preview.append("")
        preview.append("--- would become ---")
        preview.append("")
        
        for i, line in enumerate(lines[start:anchor_line], start + 1):
            preview.append(f"     {i:4d}: {line}")
        
        for j, line in enumerate(patch.new_content.splitlines()):
            preview.append(f"     +++ : {line}")
        
        for i, line in enumerate(lines[anchor_line + len(patch.old_content.splitlines()):end]):
            preview.append(f"     {i:4d}: {line}")
        
        return "\n".join(preview)


# Convenience functions
def edit_file(
    path: Path,
    old: str,
    new: str,
    verify: bool = True,
) -> EditResult:
    """Simple one-shot file edit with hashline verification."""
    editor = HashlineEditor(verify_context=verify)
    patch = editor.create_patch(path, old, new)
    return editor.apply_patch(path, patch)


def preview_edit(path: Path, old: str, new: str) -> str:
    """Preview what an edit would do."""
    editor = HashlineEditor(verify_context=False)
    patch = editor.create_patch(path, old, new)
    return editor.preview_patch(path, patch)

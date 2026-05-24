"""Hardware-aware text chunking for knowledge base ingestion.

Strategies:
- By peripheral (one chunk per peripheral section)
- By register (one chunk per register description)
- By document section (RM chapters)
- By code function (for source code)
- By constraint group (for hardware rules)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class Chunk:
    """A text chunk with metadata."""
    id: str
    content: str
    chunk_index: int
    total_chunks: int
    source_reference: str | None = None


class HardwareChunker:
    """
    Hardware-aware text chunker.

    Chunks reference manuals, SVD files, and source code
    in a way that preserves hardware semantics.
    """

    def __init__(
        self,
        max_chunk_size: int = 1500,
        overlap_size: int = 100,
    ):
        self.max_chunk_size = max_chunk_size
        self.overlap_size = overlap_size

    async def chunk(
        self,
        text: str,
        entry_type: str,  # "KBEntryType" - passed as string to avoid circular import
    ) -> list[dict[str, Any]]:
        """
        Chunk text based on entry type.

        Args:
            text: Raw text to chunk
            entry_type: Type string of knowledge entry (e.g. "register_spec")

        Returns:
            List of {"id": str, "content": str} dicts
        """
        import uuid

        if entry_type in (
            "register_spec",
            "peripheral_spec",
        ):
            chunks = self._chunk_by_register(text)
        elif entry_type == "rm_excerpt":
            chunks = self._chunk_by_section(text)
        elif entry_type == "code_snippet":
            chunks = self._chunk_by_function(text)
        elif entry_type == "hardware_constraint":
            chunks = self._chunk_by_constraint(text)
        else:
            chunks = self._chunk_by_paragraph(text)

        # Assign IDs
        return [
            {"id": str(uuid.uuid4())[:12], "content": c}
            for c in chunks
        ]

    def _chunk_by_register(self, text: str) -> list[str]:
        """Chunk by register boundaries."""
        # Split on register headers
        register_pattern = r"(?=\n[A-Z_]+\s*[:]?\s*\n)"
        parts = re.split(register_pattern, text)
        chunks: list[str] = []
        current = ""

        for part in parts:
            if len(current) + len(part) <= self.max_chunk_size:
                current += part
            else:
                if current.strip():
                    chunks.append(current.strip())
                current = part

        if current.strip():
            chunks.append(current.strip())

        return chunks or [text[: self.max_chunk_size]]

    def _chunk_by_section(self, text: str) -> list[str]:
        """Chunk by RM section headers."""
        # Split on numbered sections
        section_pattern = r"(?=\n\d+\.\d*\s)"
        parts = re.split(section_pattern, text)
        chunks: list[str] = []
        current = ""

        for part in parts:
            if len(current) + len(part) <= self.max_chunk_size:
                current += part
            else:
                if current.strip():
                    chunks.append(current.strip())
                current = part

        if current.strip():
            chunks.append(current.strip())

        return chunks or [text[: self.max_chunk_size]]

    def _chunk_by_function(self, text: str) -> list[str]:
        """Chunk by C function boundaries."""
        # Match function declarations
        func_pattern = r"(?=\n(?:void|int|uint32_t|static|const\s+\w+)\s+\w+\s*\([^)]*\)\s*\{)"
        parts = re.split(func_pattern, text)
        chunks: list[str] = []
        current = ""

        for part in parts:
            if len(current) + len(part) <= self.max_chunk_size:
                current += part
            else:
                if current.strip():
                    chunks.append(current.strip())
                current = part

        if current.strip():
            chunks.append(current.strip())

        return chunks or [text[: self.max_chunk_size]]

    def _chunk_by_constraint(self, text: str) -> list[str]:
        """Chunk by constraint rule boundaries."""
        # Split on rule IDs or constraint markers
        rule_pattern = r"(?=\n\[[A-Z0-9_]+\])"
        parts = re.split(rule_pattern, text)
        chunks: list[str] = []
        current = ""

        for part in parts:
            if len(current) + len(part) <= self.max_chunk_size:
                current += part
            else:
                if current.strip():
                    chunks.append(current.strip())
                current = part

        if current.strip():
            chunks.append(current.strip())

        return chunks or [text[: self.max_chunk_size]]

    def _chunk_by_paragraph(self, text: str) -> list[str]:
        """Chunk by paragraphs with overlap."""
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks: list[str] = []
        current = ""

        for para in paragraphs:
            if len(current) + len(para) <= self.max_chunk_size:
                current += ("\n\n" if current else "") + para
            else:
                if current:
                    chunks.append(current)
                # Keep overlap
                if self.overlap_size > 0 and len(current) > self.overlap_size:
                    current = current[-self.overlap_size:] + "\n\n" + para
                else:
                    current = para

        if current.strip():
            chunks.append(current.strip())

        return chunks or [text[: self.max_chunk_size]]

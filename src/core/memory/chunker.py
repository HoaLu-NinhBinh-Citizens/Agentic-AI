"""Text chunking system with JSON-aware splitting and safe fallback.

Supports:
- JSON objects and arrays with smart splitting
- Plain text paragraph/sentence splitting
- Safe repr() fallback for invalid JSON
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

MAX_CHUNK_SIZE = 500
MAX_JSON_CHUNK_SIZE = 2000


@dataclass
class Chunk:
    """A text chunk with metadata."""

    text: str
    chunk_index: int
    chunk_total: int
    parent_id: str
    method: str


class Chunker:
    """Text chunker with JSON-aware splitting."""

    def __init__(
        self,
        max_chunk_size: int = MAX_CHUNK_SIZE,
        max_json_chunk_size: int = MAX_JSON_CHUNK_SIZE,
    ) -> None:
        """Initialize the chunker.

        Args:
            max_chunk_size: Maximum characters per chunk for plain text.
            max_json_chunk_size: Maximum characters per JSON chunk.
        """
        self._max_chunk_size = max_chunk_size
        self._max_json_chunk_size = max_json_chunk_size

    def chunk(self, text: str, parent_id: str) -> list[Chunk]:
        """Split text into chunks.

        Args:
            text: Text to chunk.
            parent_id: Parent ID for all chunks.

        Returns:
            List of Chunk objects.
        """
        if not text or not text.strip():
            return []

        text = text.strip()

        if self._looks_like_json(text):
            return self._chunk_json(text, parent_id)
        else:
            return self._chunk_plain_text(text, parent_id)

    def _looks_like_json(self, text: str) -> bool:
        """Check if text looks like JSON.

        Args:
            text: Text to check.

        Returns:
            True if text appears to be JSON.
        """
        text = text.strip()
        return (text.startswith("{") and text.endswith("}")) or (
            text.startswith("[") and text.endswith("]")
        )

    def _chunk_json(self, text: str, parent_id: str) -> list[Chunk]:
        """Chunk JSON text.

        Args:
            text: JSON text.
            parent_id: Parent ID.

        Returns:
            List of chunks.
        """
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return self._chunk_json_fallback(text, parent_id)

        text_len = len(text)

        if text_len <= self._max_json_chunk_size:
            return [Chunk(text=text, chunk_index=0, chunk_total=1, parent_id=parent_id, method="json")]

        if isinstance(parsed, dict):
            return self._chunk_json_object(parsed, text, parent_id)
        elif isinstance(parsed, list):
            return self._chunk_json_array(parsed, text, parent_id)
        else:
            return self._chunk_json_fallback(text, parent_id)

    def _chunk_json_object(
        self, parsed: dict[str, Any], original_text: str, parent_id: str
    ) -> list[Chunk]:
        """Split JSON object by top-level keys.

        Args:
            parsed: Parsed JSON object.
            original_text: Original text.
            parent_id: Parent ID.

        Returns:
            List of chunks.
        """
        chunks: list[Chunk] = []
        current_chunk_parts: list[str] = []
        current_size = 0

        for key in parsed.keys():
            key_str = f'"{key}": {json.dumps(parsed[key], ensure_ascii=False)}'
            key_size = len(key_str) + 2

            if current_size + key_size > self._max_json_chunk_size and current_chunk_parts:
                chunk_text = "{" + ",".join(current_chunk_parts) + "}"
                chunks.append(
                    Chunk(
                        text=chunk_text,
                        chunk_index=len(chunks),
                        chunk_total=len(parsed),
                        parent_id=parent_id,
                        method="json_split",
                    )
                )
                current_chunk_parts = []
                current_size = 0

            current_chunk_parts.append(key_str)
            current_size += key_size

        if current_chunk_parts:
            chunk_text = "{" + ",".join(current_chunk_parts) + "}"
            chunks.append(
                Chunk(
                    text=chunk_text,
                    chunk_index=len(chunks),
                    chunk_total=len(chunks) + 1 if not chunks else len(chunks),
                    parent_id=parent_id,
                    method="json_split",
                )
            )

        if not chunks:
            return self._chunk_json_fallback(original_text, parent_id)

        for i, chunk in enumerate(chunks):
            chunk.chunk_total = len(chunks)

        return chunks

    def _chunk_json_array(self, parsed: list[Any], original_text: str, parent_id: str) -> list[Chunk]:
        """Split JSON array by slices.

        Args:
            parsed: Parsed JSON array.
            original_text: Original text.
            parent_id: Parent ID.

        Returns:
            List of chunks.
        """
        chunks: list[Chunk] = []
        chunk_items: list[str] = []
        current_size = 0

        for item in parsed:
            item_str = json.dumps(item, ensure_ascii=False)
            item_size = len(item_str)

            if current_size + item_size > self._max_json_chunk_size and chunk_items:
                chunk_text = "[" + ",".join(chunk_items) + "]"
                chunks.append(
                    Chunk(
                        text=chunk_text,
                        chunk_index=len(chunks),
                        chunk_total=len(parsed),
                        parent_id=parent_id,
                        method="json_array",
                    )
                )
                chunk_items = []
                current_size = 0

            chunk_items.append(item_str)
            current_size += item_size

        if chunk_items:
            chunk_text = "[" + ",".join(chunk_items) + "]"
            chunks.append(
                Chunk(
                    text=chunk_text,
                    chunk_index=len(chunks),
                    chunk_total=len(chunks) + 1 if not chunks else len(chunks),
                    parent_id=parent_id,
                    method="json_array",
                )
            )

        if not chunks:
            return self._chunk_json_fallback(original_text, parent_id)

        for i, chunk in enumerate(chunks):
            chunk.chunk_total = len(chunks)

        return chunks

    def _chunk_json_fallback(self, text: str, parent_id: str) -> list[Chunk]:
        """Fallback for invalid JSON - use repr().

        Args:
            text: Original text.
            parent_id: Parent ID.

        Returns:
            Single chunk with repr() of text.
        """
        logger.warning(
            "memory_json_parse_failed_fallback: Converting text to repr() for chunking",
        )
        safe_text = repr(text)
        if len(safe_text) > self._max_json_chunk_size:
            safe_text = safe_text[: self._max_json_chunk_size]
        return [Chunk(text=safe_text, chunk_index=0, chunk_total=1, parent_id=parent_id, method="json_fallback")]

    def _chunk_plain_text(self, text: str, parent_id: str) -> list[Chunk]:
        """Split plain text by paragraphs, sentences, or words.

        Args:
            text: Plain text.
            parent_id: Parent ID.

        Returns:
            List of chunks.
        """
        paragraphs = re.split(r"\n\n+", text)

        chunks: list[Chunk] = []
        current_chunk_parts: list[str] = []
        current_size = 0

        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue

            if len(paragraph) <= self._max_chunk_size and current_size + len(paragraph) <= self._max_chunk_size:
                current_chunk_parts.append(paragraph)
                current_size += len(paragraph) + 2
            elif len(paragraph) <= self._max_chunk_size:
                if current_chunk_parts:
                    chunks.append(
                        Chunk(
                            text="\n\n".join(current_chunk_parts),
                            chunk_index=len(chunks),
                            chunk_total=1,
                            parent_id=parent_id,
                            method="paragraph",
                        )
                    )
                current_chunk_parts = [paragraph]
                current_size = len(paragraph)
            else:
                if current_chunk_parts:
                    chunks.append(
                        Chunk(
                            text="\n\n".join(current_chunk_parts),
                            chunk_index=len(chunks),
                            chunk_total=1,
                            parent_id=parent_id,
                            method="paragraph",
                        )
                    )
                    current_chunk_parts = []
                    current_size = 0

                chunks.extend(self._chunk_long_text(paragraph, parent_id))

        if current_chunk_parts:
            chunks.append(
                Chunk(
                    text="\n\n".join(current_chunk_parts),
                    chunk_index=len(chunks),
                    chunk_total=1,
                    parent_id=parent_id,
                    method="paragraph",
                )
            )

        if not chunks:
            return [Chunk(text=text[: self._max_chunk_size], chunk_index=0, chunk_total=1, parent_id=parent_id, method="plain")]

        for i, chunk in enumerate(chunks):
            chunk.chunk_total = len(chunks)

        return chunks

    def _chunk_long_text(self, text: str, parent_id: str) -> list[Chunk]:
        """Split long text by sentences.

        Args:
            text: Long text.
            parent_id: Parent ID.

        Returns:
            List of chunks.
        """
        sentence_pattern = r"(?<=[.!?])\s+"
        sentences = re.split(sentence_pattern, text)

        chunks: list[Chunk] = []
        current_sentences: list[str] = []
        current_size = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            if current_size + len(sentence) <= self._max_chunk_size:
                current_sentences.append(sentence)
                current_size += len(sentence)
            else:
                if current_sentences:
                    chunks.append(
                        Chunk(
                            text=" ".join(current_sentences),
                            chunk_index=len(chunks),
                            chunk_total=1,
                            parent_id=parent_id,
                            method="sentence",
                        )
                    )
                if len(sentence) <= self._max_chunk_size:
                    current_sentences = [sentence]
                    current_size = len(sentence)
                else:
                    current_sentences = []
                    current_size = 0
                    for i in range(0, len(sentence), self._max_chunk_size):
                        chunks.append(
                            Chunk(
                                text=sentence[i : i + self._max_chunk_size],
                                chunk_index=len(chunks),
                                chunk_total=1,
                                parent_id=parent_id,
                                method="char_window",
                            )
                        )

        if current_sentences:
            chunks.append(
                Chunk(
                    text=" ".join(current_sentences),
                    chunk_index=len(chunks),
                    chunk_total=1,
                    parent_id=parent_id,
                    method="sentence",
                )
            )

        return chunks

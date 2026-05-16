"""Unit tests for Chunker."""

import pytest

from core.memory.chunker import Chunker, Chunk, MAX_CHUNK_SIZE


class TestChunker:
    """Tests for Chunker."""

    @pytest.fixture
    def chunker(self):
        """Create a chunker instance."""
        return Chunker(max_chunk_size=MAX_CHUNK_SIZE)

    def test_chunk_empty_text(self, chunker):
        """Test chunking empty text."""
        chunks = chunker.chunk("", "parent-1")
        assert chunks == []

    def test_chunk_whitespace_only(self, chunker):
        """Test chunking whitespace-only text."""
        chunks = chunker.chunk("   ", "parent-1")
        assert chunks == []

    def test_chunk_short_text(self, chunker):
        """Test chunking short text."""
        text = "This is a short text."
        chunks = chunker.chunk(text, "parent-1")

        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].chunk_index == 0
        assert chunks[0].chunk_total == 1

    def test_chunk_json_object(self, chunker):
        """Test chunking JSON object."""
        import json
        data = {"key1": "value1", "key2": "value2"}
        text = json.dumps(data)

        chunks = chunker.chunk(text, "parent-1")

        assert len(chunks) == 1
        assert chunks[0].method == "json"

    def test_chunk_json_array(self, chunker):
        """Test chunking JSON array."""
        import json
        data = [1, 2, 3, 4, 5]
        text = json.dumps(data)

        chunks = chunker.chunk(text, "parent-1")

        assert len(chunks) == 1
        assert chunks[0].method == "json"

    def test_chunk_plain_text_paragraphs(self, chunker):
        """Test chunking plain text with paragraphs."""
        text = "First paragraph.\n\nSecond paragraph."
        chunks = chunker.chunk(text, "parent-1")

        assert len(chunks) >= 1
        assert all(c.parent_id == "parent-1" for c in chunks)

    def test_chunk_long_json_object(self, chunker):
        """Test chunking long JSON object."""
        import json
        data = {f"key{i}": f"value{i}" * 50 for i in range(20)}
        text = json.dumps(data)

        chunks = chunker.chunk(text, "parent-1")

        assert len(chunks) > 1
        assert all(c.method in ("json_split", "json") for c in chunks)

    def test_chunk_invalid_json_fallback(self, chunker):
        """Test invalid JSON uses repr fallback."""
        text = "{ invalid json }"
        chunks = chunker.chunk(text, "parent-1")

        assert len(chunks) == 1
        assert chunks[0].method == "json_fallback"

    def test_chunk_parent_id_consistent(self, chunker):
        """Test all chunks have same parent_id."""
        text = "Long text " * 100
        chunks = chunker.chunk(text, "my-parent-id")

        assert all(c.parent_id == "my-parent-id" for c in chunks)

    def test_chunk_indices_sequential(self, chunker):
        """Test chunk indices are sequential."""
        text = "Long text " * 100
        chunks = chunker.chunk(text, "parent-1")

        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_chunk_total_consistent(self, chunker):
        """Test chunk_total is consistent."""
        text = "Long text " * 100
        chunks = chunker.chunk(text, "parent-1")

        totals = set(c.chunk_total for c in chunks)
        assert len(totals) == 1
        assert totals.pop() == len(chunks)


class TestChunk:
    """Tests for Chunk dataclass."""

    def test_chunk_creation(self):
        """Test creating a chunk."""
        chunk = Chunk(
            text="Test content",
            chunk_index=0,
            chunk_total=1,
            parent_id="parent-1",
            method="plain",
        )

        assert chunk.text == "Test content"
        assert chunk.chunk_index == 0
        assert chunk.chunk_total == 1
        assert chunk.parent_id == "parent-1"
        assert chunk.method == "plain"

    def test_chunk_mutable_fields(self):
        """Test chunk fields can be modified."""
        chunk = Chunk(
            text="Test",
            chunk_index=0,
            chunk_total=1,
            parent_id="parent-1",
            method="plain",
        )

        chunk.chunk_total = 3
        assert chunk.chunk_total == 3


class TestChunkerJsonEdgeCases:
    """Tests for JSON edge cases in Chunker."""

    @pytest.fixture
    def chunker(self):
        """Create a chunker instance."""
        return Chunker(max_chunk_size=100, max_json_chunk_size=200)

    def test_chunk_deeply_nested_json(self, chunker):
        """Test chunking deeply nested JSON (10 levels)."""
        import json

        # Create 10 levels of nesting
        data = {"level": 0}
        current = data
        for i in range(1, 10):
            current["nested"] = {"level": i}
            current = current["nested"]

        text = json.dumps(data)
        chunks = chunker.chunk(text, "parent-deep")

        assert len(chunks) >= 1
        assert all(c.parent_id == "parent-deep" for c in chunks)

    def test_chunk_empty_json_object(self, chunker):
        """Test chunking empty JSON object {}."""
        text = "{}"
        chunks = chunker.chunk(text, "parent-empty-obj")

        assert len(chunks) == 1
        assert chunks[0].text == "{}"
        assert chunks[0].method == "json"

    def test_chunk_empty_json_array(self, chunker):
        """Test chunking empty JSON array []."""
        text = "[]"
        chunks = chunker.chunk(text, "parent-empty-arr")

        assert len(chunks) == 1
        assert chunks[0].text == "[]"
        assert chunks[0].method == "json"

    def test_chunk_json_with_escaped_quotes(self, chunker):
        """Test chunking JSON with escaped quotes."""
        import json

        data = {"key": 'value with "quote"', "nested": {"inner": 'also "quoted"'}}
        text = json.dumps(data)
        chunks = chunker.chunk(text, "parent-escaped")

        assert len(chunks) >= 1
        # Verify content is parseable
        for chunk in chunks:
            try:
                parsed = json.loads(chunk.text)
                assert isinstance(parsed, dict)
            except json.JSONDecodeError:
                # Fallback repr is acceptable
                assert chunk.method == "json_fallback"

    def test_chunk_long_json_array(self, chunker):
        """Test chunking very long JSON array (5000 elements) splits correctly."""
        import json

        # Create large array
        data = [{"id": i, "value": f"item_{i}"} for i in range(5000)]
        text = json.dumps(data)
        chunks = chunker.chunk(text, "parent-long-arr")

        # Should produce multiple chunks due to size
        assert len(chunks) > 1
        assert all(c.parent_id == "parent-long-arr" for c in chunks)

        # Verify chunk_total is consistent
        totals = set(c.chunk_total for c in chunks)
        assert len(totals) == 1
        assert totals.pop() == len(chunks)

    def test_chunk_json_malformed_missing_closing(self, chunker):
        """Test chunking malformed JSON with missing closing brace.

        Note: Text that doesn't end with } is not detected as JSON-like,
        so it's processed as plain text.
        """
        text = '{"key": "value", "incomplete":'
        chunks = chunker.chunk(text, "parent-malformed-1")

        # Text doesn't look like JSON (no closing brace), so treated as plain text
        assert len(chunks) == 1
        assert chunks[0].method in ("paragraph", "json_fallback")

    def test_chunk_json_malformed_invalid_char(self, chunker):
        """Test chunking malformed JSON with invalid characters."""
        text = '{"key": @invalid#char}'
        chunks = chunker.chunk(text, "parent-malformed-2")

        assert len(chunks) == 1
        assert chunks[0].method == "json_fallback"

    def test_chunk_json_with_numbers_booleans_null(self, chunker):
        """Test chunking JSON with numbers, booleans, and null."""
        import json

        data = {
            "integer": 42,
            "float": 3.14159,
            "negative": -100,
            "boolean_true": True,
            "boolean_false": False,
            "null_value": None,
            "exponential": 1e10,
        }
        text = json.dumps(data)
        chunks = chunker.chunk(text, "parent-primitives")

        assert len(chunks) == 1
        assert chunks[0].method == "json"

        # Verify content is parseable
        parsed = json.loads(chunks[0].text)
        assert parsed["integer"] == 42
        assert parsed["float"] == 3.14159
        assert parsed["boolean_true"] is True
        assert parsed["boolean_false"] is False
        assert parsed["null_value"] is None

"""Unit tests for ToolCallAccumulator."""

import pytest

from infrastructure.llm.tool_accumulator import ToolCallAccumulator, ToolCallBuffer


class TestToolCallBuffer:
    """Tests for ToolCallBuffer."""

    def test_empty_buffer_is_not_complete(self):
        """Test that empty buffer is not complete."""
        buf = ToolCallBuffer()
        assert not buf.is_complete()

    def test_valid_json_is_complete(self):
        """Test that valid JSON is complete."""
        buf = ToolCallBuffer()
        buf.arguments_str = '{"path": "/test", "content": "hello"}'
        assert buf.is_complete()

    def test_invalid_json_is_not_complete(self):
        """Test that invalid JSON is not complete."""
        buf = ToolCallBuffer()
        buf.arguments_str = '{"path": "/test", content: "hello"}'
        assert not buf.is_complete()

    def test_partial_json_is_not_complete(self):
        """Test that partial JSON is not complete."""
        buf = ToolCallBuffer()
        buf.arguments_str = '{"path": "/test"'
        assert not buf.is_complete()

    def test_to_tool_call_valid(self):
        """Test converting valid buffer to tool call."""
        buf = ToolCallBuffer()
        buf.call_id = "call_123"
        buf.function_name = "read_file"
        buf.arguments_str = '{"path": "/test.txt"}'

        tool_call = buf.to_tool_call(0)
        assert tool_call is not None
        assert tool_call.id == "call_123"
        assert tool_call.name == "read_file"
        assert tool_call.arguments == {"path": "/test.txt"}

    def test_to_tool_call_no_function_name(self):
        """Test that buffer without function name returns None."""
        buf = ToolCallBuffer()
        buf.arguments_str = '{"path": "/test.txt"}'

        tool_call = buf.to_tool_call(0)
        assert tool_call is None

    def test_to_tool_call_invalid_json(self):
        """Test that buffer with invalid JSON returns None."""
        buf = ToolCallBuffer()
        buf.function_name = "read_file"
        buf.arguments_str = 'invalid json'

        tool_call = buf.to_tool_call(0)
        assert tool_call is None


class TestToolCallAccumulator:
    """Tests for ToolCallAccumulator."""

    def test_empty_accumulator(self):
        """Test empty accumulator has no tool calls."""
        acc = ToolCallAccumulator()
        assert not acc.has_tool_calls()
        assert acc.buffer_count == 0
        assert acc.finalized_count == 0

    def test_add_tool_call_start(self):
        """Test adding tool call start."""
        acc = ToolCallAccumulator()
        acc.add_tool_call_start(index=0, call_id="call_1", function_name="read_file")

        assert acc.has_tool_calls()
        assert acc.buffer_count == 1

    def test_add_tool_call_delta(self):
        """Test adding tool call delta."""
        acc = ToolCallAccumulator()
        acc.add_tool_call_delta(index=0, arguments='{"path": "/test')

        assert acc.has_tool_calls()
        assert acc.buffer_count == 1

    def test_accumulate_partial_json(self):
        """Test accumulating partial JSON arguments."""
        acc = ToolCallAccumulator()

        acc.add_tool_call_start(index=0, call_id="call_1", function_name="read_file")
        acc.add_tool_call_delta(index=0, arguments='{"path": "/test.txt"')
        acc.add_tool_call_delta(index=0, arguments=', "encoding": "utf-8"}')

        assert acc.has_tool_calls()
        calls = acc.finalize()
        assert len(calls) == 1
        assert calls[0].name == "read_file"
        assert calls[0].arguments == {"path": "/test.txt", "encoding": "utf-8"}

    def test_multiple_tool_calls(self):
        """Test accumulating multiple tool calls."""
        acc = ToolCallAccumulator()

        acc.add_tool_call_start(index=0, call_id="call_1", function_name="read_file")
        acc.add_tool_call_delta(index=0, arguments='{"path": "/test.txt"}')

        acc.add_tool_call_start(index=1, call_id="call_2", function_name="write_file")
        acc.add_tool_call_delta(index=1, arguments='{"path": "/out.txt", "content": "hello"}')

        calls = acc.finalize()
        assert len(calls) == 2
        assert calls[0].name == "read_file"
        assert calls[1].name == "write_file"

    def test_add_raw_chunk(self):
        """Test adding raw chunk."""
        acc = ToolCallAccumulator()

        chunk = {
            "type": "tool_call_delta",
            "index": 0,
            "call_id": "call_1",
            "function": {"name": "read_file", "arguments": '{"path": "/test"}'},
        }
        acc.add_chunk(chunk)

        assert acc.has_tool_calls()

    def test_finalize_once(self):
        """Test that finalize can only be called once."""
        acc = ToolCallAccumulator()
        acc.add_tool_call_start(index=0, call_id="call_1", function_name="read_file")

        calls1 = acc.finalize()
        calls2 = acc.get_final_calls()

        assert calls1 == calls2
        assert acc._is_finalized

    def test_reset(self):
        """Test resetting accumulator."""
        acc = ToolCallAccumulator()
        acc.add_tool_call_start(index=0, call_id="call_1", function_name="read_file")
        acc.finalize()

        acc.reset()

        assert not acc.has_tool_calls()
        assert acc.buffer_count == 0
        assert not acc._is_finalized

    def test_in_progress_calls(self):
        """Test getting in-progress calls."""
        acc = ToolCallAccumulator()
        acc.add_tool_call_start(index=0, call_id="call_1", function_name="read_file")
        acc.add_tool_call_delta(index=0, arguments='{"path": "/test')

        in_progress = acc.get_in_progress_calls()
        assert len(in_progress) == 1
        assert in_progress[0][0] == 0

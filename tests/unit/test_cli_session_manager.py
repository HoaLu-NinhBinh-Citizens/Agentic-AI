"""Unit tests for CLI Session Manager.

Tests for:
- Session creation and persistence
- Message history tracking
- Tool call recording
- Project-scoped context
- Rule discovery
- Hindsight fact tracking
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from datetime import datetime

from src.infrastructure.session.session_manager import (
    Session,
    SessionContext,
    SessionStore,
    SessionStatus,
    Message,
    ToolCall,
    create_session,
    discover_project_rules,
    get_session_store,
)


class TestSession:
    """Tests for Session dataclass."""

    def test_session_creation_default(self):
        """Test session creation with defaults."""
        session = Session()
        
        assert session.id is not None
        assert len(session.id) == 36  # UUID format
        assert session.status == SessionStatus.ACTIVE
        assert session.messages == []
        assert session.tool_calls == []
        assert session.turn_count == 0

    def test_session_creation_with_context(self):
        """Test session creation with context."""
        context = SessionContext(
            project_path=Path("/test/project"),
            project_id="test-project",
            model="qwen2.5-coder:7b",
        )
        session = Session(context=context)
        
        assert session.context.project_path == Path("/test/project")
        assert session.context.project_id == "test-project"
        assert session.context.model == "qwen2.5-coder:7b"

    def test_add_message_user(self):
        """Test adding user message."""
        session = Session()
        msg = session.add_message("user", "Hello, world!")
        
        assert msg.role == "user"
        assert msg.content == "Hello, world!"
        assert isinstance(msg.timestamp, datetime)
        assert len(session.messages) == 1

    def test_add_message_assistant(self):
        """Test adding assistant message."""
        session = Session()
        msg = session.add_message("assistant", "Hello!")
        
        assert msg.role == "assistant"
        assert msg.content == "Hello!"
        assert len(session.messages) == 1

    def test_add_message_with_tool_context(self):
        """Test adding message with tool context."""
        session = Session()
        msg = session.add_message(
            role="tool_result",
            content="File content here",
            tool_name="read",
            tool_call_id="call_123",
        )
        
        assert msg.tool_name == "read"
        assert msg.tool_call_id == "call_123"

    def test_add_tool_call(self):
        """Test recording tool call."""
        session = Session()
        tc = session.add_tool_call("read", {"path": "test.py"})
        
        assert tc.name == "read"
        assert tc.arguments == {"path": "test.py"}
        assert tc.id is not None
        assert len(session.tool_calls) == 1

    def test_tool_call_complete_success(self):
        """Test tool call completion with success."""
        session = Session()
        tc = session.add_tool_call("bash", {"command": "ls"})
        tc.complete(result="file1\nfile2")
        
        assert tc.result == "file1\nfile2"
        assert tc.error is None
        assert tc.completed_at is not None
        assert tc.duration_ms is not None

    def test_tool_call_complete_error(self):
        """Test tool call completion with error."""
        session = Session()
        tc = session.add_tool_call("read", {"path": "missing.txt"})
        tc.complete(error="File not found")
        
        assert tc.result is None
        assert tc.error == "File not found"
        assert tc.completed_at is not None

    def test_increment_turn(self):
        """Test turn counter increment."""
        session = Session()
        assert session.turn_count == 0
        
        session.increment_turn()
        assert session.turn_count == 1
        
        session.increment_turn()
        assert session.turn_count == 2

    def test_add_hindsight_fact(self):
        """Test tracking retained facts."""
        session = Session()
        
        session.add_hindsight_fact("fact_001")
        session.add_hindsight_fact("fact_002")
        
        assert len(session.hindsight_facts) == 2
        assert "fact_001" in session.hindsight_facts
        assert "fact_002" in session.hindsight_facts

    def test_add_duplicate_hindsight_fact(self):
        """Test duplicate fact is not added."""
        session = Session()
        
        session.add_hindsight_fact("fact_001")
        session.add_hindsight_fact("fact_001")
        
        assert len(session.hindsight_facts) == 1

    def test_session_to_dict(self):
        """Test session serialization."""
        session = Session()
        session.add_message("user", "Test")
        
        data = session.to_dict()
        
        assert "id" in data
        assert "created_at" in data
        assert "messages" in data
        assert len(data["messages"]) == 1
        assert data["messages"][0]["content"] == "Test"

    def test_session_from_dict(self):
        """Test session deserialization."""
        original = Session()
        original.add_message("user", "Hello")
        original.add_message("assistant", "Hi there")
        
        data = original.to_dict()
        restored = Session.from_dict(data)
        
        assert restored.id == original.id
        assert len(restored.messages) == 2
        assert restored.messages[0].content == "Hello"
        assert restored.messages[1].content == "Hi there"


class TestSessionContext:
    """Tests for SessionContext."""

    def test_context_defaults(self):
        """Test context with defaults."""
        context = SessionContext()
        
        assert context.project_path is None
        assert context.project_id is None
        assert context.rules == []
        assert context.model is None
        assert context.provider is None

    def test_context_to_dict(self):
        """Test context serialization."""
        context = SessionContext(
            project_path=Path("/project"),
            project_id="my-project",
            rules=["/path/to/rules.md"],
            model="gpt-4",
        )
        
        data = context.to_dict()
        
        assert data["project_id"] == "my-project"
        assert data["model"] == "gpt-4"
        assert "/path/to/rules.md" in data["rules"]

    def test_context_from_dict(self):
        """Test context deserialization."""
        data = {
            "project_path": "/test/path",
            "project_id": "restored-project",
            "rules": [],
            "model": "claude-3",
            "provider": "anthropic",
        }
        
        context = SessionContext.from_dict(data)
        
        assert context.project_path == Path("/test/path")
        assert context.project_id == "restored-project"
        assert context.model == "claude-3"


class TestSessionStore:
    """Tests for SessionStore."""

    @pytest.fixture
    def temp_store(self, tmp_path):
        """Create temporary session store."""
        return SessionStore(tmp_path)

    def test_save_and_load(self, temp_store):
        """Test session save and load."""
        session = temp_store.create_session()
        session.add_message("user", "Test message")
        
        temp_store.save(session)
        
        loaded = temp_store.load(session.id)
        
        assert loaded is not None
        assert loaded.id == session.id
        assert len(loaded.messages) == 1
        assert loaded.messages[0].content == "Test message"

    def test_load_nonexistent(self, temp_store):
        """Test loading nonexistent session."""
        result = temp_store.load("nonexistent-id")
        assert result is None

    def test_list_sessions(self, temp_store):
        """Test listing sessions."""
        session1 = temp_store.create_session()
        session2 = temp_store.create_session()
        
        sessions = temp_store.list_sessions()
        
        assert len(sessions) == 2
        ids = [s.id for s in sessions]
        assert session1.id in ids
        assert session2.id in ids

    def test_list_sessions_filtered_by_project(self, temp_store):
        """Test listing sessions filtered by project."""
        ctx1 = SessionContext(project_id="project-a")
        ctx2 = SessionContext(project_id="project-b")
        
        session1 = temp_store.create_session(ctx1)
        session2 = temp_store.create_session(ctx2)
        
        project_a_sessions = temp_store.list_sessions("project-a")
        
        assert len(project_a_sessions) == 1
        assert project_a_sessions[0].id == session1.id

    def test_delete_session(self, temp_store):
        """Test session deletion."""
        session = temp_store.create_session()
        
        result = temp_store.delete(session.id)
        assert result is True
        
        loaded = temp_store.load(session.id)
        assert loaded is None

    def test_delete_nonexistent(self, temp_store):
        """Test deleting nonexistent session."""
        result = temp_store.delete("nonexistent-id")
        assert result is False

    def test_session_updates_timestamp(self, temp_store):
        """Test that save updates timestamp."""
        session = temp_store.create_session()
        original_updated = session.updated_at
        
        import time
        time.sleep(0.01)
        
        session.add_message("user", "New message")
        temp_store.save(session)
        
        loaded = temp_store.load(session.id)
        assert loaded.updated_at >= original_updated


class TestDiscoverProjectRules:
    """Tests for rule discovery."""

    def test_discover_no_rules(self, tmp_path):
        """Test discovery with no rule files."""
        rules = discover_project_rules(tmp_path)
        assert rules == []

    def test_discover_agents_md(self, tmp_path):
        """Test discovery of AGENTS.md."""
        agents_file = tmp_path / "AGENTS.md"
        agents_file.write_text("# Agent rules")
        
        rules = discover_project_rules(tmp_path)
        
        assert str(agents_file) in rules

    def test_discover_multiple_rules(self, tmp_path):
        """Test discovery of multiple rule files."""
        (tmp_path / "AGENTS.md").write_text("# Agents")
        # Create .cursor/rules directory
        rules_dir = tmp_path / ".cursor" / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)
        (rules_dir / "cursor.md").write_text("# Cursor")
        
        rules = discover_project_rules(tmp_path)
        
        # At least one should be found
        assert len(rules) >= 1

    def test_discover_ignores_nonexistent(self, tmp_path):
        """Test that nonexistent paths are ignored."""
        rules = discover_project_rules(tmp_path)
        assert rules == []


class TestCreateSession:
    """Tests for create_session factory function."""

    def test_create_session_default(self, monkeypatch, tmp_path):
        """Test creating session with defaults."""
        # Reset global
        import src.infrastructure.session.session_manager as sm
        sm._session_store = None
        
        # Create temp store
        store = SessionStore(tmp_path)
        monkeypatch.setattr(
            "src.infrastructure.session.session_manager.get_session_store",
            lambda: store
        )
        
        session = create_session()
        
        assert session.id is not None
        assert session.status == SessionStatus.ACTIVE

    def test_create_session_with_project(self, monkeypatch, tmp_path):
        """Test creating session with project path."""
        # Reset global
        import src.infrastructure.session.session_manager as sm
        sm._session_store = None
        
        store = SessionStore(tmp_path)
        monkeypatch.setattr(
            "src.infrastructure.session.session_manager.get_session_store",
            lambda: store
        )
        
        session = create_session(tmp_path)
        
        assert session.context.project_path == tmp_path
        assert session.context.project_id == str(tmp_path.absolute())


class TestGetSessionStore:
    """Tests for get_session_store singleton."""

    def test_singleton_pattern(self, monkeypatch, tmp_path):
        """Test that get_session_store returns singleton."""
        # Reset global
        import src.infrastructure.session.session_manager as sm
        sm._session_store = None
        
        store1 = get_session_store()
        store2 = get_session_store()
        
        assert store1 is store2

    def test_singleton_with_custom_path(self, monkeypatch, tmp_path):
        """Test singleton with custom base path."""
        # Reset global
        import src.infrastructure.session.session_manager as sm
        sm._session_store = None
        
        custom_path = tmp_path / "custom"
        store = SessionStore(custom_path)
        sm._session_store = store
        
        retrieved = get_session_store()
        
        assert retrieved.base_path == custom_path

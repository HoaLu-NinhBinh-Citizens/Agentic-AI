"""Unit tests for Inline Chat."""
import pytest
import asyncio
from src.interfaces.ide.bridge.inline_chat import (
    ChatContext, ChatMessage, ChatRole, ChatStatus,
    EditPreview, InlineChatProvider, InlineChatSession,
)


class TestChatMessage:
    def test_user_message(self):
        msg = ChatMessage(role=ChatRole.USER, content="Hello")
        assert msg.role == ChatRole.USER
        assert msg.content == "Hello"
        assert msg.is_complete is True
        assert not msg.is_error

    def test_assistant_streaming(self):
        msg = ChatMessage(role=ChatRole.ASSISTANT, is_complete=False)
        assert msg.is_complete is False

    def test_to_dict(self):
        msg = ChatMessage(role=ChatRole.USER, content="Hi", tokens_used=10)
        d = msg.to_dict()
        assert d["role"] == "user"
        assert d["content"] == "Hi"
        assert d["tokensUsed"] == 10


class TestChatContext:
    def test_defaults(self):
        ctx = ChatContext()
        assert ctx.file_path == ""
        assert ctx.cursor_line == 0
        assert ctx.selection_text == ""

    def test_with_selection(self):
        ctx = ChatContext(file_path="test.py", selection_text="def foo(): pass")
        assert ctx.selection_text == "def foo(): pass"


class TestInlineChatSession:
    def test_creation(self):
        session = InlineChatSession()
        assert session.status == ChatStatus.IDLE
        assert len(session.messages) == 0
        assert len(session.edit_previews) == 0

    def test_add_message(self):
        session = InlineChatSession()
        msg = ChatMessage(role=ChatRole.USER, content="test")
        session.add_message(msg)
        assert len(session.messages) == 1
        assert session.messages[0].content == "test"

    def test_get_conversation(self):
        session = InlineChatSession()
        session.add_message(ChatMessage(role=ChatRole.USER, content="Hi"))
        session.add_message(ChatMessage(role=ChatRole.ASSISTANT, content="Hello"))
        conv = session.get_conversation()
        assert len(conv) == 2
        assert conv[0]["role"] == "user"

    def test_get_context_summary(self):
        session = InlineChatSession(context=ChatContext(
            file_path="test.py", cursor_line=5,
            selection_text="def foo(): pass",
        ))
        summary = session.get_context_summary()
        assert "test.py" in summary
        assert "line 6" in summary  # 0-indexed + 1

    def test_get_context_summary_no_selection(self):
        session = InlineChatSession(context=ChatContext(file_path="main.py"))
        summary = session.get_context_summary()
        assert "main.py" in summary


class TestEditPreview:
    def test_creation(self):
        edit = EditPreview(
            title="Fix API key",
            file_path="test.py",
            new_text='api_key = os.getenv("API_KEY")',
        )
        assert not edit.applied
        assert not edit.rejected
        assert edit.confidence == 1.0

    def test_to_dict(self):
        edit = EditPreview(title="test", new_text="x")
        d = edit.to_dict()
        assert d["title"] == "test"
        assert d["newText"] == "x"


class TestInlineChatProvider:
    def setup_method(self):
        self.provider = InlineChatProvider(debounce_ms=10)

    def test_create_session(self):
        session = self.provider.create_session(
            file_path="test.py",
            cursor_line=10,
            selection_text="def foo(): pass",
        )
        assert session.id.startswith("")
        assert session.context.file_path == "test.py"
        assert session.context.selection_text == "def foo(): pass"
        assert self.provider.get_active_session() == session

    def test_create_multiple_sessions(self):
        s1 = self.provider.create_session()
        s2 = self.provider.create_session()
        assert s1.id != s2.id
        assert self.provider.get_active_session() == s2

    def test_get_session(self):
        s1 = self.provider.create_session()
        s2 = self.provider.get_session(s1.id)
        assert s2 == s1

    def test_get_session_not_found(self):
        assert self.provider.get_session("nonexistent") is None

    def test_end_session(self):
        session = self.provider.create_session()
        self.provider.end_session(session.id)
        assert session.id not in self.provider._sessions
        assert self.provider.get_active_session() is None

    def test_end_session_not_found(self):
        # Should not raise
        self.provider.end_session("nonexistent")

    def test_stats(self):
        self.provider.create_session()
        stats = self.provider.get_stats()
        assert stats["sessions_created"] == 1
        assert "active_sessions" in stats

    @pytest.mark.asyncio
    async def test_send_message(self):
        session = self.provider.create_session(file_path="test.py")
        response = await self.provider.send_message(session.id, "Review this code")
        assert response.role == ChatRole.ASSISTANT
        assert response.content
        assert response.is_complete is True
        assert not response.is_error

    @pytest.mark.asyncio
    async def test_send_message_session_not_found(self):
        with pytest.raises(ValueError, match="Session not found"):
            await self.provider.send_message("nonexistent", "hello")

    def test_accept_edit(self):
        session = self.provider.create_session()
        edit = EditPreview(title="test")
        session.edit_previews.append(edit)
        result = self.provider.accept_edit(session.id, edit.id)
        assert result is True
        assert edit.applied

    def test_reject_edit(self):
        session = self.provider.create_session()
        edit = EditPreview(title="test")
        session.edit_previews.append(edit)
        result = self.provider.reject_edit(session.id, edit.id)
        assert result is True
        assert edit.rejected

    def test_accept_edit_not_found(self):
        session = self.provider.create_session()
        result = self.provider.accept_edit(session.id, "nonexistent")
        assert result is False

    def test_parse_edits_from_response(self):
        response = """Here's a fix:

```python
api_key = os.getenv("API_KEY")
```

And another:

```python
result = process(data)
```
"""
        edits = self.provider._parse_edits_from_response(response, "test.py")
        assert len(edits) >= 1

    def test_parse_edits_no_code_blocks(self):
        response = "This is just a regular message without code."
        edits = self.provider._parse_edits_from_response(response, "test.py")
        assert len(edits) == 0

    def test_response_builders_review(self):
        session = InlineChatProvider().create_session(
            file_path="test.py",
            selection_text="def foo(): pass",
        )
        response = self.provider._build_review_response(session, "review this")
        assert "Review" in response

    def test_response_builders_fix(self):
        provider = InlineChatProvider()
        session = provider.create_session(selection_text='api_key = "sk-xxx"')
        response = provider._build_fix_response(session, "fix this")
        assert "Fix" in response or "fix" in response

    def test_response_builders_explain(self):
        provider = InlineChatProvider()
        session = provider.create_session(selection_text="def foo(): pass")
        response = provider._build_explain_response(session, "explain")
        assert "Explanation" in response or "explain" in response

    def test_response_builders_refactor(self):
        provider = InlineChatProvider()
        session = provider.create_session(selection_text="for x in items: pass")
        response = provider._build_refactor_response(session, "refactor")
        assert "Refactor" in response

    def test_response_builders_general(self):
        provider = InlineChatProvider()
        session = provider.create_session()
        response = provider._build_general_response(session, "hello")
        assert len(response) > 0

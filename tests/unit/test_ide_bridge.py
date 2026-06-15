"""Unit tests for IDE Bridge protocol and providers."""
import pytest
from src.interfaces.ide.bridge.protocol import (
    CodeAction, CompletionItem, Diagnostic, IDEBridgeMessage,
    InlineChat, InlineCompletion, MessageType, Range, TextEdit,
)
from src.interfaces.ide.bridge.code_actions import CodeActionProvider, CodeActionContext


class TestRange:
    def test_creation(self):
        r = Range(1, 5, 3, 10)
        assert r.start_line == 1
        assert r.end_col == 10

    def test_to_lsp(self):
        r = Range(0, 0, 1, 10)
        lsp = r.to_lsp()
        assert lsp["start"]["line"] == 0
        assert lsp["end"]["character"] == 10

    def test_from_lsp(self):
        lsp = {"start": {"line": 2, "character": 5}, "end": {"line": 2, "character": 12}}
        r = Range.from_lsp(lsp)
        assert r.start_line == 2
        assert r.end_col == 12


class TestTextEdit:
    def test_creation(self):
        r = Range(0, 0, 0, 5)
        edit = TextEdit(range=r, new_text="hello")
        assert edit.new_text == "hello"
        assert edit.priority == 0

    def test_to_lsp(self):
        r = Range(1, 0, 1, 3)
        edit = TextEdit(range=r, new_text="def")
        lsp = edit.to_lsp()
        assert lsp["newText"] == "def"


class TestCompletionItem:
    def test_to_dict(self):
        item = CompletionItem(
            label="print",
            insert_text="print()",
            detail="Print to stdout",
            score=0.95,
        )
        d = item.to_dict()
        assert d["label"] == "print"
        assert d["insertText"] == "print()"
        assert d["_score"] == 0.95


class TestInlineCompletion:
    def test_to_ide_message_with_items(self):
        item = CompletionItem(label="x", insert_text="x")
        comp = InlineCompletion(items=[item])
        msg = comp.to_ide_message()
        assert msg["type"] == "completion"
        assert len(msg["items"]) == 1

    def test_to_ide_message_ghost_text(self):
        comp = InlineCompletion(text="def new_func():")
        msg = comp.to_ide_message()
        assert msg["type"] == "ghost_text"
        assert msg["text"] == "def new_func():"


class TestCodeAction:
    def test_to_dict(self):
        action = CodeAction(
            title="Fix name",
            kind="quickfix",
            is_preferred=True,
        )
        d = action.to_dict()
        assert d["title"] == "Fix name"
        assert d["kind"] == "quickfix"
        assert d["isPreferred"] is True

    def test_disabled_action(self):
        action = CodeAction(title="Broken", disabled="Rule not applicable")
        d = action.to_dict()
        assert d["disabled"]["reason"] == "Rule not applicable"


class TestDiagnostic:
    def test_severity_mapping(self):
        for sev, expected in [("error", 1), ("warning", 2), ("info", 3), ("hint", 4)]:
            diag = Diagnostic(severity=sev, message="test")
            assert diag._severity_to_lsp() == expected

    def test_to_ide_message(self):
        diag = Diagnostic(
            severity="error",
            message="Undefined variable",
            file_path="test.py",
            code="E001",
        )
        msg = diag.to_ide_message()
        assert msg["severity"] == 1
        assert msg["filePath"] == "test.py"
        assert msg["code"] == "E001"


class TestInlineChat:
    def test_to_ide_message(self):
        chat = InlineChat(
            message="I found a bug in this function.",
            suggestions=["Fix with SEC001", "Ignore"],
        )
        msg = chat.to_ide_message()
        assert msg["type"] == "inline_chat"
        assert msg["agent"]["name"] == "AI_SUPPORT"
        assert len(msg["suggestions"]) == 2


class TestIDEBridgeMessage:
    def test_to_json(self):
        msg = IDEBridgeMessage(
            type=MessageType.COMPLETION,
            payload={"text": "hello"},
        )
        j = msg.to_json()
        assert j["jsonrpc"] == "2.0"


class TestCodeActionProvider:
    def test_organize_imports_action(self):
        provider = CodeActionProvider()
        context = CodeActionContext(file_path="test.py", cursor_line=1, cursor_col=5)
        actions = provider._get_context_actions(context)
        assert any(a.kind == "source.organizeImports" for a in actions)

    def test_extract_function_action_requires_selection(self):
        provider = CodeActionProvider()
        # Without selection
        context_no_sel = CodeActionContext(file_path="test.py", cursor_line=1, cursor_col=5)
        actions_no_sel = provider._get_context_actions(context_no_sel)
        assert not any(a.kind == "refactor.extract.function" for a in actions_no_sel)

        # With selection
        context_with_sel = CodeActionContext(
            file_path="test.py",
            cursor_line=1,
            cursor_col=5,
            selection=(1, 0, 3, 10),
        )
        actions_with_sel = provider._get_context_actions(context_with_sel)
        assert any(a.kind == "refactor.extract.function" for a in actions_with_sel)

    def test_stats(self):
        provider = CodeActionProvider()
        stats = provider.get_stats()
        assert "offered" in stats
        assert "accepted" in stats
        assert "acceptance_rate" in stats

    def test_on_message_callback(self):
        provider = CodeActionProvider()
        received = []
        provider.on_message(lambda m: received.append(m))
        provider._send_to_ide({"type": "test"})
        assert len(received) == 1

    def test_action_from_rule(self):
        """Test _make_action_from_rule with a mock rule."""
        from src.infrastructure.analysis.rule_engine import Rule, RuleSeverity
        from src.interfaces.ide.bridge.protocol import Range

        rule = Rule(
            id="TEST001",
            name="test-rule",
            description="A test rule",
            severity=RuleSeverity.WARNING,
            languages=["python"],
            fix_template="fixed_text",
        )
        diag = Diagnostic(
            severity="warning",
            message="Test diagnostic",
            range=Range(1, 0, 1, 10),
        )
        action = CodeActionProvider()._make_action_from_rule(rule, diag)
        assert action is not None
        assert action.kind == "quickfix"
        assert action.edits[0].new_text == "fixed_text"

    def test_action_from_rule_no_fix(self):
        """Test _make_action_from_rule returns None when no fix template."""
        from src.infrastructure.analysis.rule_engine import Rule, RuleSeverity

        rule = Rule(
            id="TEST002",
            name="no-fix-rule",
            description="No fix template",
            severity=RuleSeverity.INFO,
            languages=["python"],
            fix_template="",
        )
        diag = Diagnostic(severity="info", message="Test")
        action = CodeActionProvider()._make_action_from_rule(rule, diag)
        assert action is None

    @pytest.mark.asyncio
    async def test_apply_action_not_found(self):
        provider = CodeActionProvider()
        result = await provider.apply_action("non-existent-id", "test.py")
        assert result["success"] is False
        assert "not found" in result["error"]

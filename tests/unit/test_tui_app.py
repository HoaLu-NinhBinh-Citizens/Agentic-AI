"""Unit tests for TUI app components."""
import pytest
from pathlib import Path
import tempfile
from src.interfaces.tui.app import (
    AISupportTUI,
    ChatRenderer,
    EditorRenderer,
    FileNode,
    FileTreeRenderer,
    PanelConfig,
    StatusInfo,
    TUIControls,
    TerminalLine,
    TerminalRenderer,
    Theme,
)


class TestTheme:
    def test_colors_defined(self):
        assert Theme.BG.startswith("#")
        assert Theme.ACCENT.startswith("#")
        assert Theme.ACCENT_GREEN.startswith("#")
        assert Theme.ACCENT_RED.startswith("#")
        assert Theme.ACCENT_YELLOW.startswith("#")
        assert Theme.TEXT.startswith("#")

    def test_rich_styles(self):
        styles = Theme.rich_styles()
        assert isinstance(styles, dict)
        assert "repr.number" in styles


class TestPanelConfig:
    def test_defaults(self):
        assert PanelConfig.FILE_TREE_WIDTH == 28
        assert PanelConfig.CHAT_WIDTH == 40
        assert PanelConfig.TERMINAL_HEIGHT == 15
        assert PanelConfig.STATUS_HEIGHT == 3


class TestFileTreeRenderer:
    def test_file_icon(self):
        renderer = FileTreeRenderer(Path("."))
        assert renderer._file_icon(".py") == "🐍"
        assert renderer._file_icon(".js") == "📜"
        assert renderer._file_icon(".md") == "📝"
        assert renderer._file_icon(".txt") == "📄"
        assert renderer._file_icon(".xyz") == "📄"

    def test_should_ignore_dirs(self):
        renderer = FileTreeRenderer(Path("."))
        assert renderer._should_ignore(Path("__pycache__"))
        assert renderer._should_ignore(Path(".git"))
        assert renderer._should_ignore(Path("node_modules"))
        assert renderer._should_ignore(Path(".venv"))

    def test_should_ignore_extensions(self):
        renderer = FileTreeRenderer(Path("."))
        assert renderer._should_ignore(Path("test.pyc"))
        assert renderer._should_ignore(Path("module.so"))

    def test_should_not_ignore_source_files(self):
        renderer = FileTreeRenderer(Path("."))
        assert not renderer._should_ignore(Path("test.py"))
        assert not renderer._should_ignore(Path("main.rs"))
        assert not renderer._should_ignore(Path("app.js"))

    def test_toggle_expand(self):
        renderer = FileTreeRenderer(Path("."))
        path = Path("test_dir")
        renderer.toggle_expand(path)
        assert path in renderer._expanded
        renderer.toggle_expand(path)
        assert path not in renderer._expanded


class TestTerminalRenderer:
    def test_add_line(self):
        renderer = TerminalRenderer()
        renderer.add_line("Hello")
        assert len(renderer.lines) == 1
        assert renderer.lines[0].text == "Hello"

    def test_add_command(self):
        renderer = TerminalRenderer()
        renderer.add_command("ls -la")
        assert len(renderer.lines) == 1
        assert renderer.lines[0].is_command is True
        assert "❯" in renderer.lines[0].text

    def test_add_error(self):
        renderer = TerminalRenderer()
        renderer.add_error("Something went wrong")
        assert renderer.lines[-1].style == Theme.ACCENT_RED

    def test_add_success(self):
        renderer = TerminalRenderer()
        renderer.add_success("Operation completed")
        assert renderer.lines[-1].style == Theme.ACCENT_GREEN

    def test_max_lines(self):
        renderer = TerminalRenderer(max_lines=5)
        for i in range(10):
            renderer.add_line(f"line {i}")
        assert len(renderer.lines) == 5

    def test_clear(self):
        renderer = TerminalRenderer()
        renderer.add_line("test")
        renderer.clear()
        assert len(renderer.lines) == 0


class TestChatRenderer:
    def test_add_user_message(self):
        chat = ChatRenderer()
        chat.add_user("Hello")
        assert len(chat.messages) == 1
        assert chat.messages[0].role == "user"
        assert chat.messages[0].content == "Hello"

    def test_add_assistant_message(self):
        chat = ChatRenderer()
        chat.add_assistant("Hi there!")
        assert len(chat.messages) == 1
        assert chat.messages[0].role == "assistant"
        assert chat.messages[0].agent_name == "AI_SUPPORT"

    def test_clear(self):
        chat = ChatRenderer()
        chat.add_user("test")
        chat.clear()
        assert len(chat.messages) == 0


class TestEditorRenderer:
    def test_file_lexer_detection(self):
        renderer = EditorRenderer()
        assert renderer._get_lexer(".py") == "python"
        assert renderer._get_lexer(".rs") == "rust"
        assert renderer._get_lexer(".js") == "javascript"
        assert renderer._get_lexer(".go") == "go"
        assert renderer._get_lexer(".yaml") == "yaml"
        assert renderer._get_lexer(".xyz") == "text"


class TestStatusInfo:
    def test_defaults(self):
        status = StatusInfo()
        assert status.file_path == ""
        assert status.line_col == "Ln 1, Col 1"
        assert status.language == "Plain Text"


class TestTUIControls:
    def test_keybindings_exist(self):
        bindings = TUIControls.get_key_bindings()
        assert "ctrl+k" in bindings
        assert "ctrl+p" in bindings
        assert "ctrl+b" in bindings
        assert "ctrl+shift+f" in bindings


class TestAISupportTUI:
    def test_init_defaults(self, tmp_path):
        app = AISupportTUI(workspace_root=str(tmp_path))
        assert app.workspace_root == tmp_path
        assert app.selected_file is None
        assert app.terminal_visible is True
        assert app.chat_visible is False
        assert app.file_tree_visible is True

    def test_init_with_file(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("print('hello')")
        app = AISupportTUI(workspace_root=str(tmp_path), initial_file=str(f))
        assert app.selected_file == f
        assert app.status.language == "Python"

    def test_detect_language(self, tmp_path):
        app = AISupportTUI(workspace_root=str(tmp_path))
        assert app._detect_language(Path("main.py")) == "Python"
        assert app._detect_language(Path("main.rs")) == "Rust"
        assert app._detect_language(Path("main.js")) == "JavaScript"
        assert app._detect_language(Path("main.txt")) == "Plain Text"

    def test_toggle_terminal(self, tmp_path):
        app = AISupportTUI(workspace_root=str(tmp_path))
        assert app.terminal_visible is True
        app.toggle_terminal()
        assert app.terminal_visible is False
        app.toggle_terminal()
        assert app.terminal_visible is True

    def test_toggle_chat(self, tmp_path):
        app = AISupportTUI(workspace_root=str(tmp_path))
        assert app.chat_visible is False
        app.toggle_chat()
        assert app.chat_visible is True
        app.toggle_chat()
        assert app.chat_visible is False

    def test_toggle_file_tree(self, tmp_path):
        app = AISupportTUI(workspace_root=str(tmp_path))
        assert app.file_tree_visible is True
        app.toggle_file_tree()
        assert app.file_tree_visible is False
        app.toggle_file_tree()
        assert app.file_tree_visible is True

    def test_open_file_not_found(self, tmp_path):
        app = AISupportTUI(workspace_root=str(tmp_path))
        app.open_file(tmp_path / "nonexistent.py")
        assert "File not found" in app.terminal.lines[-1].text

    def test_open_file(self, tmp_path):
        f = tmp_path / "main.py"
        f.write_text("def main(): pass")
        app = AISupportTUI(workspace_root=str(tmp_path))
        app.open_file(f)
        assert app.selected_file == f
        assert app.status.file_path == str(f)
        assert app.status.language == "Python"
        assert any("Opened:" in line.text for line in app.terminal.lines)

    def test_add_terminal_output(self, tmp_path):
        app = AISupportTUI(workspace_root=str(tmp_path))
        app.add_terminal_output("Test output")
        assert any(line.text == "Test output" for line in app.terminal.lines)

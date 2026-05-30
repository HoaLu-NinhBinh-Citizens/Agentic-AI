"""Refactoring Panel — Cursor-like code transformation interface.

Provides refactoring operations:
- Rename symbol (all references)
- Extract to function/method
- Inline variable
- Move to new file
- Change signature
- Introduce variable
- Add type annotation
"""

from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional


# ─── Refactor types ──────────────────────────────────────────────────────────

class RefactorKind(Enum):
    RENAME = "rename"
    EXTRACT_FUNCTION = "extract_function"
    EXTRACT_METHOD = "extract_method"
    INLINE_VARIABLE = "inline_variable"
    MOVE_TO_FILE = "move_to_file"
    CHANGE_SIGNATURE = "change_signature"
    INTRODUCE_VARIABLE = "introduce_variable"
    ADD_TYPE_ANNOTATION = "add_type_annotation"
    ENCAPSULATE_FIELD = "encapsulate_field"
    EXTRACT_INTERFACE = "extract_interface"


@dataclass
class RefactorTarget:
    """A symbol being refactored."""
    name: str
    kind: str  # function, class, method, variable, field, parameter
    file_path: str
    line: int
    col: int
    end_line: int
    end_col: int
    symbol_type: str = ""  # e.g., "int", "str", "MyClass"
    references: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "file": self.file_path,
            "line": self.line,
            "column": self.col,
            "endLine": self.end_line,
            "endColumn": self.end_col,
            "symbolType": self.symbol_type,
            "references": self.references,
        }


@dataclass
class RefactorEdit:
    """A single edit in a refactoring operation."""
    file_path: str
    range: tuple[int, int, int, int]  # start_line, start_col, end_line, end_col
    old_text: str
    new_text: str
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file_path,
            "range": self.range,
            "oldText": self.old_text,
            "newText": self.new_text,
            "description": self.description,
        }


@dataclass
class RefactorPreview:
    """A preview of a complete refactoring."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    kind: RefactorKind = RefactorKind.RENAME
    target: Optional[RefactorTarget] = None
    edits: list[RefactorEdit] = field(default_factory=list)
    new_name: str = ""
    description: str = ""
    files_changed: int = 0
    references_changed: int = 0
    confidence: float = 1.0
    applied: bool = False
    rejected: bool = False
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "target": self.target.to_dict() if self.target else None,
            "edits": [e.to_dict() for e in self.edits],
            "newName": self.new_name,
            "description": self.description,
            "filesChanged": self.files_changed,
            "referencesChanged": self.references_changed,
            "confidence": self.confidence,
            "applied": self.applied,
            "rejected": self.rejected,
            "error": self.error,
        }


# ─── Rename Provider ──────────────────────────────────────────────────────────

class RenameProvider:
    """Provides rename refactoring."""

    def __init__(self):
        self._callbacks: list[Callable[[dict], None]] = []

    async def prepare_rename(
        self,
        file_path: str,
        line: int,
        col: int,
    ) -> Optional[dict[str, Any]]:
        """Prepare a rename at the given position."""
        symbol = self._find_symbol(file_path, line, col)
        if not symbol:
            return None

        references = self._find_references(symbol)
        symbol.references = references

        return {
            "canRename": True,
            "name": symbol.name,
            "kind": symbol.kind,
            "references": len(references),
            "files": len({r["file"] for r in references}),
        }

    def _find_symbol(self, file_path: str, line: int, col: int) -> Optional[RefactorTarget]:
        """Find the symbol at a position."""
        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            return None

        if line >= len(lines):
            return None

        line_text = lines[line]

        start = col
        end = col
        while start > 0 and line_text[start - 1].isalnum():
            start -= 1
        while end < len(line_text) and line_text[end].isalnum():
            end += 1

        word = line_text[start:end]
        if not word:
            return None

        for i, content in enumerate(lines):
            for pattern in [
                f"def {word}(", f"async def {word}(",
                f"class {word}(", f"async def {word}",
                f"def {word}:",
            ]:
                if pattern in content:
                    kind = "function" if "def " in content else "class"
                    return RefactorTarget(
                        name=word,
                        kind=kind,
                        file_path=file_path,
                        line=i,
                        col=content.index(word),
                        end_line=i,
                        end_col=content.index(word) + len(word),
                    )

        return RefactorTarget(
            name=word,
            kind="variable",
            file_path=file_path,
            line=line,
            col=start,
            end_line=line,
            end_col=end,
        )

    def _find_references(self, symbol: RefactorTarget) -> list[dict[str, Any]]:
        """Find all references to a symbol."""
        references = []
        name = symbol.name

        try:
            import glob
            pattern = str(Path(symbol.file_path).parent / "*.py")
            files = glob.glob(pattern, recursive=True)
        except Exception:
            files = [symbol.file_path]

        for file_path in files:
            try:
                with open(file_path, encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
            except OSError:
                continue

            for i, content in enumerate(lines):
                if name in content:
                    pattern = rf"\b{re.escape(name)}\b"
                    for m in re.finditer(pattern, content):
                        if not self._is_in_comment_or_string(content, m.start()):
                            references.append({
                                "file": file_path,
                                "line": i,
                                "col": m.start(),
                                "endCol": m.end(),
                                "context": content.strip()[:80],
                            })

        return references

    def _is_in_comment_or_string(self, line: str, pos: int) -> bool:
        """Check if a position is in a comment or string."""
        before = line[:pos]
        if "#" in before:
            return True
        single_quote = before.count("'") - before.count("\\'")
        double_quote = before.count('"') - before.count('\\"')
        if single_quote % 2 == 1 or double_quote % 2 == 1:
            return True
        return False

    async def rename(
        self,
        file_path: str,
        line: int,
        col: int,
        new_name: str,
    ) -> RefactorPreview:
        """Perform a rename refactoring."""
        preview = RefactorPreview(
            kind=RefactorKind.RENAME,
            new_name=new_name,
        )

        symbol = self._find_symbol(file_path, line, col)
        if not symbol:
            preview.error = f"Cannot rename: symbol not found"
            return preview

        preview.target = symbol
        old_name = symbol.name
        preview.description = f"Rename {symbol.kind} '{old_name}' to '{new_name}'"

        references = self._find_references(symbol)

        files_changed = set()
        for ref in references:
            try:
                with open(ref["file"], encoding="utf-8", errors="replace") as f:
                    content = f.read()

                lines = content.split("\n")
                line_text = lines[ref["line"]]
                old_text = line_text

                new_text = line_text[:ref["col"]] + new_name + line_text[ref["endCol"]:]

                if old_text != new_text:
                    edit = RefactorEdit(
                        file_path=ref["file"],
                        range=(ref["line"], ref["col"], ref["line"], ref["endCol"]),
                        old_text=old_text.strip(),
                        new_text=new_text.strip(),
                        description=f"Replace '{old_name}' with '{new_name}'",
                    )
                    preview.edits.append(edit)
                    files_changed.add(ref["file"])

            except OSError:
                continue

        preview.files_changed = len(files_changed)
        preview.references_changed = len(preview.edits)

        return preview


# ─── Extract Provider ─────────────────────────────────────────────────────────

class ExtractProvider:
    """Provides extract refactorings."""

    def __init__(self):
        self._callbacks: list[Callable[[dict], None]] = []

    async def extract_to_function(
        self,
        file_path: str,
        selection: tuple[int, int, int, int],
        new_function_name: str,
    ) -> RefactorPreview:
        """Extract selected code to a new function."""
        preview = RefactorPreview(kind=RefactorKind.EXTRACT_FUNCTION)
        preview.new_name = new_function_name

        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            preview.error = "Cannot read file"
            return preview

        start_line, start_col, end_line, end_col = selection

        if start_line == end_line:
            selected_code = lines[start_line][start_col:end_col]
        else:
            first_line = lines[start_line][start_col:]
            last_line = lines[end_line][:end_col]
            middle_lines = lines[start_line + 1:end_line]
            selected_code = "\n".join([first_line] + middle_lines + [last_line])

        first_line_indent = len(lines[start_line]) - len(lines[start_line].lstrip())

        function_code = f"def {new_function_name}():\n"
        for line in selected_code.split("\n"):
            if line.strip():
                function_code += " " * (first_line_indent + 4) + line + "\n"

        old_text = selected_code
        new_text = f"{new_function_name}()"

        edit = RefactorEdit(
            file_path=file_path,
            range=selection,
            old_text=old_text,
            new_text=new_text,
            description=f"Extract to function '{new_function_name}()'",
        )
        preview.edits.append(edit)

        func_edit = RefactorEdit(
            file_path=file_path,
            range=(start_line, 0, start_line, 0),
            old_text="",
            new_text=function_code + "\n",
            description=f"Add function definition",
        )
        preview.edits.insert(0, func_edit)

        preview.files_changed = 1
        preview.references_changed = 1
        preview.description = f"Extract {len(selected_code.split(chr(10)))} lines to function '{new_function_name}'"

        return preview


# ─── Inline Variable Provider ────────────────────────────────────────────────

class InlineProvider:
    """Provides inline refactorings."""

    async def inline_variable(
        self,
        file_path: str,
        line: int,
        col: int,
    ) -> RefactorPreview:
        """Inline a variable at its usage sites."""
        preview = RefactorPreview(kind=RefactorKind.INLINE_VARIABLE)

        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            preview.error = "Cannot read file"
            return preview

        if line >= len(lines):
            preview.error = "Invalid line number"
            return preview

        line_text = lines[line]
        pattern = r"(\w+)\s*=\s*(.+)"

        for m in re.finditer(pattern, line_text):
            var_name = m.group(1)
            expression = m.group(2).rstrip()

            if m.start(1) <= col <= m.start(2):
                uses = self._find_uses(file_path, var_name, line)

                if uses:
                    for use_line, use_col, use_end_col in uses:
                        use_text = lines[use_line]
                        old_text = use_text[use_col:use_end_col]

                        edit = RefactorEdit(
                            file_path=file_path,
                            range=(use_line, use_col, use_line, use_end_col),
                            old_text=old_text.strip(),
                            new_text=expression.strip(),
                            description=f"Inline '{var_name}' with '{expression.strip()}'",
                        )
                        preview.edits.append(edit)

                    assignment_edit = RefactorEdit(
                        file_path=file_path,
                        range=(line, 0, line, len(line_text)),
                        old_text=line_text.strip(),
                        new_text="",
                        description=f"Remove variable assignment",
                    )
                    preview.edits.append(assignment_edit)

                    preview.files_changed = 1
                    preview.references_changed = len(uses) + 1
                    preview.description = f"Inline variable '{var_name}' at {len(uses)} usage(s)"
                break

        return preview

    def _find_uses(self, file_path: str, var_name: str, exclude_line: int) -> list:
        """Find all uses of a variable."""
        uses = []
        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            return uses

        for i, content in enumerate(lines):
            if i == exclude_line:
                continue

            pattern = rf"\b{re.escape(var_name)}\b"
            for m in re.finditer(pattern, content):
                uses.append((i, m.start(), m.end()))

        return uses


# ─── Refactoring Panel ────────────────────────────────────────────────────────

class RefactorPanel:
    """Main refactoring panel coordinating all refactoring operations."""

    def __init__(self):
        self._rename = RenameProvider()
        self._extract = ExtractProvider()
        self._inline = InlineProvider()
        self._callbacks: list[Callable[[dict], None]] = []
        self._preview_history: list[RefactorPreview] = []
        self._stats = {
            "renames": 0,
            "extracts": 0,
            "inlines": 0,
            "previews_generated": 0,
            "previews_applied": 0,
        }

    async def prepare_refactor(
        self,
        kind: RefactorKind,
        file_path: str,
        line: int,
        col: int,
        selection: Optional[tuple[int, int, int, int]] = None,
    ) -> Optional[dict[str, Any]]:
        """Prepare a refactoring of the given kind."""
        if kind == RefactorKind.RENAME:
            return await self._rename.prepare_rename(file_path, line, col)
        elif kind in (RefactorKind.EXTRACT_FUNCTION, RefactorKind.EXTRACT_METHOD):
            return {"canExtract": True, "selection": selection}
        return None

    async def execute_refactor(
        self,
        kind: RefactorKind,
        file_path: str,
        line: int,
        col: int,
        selection: Optional[tuple[int, int, int, int]] = None,
        new_name: str = "",
        new_function_name: str = "",
    ) -> RefactorPreview:
        """Execute a refactoring and return a preview."""
        preview: Optional[RefactorPreview] = None

        if kind == RefactorKind.RENAME:
            preview = await self._rename.rename(file_path, line, col, new_name)
            self._stats["renames"] += 1
        elif kind == RefactorKind.EXTRACT_FUNCTION:
            preview = await self._extract.extract_to_function(
                file_path, selection, new_function_name
            )
            self._stats["extracts"] += 1
        elif kind == RefactorKind.INLINE_VARIABLE:
            preview = await self._inline.inline_variable(file_path, line, col)
            self._stats["inlines"] += 1

        if preview:
            self._preview_history.append(preview)
            self._stats["previews_generated"] += 1

        return preview or RefactorPreview(error="Unknown refactor kind")

    def apply_preview(self, preview: RefactorPreview) -> bool:
        """Apply a refactoring preview."""
        try:
            for edit in preview.edits:
                self._apply_edit(edit)
            preview.applied = True
            self._stats["previews_applied"] += 1
            return True
        except Exception as exc:
            preview.error = str(exc)
            return False

    def _apply_edit(self, edit: RefactorEdit) -> None:
        """Apply a single refactor edit."""
        with open(edit.file_path, encoding="utf-8", errors="replace") as f:
            content = f.read()

        lines = content.split("\n")
        start_line, start_col, end_line, end_col = edit.range

        if start_line == end_line:
            lines[start_line] = lines[start_line][:start_col] + edit.new_text + lines[start_line][end_col:]
        else:
            first = lines[start_line][:start_col]
            last = lines[end_line][end_col:]
            lines[start_line] = first + edit.new_text + last
            del lines[start_line + 1:end_line + 1]

        with open(edit.file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def on_message(self, callback: Callable[[dict], None]) -> None:
        self._callbacks.append(callback)

    def _send_to_ide(self, message: dict) -> None:
        for cb in self._callbacks:
            try:
                cb(message)
            except Exception:
                pass

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "preview_history": len(self._preview_history),
        }
